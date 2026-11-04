from __future__ import annotations
import base64, hashlib, html, io, json, posixpath, re, time, urllib.parse, zlib
from collections import Counter
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
from lxml import etree as E
from PIL import Image, ImageChops, ImageStat
import pymupdf as fitz

LIMIT = 64 * 1024 * 1024
XML_LIMIT = 8 * 1024 * 1024
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'v':'urn:schemas-microsoft-com:vml',
    'o':'urn:schemas-microsoft-com:office:office'}

class ProbeError(ValueError): pass

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def read_bytes(p: Path) -> bytes:
    if not p.is_file(): raise ProbeError(f'Not a readable file: {p.name}')
    if p.stat().st_size > LIMIT: raise ProbeError('File exceeds configured size limit')
    return p.read_bytes()
def xml(data: bytes):
    if len(data) > XML_LIMIT: raise ProbeError('XML exceeds limit')
    if b'<!ENTITY' in data.upper(): raise ProbeError('XML entity declaration rejected')
    return E.fromstring(data, E.XMLParser(resolve_entities=False,no_network=True,huge_tree=False))
def flatten_markup(markup: str) -> str:
    # Text evidence only: retain original HTML separately; do not execute HTML.
    markup = re.sub(r'<(?:br\s*/?|/(?:div|p|h[1-6]))\s*>','\n',markup,flags=re.I)
    markup = re.sub(r'<[^>]*>', '', markup)
    return '\n'.join(' '.join(html.unescape(line).split()) for line in markup.splitlines()).strip()
def bounded_inflate(text: str) -> bytes:
    compressed=base64.b64decode(''.join(text.split()),validate=True)
    obj=zlib.decompressobj(-15);data=obj.decompress(compressed,XML_LIMIT+1)
    if len(data)>XML_LIMIT or obj.unconsumed_tail or not obj.eof: raise ProbeError('Invalid/oversized draw.io payload')
    return urllib.parse.unquote(data.decode('utf-8')).encode('utf-8')
def graph_model(model):
    cells=model.findall('.//mxCell'); ids={c.get('id') for c in cells}
    vertices=[];edges=[]
    for c in cells:
        if c.get('vertex')!='1' and c.get('edge')!='1': continue
        geo=c.find('mxGeometry')
        row={'id':c.get('id'),'parent':c.get('parent'),'style_raw':c.get('style',''),
             'label_html':c.get('value',''),'label_text':flatten_markup(c.get('value','')),
             'geometry_xml':E.tostring(geo,encoding='unicode') if geo is not None else None}
        if c.get('vertex')=='1':
            vertices.append(row)
        else:
            s,t=c.get('source'),c.get('target')
            bad=[v for v in (s,t) if v and v not in ids]
            row.update(source=s,target=t,endpoint_status='dangling_reference' if bad else 'bound' if s and t else 'free_geometry',dangling_ids=bad)
            edges.append(row)
    return {'cell_count':len(cells),'vertex_count':len(vertices),'edge_object_count':len(edges),
            'bound_edge_count':sum(e['endpoint_status']=='bound' for e in edges),
            'free_geometry_edge_count':sum(e['endpoint_status']=='free_geometry' for e in edges),
            'dangling_edges':[e['id'] for e in edges if e['endpoint_status']=='dangling_reference'],
            'vertices':vertices,'edges':edges,'semantic_topology_verified':False,
            'note':'Counts include labels, group containers and legend samples; they are not semantic node/relationship counts.'}
def probe_svg(p: Path, out: Path):
    root=xml(read_bytes(p))
    if E.QName(root).localname!='svg': raise ProbeError('Not SVG')
    tags=Counter(E.QName(e).localname for e in root.iter() if isinstance(e.tag,str))
    external=[];active=bool(tags.get('script',0))
    fallback=0;images=0
    for e in root.iter():
        if not isinstance(e.tag,str): continue
        if any(k.lower().startswith('on') for k in e.attrib): active=True
        for k,v in e.attrib.items():
            if E.QName(k).localname in ['href','src'] and v and not v.startswith(('data:','#')):external.append(v[:300])
        if E.QName(e).localname=='image':
            images+=1
            if any(E.QName(a).localname=='switch' and a.xpath('./*[local-name()="foreignObject"]') for a in e.iterancestors()):fallback+=1
    native=[''.join(e.itertext()) for e in root.xpath('//*[local-name()="text" or local-name()="foreignObject"]')]
    pages=[];content=root.get('content')
    if content:
        mx=xml(content.encode('utf-8'))
        for idx,d in enumerate(mx.iter('diagram')):
            model=d.find('mxGraphModel')
            if model is None: model=xml(bounded_inflate(d.text or ''))
            model_file=out/f'graph-{idx+1}.xml';model_file.write_bytes(E.tostring(model,pretty_print=True,encoding='utf-8'))
            pages.append({'name':d.get('name'),'id':d.get('id'),'model_file':model_file.name,**graph_model(model)})
    textfile=out/'native-text.txt';textfile.write_text('\n'.join(native),encoding='utf-8')
    return {'kind':'svg_drawio' if pages else 'svg','size_hint':[root.get('width'),root.get('height')],
            'viewBox':root.get('viewBox'),'native_text_count':len(native),'native_text_file':textfile.name,
            'tags':dict(tags),'image_count':images,'text_fallback_image_count':fallback,
            'scientific_raster_images_not_in_text_fallback':images-fallback,
            'drawio_pages':pages,'active_content_present':active,'external_reference_count':len(external),
            'requires_sandbox_render':active or bool(external),
            'native_semantics_available':bool(pages),'content_classification_verified':False}
def probe_pdf(p: Path,out: Path):
    result={'kind':'pdf','pages':[]}
    with fitz.open(p) as doc:
        if doc.needs_pass: raise ProbeError('Encrypted PDF; password needed')
        if len(doc)>250: raise ProbeError('PDF page limit exceeded')
        for i,page in enumerate(doc):
            imgs=[]
            for j,info in enumerate(page.get_image_info(xrefs=True,hashes=True)):
                xref=info['xref'];row={k:info[k] for k in ('bbox','width','height','colorspace','cs-name','has-mask','xref') if k in info}
                row['pixel_digest_md5']=info['digest'].hex()
                if xref:
                    obj=doc.extract_image(xref);file=out/f'p{i+1}-image{j+1}.{obj["ext"]}';file.write_bytes(obj['image'])
                    row.update(asset=file.name,asset_sha256=sha(obj['image']),smask_xref=obj.get('smask',0),render_requires_mask=bool(obj.get('smask')))
                imgs.append(row)
            text=page.get_text();paths=page.get_drawings()
            result['pages'].append({'number':i+1,'width_pt':page.rect.width,'height_pt':page.rect.height,
                    'text':text,'images':imgs,'vector_path_count':len(paths),
                    'content_kind':'mixed_text_raster' if text.strip() and imgs and not paths else 'raster_only' if imgs and not text.strip() and not paths else 'native_or_mixed'})
    return result

def safe_zip_member(z,name):
    if name not in z.namelist(): raise ProbeError('Missing package member')
    if name.startswith('/') or '..' in PurePosixPath(name).parts: raise ProbeError('Unsafe package path')
    item=z.getinfo(name)
    if item.file_size>LIMIT: raise ProbeError('Zip entry exceeds limit')
    return z.read(name)
def document_legacy_evidence(root,paragraphs,relationships):
    # Inventory caches without decoding them or claiming they identify a figure.
    # OLE program IDs are evidence, not permission to execute embedded objects.
    indexes={para:index for index,para in enumerate(paragraphs)}
    evidence=[]
    def relationship(rid):
        rel=relationships.get(rid)
        return {'relationship_id':rid,
                'relationship_status':'missing' if rel is None else 'external' if rel.get('TargetMode')=='External' else 'internal',
                'target':rel.get('Target') if rel is not None else None}
    for node in root.xpath('.//w:object | .//w:pict',namespaces=NS):
        if any(a.tag in {f"{{{NS['w']}}}object",f"{{{NS['w']}}}pict"} for a in node.iterancestors()):
            continue
        nearest_para=next((a for a in node.iterancestors() if a.tag==f"{{{NS['w']}}}p"),None)
        ole=[{'prog_id':obj.get('ProgID'),**relationship(obj.get(f"{{{NS['r']}}}id"))}
             for obj in node.findall('.//o:OLEObject',NS)]
        images=[relationship(im.get(f"{{{NS['r']}}}id") or im.get(f"{{{NS['o']}}}relid"))
                for im in node.findall('.//v:imagedata',NS)]
        equation=bool(ole) and all(re.match(r'^(?:equation|mathtype)(?:\.|$)',obj['prog_id'] or '',re.I) for obj in ole)
        evidence.append({'kind':'ole_object' if node.tag==f"{{{NS['w']}}}object" else 'vml_picture',
                         'paragraph_index':indexes.get(nearest_para),
                         'ole_objects':ole,'vml_images':images,
                         'classification':'equation_cache' if equation else 'unclassified_legacy_object',
                         'extracted_as_figure':False,'figure_identity_verified':False})
    return evidence

def document_images(p: Path,out: Path):
    with ZipFile(p) as z:
        if sum(i.file_size for i in z.infolist())>128*1024*1024:raise ProbeError('Uncompressed package too large')
        root=xml(safe_zip_member(z,'word/document.xml'))
        rels=xml(safe_zip_member(z,'word/_rels/document.xml.rels'))
        rm={r.get('Id'):r for r in rels}
        paragraphs=root.findall('.//w:body/w:p',NS)
        figures=[];pending=[];warnings=[];unmapped=[];caption_count=0
        unsupported=document_legacy_evidence(root,paragraphs,rm)
        if any(e['kind']=='ole_object' for e in unsupported):warnings.append('ole_object_evidence_not_extracted')
        if any(e['kind']=='vml_picture' or e['vml_images'] for e in unsupported):warnings.append('vml_image_evidence_not_extracted')
        legacy_paragraphs={e['paragraph_index'] for e in unsupported if e['paragraph_index'] is not None}
        for index,para in enumerate(paragraphs):
            text=''.join(para.xpath('.//w:t/text()',namespaces=NS)).strip()
            rids=para.xpath('.//w:drawing[not(ancestor::w:object)]//a:blip/@r:embed',namespaces=NS)
            # An unsupported object is a boundary: do not bind an earlier image
            # to its caption, and never promote formula/OLE fallback caches.
            if index in legacy_paragraphs:pending=[]
            for rid in dict.fromkeys(rids):
                rel=rm.get(rid)
                if rel is None or rel.get('TargetMode')=='External': warnings.append('external_or_missing_image_relationship');continue
                member=posixpath.normpath(posixpath.join('word',rel.get('Target')))
                if not member.startswith('word/media/'):warnings.append('non_media_image_relationship');continue
                raw=safe_zip_member(z,member)
                try:
                    im=Image.open(io.BytesIO(raw));size=im.size
                    if size[0]*size[1]>40_000_000: raise ProbeError('Image exceeds pixel budget')
                    im.verify()
                except ProbeError:raise
                except Exception:warnings.append('image_format_not_decoded');continue
                if size[0]<250 or size[1]<150:
                    warnings.append('small_inline_drawing_not_auto_counted_as_figure');continue
                saved=out/Path(member).name;saved.write_bytes(raw)
                ext=para.find('.//wp:extent',NS)
                pending.append({'paragraph_index':index,'relationship_id':rid,'member':member,
                     'asset':saved.name,'asset_sha256':sha(raw),'width_px':size[0],'height_px':size[1],
                     'word_extent_mm':[int(ext.get('cx'))/36000,int(ext.get('cy'))/36000] if ext is not None else None})
            # A title separator distinguishes caption candidates from prefixes
            # such as “图4展示…”. Candidates alone never establish figure identity.
            m=re.match(r'^图\s*([0-9]+(?:[.．\-－][0-9]+)*)(?:\s+(.*)|$)',text)
            recent=[x for x in pending if 0<=index-x['paragraph_index']<=3]
            if m:
                caption_count+=1
                caption={'number':m.group(1),'caption':text,'caption_paragraph_index':index,'caption_title':m.group(2) or ''}
                if recent and not rids:
                    figures.append({**caption,'images':recent})
                    pending=[x for x in pending if x not in recent]
                else:
                    nearby=[j for j,e in enumerate(unsupported)
                            if e['paragraph_index'] is not None and 0<=index-e['paragraph_index']<=3
                            and e['classification']!='equation_cache']
                    unmapped.append({**caption,'reason':'no_supported_drawing_bound',
                                     'nearby_unsupported_object_indexes':nearby,'figure_identity_verified':False})
            elif text and not rids:
                pending=[x for x in pending if index-x['paragraph_index']<2]
        if unmapped:warnings.append('unmapped_figure_caption_candidates')
        return {'kind':'docx','figures':figures,'figure_caption_count':caption_count,
                'figure_caption_count_basis':'caption_candidates_not_verified_inventory',
                'figure_extraction_status':'incomplete' if unmapped else 'requires_review' if unsupported or warnings else 'supported_scope_only',
                'mapped_figure_caption_count':len(figures),'unmapped_figure_captions':unmapped,
                'unsupported_object_evidence':unsupported,'figure_inventory_verified':False,
                'media_member_count':sum(n.startswith('word/media/') and not n.endswith('/') for n in z.namelist()),
                'warnings':sorted(set(warnings)),
                'scope_note':'Body DrawingML + nearby caption candidates with a number/title separator. Counts are not a verified figure inventory. VML/OLE caches are evidence only; nearby objects are not source identity matches. Floating text-box/multi-paragraph assemblies and other caption formats need Agent review.',
                'manuscript_column_not_inferred':True}
def image_distance(a: Path,b: Path):
    with Image.open(a) as im_a,Image.open(b) as im_b:
        if im_a.size!=im_b.size:return None
        diff=ImageChops.difference(im_a.convert('RGB'),im_b.convert('RGB'))
        return {'same_pixel_dimensions':True,'rgb_mean_absolute_difference':sum(ImageStat.Stat(diff).mean)/3,
                'identical_decoded_rgb':diff.getbbox() is None}
def probe_raster(p: Path,out: Path):
    raw=read_bytes(p)
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>40_000_000:raise ProbeError('Image exceeds pixel budget')
        if getattr(im,'n_frames',1)!=1:raise ProbeError('Multi-frame image needs explicit frame selection')
        result={'kind':'raster','width_px':im.width,'height_px':im.height,'mode':im.mode,
                'format':im.format,'asset':'source'+p.suffix.lower(),'semantic_text_extracted':False,
                'requires_agent_visual_review':True}
        im.verify()
    (out/result['asset']).write_bytes(raw)
    return result

def candidate_matches(assets,root):
    docs=[a for a in assets if a['probe']['kind']=='docx'];matches=[]
    for s in assets:
        pr=s['probe'];candidates=[]
        if pr['kind']=='pdf':
            for page in pr['pages']:
                for image in page['images']:
                    if image.get('asset'):candidates.append((page['number'],image['asset'],root/s['evidence_dir']/image['asset'],[image['width'],image['height']]))
        elif pr['kind']=='raster':
            candidates=[(None,pr['asset'],root/s['evidence_dir']/pr['asset'],[pr['width_px'],pr['height_px']])]
        elif pr['kind'].startswith('svg'):
            vb=(pr.get('viewBox') or '').replace(',',' ').split()
            if len(vb)==4:candidates=[(None,None,None,[float(vb[2]),float(vb[3])])]
        for page,member,file,size in candidates:
            found=[]
            for d in docs:
                for fig in d['probe']['figures']:
                    for im in fig['images']:
                        if size!=[im['width_px'],im['height_px']]:continue
                        target=root/d['evidence_dir']/im['asset']
                        dist=image_distance(file,target) if file else None
                        if dist and dist['rgb_mean_absolute_difference']>6:continue
                        found.append({'word_asset_id':d['id'],'word_figure_number':fig['number'],'word_member':im['member'],
                                'basis':'same_dimensions_and_decoded_image_comparison' if dist else 'same_dimensions_only_requires_visual_review',
                                'image_comparison':dist,'identity_verified':False})
            matches.append({'source_asset_id':s['id'],'source_page':page,'source_image_asset':member,'candidates':found,
                     'decision':'needs_agent_visual_review' if len(found)==1 else 'ambiguous' if len(found)>1 else 'no_match'})
    return matches

def scan(manifest:dict,out:Path):
    if (out/'probe.json').exists() or (out/'evidence').exists():raise ProbeError('Choose a fresh evidence directory; never overwrite a snapshot')
    out.mkdir(parents=True,exist_ok=True);beg=time.perf_counter();items=[]
    seen=set()
    for row in manifest['files']:
        if row['id'] in seen or not re.fullmatch(r'[A-Za-z0-9_-]+',row['id']):raise ProbeError('Duplicate/unsafe asset ID')
        seen.add(row['id']);p=Path(row['path']);data=read_bytes(p)
        target=out/'evidence'/row['id'];target.mkdir(parents=True,exist_ok=True)
        t=time.perf_counter();suffix=p.suffix.lower()
        try:
            if suffix=='.svg':pr=probe_svg(p,target)
            elif suffix=='.pdf':pr=probe_pdf(p,target)
            elif suffix=='.docx':pr=document_images(p,target)
            elif suffix in {'.png','.jpg','.jpeg','.tif','.tiff','.webp'}:pr=probe_raster(p,target)
            else:pr={'kind':'unsupported','reason':'Explicitly unsupported, not silently ignored'}
        except (ValueError,OSError,E.XMLSyntaxError,fitz.FileDataError) as e:pr={'kind':'error','reason':str(e)}
        if sha(read_bytes(p))!=sha(data):raise ProbeError('Source changed while probing; discard this snapshot')
        items.append({'id':row['id'],'name':p.name,'sha256':sha(data),'bytes':len(data),
                      'evidence_dir':str(target.relative_to(out)),'probe':pr,'probe_seconds':time.perf_counter()-t})
    result={'schema_version':'preflight-probe/2','asset_count':len(items),'assets':items,
        'matching_candidates':candidate_matches(items,out),'read_only':True,'source_files_modified':False,
        'ocr_calls':0,'font_directory_scans':0,'model_semantic_calls_inside_program':0,
        'program_seconds':time.perf_counter()-beg,'bench_scope':'Source probing and matching candidates only; excludes Agent semantic review, production/layout/PDF and tool latency.'}
    (out/'probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
