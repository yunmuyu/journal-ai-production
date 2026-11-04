import copy
from pathlib import Path
from lxml import etree as ET
import pytest
from journal_pdf.common import FigureError,digest_file
from journal_pdf.source_outline_chart import primitive_inventory,bind_registration,prepare_registered_svg
from journal_pdf.agent_spec import compile_reply_figure
from journal_pdf.charts import chart
from journal_pdf.assets import Assets
from journal_pdf.scene import audit_scene


def fixture(tmp_path, *, renamed=False, reordered=False):
    # Entirely synthetic. Mixed-series groups intentionally defeat group heuristics.
    glyph=lambda id,x,y:f'<path id="{id}" transform="translate({x},{y})" d="M0 0 L4 0 L4 5 L0 5 Z" fill="black" stroke="none"/>'
    groups=[
      '<g id="arbitrary"><path id="frame" d="M60 60 L360 60 L360 260 L60 260 Z" fill="none" stroke="black" stroke-width="1"/>'
      '<line id="xt1" x1="80" y1="260" x2="80" y2="254"/><line id="xt2" x1="340" y1="260" x2="340" y2="254"/>'
      '<line id="yt1" x1="60" y1="240" x2="66" y2="240"/><line id="yt2" x1="60" y1="170" x2="66" y2="170"/></g>',
      '<g id="not_a_series"><path id="curve1" d="M80 210 L200 220 L340 200" fill="none" stroke="blue"/>'
      '<path id="curve2" d="M80 230 L200 240 L340 225" fill="none" stroke="red"/></g>',
      '<g id="labels">'+''.join(glyph(*q) for q in [('xl1',78,270),('xl2',338,270),('yl1',40,238),('yl2a',40,168),('yl2b',45,164),('xtitle',170,285),('ytitle',15,170),('title',190,25),('ll1',120,88),('ll2',120,118)])+'</g>',
      '<g id="unusual"><path id="legendfill" d="M75 75 L230 75 L230 145 L75 145 Z" fill="white" stroke="none"/>'
      '<path id="legendframe" d="M75 75 L230 75 L230 145 L75 145 Z" fill="none" stroke="black"/>'
      '<line id="sw1" x1="85" y1="95" x2="110" y2="95" stroke="blue"/>'
      '<line id="sw2" x1="85" y1="125" x2="110" y2="125" stroke="red"/></g>']
    if renamed:groups=[s.replace('id="arbitrary"','id="changed"').replace('id="not_a_series"','id="random"') for s in groups]
    groups=[groups[0],groups[1],groups[3],groups[2]]
    if reordered:groups=[groups[1],groups[0],groups[2],groups[3]]
    p=tmp_path/'synthetic.svg';p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="310" stroke="black" stroke-width="1" stroke-linejoin="round">'+''.join(groups)+'</svg>')
    inv=primitive_inventory(p);root=ET.parse(p)
    lookup={root.xpath(q['address'])[0].get('id'):q['id'] for q in inv['objects']}
    def label(ids,text):return {'refs':[lookup[x] for x in ids.split()],'text':text}
    r={'source_sha256':digest_file(p),'bindings':{q['id']:q['sha256'] for q in inv['objects']},'frame':lookup['frame'],
       'x_ticks':[{'tick_ref':lookup['xt1'],'label':label('xl1','1'),'text':'1'},{'tick_ref':lookup['xt2'],'label':label('xl2','2'),'text':'2'}],
       'y_ticks':[{'tick_ref':lookup['yt1'],'label':label('yl1','10^-3'),'text':'10^-3','power10':-3},
                  {'tick_ref':lookup['yt2'],'label':label('yl2a yl2b','10^-2'),'text':'10^-2','power10':-2}],
       'x_title':{'source':label('xtitle','Noise (%)'),'text':'Noise/%','correction_evidence':'explicit synthetic test instruction'},
       'y_title':{'source':label('ytitle','Rate (BER)'),'text':'Rate/BER','correction_evidence':'explicit synthetic test instruction'},
       'title':label('title','Original title'),
       'legend':{'decoration_refs':[lookup['legendfill'],lookup['legendframe']],'region_ref':lookup['legendframe'],'width_extension':0,'extension_evidence':''},
       'series':[{'id':'first','label':label('ll1','A'),'source_refs':[lookup['curve1']],'swatch_refs':[lookup['sw1']]},
                 {'id':'second','label':label('ll2','B'),'source_refs':[lookup['curve2']],'swatch_refs':[lookup['sw2']]}],
       'protected_refs':[lookup[k] for k in ['frame','xt1','xt2','yt1','yt2','curve1','curve2']]}
    return p,inv,r,lookup


def compile_spec(p,inv,r):
    reply={'id':'synthetic-outline','author':'Synthetic','kind':'outlined-svg-chart','review':{'source_checked':True,'labels_checked':True,'outline_transcription_checked':True,'series_identity_checked':True},'outline_chart':r}
    source={'snapshot':p.name,'sha256':digest_file(p),'id':'source-1'}
    return compile_reply_figure(reply,source,{'kind':'svg','id':'svg-1','outline_inventory':inv}),reply,source


@pytest.mark.parametrize('renamed,reordered',[(False,False),(True,False),(True,True)])
def test_register_anonymous_or_reordered_groups(tmp_path,renamed,reordered):
    p,inv,r,ids=fixture(tmp_path,renamed=renamed,reordered=reordered)
    b=bind_registration(inv,r)
    assert b['axis_frame_source']==[60,60,360,260]
    assert b['plot_clip'][0]<60 and b['plot_clip'][2]>360
    assert [t['position'] for t in b['x_ticks']]==[80,340]
    root,b,proof=prepare_registered_svg(p,r)
    remaining=set(root.xpath('//@id'))
    assert {'curve1','curve2','frame','xt1','yt2'}<=remaining
    assert not {'ll1','legendfill','sw1','title'}&remaining
    assert proof['geometry_unchanged'] and proof['coordinate_conversion']['pdf_points_per_source_unit']==1
    sw,_,_=prepare_registered_svg(p,r,swatch_id='second')
    assert sw.xpath('//*[@id="sw2"]') and not sw.xpath('//*[@id="curve1" or @id="sw1"]')


@pytest.mark.parametrize('change',['source','hash','omit','delete_curve','reuse','direction','power','extension','title'])
def test_tampering_fails_closed(tmp_path,change):
    p,inv,r,ids=fixture(tmp_path)
    if change=='source':r['source_sha256']='0'*64
    elif change=='hash':r['bindings'][ids['curve1']]='0'*64
    elif change=='omit':r['protected_refs'].remove(ids['curve1'])
    elif change=='delete_curve':r['series'][0]['swatch_refs']=[ids['curve1']]
    elif change=='reuse':r['series'][1]['source_refs']=[ids['curve1']]
    elif change=='direction':r['x_ticks'][0]['tick_ref']=ids['yt1']
    elif change=='power':r['y_ticks'][0]['power10']=-1
    elif change=='extension':r['legend']['width_extension']=10
    elif change=='title':r['title']['refs']=[]
    with pytest.raises(FigureError):bind_registration(inv,r)


def test_runtime_rechecks_source(tmp_path):
    p,inv,r,ids=fixture(tmp_path);p.write_text(p.read_text().replace('L200 220','L200 219'))
    with pytest.raises(FigureError):prepare_registered_svg(p,r)


def test_semantics_and_font_policy(tmp_path):
    p,inv,r,ids=fixture(tmp_path);spec,reply,source=compile_spec(p,inv,r)
    assert spec['kind']=='chart' and spec['policy']['design_font_size_pt']==8
    assert spec['x_title']=='Noise/%' and spec['y_title']=='Rate/BER'
    assert spec['y_ticks'][1]['power10']==-3
    assert spec['restore_verified_tick_stubs'] is False
    reply['policy']={'design_font_size_pt':6}
    with pytest.raises(FigureError):compile_reply_figure(reply,source,{'kind':'svg','id':'svg-1','outline_inventory':inv})
    reply.pop('policy');reply['review']['outline_transcription_checked']=False
    with pytest.raises(FigureError):compile_reply_figure(reply,source,{'kind':'svg','id':'svg-1','outline_inventory':inv})


def test_chart_uses_shared_typography_and_original_legend(tmp_path,reg):
    p,inv,r,ids=fixture(tmp_path);spec,_,_=compile_spec(p,inv,r);assets=Assets()
    try:
        scene=chart(spec,reg,8,assets,tmp_path)
        assert next(t for t in scene.texts if t['id']=='xtitle')['role']=='axis-title'
        assert next(t for t in scene.texts if t['id']=='figure-title')['source_content']=='Original title'
        assert not scene.paths
        box=next(n['rect'] for n in scene.nodes if n['id']=='legend-frame')
        assert abs((box[3]-box[1])-42)<1e-6
        assert audit_scene(scene)==[]
    finally:assets.close()


def test_capacity_failure_never_relocates_or_shrinks(tmp_path,reg):
    p,inv,r,ids=fixture(tmp_path);r['series'][0]['label']['text']='A very long verified legend label that cannot fit in this original region'
    spec,_,_=compile_spec(p,inv,r);assets=Assets()
    try:
        with pytest.raises(FigureError) as e:chart(spec,reg,8,assets,tmp_path)
        assert e.value.code=='legend_source_region_capacity'
    finally:assets.close()


def test_unsupported_dimensions_fail(tmp_path):
    p,_,_,_=fixture(tmp_path);p.write_text(p.read_text().replace('width="400"','width="100%"'))
    with pytest.raises(FigureError):primitive_inventory(p)


def test_ingest_inventory_does_not_claim_chart_recognition(tmp_path):
    from journal_pdf.ingest_native import svg_pages
    p,inv,r,ids=fixture(tmp_path)
    page=svg_pages(p,tmp_path)[0]
    assert page['chart_candidates']==[] and page['outline_inventory']['source_sha256']==digest_file(p)
    assert page['warnings'][0]['code']=='outlined_svg_registration_required'


@pytest.mark.parametrize('key,value',[('plot_clip',[0,0,100,100]),('x_title','Altered'),('legend_placement','outside-top'),('restore_verified_tick_stubs',True)])
def test_compiled_geometry_cannot_override_registration(tmp_path,key,value):
    from journal_pdf.source_outline_chart import validate_chart_spec
    p,inv,r,ids=fixture(tmp_path);spec,_,_=compile_spec(p,inv,r);spec[key]=value
    with pytest.raises(FigureError):validate_chart_spec(p,spec)


def test_synthetic_pdf_has_real_axis_audits(tmp_path,reg):
    from journal_pdf.render import render_one
    source=tmp_path/'inputs';source.mkdir();p,inv,r,ids=fixture(source)
    spec,_,_=compile_spec(p,inv,r);assets=Assets()
    try:
        result=render_one(spec,reg,assets,source,tmp_path/'outputs')
        assert result['kind']=='chart' and result['mechanical_checks_passed']
        assert len(result['pdf_audit']['axis_unit_notation']['checks'])==2
        assert result['pdf_audit']['source_path_ownership']['matched_path_count']>0
        assert result['ready_for_publication'] is False
    finally:assets.close()


def test_actual_path_ownership_does_not_exempt_viewport(tmp_path,reg):
    import pymupdf as fitz
    from journal_pdf.source_icons import audit_icon_paths
    p,inv,r,ids=fixture(tmp_path);spec,_,_=compile_spec(p,inv,r);assets=Assets()
    try:
        scene=chart(spec,reg,8,assets,tmp_path)
        with fitz.open() as doc:
            page=doc.new_page(width=scene.width,height=scene.height)
            for item in scene.assets:assets.place(page,item['asset'],item['rect'])
            page.draw_line((80,100),(100,110),width=.8,color=(0,))
            audit=audit_icon_paths(page,scene.assets)
            assert audit['matched_path_count']>0 and len(audit['stroke_violations'])==1
            assert abs(audit['stroke_violations'][0]['width_pt']-.8)<.001
            scene.assets[0]['asset'].data+=b' tampered'
            with pytest.raises(FigureError) as e:audit_icon_paths(page,scene.assets)
            assert e.value.code=='source_icon_derivative_changed'
    finally:assets.close()


def test_changed_source_stroke_rejected(tmp_path):
    p,inv,r,ids=fixture(tmp_path);p.write_text(p.read_text().replace('stroke-width="1"','stroke-width="2"'))
    with pytest.raises(FigureError):prepare_registered_svg(p,r)


def test_registration_cannot_substitute_provenance_source(tmp_path):
    p,inv,r,ids=fixture(tmp_path);_,reply,source=compile_spec(p,inv,r)
    source['sha256']='0'*64
    with pytest.raises(FigureError) as e:compile_reply_figure(reply,source,{'kind':'svg','id':'svg-1','outline_inventory':inv})
    assert e.value.code=='outline_chart_source'


def test_legend_order_and_unclassified_path_fail_closed(tmp_path):
    p,inv,r,ids=fixture(tmp_path);r['series'].reverse()
    with pytest.raises(FigureError):bind_registration(inv,r)
    r['series'].reverse();r['series'][0]['source_refs']=[ids['frame']]
    with pytest.raises(FigureError):bind_registration(inv,r)


@pytest.mark.parametrize('replacement',[
    'M20 210 L200 220 L390 200',
    'M80 210 L200 280 L340 200',
])
def test_registered_series_outside_frame_is_not_silently_cropped(tmp_path,replacement):
    p,inv,r,ids=fixture(tmp_path)
    p.write_text(p.read_text().replace('M80 210 L200 220 L340 200',replacement))
    inv=primitive_inventory(p);r['source_sha256']=digest_file(p)
    r['bindings']={q['id']:q['sha256'] for q in inv['objects']}
    with pytest.raises(FigureError,match='系列几何超出原轴框'):bind_registration(inv,r)


def test_registered_structural_line_outside_frame_is_rejected(tmp_path):
    p,inv,r,ids=fixture(tmp_path)
    p.write_text(p.read_text().replace('x1="80" y1="260" x2="80" y2="254"','x1="80" y1="260" x2="80" y2="-10"'))
    inv=primitive_inventory(p);r['source_sha256']=digest_file(p);r['bindings']={q['id']:q['sha256'] for q in inv['objects']}
    with pytest.raises(FigureError,match='轴线/网格几何超出'):bind_registration(inv,r)


def test_boundary_stroke_padding_preserves_frame_scale(tmp_path,reg):
    p,inv,r,ids=fixture(tmp_path)
    p.write_text(p.read_text().replace('M80 210 L200 220 L340 200','M60 210 L200 220 L360 200'))
    inv=primitive_inventory(p);r['source_sha256']=digest_file(p);r['bindings']={q['id']:q['sha256'] for q in inv['objects']}
    spec,_,_=compile_spec(p,inv,r);assets=Assets()
    try:
        scene=chart(spec,reg,8,assets,tmp_path)
        assert scene.layout_evidence['scale']==pytest.approx(180/300)
        assert scene.assets[0]['rect'][2]-scene.assets[0]['rect'][0]>180
        assert spec['plot_clip'][0]<60 and spec['plot_clip'][2]>360
        assert spec['axis_frame_source']==[60,60,360,260]
        assert assets.registered_outline_chart(p,r).audit['protected_ink_inside_viewport'] is True
    finally:assets.close()


def test_actual_pixels_keep_boundary_series_ink_outside_mathematical_frame(tmp_path):
    import pymupdf as fitz
    p,inv,r,ids=fixture(tmp_path)
    p.write_text(p.read_text().replace('M80 210 L200 220 L340 200','M60 200 L60 230').replace('id="curve1"','id="curve1" stroke-width="6"'))
    inv=primitive_inventory(p);r['source_sha256']=digest_file(p);r['bindings']={q['id']:q['sha256'] for q in inv['objects']}
    b=bind_registration(inv,r);clip=b['plot_clip'];assets=Assets()
    try:
        asset=assets.registered_outline_chart(p,r)
        with fitz.open() as doc:
            page=doc.new_page(width=400,height=300);scale=.6
            target=[20,20,20+(clip[2]-clip[0])*scale,20+(clip[3]-clip[1])*scale]
            assets.place(page,asset,target)
            # This is 1.5 source units OUTSIDE the mathematical frame and beyond
            # its thin border. Only the retained 6-unit series stroke paints it.
            x=20+(58.5-clip[0])*scale;y=20+(215-clip[1])*scale
            pix=page.get_pixmap(matrix=fitz.Matrix(8,8),alpha=False)
            assert max(pix.pixel(round(x*8),round(y*8)))<180
            # Original paper remains blank beyond the full series stroke.
            outside=20+(55-clip[0])*scale
            assert min(pix.pixel(round(outside*8),round(y*8)))>245
    finally:assets.close()
