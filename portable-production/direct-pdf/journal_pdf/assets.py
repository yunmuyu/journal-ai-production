"""Lossless raster placement and conservative SVG/PDF viewports.
This module never guesses data points or paints missing curves.
"""
from __future__ import annotations
from pathlib import Path
import copy, hashlib, io, re
from dataclasses import dataclass, field
from PIL import Image, ImageDraw, ImageChops
from lxml import etree as ET
import pymupdf as fitz
from .common import FigureError, digest_file, digest_json, contains

SVGNS='http://www.w3.org/2000/svg'; NS={'s':SVGNS}
XLINK='{http://www.w3.org/1999/xlink}href'

@dataclass
class Asset:
    key: str
    kind: str
    source_path: str
    source_hash: str
    rect: list[float]
    data: bytes
    audit: dict=field(default_factory=dict)
    doc: object=None
    svg_bytes: bytes|None=None


def svg_root(path: Path):
    parser=ET.XMLParser(resolve_entities=False,no_network=True,load_dtd=False,huge_tree=False,remove_comments=False)
    root=ET.parse(str(path),parser).getroot()
    if root.tag!='{'+SVGNS+'}svg': raise FigureError('svg_root','不是SVG文件')
    for e in root.iter():
        if not isinstance(e.tag,str):continue
        local=ET.QName(e).localname
        if local=='style' and e.text and ('@import' in e.text or re.search(r'url\(\s*[\'\"]?(?!#)',e.text)):
            raise FigureError('svg_external_style','拒绝样式块中的外部资源')
        if local in ('script','foreignObject','filter','animate','set'):
            raise FigureError('unsupported_svg_feature','SVG包含尚未支持的动态或滤镜内容',tag=local)
        for k,v in e.attrib.items():
            if k.startswith('on'): raise FigureError('svg_script','拒绝SVG事件处理器')
            if k in ('href',XLINK) and not v.startswith('#'):
                raise FigureError('svg_external_resource','拒绝SVG外部资源和数据资源',href=v[:120])
            if 'url(' in v and re.search(r'url\(\s*[\'"]?(?!#)',v):
                raise FigureError('svg_external_style','拒绝SVG外部样式资源')
    return root


def svg_pdf_bytes(root):
    # Lazy dependency: missing Windows Cairo DLL blocks SVG only, not diagrams.
    # Do not silently substitute a converter that drops dashed strokes.
    try:
        import cairosvg
    except (ImportError, OSError) as e:
        raise FigureError('svg_backend_unavailable',
            'SVG矢量转换需要CairoSVG及Cairo运行库；请运行doctor检查。本次不自动栅格化或改线型。', detail=str(e)) from e
    return cairosvg.svg2pdf(bytestring=ET.tostring(root), unsafe=False)


def element(root,id):
    rows=root.xpath('//*[@id=$id]',id=id)
    if len(rows)!=1:raise FigureError('svg_object_identity','SVG对象ID缺失或不唯一',id=id,count=len(rows))
    return rows[0]


def geometry_signature(root,ids):
    rows=[]; seen=set()
    fields={'d','points','x','y','x1','x2','y1','y2','cx','cy','r','rx','ry','width','height','transform','clip-path',XLINK,'href'}
    def record(ident):
        if ident in seen:return
        seen.add(ident); e=element(root,ident)
        for p in e.iter():
            if not isinstance(p.tag,str):continue
            attrs={k:v for k,v in p.attrib.items() if k in fields}
            # Stroke style is protected too; grayscale conversion is audited separately.
            style=p.get('style','')
            protected={k.strip():v.strip() for term in style.split(';') if ':' in term for k,v in [term.split(':',1)]
                       if k.strip() in ('stroke-width','stroke-dasharray','stroke-dashoffset','stroke-linecap','stroke-linejoin')}
            if attrs or protected:rows.append([ident,ET.QName(p).localname,attrs,protected])
            for value in attrs.values():
                for ref in re.findall(r'url\(#([^)]*)\)',value):record(ref)
                if value.startswith('#'):record(value[1:])
    for ident in ids:record(ident)
    return digest_json(rows)


def grayscale_svg(root):
    count=0
    def replace(m):
        nonlocal count
        hx=m.group(0)[1:]; hx=''.join(c*2 for c in hx) if len(hx)==3 else hx
        vals=[int(hx[i:i+2],16) for i in (0,2,4)]
        gray=round(.2126*vals[0]+.7152*vals[1]+.0722*vals[2])
        if len(set(vals))>1:count+=1
        return '#'+f'{gray:02x}'*3
    for e in root.iter():
        if not isinstance(e.tag,str):continue
        if ET.QName(e).localname=='style' and e.text:
            e.text=re.sub(r'((?:fill|stroke|stop-color|color)\s*:\s*)(#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b)',
                          lambda m:m.group(1)+re.sub(r'#[0-9a-fA-F]+',replace,m.group(2)),e.text)
        for attr in ('style','fill','stroke','stop-color'):
            if attr in e.attrib:e.set(attr,re.sub(r'#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b',replace,e.get(attr)))
    return count


def all_defs(root):
    """Hoist definitions before removing text groups; Matplotlib may define reused
    line-marker paths inside earlier groups. Duplicate IDs are not introduced."""
    defs=ET.Element('{'+SVGNS+'}defs'); seen=set()
    for d in root.findall('.//s:defs',NS):
        for child in d:
            ident=child.get('id')
            if ident and ident in seen: continue
            if ident:seen.add(ident)
            defs.append(copy.deepcopy(child))
    for d in list(root.findall('.//s:defs',NS)):
        p=d.getparent()
        if p is not None:p.remove(d)
    root.insert(0,defs)


class Assets:
    def __init__(self):
        self._cache={};self.stats={'preparations':0,'cache_hits':0}

    def close(self):
        for a in self._cache.values():
            if a.doc is not None:a.doc.close()

    def source_icon(self,path:Path,page_no:int,clip,*,text_replacements=None):
        """Explicit font-free source vector icon; ordinary PDF defaults stay unchanged."""
        from .source_icons import prepare_icon
        sha=digest_file(path);key=digest_json(['source-icon-v1',sha,page_no,clip,text_replacements])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        prepared=prepare_icon(path,page_no,clip,text_replacements=text_replacements)
        import json
        audit=json.loads(prepared.receipt_json)
        doc=fitz.open(stream=prepared.data,filetype='pdf')
        a=Asset(key,'pdf',str(path),sha,list(doc[0].rect),prepared.data,audit)
        a.doc=doc;self._cache[key]=a;self.stats['preparations']+=1
        return a

    def registered_pdf_text(self,path:Path,page_no:int,clip,svg_path:Path,registration,*,text_replacements=None,grayscale=False):
        from .source_pdf_text import prepare_registered_text
        sha=digest_file(path);key=digest_json(['registered-native-pdf-text-v1',sha,digest_file(svg_path),page_no,clip,registration,text_replacements,grayscale])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        prepared=prepare_registered_text(path,page_no,clip,svg_path,registration,text_replacements=text_replacements,grayscale=grayscale)
        import json
        audit=json.loads(prepared.receipt_json);doc=fitz.open(stream=prepared.data,filetype='pdf')
        a=Asset(key,'pdf',str(path),sha,list(doc[0].rect),prepared.data,audit)
        a.doc=doc;self._cache[key]=a;self.stats['preparations']+=1
        return a

    def source_vector_body(self,path:Path,page_no:int,clip,*,text_replacements=None):
        """Explicit original nontext vector body with source-bound glyph replacements."""
        from .source_icons import prepare_icon
        sha=digest_file(path);key=digest_json(['source-vector-body-v1',sha,page_no,clip,text_replacements])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        prepared=prepare_icon(path,page_no,clip,text_replacements=text_replacements,source_vector_body=True)
        import json
        audit=json.loads(prepared.receipt_json)
        doc=fitz.open(stream=prepared.data,filetype='pdf')
        a=Asset(key,'pdf',str(path),sha,list(doc[0].rect),prepared.data,audit)
        a.doc=doc;self._cache[key]=a;self.stats['preparations']+=1
        return a

    def source_mixed_body(self,path:Path,page_no:int,clip,*,text_replacements=None,outline_text_replacements=None,source_shape_replacements=None):
        from .source_mixed_body import prepare_mixed_body
        sha=digest_file(path);key=digest_json(['source-mixed-body-v1',sha,page_no,clip,text_replacements,outline_text_replacements,source_shape_replacements])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        prepared=prepare_mixed_body(path,page_no,clip,text_replacements=text_replacements,outline_text_replacements=outline_text_replacements,source_shape_replacements=source_shape_replacements)
        import json
        audit=json.loads(prepared.receipt_json);doc=fitz.open(stream=prepared.data,filetype='pdf')
        a=Asset(key,'pdf',str(path),sha,list(doc[0].rect),prepared.data,audit)
        a.doc=doc;self._cache[key]=a;self.stats['preparations']+=1
        return a

    def source_vector_glyph(self,path:Path,page_no:int,clip,source_path_indices,*,gray=True,text_replacements=None):
        """Explicit original nontext vector body with source-bound glyph replacements."""
        from .source_native_paths import prepare_native_glyph
        sha=digest_file(path);key=digest_json(['source-vector-glyph-v1',sha,page_no,clip,source_path_indices,gray,text_replacements])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        prepared=prepare_native_glyph(path,page_no,clip,source_path_indices,gray=gray,text_replacements=text_replacements)
        import json
        audit=json.loads(prepared.receipt_json)
        doc=fitz.open(stream=prepared.data,filetype='pdf')
        a=Asset(key,'pdf',str(path),sha,list(doc[0].rect),prepared.data,audit)
        a.doc=doc;self._cache[key]=a;self.stats['preparations']+=1
        return a

    def source_svg_group(self,path:Path,group_id:str,clip,*,text_replacements=None,clipped_viewport=False):
        """Explicit original nontext vector body with source-bound glyph replacements."""
        from .source_svg_groups import prepare_svg_group
        sha=digest_file(path);key=digest_json(['source-svg-group-v1',sha,group_id,clip,text_replacements,clipped_viewport])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        prepared=prepare_svg_group(path,group_id,clip,text_replacements=text_replacements,clipped_viewport=clipped_viewport)
        import json
        audit=json.loads(prepared.receipt_json)
        doc=fitz.open(stream=prepared.data,filetype='pdf')
        a=Asset(key,'pdf',str(path),sha,list(doc[0].rect),prepared.data,audit)
        a.doc=doc;self._cache[key]=a;self.stats['preparations']+=1
        return a

    def registered_outline_chart(self,path:Path,registration,*,swatch_id=None):
        from .source_outline_chart import prepare_registered_svg
        from .source_native_gray import native_gray
        sha=digest_file(path);key=digest_json(['registered-outline-chart',sha,registration,swatch_id])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        root,bound,audit=prepare_registered_svg(path,registration,swatch_id=swatch_id)
        raw=svg_pdf_bytes(root);data,gray_audit=native_gray(raw)
        audit['grayscale']=gray_audit
        with fitz.open(stream=data,filetype='pdf') as stable:
            stable.set_metadata({})
            data=stable.tobytes(garbage=4,deflate=True,no_new_id=True)
        clip=bound['plot_clip'] if swatch_id is None else next(s['swatch_clip'] for s in bound['series'] if s['id']==swatch_id)
        audit.update(source_page=0,source_clip=list(clip),prepared_sha256=hashlib.sha256(data).hexdigest(),
                     outline_chart_registration=registration,swatch_id=swatch_id)
        a=Asset(key,'pdf',str(path),sha,list(clip),data,audit)
        a.doc=fitz.open(stream=data,filetype='pdf');self._cache[key]=a;self.stats['preparations']+=1
        return a

    def svg_chart(self,path: Path,axes_id: str,plot_rect,series_ids,legend_id,gray=True):
        sha=digest_file(path); key=digest_json(['svg-chart',sha,axes_id,plot_rect,series_ids,legend_id,gray])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        root=svg_root(path)
        # Preserve all definitions; remove only identified text/legend/other axes.
        all_defs(root)
        before=geometry_signature(root,series_ids)
        for e in list(root.findall('.//s:g',NS)):
            ident=e.get('id','')
            if ident.startswith('axes_') and ident!=axes_id:
                par=e.getparent()
                if par is not None:par.remove(e)
        # Only axes labels and the identified legend have replacement text in
        # this route. Other Matplotlib text includes data/annotation content;
        # deleting it while auditing only curve paths produces false success.
        unhandled=[]
        for e in root.findall('.//s:g',NS):
            if not e.get('id','').startswith('text_'):continue
            ancestors=[a.get('id','') for a in e.iterancestors()]
            if legend_id not in ancestors and not any(a.startswith('matplotlib.axis_') for a in ancestors):
                unhandled.append(e.get('id'))
        if unhandled:
            raise FigureError('svg_unhandled_source_text',
                '图内数据标注或说明尚无文字保留方案；拒绝删除后生成候选',object_ids=unhandled)
        removed=[]
        for e in list(root.findall('.//s:g',NS)):
            ident=e.get('id','')
            if ident.startswith('text_') or ident==legend_id:
                par=e.getparent()
                if par is not None:par.remove(e);removed.append(ident)
        after=geometry_signature(root,series_ids)
        if before!=after:raise FigureError('svg_data_changed','SVG数据路径在处理时发生改变')
        n=grayscale_svg(root) if gray else 0
        # Render vector SVG to vector PDF, retaining original viewBox coordinates.
        data=svg_pdf_bytes(root)
        a=Asset(key,'pdf',str(path),sha,list(plot_rect),data,
                {'mode':'svg-vector-preserve','series_ids':series_ids,'geometry_before':before,'geometry_after':after,
                 'geometry_unchanged':True,'removed_groups':removed,'grayscale_operations':n,
                 'curve_values_reconstructed':False})
        a.svg_bytes=ET.tostring(root)
        a.doc=fitz.open(stream=data,filetype='pdf');self._cache[key]=a;self.stats['preparations']+=1;return a

    def svg_swatch(self,path:Path,group_id:str,clip,gray=True):
        sha=digest_file(path);key=digest_json(['svg-swatch',sha,group_id,clip,gray])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        root=svg_root(path);saved=copy.deepcopy(element(root,group_id));all_defs(root)
        defs=copy.deepcopy(root.find('s:defs',NS));new=ET.Element(root.tag,nsmap=root.nsmap,attrib=dict(root.attrib))
        if defs is not None:new.append(defs)
        new.append(saved)
        n=grayscale_svg(new) if gray else 0
        data=svg_pdf_bytes(new)
        a=Asset(key,'pdf',str(path),sha,list(clip),data,{'mode':'original-svg-legend-swatch','group_id':group_id,'grayscale_operations':n})
        a.svg_bytes=ET.tostring(new)
        a.doc=fitz.open(stream=data,filetype='pdf');self._cache[key]=a;self.stats['preparations']+=1;return a

    def raster(self,path:Path,clip,*,masks=None,approved_empty_regions=None,gray=True,swatch=False):
        masks=masks or [];approved_empty_regions=approved_empty_regions or []
        sha=digest_file(path);key=digest_json(['raster',sha,clip,masks,approved_empty_regions,gray,swatch])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        opened=Image.open(path);source_alpha_present='A' in opened.getbands()
        if source_alpha_present:
            rgba=opened.convert('RGBA');background=Image.new('RGBA',rgba.size,(255,255,255,255))
            background.alpha_composite(rgba);img=background.convert('RGB')
        else:img=opened.convert('RGB')
        full=[0,0,*img.size]
        if not contains(full,clip):raise FigureError('raster_clip','裁取范围越过原图片')
        if any(int(v)!=v for v in clip):raise FigureError('raster_subpixel_clip','位图裁取只接受整数像素，避免隐式插值')
        for mask in masks:
            if not contains(clip,mask) or not any(contains(region,mask) for region in approved_empty_regions):
                raise FigureError('unapproved_raster_mask','清字区域未落入显式审核的非数据区域',mask=mask)
        original=img.crop(tuple(clip))
        if swatch and original.convert('L').point(lambda v: 255 if v<180 else 0).getbbox() is None:
            raise FigureError('empty_legend_swatch','图例样符裁取区没有可辨认墨迹，拒绝以空样符代替')
        work=original.copy();draw=ImageDraw.Draw(work)
        mask_bitmap=Image.new('L',work.size,0);md=ImageDraw.Draw(mask_bitmap)
        for b in masks:
            box=(b[0]-clip[0],b[1]-clip[1],b[2]-clip[0]-1,b[3]-clip[1]-1)
            draw.rectangle(box,fill=(255,255,255));md.rectangle(box,fill=255)
        diff=ImageChops.difference(original,work);diff.paste((0,0,0),mask=mask_bitmap)
        preserved=diff.getbbox() is None
        if not preserved:raise FigureError('protected_pixels_changed','受保护像素在遮字区域外变化')
        source_icc_present=bool(work.info.get('icc_profile'))
        if gray:
            work=work.convert('L')
            # Pillow carries source RGB metadata through convert('L'). An RGB
            # ICC profile on a one-channel PNG is invalid. Remove that profile;
            # this does not alter the already computed gray pixel values.
            work.info.pop('icc_profile',None)
        dataio=io.BytesIO();work.save(dataio,format='PNG',optimize=False)
        a=Asset(key,'raster',str(path),sha,[0,0,*work.size],dataio.getvalue(),
                {'mode':'original-raster-swatch' if swatch else 'raster-protected-viewport',
                 'source_clip_pixels':list(clip),'approved_empty_regions':approved_empty_regions,'masks':masks,
                 'protected_pixels_unchanged_before_color_conversion':preserved,'grayscale':gray,
                 'source_alpha_present':source_alpha_present,
                 'transparent_pixels_composited_to_white':source_alpha_present,
                 'source_icc_present':source_icc_present,'rgb_icc_removed_for_gray':bool(gray and source_icc_present),
                 'native_pixels':list(work.size),'resampled_before_embedding':False,'curve_values_reconstructed':False})
        self._cache[key]=a;self.stats['preparations']+=1;return a

    def pdf(self,path:Path,page_no:int,clip):
        sha=digest_file(path);key=digest_json(['pdf',sha,page_no,clip])
        if key in self._cache:self.stats['cache_hits']+=1;return self._cache[key]
        doc=fitz.open(path)
        if page_no<0 or page_no>=len(doc):raise FigureError('pdf_page','源PDF页号超出范围')
        if not contains(list(doc[page_no].rect),clip):raise FigureError('pdf_clip','PDF裁切越界')
        source_text=doc[page_no].get_text('text',clip=fitz.Rect(clip))
        # Isolate the requested page without modifying source.
        single=fitz.open();single.insert_pdf(doc,from_page=page_no,to_page=page_no);doc.close()
        data=single.tobytes(garbage=4,deflate=True)
        a=Asset(key,'pdf',str(path),sha,list(clip),data,{'mode':'pdf-preserved-viewport','source_page':page_no,
            'font_policy':'source_fonts_preserved','source_text':source_text,'source_text_character_count':len(source_text)})
        a.doc=single;self._cache[key]=a;self.stats['preparations']+=1;return a

    def normalized_svg_pdf(self,asset,scale):
        key=digest_json(['r21-final-svg-strokes',asset.key,scale])
        if key in self._cache:return self._cache[key]
        root=ET.fromstring(asset.svg_bytes)
        vb=[float(v) for v in root.get('viewBox','').split()]
        if len(vb)!=4 or abs(asset.doc[0].rect.width/vb[2]-1)>1e-5:
            raise FigureError('svg_stroke_transform_unsupported','SVG坐标到PDF不是已验证的1:1单位；不猜测最终描边')
        for e in root.iter():
            if not isinstance(e.tag,str):continue
            if any(ET.QName(a).localname=='defs' for a in e.iterancestors()):continue
            transform=e.get('transform','')
            # The supported Matplotlib viewport contains no visible scale/shear.
            # Unused font definitions are exempt; their outlines are never painted.
            if transform and re.sub(r'translate\([^)]*\)\s*','',transform).strip():
                raise FigureError('svg_stroke_transform_unsupported','可见SVG对象存在未适配变换',transform=transform)
        changed=0;geometry_before=[];geometry_after=[]
        for e in root.iter():
            if not isinstance(e.tag,str):continue
            geometry_before.append((e.tag,dict(e.attrib)))
            if ET.QName(e).localname in ('path','line','polyline','polygon','rect','ellipse','circle','use'):
                st={k.strip():v.strip() for t in e.get('style','').split(';') if ':' in t for k,v in [t.split(':',1)]}
                st['stroke-width']=format(.5/scale,'.12g')
                e.set('style',';'.join(k+':'+v for k,v in st.items()))
                if 'stroke-width' in e.attrib:e.set('stroke-width',st['stroke-width'])
                changed+=1
            geometry_after.append((e.tag,dict(e.attrib)))
        # Prove the only XML changes are stroke widths. No point/path/clip/dash edits.
        def without_width(rows):
            out=[]
            for tag,attrs in rows:
                attrs=dict(attrs);attrs.pop('stroke-width',None)
                st={k.strip():v.strip() for t in attrs.pop('style','').split(';') if ':' in t for k,v in [t.split(':',1)]}
                st.pop('stroke-width',None);out.append((tag,attrs,st))
            return out
        if without_width(geometry_before)!=without_width(geometry_after):
            raise FigureError('stroke_normalization_changed_geometry','线宽标准化改变了非线宽信息')
        data=svg_pdf_bytes(root)
        a=Asset(key,'pdf',asset.source_path,asset.source_hash,list(asset.rect),data,
                dict(asset.audit,final_stroke_normalization={'target_pt':.5,'placement_scale':scale,
                    'changed_svg_elements':changed,'geometry_and_dash_attributes_unchanged':True}))
        a.doc=fitz.open(stream=data,filetype='pdf');self._cache[key]=a
        return a

    def place(self,page,asset:Asset,target):
        r=fitz.Rect(target);sr=fitz.Rect(asset.rect)
        if asset.svg_bytes is not None:asset=self.normalized_svg_pdf(asset,r.width/sr.width)
        if abs(r.width/r.height-sr.width/sr.height)>1e-4:
            raise FigureError('asset_aspect_ratio','禁止隐式拉伸素材',source=asset.rect,target=target)
        if asset.kind=='raster':page.insert_image(r,stream=asset.data,keep_proportion=True,overlay=True)
        else:page.show_pdf_page(r,asset.doc,0,clip=sr,keep_proportion=True,overlay=True)
        info={**asset.audit,'source_hash':asset.source_hash,'target_pt':list(target),'asset_key':asset.key}
        if asset.kind=='raster':info['effective_ppi']=sr.width/(r.width/72)
        return info
