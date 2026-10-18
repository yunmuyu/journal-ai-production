from __future__ import annotations
import collections, hashlib, io, math, os, tempfile, time
from pathlib import Path
import pymupdf as fitz
from PIL import Image,ImageChops
from . import __version__
from .common import FigureError, atomic_json, digest_file, digest_json, safe_name, resolve_source, PT_PER_MM, contains, finite
from .fonts import draw_text
from .pdf_fonts import normalize_type0_font_names
from .scene import audit_scene, arrow_vertices
from .layouts import DIAGRAMS
from .charts import chart
from .editorial import engine_signature,RULESET


def draw_path(page,p):
    pts=[list(v) for v in p['points']]
    heads=[]
    for start in ([False,True] if p['both'] else [False] if p['arrow'] else []):
        heads.append(arrow_vertices(pts,at_start=start,scale=p.get("arrow_scale",1)))
    # Same notched-arrow dimensions as the current project contract.
    for idx,nextidx in ([(len(pts)-1,len(pts)-2),(0,1)] if p['both'] else [(len(pts)-1,len(pts)-2)] if p['arrow'] else []):
        tip,prev=pts[idx],pts[nextidx];length=math.dist(tip,prev)
        ux,uy=(tip[0]-prev[0])/length,(tip[1]-prev[1])/length
        pts[idx]=[tip[0]-2.2*p.get("arrow_scale",1)*ux,tip[1]-2.2*p.get("arrow_scale",1)*uy]
    sh=page.new_shape();sh.draw_polyline(pts)
    sh.finish(width=p['width'],color=(0,),dashes=('['+' '.join(map(str,p['dash']))+'] 0') if p['dash'] else None,closePath=False)
    sh.commit()
    for vertices in heads:
        sh=page.new_shape();sh.draw_polyline(vertices);sh.finish(color=None,fill=(0,),closePath=True);sh.commit()


def draw_node(page,n):
    r=fitz.Rect(n['rect']);kind=n['kind'];sh=page.new_shape()
    if kind=='rectangle':sh.draw_rect(r)
    elif kind=='roundrect':sh.draw_rect(r,radius=.22)
    elif kind=='terminator':sh.draw_rect(r,radius=.5)
    elif kind=='ellipse':sh.draw_oval(r)
    elif kind=='diamond':sh.draw_polyline([(r.x0+r.x1)/2,r.y0] if False else [[(r.x0+r.x1)/2,r.y0],[r.x1,(r.y0+r.y1)/2],[(r.x0+r.x1)/2,r.y1],[r.x0,(r.y0+r.y1)/2]])
    elif kind=='inputOutput':
        inset=min(r.height*.25,4)
        sh.draw_polyline([[r.x0+inset,r.y0],[r.x1,r.y0],[r.x1-inset,r.y1],[r.x0,r.y1]])
    sh.finish(width=n['width'],color=(n.get('gray',0),),fill=(n['fill'],) if 'fill' in n else None,closePath=True);sh.commit()


def compile_figure(spec,reg,assets,root):
    from .editorial import scale_scene
    kind=spec.get('kind');policy=spec.get('policy',{});mode=policy.get('column','single')
    if mode not in ('single','double','auto'):raise FigureError('column_policy','栏宽选项为single/double/auto')
    col=160 if mode=='double' else 80
    legacy=policy.get('font_sizes',[8])
    if not legacy or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) or x<6 or x>8 for x in legacy):
        raise FigureError('font_sizes_policy','设计字号必须在6—8pt之间')
    size=policy.get('design_font_size_pt',legacy[0])
    if not isinstance(size,(int,float)) or not math.isfinite(size) or not 6<=size<=8:
        raise FigureError('font_sizes_policy','设计字号必须在6—8pt之间')
    if kind=='chart':scene=chart(spec,reg,size,assets,root)
    elif kind in DIAGRAMS:scene=DIAGRAMS[kind](spec,reg,size)
    else:raise FigureError('unsupported_figure_kind','未实现的图种，不生成冒充成果的空页',kind=kind)
    layout_build_count=1
    limit=col*PT_PER_MM-.5
    factor=min(1.,limit/scene.width)
    if factor<1 and any(p.get('exact_terminal') for p in scene.paths):
        def rebuild(font_size):
            nonlocal layout_build_count
            layout_build_count+=1
            if kind=='chart':return chart(spec,reg,font_size,assets,root)
            return DIAGRAMS[kind](spec,reg,font_size)
        # Exact 3 mm terminals are a final-size constraint. Rebuild the layout at
        # the largest feasible font size instead of shrinking the completed scene.
        smallest=rebuild(6.)
        if smallest.width>limit+1e-7:
            scene=smallest
            factor=min(1.,limit/scene.width)
        else:
            low,high,best=6.,float(size),smallest
            for _ in range(16):
                mid=(low+high)/2
                candidate=rebuild(mid)
                if candidate.width<=limit+1e-7:
                    low,best=mid,candidate
                else:high=mid
            scene=best
            factor=1.
    if scene.size*factor<6-1e-7:
        raise FigureError('layout_reflow_required','完整图件缩后低于6pt；先重新布局，不自动改双栏或只缩字',
                          design_size=size,width_pt=scene.width,column_mm=col,proposed_size=scene.size*factor)
    scene=scale_scene(scene,factor)
    issues=audit_scene(scene)
    if scene.height>policy.get('max_height_mm',240)*PT_PER_MM:issues.append({'code':'page_height_overflow'})
    attempts=[{'column_mm':col,'design_font_size_pt':size,'font_size_pt':scene.size,'whole_artwork_scale':factor,
               'width_pt':scene.width,'height_pt':scene.height,'issues':issues}]
    scene.layout_evidence.update({'fit_attempts':attempts,'column_mm':col,
        'layout_build_count':layout_build_count,'pdf_font_ladder_renders':False,
        'priority':'default-8pt-first; no exhaustive 8/7/6 PDF rendering',
        'optimization_claim':'feasible measured template layout; not a proven global optimum'})
    if issues:raise FigureError('no_feasible_layout','布局未通过实际几何检查，不输出定稿',attempts=attempts)
    return scene


def pdf_audit(path:Path,scene,reg):
    d=fitz.open(path);p=d[0]
    if len(d)!=1:raise FigureError('page_count','单图必须只有一页')
    # Ignore only formatting whitespace. Missing scientific symbols remain failures.
    actual=collections.Counter(c for c in p.get_text() if not c.isspace())
    expected=collections.Counter(c for t in scene.texts for c in t['measurement']['text'] if not c.isspace())
    content_ok=actual==expected
    missing=dict(expected-actual);extra=dict(actual-expected)
    fontrows=[]
    for row in p.get_fonts(full=True):
        info=d.extract_font(row[0]);fontrows.append({'xref':row[0],'name':row[3],'embedded':bool(info[3])})
    pix=p.get_pixmap(dpi=300,colorspace=fitz.csRGB,alpha=False)
    img=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
    r,g,b=img.split();dif=ImageChops.lighter(ImageChops.difference(r,g),ImageChops.lighter(ImageChops.difference(r,b),ImageChops.difference(g,b)))
    hist=dif.histogram();off=sum(hist[3:]);color_ok=off==0
    ink=ImageChops.difference(img,Image.new('RGB',img.size,'white')).getbbox()
    if not ink:raise FigureError('empty_pdf','最终PDF没有可见内容')
    from .axis_units import audit_axis_titles
    axis_units=audit_axis_titles(scene,p.get_text())
    numeric_expected=collections.Counter(t['measurement']['text'] for t in scene.texts if t['role'] in ('axis-tick','numeric-value','number'))
    numeric_actual=collections.Counter(line.strip() for line in p.get_text().splitlines())
    numeric_missing=dict(numeric_expected-numeric_actual)
    trace=p.get_texttrace()
    black_ok=all(all(abs(v)<1e-8 for v in t['color']) for t in trace)
    stroke_rows=[g for g in p.get_drawings() if g['type'] in ('s','fs') and g['rect'].intersects(p.rect)]
    stroke_bad=[{'width_pt':g['width'],'rect':list(g['rect'])} for g in stroke_rows if abs(g['width']-.5)>.005]
    result={'page_count':len(d),'width_mm':p.rect.width/PT_PER_MM,'height_mm':p.rect.height/PT_PER_MM,
            'expected_text_characters':sum(expected.values()),'actual_text_characters':sum(actual.values()),
            'text_multiset_exact':content_ok,'missing_characters':missing,'extra_characters':extra,
            'all_fonts_embedded':all(x['embedded'] for x in fontrows),'fonts':fontrows,
            'neutral_rgb_300dpi':color_ok,'nonneutral_pixels':off,'max_channel_difference':max(i for i,v in enumerate(hist) if v),
            'image_resource_count':len(p.get_images()),'vector_drawing_count':len(p.get_drawings()),
            'axis_unit_notation':axis_units,'numeric_grouping_in_actual_pdf':not numeric_missing,'numeric_missing':numeric_missing,
            'editable_text_pure_black':black_ok,'effective_path_strokes_05pt':not stroke_bad,
            'audited_stroke_count':len(stroke_rows),'stroke_violations':stroke_bad,
            'stroke_scope':'Visible PDF stroke paths only; raster curves, fills and glyph outlines are not stroke-width checks',
            'not_pdfx_certified':True,'font_profile_is_preview':reg.is_preview,
            'requires_semantic_visual_review':True,'requires_indesign_placement_test':True}
    if not content_ok or not color_ok or not result['all_fonts_embedded'] or numeric_missing or not black_ok or stroke_bad or not axis_units['ok']:
        raise FigureError('actual_pdf_audit_failed','实际PDF检查失败',audit=result)
    d.close();return result,img


def render_one(spec,reg,assets,source_root:Path,output_root:Path,*,overwrite=False):
    start=time.perf_counter()
    from .common import validate_output_isolation
    validate_output_isolation(source_root, output_root)
    id=safe_name(spec['id']);author=safe_name(spec.get('author','未归属'))
    # Bind source bytes before constructing any derivative. References are never edited.
    bindings=[]
    for v in spec.get('sources',[]):
        p=resolve_source(source_root,v['path']);sha=digest_file(p)
        if sha!=v['sha256']:raise FigureError('source_hash_mismatch','原始素材与制作说明绑定的版本不同',source=v['path'])
        bindings.append({'path':v['path'],'sha256':sha,'role':v.get('role','source')})
    if not bindings and not spec.get('synthetic',False):raise FigureError('source_identity_missing','真实图件必须绑定原始素材哈希')
    scene=compile_figure(spec,reg,assets,source_root)
    allowed={str(resolve_source(source_root,b['path'])):b['sha256'] for b in bindings}
    for a in scene.assets:
        asset=a['asset']
        if allowed.get(str(Path(asset.source_path).resolve()))!=asset.source_hash:
            raise FigureError('unbound_asset','版位引用的素材没有在来源清单中绑定',asset=a['id'])
    layout_finished=time.perf_counter()
    folder=output_root/author/id;folder.mkdir(parents=True,exist_ok=True)
    pdf=folder/(id+'.pdf');preview=folder/(id+'.png');report=folder/'report.json'
    if pdf.exists() and not overwrite:raise FigureError('output_exists','输出已存在，拒绝覆盖；用新目录或显式--overwrite',path=str(pdf))
    tempdir=Path(tempfile.mkdtemp(prefix='.build-',dir=folder));tmp=tempdir/'figure.pdf'
    try:
        reg.prepare_document_fonts(scene.texts)
        doc=fitz.open();page=doc.new_page(width=scene.width,height=scene.height);asset_reports=[]
        for a in scene.assets:
            if a['role']!='legend-swatch':asset_reports.append(assets.place(page,a['asset'],a['rect'])|{'id':a['id'],'role':a['role']})
        for p in scene.paths:draw_path(page,p)
        for n in scene.nodes:draw_node(page,n)
        for a in scene.assets:
            if a['role']=='legend-swatch':asset_reports.append(assets.place(page,a['asset'],a['rect'])|{'id':a['id'],'role':a['role']})
        for t in scene.texts:draw_text(page,reg,t)
        doc.set_metadata({'title':id,'author':'Journal Direct PDF candidate','subject':'实验样张；须真实字体和本机终检，不自动发布',
                          'creator':f'journal-direct-pdf {__version__}','producer':'PyMuPDF direct vector/mixed renderer; no Adobe runtime'})
        crop_pix=page.get_pixmap(dpi=300,colorspace=fitz.csRGB,alpha=False)
        crop_img=Image.frombytes('RGB',(crop_pix.width,crop_pix.height),crop_pix.samples)
        ink=ImageChops.difference(crop_img,Image.new('RGB',crop_img.size,'white')).getbbox()
        if not ink:raise FigureError('empty_pdf','裁切前没有可见墨迹')
        unit=72/300
        crop=fitz.Rect(max(0,ink[0]*unit-.25),max(0,ink[1]*unit-.25),
                       min(page.rect.width,ink[2]*unit+.25),min(page.rect.height,ink[3]*unit+.25))
        scene.layout_evidence['export_crop']={'method':'actual-PDF-300dpi-ink','source_page_rect':list(page.rect),
              'crop_box':list(crop),'protection_pt':.25,'rescaled':False,'scene_coordinates':'before CropBox offset'}
        page.set_cropbox(crop)
        normalize_type0_font_names(doc,reg.postscript_names)
        doc.save(tmp,garbage=4,deflate=True);doc.close()
        drawing_finished=time.perf_counter()
        audit,img=pdf_audit(tmp,scene,reg)
        preview_tmp=tempdir/'figure.png';img.save(preview_tmp,optimize=True)
        warnings=[dict(w) for w in spec.get('warnings',[])]+list(scene.notes)
        unit_changes=[ev for ev in scene.layout_evidence.get('axis_title_normalization',{}).values() if ev['changed']]
        if unit_changes:
            for w in warnings:
                if w.get('code')=='literal_scientific_notation_retained':
                    w['message']='量名、原数值、刻度后缀及原样式含义保留；已知轴单位的括号已按现行量名/单位规则规范，未换算单位或推断下标。'
            warnings.append({'code':'axis_unit_notation_normalized','changes':unit_changes,'message':'单位标注已在测量前按公共规则规范，并核对实际PDF'})
        for a in asset_reports:
            if a['role']=='plot' and a.get('effective_ppi',9999)<spec.get('minimum_raster_ppi',300):
                warnings.append({'code':'low_source_resolution','effective_ppi':round(a['effective_ppi'],1),
                                 'message':'原位图清晰度不足；没有通过放大或AI补画伪造细节，须按实际印制要求评估'})
        if reg.is_preview:warnings.append({'code':'preview_font_profile','message':'使用显式标明的替代字体；不是正式宋体/汉仪中宋简/Times New Roman验收稿'})
        reg.verify_unchanged()
        # Detect source changes during a long render, not only before it.
        for b in bindings:
            if digest_file(resolve_source(source_root,b['path']))!=b['sha256']:
                raise FigureError('source_changed_during_render','输出前发现源文件变化')
        result={'schema_version':1,'engine_version':__version__,'engine_signature':engine_signature(),
                'editorial_ruleset':RULESET,'editorial_coverage':'partial-see-RULE-COVERAGE.md','id':id,'author':author,'kind':spec['kind'],
                'status':'candidate-rendered','mechanical_checks_passed':True,'ready_for_publication':False,
                'backend':'direct-pdf','required_artifact':'pdf','ai_required':False,
                'editable_policy':spec.get('policy',{}),'spec_hash':digest_json(spec),'source_bindings':bindings,'font':reg.summary(),
                'layout':scene.export(),'assets':asset_reports,'pdf_audit':audit,'warnings':warnings,
                'needs_review':['source-pairing-and-topology','font-profile-equivalence','actual-size-visual-review','InDesign-placement'],
                'timings_ms':{'compile':round((layout_finished-start)*1000,3),
                              'pdf_write_and_font_subset':round((drawing_finished-layout_finished)*1000,3),
                              'actual_pdf_audit_and_preview':round((time.perf_counter()-drawing_finished)*1000,3),
                              'total':round((time.perf_counter()-start)*1000,3)},
                'pdf_sha256':digest_file(tmp),'output_pdf':str(pdf.relative_to(output_root)),
                'preview':str(preview.relative_to(output_root))}
        os.replace(tmp,pdf);os.replace(preview_tmp,preview);atomic_json(report,result)
        atomic_json(folder/'figure.spec.json',spec)
        return result
    finally:
        import shutil;shutil.rmtree(tempdir,ignore_errors=True)
