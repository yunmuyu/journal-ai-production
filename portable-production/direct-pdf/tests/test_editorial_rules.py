import copy,json,math
from pathlib import Path
import pytest,pymupdf as fitz
from journal_pdf.editorial import group_number,display_content,wrap_text,diamond_size,scale_scene,RULESET,ARROW_LENGTH,ARROW_BOUNDARY_GAP
from journal_pdf.scene import Scene,audit_scene,port
from journal_pdf.common import FigureError,PT_PER_MM
from journal_pdf.assets import Assets
from journal_pdf.render import compile_figure,render_one

@pytest.mark.parametrize('raw,want',[
 ('0.1000','0.100 0'),('0.0975','0.097 5'),('0.0950','0.095 0'),('0.0925','0.092 5'),
 ('1000','1 000'),('1200','1 200'),('0.073162','0.073 162'),
 ('-1234567.8901230','-1 234 567.890 123 0'),('−1000.0000','−1 000.000 0'),
 ('+1234.567890e-003','+1 234.567 890e-003'),('1 000.123 400','1 000.123 400'),
 ('0001234.000000','0 001 234.000 000'),('10','10'),('0.1','0.1'),('123','123'),('1234','1 234')])
def test_number_preserves_digits_sign_precision(raw,want):
 assert group_number(raw)==want
 assert group_number(want)==want
 assert raw.replace(' ','')==want.replace(' ','')

@pytest.mark.parametrize('label',['STM32F103','192.168.1.1','v1.2.3','2026-10-15','GB/T 7714','1.建模分析'])
def test_non_numeric_identifiers_untouched(label):
 assert display_content(label)==label
 with pytest.raises(FigureError):group_number(label)

@pytest.mark.parametrize('source,expected',[
 ('否 (继续监听)','否（继续监听）'),
 ('否 (等待重连)','否（等待重连）'),
 ('与后端进行持续通信\n(监听消息并发送短信)','与后端进行持续通信\n（监听消息并发送短信）'),
 ('连接是否成功?','连接是否成功？'),
 ('是否获取到后端 IP?','是否获取到后端 IP？'),
 ('创建 Map 集合\n{phone, msg}','创建 Map 集合\n{phone, msg}'),
 ('发送至主题：\n/topic/sms-send','发送至主题：\n/topic/sms-send'),
 ('Map ⮕ JSON 字符串','Map → JSON 字符串'),
 ('函数 f(x)','函数 f(x)'),
])
def test_chinese_prose_punctuation_keeps_technical_literals(source,expected):
 assert display_content(source)==expected

@pytest.mark.parametrize('source,expected',[
 ('用户交互\n层','用户\n交互层'),
 ('蓝牙通信\n层','蓝牙\n通信层'),
 ('设备\n层','设备层'),
 ('Bluetooth\nAdapter','Bluetooth\nAdapter'),
])
def test_manual_cjk_breaks_do_not_leave_one_character_line(source,expected):
 assert display_content(source)==expected

def test_latin_wrap_prefers_words_and_marks_word_internal_breaks():
 assert wrap_text('media layer',6)=='media\nlayer'
 assert wrap_text('media',4)=='med-\nia'

def test_graph_uses_local_label_gap_and_exact_unlabeled_arrow5_shaft(reg):
 from journal_pdf.graph_layout import graph
 spec={'nodes':[{'id':x,'text':x,'shape':'terminator' if x in ('a','d') else 'rectangle'} for x in 'abcd'],
       'edges':[{'id':'ab','from':'a','to':'b'},
                {'id':'bc','from':'b','to':'c','label':'是'},
                {'id':'cd','from':'c','to':'d'}]}
 s=graph(spec,reg,8);nodes={n['id']:n for n in s.nodes}
 gaps=[nodes[b]['rect'][1]-nodes[a]['rect'][3] for a,b in [('a','b'),('b','c'),('c','d')]]
 assert gaps[0]==pytest.approx(ARROW_BOUNDARY_GAP)
 assert gaps[2]==pytest.approx(ARROW_BOUNDARY_GAP)
 assert gaps[1]>ARROW_BOUNDARY_GAP
 assert gaps[0]==pytest.approx(ARROW_LENGTH)
 assert nodes['a']['kind']=='terminator' and nodes['d']['kind']=='terminator'

def test_graph_input_output_remains_native_shape(reg):
 from journal_pdf.graph_layout import graph
 s=graph({'nodes':[{'id':'a','text':'输入','shape':'terminator'},
                   {'id':'b','text':'输出数据','shape':'inputOutput'}],
          'edges':[{'from':'a','to':'b'}]},reg,8)
 assert [n['kind'] for n in s.nodes]==['terminator','inputOutput']
 assert not audit_scene(s)

def test_graph_branch_buses_keep_real_arrow5_shaft_and_one_merge_arrow(reg):
 from journal_pdf.graph_layout import graph
 spec={'nodes':[{'id':'source','text':'分叉'},
                {'id':'left','text':'左支'},
                {'id':'right','text':'右支'},
                {'id':'target','text':'汇合'}],
       'edges':[{'id':'fan-left','from':'source','to':'left'},
                {'id':'fan-right','from':'source','to':'right'},
                {'id':'merge-left','from':'left','to':'target'},
                {'id':'merge-right','from':'right','to':'target'}]}
 s=graph(spec,reg,8)
 branch_gap=ARROW_LENGTH+2*PT_PER_MM
 assert s.layout_evidence['rank_gaps_pt']==pytest.approx({0:branch_gap,1:branch_gap})
 arrow_paths=[p for p in s.paths if p['arrow']]
 terminal_segments=[(tuple(p['points'][-2]),tuple(p['points'][-1])) for p in arrow_paths]
 assert len(arrow_paths)==3
 assert len(terminal_segments)==len(set(terminal_segments))
 assert all(math.dist(*segment)>=ARROW_LENGTH-1e-5 for segment in terminal_segments)
 assert not any(i['code']=='arrow_terminal_length' for i in audit_scene(s))

def test_arrow_audit_checks_actual_external_terminal_segment(reg):
 short=Scene(reg,8);short.line('external',[[2,10],[20,10],[20,14.5]],arrow=True);short.finish(30,30)
 issues=audit_scene(short)
 issue=next(i for i in issues if i['code']=='arrow_terminal_length')
 assert issue['id']=='external'
 assert issue['actual_pt']==pytest.approx(4.5)
 assert issue['required_pt']==pytest.approx(ARROW_LENGTH)
 exact=Scene(reg,8);exact.line('external',[[2,10],[20,10],[20,10+ARROW_LENGTH]],arrow=True);exact.finish(35,35)
 assert not any(i['code']=='arrow_terminal_length' for i in audit_scene(exact))

def test_right_return_label_has_real_page_margin(reg):
 from journal_pdf.graph_layout import graph
 s=graph({'nodes':[{'id':'a','text':'连接','shape':'rectangle'},
                   {'id':'b','text':'连接是否成功？','shape':'diamond'}],
          'edges':[{'from':'a','to':'b'},
                   {'id':'retry','from':'b','to':'a','return_edge':True,
                    'from_port':'right','to_port':'right','label':'否 (等待重连)'}]},reg,8)
 label=next(t for t in s.texts if t['id']=='retry:label')
 assert label['measurement']['text']=='否（等待重连）'
 assert label['position']['bbox'][2]<s.width
 assert not audit_scene(s)

def test_explicit_numeric_run_only(reg):
 original=[{'text':'型号 STM32F103：'},{'text':'1234.567890','role':'number'}]
 m=reg.measure(original,8)
 assert m['text']=='型号 STM32F103：1 234.567 890'
 assert original[1]['text']=='1234.567890'

@pytest.mark.parametrize('w,h,size',[(8,7,6),(37,18,6.5),(64,7,7),(25,40,8),(36,7.2,8)])
def test_diamond_matches_formal_adapter_not_root_multiplier(w,h,size):
 W,H,ev=diamond_size(w,h,size);scale=size/8
 a=w*.85+2*scale;b=h*.8+2*scale
 correction=max(1,w/(2*(a-scale))+h/(2*(b-scale)))
 assert W==pytest.approx(2*a*correction) and H==pytest.approx(2*b*correction)
 assert w/W+h/H<=1
 assert ev['source']=='production-runtime/adobe/editorial-generator.jsx'

def test_ordinary_padding_cannot_pass_only_noncollision(reg):
 s=Scene(reg,8);m=reg.measure('测试',8)
 s.box('n','测试',5,5,m['width']+2,m['height']+2);s.finish(60,60)
 assert any(x['code']=='node_text_padding' for x in audit_scene(s))

def test_whole_scale_copies_measurements_and_keeps_final_stroke(reg):
 m=reg.measure('测试',8);old=copy.deepcopy(m)
 s=Scene(reg,8);s.box('n','测试',10,10);s.line('p',[[1,1],[40,1]],arrow=True);s.finish(50,40)
 scale_scene(s,.8)
 assert m==old
 assert s.size==pytest.approx(6.4)
 assert s.nodes[0]['width']==.5 and s.paths[0]['width']==.5
 assert s.paths[0]['arrow_scale']==1
 assert s.texts[0]['measurement']['size']==pytest.approx(6.4)

def test_fractional_fit_not_legacy_font_ladder(reg,tmp_path):
 spec={'kind':'scene','nodes':[{'id':'n','text':'测试'}],
       'measured_groups':[{'id':'measured','axis':'row','origin':[110,10],'nodes':['n']}],
       'width_pt':260,'height_pt':60,'policy':{'column':'single','font_sizes':[8,7,6]}}
 a=Assets()
 try:
  s=compile_figure(spec,reg,a,tmp_path)
  assert 6<s.size<8 and s.size not in (6,7,8)
  assert s.nodes[0]['width']==.5
  assert s.layout_evidence['whole_artwork_scale']<1
 finally:a.close()

def test_fractional_fit_reflows_exact_arrows_at_final_three_mm(reg,tmp_path):
 spec={'kind':'graph','nodes':[{'id':'a','text':'较长的开始处理节点文字开始处理'},{'id':'b','text':'较长的后续处理节点文字后续处理'}],
       'edges':[{'from':'a','to':'b'}],'width_pt':260,'height_pt':60,
       'direction':'LR','policy':{'column':'single','design_font_size_pt':8}}
 a=Assets()
 try:
  s=compile_figure(spec,reg,a,tmp_path)
  path=next(p for p in s.paths if p['arrow'])
  assert s.size<8
  assert math.dist(path['points'][-2],path['points'][-1])==pytest.approx(ARROW_LENGTH)
  assert path['arrow_scale']==1
  assert not any(i['code'].startswith('arrow_terminal_') for i in audit_scene(s))
 finally:a.close()

def test_fractional_rebuild_preserves_verified_fixed_source_binding(reg,tmp_path,monkeypatch):
 import journal_pdf.render as render_module
 from journal_pdf.scene import Scene
 digest='b'*64
 def build(spec,registry,size):
  scene=Scene(registry,size);scene.template='synthetic-responsive-fixed'
  node=scene.shape('viewport',[5,5,90,35]);node['role']='source-locked-viewport'
  node['measurement_contract']={'mode':'fixed','fixed_size':{'purpose':'source-locked-viewport',
    'evidence':{'constraint':'source-artwork-bounds','source_id':'source.svg','source_sha256':digest}}}
  scene.text('viewport-text','源图视口',47.5,20,owner='viewport')
  scene.line('fit-trigger',[[5,45],[5+ARROW_LENGTH,45]],arrow=True,exact_terminal=True,semantic_role='decorative')
  return scene.finish(size*30,55)
 monkeypatch.setitem(render_module.DIAGRAMS,'synthetic-responsive-fixed',build)
 scene=compile_figure({'kind':'synthetic-responsive-fixed','policy':{'column':'single','design_font_size_pt':8}},
                      reg,None,tmp_path,verified_sources={'source.svg':digest})
 assert scene.layout_evidence['layout_build_count']>1
 assert scene.verified_source_bindings=={'source.svg':digest}
 assert scene.source_root==tmp_path
 assert not any(i['code'].startswith('primitive_box_measurement') for i in audit_scene(scene))

def test_under_6pt_requires_reflow_not_auto_double(reg,tmp_path):
 spec={'kind':'scene','nodes':[{'id':'n','text':'测试','rect':[10,10,50,40]}],
       'width_pt':400,'height_pt':60,'policy':{'column':'auto','font_sizes':[8,7,6]}}
 a=Assets()
 try:
  with pytest.raises(FigureError) as e:compile_figure(spec,reg,a,tmp_path)
  assert e.value.code=='layout_reflow_required'
 finally:a.close()

def test_synthetic_numeric_pdf_actual_spaces_and_black_strokes(reg,tmp_path):
 spec={'id':'numeric-rules','author':'Synthetic','synthetic':True,'kind':'scene','width_pt':125,'height_pt':50,
  'texts':[{'id':'txt','text':[{'text':'0.1000','role':'number'}],'x':50,'y':20}],
  'paths':[{'id':'p','points':[[5,40],[120,40]]}], 'policy':{'column':'single'}}
 src=tmp_path/'sources';src.mkdir();a=Assets()
 try:
  r=render_one(spec,reg,a,src,tmp_path/'out');d=fitz.open(tmp_path/'out'/r['output_pdf'])
  assert '0.100 0' in d[0].get_text()
  assert r['pdf_audit']['effective_path_strokes_05pt'] and r['pdf_audit']['editable_text_pure_black']
  assert r['layout']['layout_evidence']['export_crop']['rescaled'] is False
  assert not r['ready_for_publication']
 finally:a.close()

def test_summary_identity_band_keeps_size_and_complete_id(reg,tmp_path,simple_spec):
 from journal_pdf.batch import make_summary
 src=tmp_path/'src';src.mkdir();a=Assets();out=tmp_path/'out'
 try:
  r=render_one(simple_spec,reg,a,src,out)
  name=make_summary([r],out,reg);d=fitz.open(out/name);single=fitz.open(out/r['output_pdf'])
  assert simple_spec['id'] in d[0].get_text()
  ev=json.loads((out/'summary-audit.json').read_text())['pages'][0]
  rect=fitz.Rect(ev['target_rect_pt'])
  assert rect.width==pytest.approx(single[0].rect.width) and rect.height==pytest.approx(single[0].rect.height)
  assert ev['label_font_size_pt']==7 and ev['figure_scale']==1
  assert d[0].rect.height>single[0].rect.height
 finally:a.close()


def test_oversized_old_diamond_is_not_accepted_as_merely_noncolliding(reg):
 m=reg.measure('符合预期？',8);s=Scene(reg,8)
 s.box('d','符合预期？',5,5,2*(m['width']+9),2*(m['height']+5.4),'diamond');s.finish(140,80)
 assert any(i['code']=='diamond_calibration_mismatch' for i in audit_scene(s))

def test_old_engine_report_cannot_reuse_approval(profile,tmp_path):
 from journal_pdf.server import validate_review_identity
 with pytest.raises(FigureError) as e:validate_review_identity({},tmp_path/'batch.json',{},[],profile)
 assert e.value.code=='review_rules_changed'

def test_fractional_manual_override(simple_spec):
 from journal_pdf.server import apply_changes
 s=apply_changes(simple_spec,{'font_size':'6.4'})
 assert s['policy']['design_font_size_pt']==6.4

def test_primitive_defaults_to_straight_measured_ordinary_boxes(reg):
 from journal_pdf.layouts import primitive
 spec={'width_pt':80,'height_pt':50,
       'nodes':[{'id':'ordinary','text':'功能','shape':'roundrect','rect':[5,5,35,25]},
                {'id':'semantic','text':'特殊','shape':'roundrect','semantic_shape':True,'rect':[40,5,75,25]}]}
 scene=primitive(spec,reg,8)
 assert scene.nodes[0]['kind']=='rectangle'
 assert scene.nodes[0]['padding_pt']==[4.5,2.7]
 assert scene.nodes[1]['kind']=='roundrect'

def test_primitive_connection_requires_exact_three_mm_terminal(reg):
 from journal_pdf.layouts import primitive
 spec={'width_pt':80,'height_pt':50,
       'nodes':[{'id':'a','text':'甲','rect':[5,10,25,30]},
                {'id':'b','text':'乙','rect':[25+ARROW_LENGTH,10,45+ARROW_LENGTH,30]}],
       'connections':[{'id':'a-b','from':'a','from_port':'right','to':'b','to_port':'left','arrow':True}]}
 scene=primitive(spec,reg,8)
 assert not any(i['code'].startswith('arrow_terminal_') for i in audit_scene(scene))
 scene.paths[0]['points'][-2][0]-=1
 assert any(i['code']=='arrow_terminal_not_exact' for i in audit_scene(scene))

def test_primitive_raw_arrow_without_node_semantics_is_not_mechanically_covered(reg):
 from journal_pdf.layouts import primitive
 scene=primitive({'width_pt':100,'height_pt':40,
                  'paths':[{'id':'manual','points':[[5,20],[82,20]],'arrow':True}]},reg,8)
 assert any(i['code']=='arrow_endpoint_semantics_missing' for i in audit_scene(scene))

def test_primitive_raw_arrow_must_reach_declared_target_port(reg):
 from journal_pdf.layouts import primitive
 scene=primitive({'width_pt':180,'height_pt':70,
                  'nodes':[{'id':'origin','rect':[10,20,50,50]},
                           {'id':'destination','rect':[120,20,170,50]}],
                  'paths':[{'id':'manual','points':[[50,35],[125,35]],'arrow':True,
                            'endpoint_nodes':['origin','destination']}]},reg,8)
 assert any(i['code']=='arrow_endpoint_node_port_mismatch' for i in audit_scene(scene))

def test_primitive_raw_arrow_must_leave_declared_source_port(reg):
 from journal_pdf.layouts import primitive
 scene=primitive({'width_pt':180,'height_pt':70,
                  'nodes':[{'id':'origin','rect':[10,20,50,50]},
                           {'id':'destination','rect':[120,20,170,50]}],
                  'paths':[{'id':'manual','points':[[45,35],[120,35]],'arrow':True,
                            'endpoint_nodes':['origin','destination']}]},reg,8)
 assert any(i['code']=='arrow_endpoint_node_port_mismatch' and i['at_start']
            for i in audit_scene(scene))

def test_primitive_raw_arrow_cannot_claim_an_unrelated_target_node(reg):
 from journal_pdf.layouts import primitive
 scene=primitive({'width_pt':220,'height_pt':90,
                  'nodes':[{'id':'origin','rect':[10,20,50,50]},
                           {'id':'actual','rect':[120,20,170,50]},
                           {'id':'claimed','rect':[120,60,170,85]}],
                  'paths':[{'id':'manual','points':[[50,35],[120,35]],'arrow':True,
                            'endpoint_nodes':['origin','claimed']}]},reg,8)
 assert any(i['code']=='arrow_endpoint_node_port_mismatch' for i in audit_scene(scene))

def test_plain_legend_sample_is_not_a_business_arrow(reg):
 from journal_pdf.layouts import primitive
 scene=primitive({'width_pt':120,'height_pt':50,
                  'nodes':[{'id':'series','rect':[80,10,110,30]}],
                  'paths':[{'id':'legend-sample','points':[[10,20],[30,20]],
                            'endpoint_nodes':['series','series']}]},reg,8)
 assert not any(i['code'].startswith('arrow_endpoint_') for i in audit_scene(scene))

def test_primitive_connection_endpoint_audit_uses_generated_port(reg):
 from journal_pdf.layouts import primitive
 scene=primitive({'width_pt':180,'height_pt':70,
                  'nodes':[{'id':'origin','rect':[10,20,50,50]},
                           {'id':'destination','rect':[120,20,170,50]}],
                  'connections':[{'id':'generated','from':'origin','from_port':'right',
                                  'to':'destination','to_port':'left','arrow':True}]},reg,8)
 assert not any(i['code']=='arrow_endpoint_node_port_mismatch' for i in audit_scene(scene))
 scene.paths[0]['points'][-1][0]+=2
 assert any(i['code']=='arrow_endpoint_node_port_mismatch' for i in audit_scene(scene))

def test_long_elbow_arrow_keeps_flexible_terminal_length(reg):
 from journal_pdf.layouts import primitive
 scene=primitive({'width_pt':220,'height_pt':90,
                  'nodes':[{'id':'origin','rect':[10,20,50,50]},
                           {'id':'destination','rect':[170,40,215,70]}],
                  'paths':[{'id':'elbow','points':[[50,35],[100,35],[100,55],[170,55]],
                            'arrow':True,'endpoint_nodes':['origin','destination']}]},reg,8)
 assert not any(i['code'].startswith('arrow_terminal_') for i in audit_scene(scene))
 assert not any(i['code']=='arrow_endpoint_node_port_mismatch' for i in audit_scene(scene))

def test_declared_junction_must_touch_shared_path(reg):
 from journal_pdf.layouts import primitive
 scene=primitive({'width_pt':180,'height_pt':70,
                  'nodes':[{'id':'destination','rect':[120,6,170,36]}],
                  'paths':[{'id':'shared','points':[[10,20],[100,20]]},
                           {'id':'branch','points':[[50,21],[120,21]],'arrow':True,
                            'endpoint_nodes':[None,'destination']}]},reg,8)
 assert any(i['code']=='arrow_endpoint_node_port_mismatch' and i['at_start']
            for i in audit_scene(scene))

@pytest.mark.parametrize('endpoint_nodes',(['destination'],'destination'))
def test_arrow_endpoint_semantics_must_be_a_two_item_list(reg,endpoint_nodes):
 from journal_pdf.layouts import primitive
 scene=primitive({'width_pt':180,'height_pt':70,
                  'nodes':[{'id':'destination','rect':[120,20,170,50]}],
                  'paths':[{'id':'manual','points':[[50,35],[120,35]],'arrow':True,
                            'endpoint_nodes':endpoint_nodes}]},reg,8)
 assert any(i['code']=='arrow_endpoint_semantics_invalid' for i in audit_scene(scene))

def test_rich_runs_keep_explicit_math_semantics_and_true_baseline(reg):
 runs=[{'text':'D','style':'italic'},
       {'text':'4','scale':.7,'baseline_shift_pt':2.0},
       {'text':' GT'},
       {'text':'i','style':'italic','scale':.7,'baseline_shift_pt':2.0}]
 m=reg.measure(runs,8)
 assert m['glyphs'][0]['face']=='latin_italic'
 assert m['glyphs'][1]['face']=='latin' and m['glyphs'][1]['size']==pytest.approx(5.6)
 assert m['glyphs'][1]['y']==pytest.approx(2.0)
 assert m['glyphs'][-1]['face']=='latin_italic' and m['glyphs'][-1]['y']==pytest.approx(2.0)
