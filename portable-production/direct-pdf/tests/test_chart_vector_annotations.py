import fitz
import pytest
import json
from journal_pdf.chart_vector_annotations import place_annotations
from journal_pdf.common import FigureError


def test_annotation_is_bound_to_real_source_text_and_avoids_curve(reg,tmp_path):
    path=tmp_path/'source.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=100)
        page.insert_text((48,45),'A',fontsize=8)
        page.draw_line((30,43),(70,43),width=.5)
        span=page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        bbox=list(span['bbox']);doc.save(path)
    body={'page':0,'text_replacements':[{'source_text':'A','source_bbox':bbox,'target_text_id':'a'}]}
    text={'a':{'text':'A'}}
    rows=[{'parts':[{'id':'a'}],'evidence':'原图真实标注'}]
    evidence=place_annotations(rows,text,body,path,reg,8,[0,0,100,100],[0,0,100,100],[10,90],[90,90],[10,10])
    assert evidence[0]['offset_pt']!=[0,0]
    assert text['a']['x']>10 and text['a']['y']<90
    text['a']['text']='B'
    with pytest.raises(FigureError,match='原图不一致'):
        place_annotations(rows,text,body,path,reg,8,[0,0,100,100],[0,0,100,100],[10,90],[90,90],[10,10])


def test_final_pdf_with_source_bound_annotation(reg,tmp_path):
    from journal_pdf.assets import Assets
    from journal_pdf.common import digest_file
    from journal_pdf.render import render_one
    root=tmp_path/'input';root.mkdir();path=root/'chart.pdf'
    with fitz.open() as doc:
        p=doc.new_page(width=120,height=120)
        p.draw_line((20,90),(100,90));p.draw_line((20,90),(20,15));p.draw_line((30,75),(90,40))
        for x in (40,65,90):p.draw_line((x,90),(x,86))
        for y in (75,55,35):p.draw_line((20,y),(24,y))
        items=[('x1','1',38,98),('x2','2',63,98),('x3','3',88,98),('y1','1',10,77),('y2','2',10,57),('y3','3',10,37),('xt','Time',50,111),('yt','Value',1,25),('note','cross',50,32)]
        for _,text,x,y in items:p.insert_text((x,y),text,fontsize=4)
        spans=[s for b in p.get_text('dict')['blocks'] if b['type']==0 for line in b['lines'] for s in line['spans']]
        replacements=[]
        for ident,value,x,y in items:
            match=min((s for s in spans if s['text']==value),key=lambda s:abs(s['bbox'][0]-x)+abs(s['bbox'][3]-y))
            replacements.append({'target_text_id':ident,'source_text':value,'source_bbox':list(match['bbox'])})
        doc.save(path)
    sha=digest_file(path)
    texts=[{'id':ident,'text':value,'role':('label' if ident=='note' else 'axis-title' if ident in ('xt','yt') else 'axis-tick'),'x':0,'y':0} for ident,value,_,_ in items]
    texts[-1]['text']=[{'text':'cross','scale':.7}]
    spec={'version':1,'id':'annotation-synthetic','author':'test','synthetic':True,'kind':'scene','width_pt':240,'height_pt':240,
          'sources':[{'path':'chart.pdf','sha256':sha}],'texts':texts,'nodes':[],'paths':[],
          'assets':[{'id':'body','path':'chart.pdf','page':0,'source_kind':'pdf','source_vector_body':True,'clip':[0,0,120,120],'target':[0,0,240,240],'text_replacements':replacements}],
          'legend_review':{'present':False,'source_sha256':sha,'reason':'synthetic source has no legend'},
          'chart_vector_layout':{'body_id':'body','source_sha256':sha,'axis_origin':[20,90],'x_axis_end':[100,90],'y_axis_end':[20,15],
          'x_ticks':[{'id':i,'point':[x,90]} for i,x in [('x1',40),('x2',65),('x3',90)]],
          'y_ticks':[{'id':i,'point':[20,y]} for i,y in [('y1',75),('y2',55),('y3',35)]],
          'x_title_id':'xt','y_title_id':'yt','annotations':[{'parts':[{'id':'note','offset_y_pt':2}],'evidence':'source text'}]},
          'policy':{'column':'single','font_sizes':[8]}}
    assets=Assets()
    try:
        result=render_one(spec,reg,assets,root,tmp_path/'output')
        assert result
        report=json.loads((tmp_path/'output'/'test'/'annotation-synthetic'/'report.json').read_text(encoding='utf8'))
        assert report['pdf_audit']['chart_vector_layout']['annotations_verified']==1
    finally:assets.close()
