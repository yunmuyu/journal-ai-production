import copy
import fitz
import pytest
from journal_pdf.chart_vector_layout import layout_vector_chart
from journal_pdf.common import FigureError, digest_file


def fixture(tmp_path):
    p=tmp_path/'source.pdf';doc=fitz.open();page=doc.new_page(width=100,height=100)
    page.draw_line((15,80),(90,80));page.draw_line((15,80),(15,10))
    for x in (30,34,38):page.draw_line((x,80),(x,76))
    for y in (65,50):page.draw_line((15,y),(19,y))
    doc.save(p);doc.close()
    ids=['x1','x2','x3','y0','y1','y2','xt','yt']
    vals=['1.01','1.02','1.03','0','1','2','Time','Faults']
    roles=['axis-tick']*6+['axis-title']*2
    spec={'width_pt':200,'height_pt':200,'assets':[{'id':'body','path':'source.pdf','page':0,'source_kind':'pdf','source_vector_body':True,'clip':[0,0,100,100],'target':[0,0,200,200],'text_replacements':[{'target_text_id':i} for i in ids]}],
          'texts':[{'id':i,'text':v,'role':r,'x':0,'y':0} for i,v,r in zip(ids,vals,roles)],
          'chart_vector_layout':{'body_id':'body','source_sha256':digest_file(p),'axis_origin':[15,80],
          'x_axis_end':[90,80],'y_axis_end':[15,10],
          'x_ticks':[{'id':i,'point':[x,80]} for i,x in zip(ids[:3],(30,34,38))],
          'y_ticks':[{'id':i,'point':[15,y]} for i,y in zip(ids[3:6],(80,65,50))],
          'x_title_id':'xt','y_title_id':'yt'}}
    for i,r in enumerate(spec['assets'][0]['text_replacements']):
        if i<3:r['source_bbox']=[(30,34,38)[i]-1,81,(30,34,38)[i]+1,82]
        elif i<6:r['source_bbox']=[10,(80,65,50)[i-3]-1,14,(80,65,50)[i-3]+1]
    spec['legend_review']={'present':False,'source_sha256':digest_file(p),'reason':'合成原图无图例'}
    return spec


def test_dense_vector_ticks_use_real_positions_and_auto_rotate(reg,tmp_path):
    s=fixture(tmp_path);out,evidence=layout_vector_chart(s,reg,tmp_path,8)
    x=[t for t in out['texts'] if t['id'].startswith('x') and t['role']=='axis-tick']
    assert [t['x'] for t in x]==pytest.approx([60,68,76])
    assert all(t['rotation']==90 for t in x)
    assert evidence['x_tick_rotation']==90 and evidence['source_geometry_verified']
    assert next(t for t in out['texts'] if t['id']=='yt')['rotation']==90
    assert s['texts'][0]['x']==0


def test_secondary_axis_uses_own_outward_ticks_and_grouped_title(reg,tmp_path):
    s=fixture(tmp_path);p=tmp_path/'source.pdf'
    with fitz.open(p) as doc:
        page=doc[0];page.draw_line((90,10),(90,80))
        for y in (80,45,10):page.draw_line((90,y),(94,y))
        data=doc.tobytes()
    p.write_bytes(data);sha=digest_file(p)
    s['chart_vector_layout']['source_sha256']=sha;s['legend_review']['source_sha256']=sha
    ticks=[]
    for i,y in enumerate((80,45,10)):
        ident=f'r{i}';ticks.append({'id':ident,'point':[90,y]})
        s['texts'].append({'id':ident,'text':str(i),'role':'secondary-axis-tick','x':0,'y':0})
        s['assets'][0]['text_replacements'].append({'target_text_id':ident,'source_bbox':[95,y-1,98,y+1]})
    for ident,text in [('rt','Phase'),('unit','deg')]:
        s['texts'].append({'id':ident,'text':text,'role':'secondary-axis-title','x':0,'y':0})
        s['assets'][0]['text_replacements'].append({'target_text_id':ident,'source_bbox':[98,25,99,60]})
    s['chart_vector_layout']['secondary_y_axis']={'ticks':ticks,'title_ids':['rt','unit']}
    out,evidence=layout_vector_chart(s,reg,tmp_path,8)
    targets={t['id']:t for t in out['texts']}
    assert all(targets[t['id']]['x']>188 for t in ticks)
    assert [t['tick_end'] for t in evidence['secondary_y_axis']['ticks']]==[[94,80],[94,45],[94,10]]
    assert targets['rt']['rotation']==targets['unit']['rotation']==90
    assert 'tick_end' not in ticks[0]
    s['chart_vector_layout']['secondary_y_axis']['ticks'][1]['point'][1]=50
    with pytest.raises(FigureError):layout_vector_chart(s,reg,tmp_path,8)


def test_axis_ink_uses_transformed_geometry_not_form_line_width(tmp_path):
    from journal_pdf.chart_vector_layout import _axis_outer_ink
    with fitz.open() as source,fitz.open() as target:
        page=source.new_page(width=1000,height=1000)
        page.draw_line((100,900),(900,900),width=16)
        page.draw_line((900,900),(900,100),width=16)
        dest=target.new_page(width=100,height=100);dest.show_pdf_page(dest.rect,source,0)
        bottom,right=_axis_outer_ink(dest,[0,0,100,100],(90,90),(10,90),(90,10),1,y_outward=1)
        assert .6<bottom<1 and .6<right<1


def test_vector_chart_accepts_source_bound_legend_and_keeps_complete_text(reg,tmp_path,monkeypatch):
    s=fixture(tmp_path);p=tmp_path/'source.pdf'
    with fitz.open(p) as doc:
        page=doc[0];page.draw_line((25,50),(60,30),color=(0,))
        page.draw_rect((30,45,32,47),color=(0,),fill=(0,))
        page.draw_line((60,20),(70,20),color=(0,));page.draw_rect((64,19,66,21),color=(0,),fill=(0,))
        page.draw_rect((58,16,85,26),color=(0,))
        p.write_bytes(doc.tobytes())
    sha=digest_file(p);s['chart_vector_layout']['source_sha256']=sha
    s['legend_review']={'present':True,'source_sha256':sha,'reason':'source legend','frame_rect':[58,16,85,26],'frame_path_indices':[11],
       'entries':[{'text_id':'legend1','series_path_index':7,'series_marker_index':8,'swatch_path_index':9,'swatch_marker_index':10}]}
    s['assets'][0]['text_replacements'].append({'target_text_id':'legend1','source_text':'A','source_bbox':[72,18,76,22]})
    s['texts'].append({'id':'legend1','text':'A','role':'legend-label','x':0,'y':0})
    from journal_pdf import source_icons
    from types import SimpleNamespace
    monkeypatch.setattr(source_icons,'prepare_icon',lambda *args,**kwargs:SimpleNamespace(data=p.read_bytes()))
    out,evidence=layout_vector_chart(s,reg,tmp_path,8)
    assert evidence['legend_bindings'][0]['text_id']=='legend1'
    assert next(t for t in out['texts'] if t['id']=='legend1')['text']=='A'
    s['legend_review']['entries'][0]['series_path_index']=0
    with pytest.raises(FigureError):layout_vector_chart(s,reg,tmp_path,8)


def test_legend_pixel_check_uses_local_coordinates_after_source_crop():
    from journal_pdf.chart_vector_legend import local_crop_box
    assert list(local_crop_box([40,60,60,80],[20,40,120,140],[100,200,300,400]))==pytest.approx([40,40,80,80])


def test_frameless_split_legend_accepts_bound_grid_but_rejects_data_ink(reg,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from journal_pdf import source_icons
    s=fixture(tmp_path);p=tmp_path/'source.pdf'
    with fitz.open(p) as doc:
        page=doc[0];page.draw_line((25,50),(60,30),color=(0,))
        page.draw_rect((30,45,32,47),color=(0,),fill=(0,))
        page.draw_line((60,20),(70,20),color=(0,));page.draw_rect((64,19,66,21),color=(0,),fill=(0,))
        page.draw_line((71,20),(90,20),color=(.8,.8,.8),width=.2)
        data=doc.tobytes()
    p.write_bytes(data);sha=digest_file(p);s['chart_vector_layout']['source_sha256']=sha
    s['legend_review']={'present':True,'source_sha256':sha,'reason':'native frameless split legend','frame_mode':'region-without-frame','frame_rect':[58,16,95,26],'frame_path_indices':[],'source_grid_path_indices':[11],
        'entries':[{'text_id':'legend1','text_ids':['legend1','legend2'],'series_path_index':7,'series_marker_index':8,'swatch_path_index':9,'swatch_marker_index':10}]}
    for ident,txt,x in [('legend1','A',72),('legend2','B',77)]:
        s['assets'][0]['text_replacements'].append({'target_text_id':ident,'source_text':txt,'source_bbox':[x,18,x+4,22]})
        s['texts'].append({'id':ident,'text':txt,'role':'legend-label','x':0,'y':0})
    monkeypatch.setattr(source_icons,'prepare_icon',lambda *a,**kw:SimpleNamespace(data=p.read_bytes()))
    _,evidence=layout_vector_chart(s,reg,tmp_path,8)
    assert evidence['legend_bindings'][0]['text_ids']==['legend1','legend2']
    with fitz.open(p) as doc:
        doc[0].draw_line((73,18),(73,22),color=(0,),width=.2);data=doc.tobytes()
    p.write_bytes(data);sha=digest_file(p);s['chart_vector_layout']['source_sha256']=sha;s['legend_review']['source_sha256']=sha
    with pytest.raises(FigureError,match='非网格图形'):layout_vector_chart(s,reg,tmp_path,8)


def test_legend_series_candidates_support_fragmented_curve(tmp_path):
    from journal_pdf.chart_vector_legend import propose_series_binding
    p=tmp_path/'fragmented.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=100)
        page.draw_line((20,50),(28,48),color=(.4,.4,.4))
        page.draw_line((28,48),(40,45),color=(.4,.4,.4))
        page.draw_rect((27,47,29,49),color=(.4,.4,.4),fill=(.4,.4,.4))
        page.draw_rect((39,44,41,46),color=(.4,.4,.4),fill=(.4,.4,.4))
        page.draw_line((65,20),(75,20),color=(.4,.4,.4))
        page.draw_rect((69,19,71,21),color=(.4,.4,.4),fill=(.4,.4,.4))
        doc.save(p)
    with fitz.open(p) as doc:
        candidate=propose_series_binding(doc[0].get_drawings(),4,5,[60,15,90,25],[10,30,55,60])
    assert candidate['series_path_index'] in (0,1)
    assert candidate['series_marker_index'] in (2,3)
    assert candidate['verified'] is False


def test_unbound_or_fake_tick_does_not_produce_layout(reg,tmp_path):
    s=fixture(tmp_path);s['chart_vector_layout']['x_ticks'][1]['point'][0]=35
    with pytest.raises(FigureError):layout_vector_chart(s,reg,tmp_path,8)


def test_corner_x_tick_automatically_moves_down_to_avoid_y_label(reg,tmp_path):
    s=fixture(tmp_path)
    for t,value in zip(s['texts'][:3],('0.5','5','9')):t['text']=value
    s['chart_vector_layout']['x_ticks'][0]['point']=[15,80]
    s['assets'][0]['text_replacements'][0]['source_bbox']=[14,81,16,82]
    out,evidence=layout_vector_chart(s,reg,tmp_path,8)
    assert evidence['corner_tick_adjustment_pt']>0
    x=next(t for t in out['texts'] if t['id']=='x1')
    y=next(t for t in out['texts'] if t['id']=='y0')
    assert x['y']>y['y']
    s=fixture(tmp_path);s['chart_vector_layout']['source_sha256']='0'*64
    with pytest.raises(FigureError):layout_vector_chart(s,reg,tmp_path,8)

def test_complete_vector_chart_render_applies_measured_layout(reg,tmp_path):
    import hashlib
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one
    source=tmp_path/'source';source.mkdir()
    spec=fixture(source);p=source/'source.pdf'
    doc=fitz.open(p);page=doc[0]
    for i,t in enumerate(spec['texts']):
        x,y=((29,84),(33,84),(37,84),(12,80),(12,65),(12,50),(45,90),(3,20))[i]
        page.insert_text((x,y),t['text'],fontsize=1.3,fontname='helv')
    data=doc.tobytes();doc.close();p.write_bytes(data)
    with fitz.open(p) as d:
        spans=[s for b in d[0].get_text('dict')['blocks'] if b['type']==0 for line in b['lines'] for s in line['spans']]
    for t,replacement in zip(spec['texts'],spec['assets'][0]['text_replacements']):
        span=next(s for s in spans if s['text']==t['text'])
        replacement.update(source_text=span['text'],source_bbox=list(span['bbox']))
    sha=hashlib.sha256(p.read_bytes()).hexdigest();spec['chart_vector_layout']['source_sha256']=sha;spec['legend_review']['source_sha256']=sha
    spec.update(version=1,id='fixture-chart',author='synthetic',kind='scene',sources=[{'path':'source.pdf','sha256':sha,'role':'original'}],policy={'column':'single','design_font_size_pt':8,'export_crop_padding_pt':4})
    assets=Assets()
    try:
        try:report=render_one(spec,reg,assets,source,tmp_path/'output')
        except FigureError as error:raise AssertionError((error.code,error.details)) from error
        assert report['pdf_audit']['chart_vector_layout']['passed']
        assert report['assets'][0]['source_path_multiset_preserved']
        assert report['layout']['layout_evidence']['chart_vector_layout']['x_tick_rotation']==90
    finally:assets.close()


def test_swapped_tick_label_cannot_be_bound_to_other_tick(reg,tmp_path):
    s=fixture(tmp_path)
    s['chart_vector_layout']['x_ticks'][0]['point'][0]=34
    with pytest.raises(FigureError) as error:layout_vector_chart(s,reg,tmp_path,8)
    assert error.value.code=='chart_vector_tick_binding'
