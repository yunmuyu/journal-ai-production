from pathlib import Path
import hashlib,json,sys
import fitz
from journal_pdf.chart_vector_legend import propose_series_binding

root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=True)
pdf=root/'source.pdf'
with fitz.open() as doc:
    page=doc.new_page(width=200,height=160)
    page.draw_line((30,110),(180,110));page.draw_line((30,110),(30,20))
    for x in (50,100,150):page.draw_line((x,110),(x,106))
    for y in (90,60,30):page.draw_line((30,y),(34,y))
    page.draw_polyline([(45,95),(100,75),(165,55)],color=(0,0,0))
    page.draw_rect((99,74,101,76),color=(0,0,0),fill=(0,0,0))
    page.draw_rect((164,54,166,56),color=(0,0,0),fill=(0,0,0))
    page.draw_rect((110,22,175,42),color=(0,0,0))
    page.draw_line((114,32),(126,32),color=(0,0,0))
    page.draw_rect((119,31,121,33),color=(0,0,0),fill=(0,0,0))
    for text,x,y in [('1',48,122),('2',98,122),('3',148,122),('1',18,93),('2',18,63),('3',18,33),('Time',87,140),('Rate',1,15),('S',132,35)]:page.insert_text((x,y),text,fontsize=8)
    doc.save(pdf)
sha=hashlib.sha256(pdf.read_bytes()).hexdigest()
with fitz.open(pdf) as doc:
    page=doc[0];spans=[s for b in page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']];drawings=page.get_drawings()
    roles=['axis-tick']*6+['axis-title','axis-title','legend-label'];ids=['x1','x2','x3','y1','y2','y3','xt','yt','legend1']
    texts=[{'id':i,'text':s['text'],'role':r,'x':0,'y':0,'size':8} for i,s,r in zip(ids,spans,roles)]
    replacements=[{'target_text_id':i,'source_text':s['text'],'source_bbox':list(s['bbox'])} for i,s in zip(ids,spans)]
    spec={'version':1,'id':'synthetic-chart','author':'fixture','kind':'scene','width_pt':200,'height_pt':160,'policy':{'column':'single','font_sizes':[8],'design_font_size_pt':8,'export_crop_padding_pt':4},'sources':[{'path':'source.pdf','sha256':sha,'role':'original'}],
      'assets':[{'id':'body','path':'source.pdf','source_kind':'pdf','page':0,'clip':[0,0,200,160],'target':[0,0,200,160],'source_vector_body':True,'text_replacements':replacements}],
      'texts':texts,'legend_review':{'present':True,'source_sha256':sha,'reason':'synthetic legend','frame_rect':[110,22,175,42],'frame_path_indices':[11],'entries':[{'text_id':'legend1','swatch_path_index':12,'swatch_marker_index':13}]},
      'chart_vector_layout':{'body_id':'body','source_sha256':sha,'axis_origin':[30,110],'x_axis_end':[180,110],'y_axis_end':[30,20],'x_ticks':[{'id':i,'point':[x,110]} for i,x in zip(ids[:3],(50,100,150))],'y_ticks':[{'id':i,'point':[30,y]} for i,y in zip(ids[3:6],(90,60,30))],'x_title_id':'xt','y_title_id':'yt'}}
    (root/'template.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf8')
    candidate=propose_series_binding(drawings,12,13,[110,22,175,42],[30,20,180,110])
    (root/'candidates.json').write_text(json.dumps({'status':'needs_review','source':str(pdf),'sourceSha256':sha,'candidates':[candidate]}),encoding='utf8')
