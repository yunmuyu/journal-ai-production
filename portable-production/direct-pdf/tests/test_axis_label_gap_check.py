import pytest
from journal_pdf.layouts import primitive
from journal_pdf.scene import audit_scene
from journal_pdf.editorial import scale_scene


def test_axis_title_gap_is_measured_from_tick_ink(reg):
    spec={'width_pt':140,'height_pt':100,'nodes':[],'paths':[],
          'texts':[{'id':'tick','text':'0.95','x':40,'y':40},
                   {'id':'title','text':'Axis','x':40,'y':60}]}
    scene=primitive(spec,reg,8)
    tick,title=scene.texts
    current=title['position']['bbox'][1]-tick['position']['bbox'][3]
    spec['texts'][1]['y']+=3-current
    spec['axis_label_gap_checks']=[{'title_id':'title','tick_ids':['tick']}]
    scene=primitive(spec,reg,8)
    assert not any(i['code']=='axis_label_gap_mismatch' for i in audit_scene(scene))
    assert abs(scene.layout_evidence['axis_label_gap_checks'][0]['gap_pt']-3)<.01
    spec['texts'][1]['y']+=4
    scene=primitive(spec,reg,8)
    assert any(i['code']=='axis_label_gap_mismatch' for i in audit_scene(scene))


def test_legend_bottom_gap_uses_last_text_ink(reg):
    spec={'width_pt':140,'height_pt':100,'nodes':[],
          'paths':[{'id':'frame','points':[[10,10],[100,10],[100,50],[10,50],[10,10]],'semantic_role':'decorative'}],
          'texts':[{'id':'label','text':'Legend','x':35,'y':30}]}
    scene=primitive(spec,reg,8)
    desired=scene.texts[0]['position']['bbox'][3]+3
    spec['paths'][0]['points']=[[10,10],[100,10],[100,desired],[10,desired],[10,10]]
    spec['legend_frame_gap_checks']=[{'frame_id':'frame','text_ids':['label']}]
    scene=primitive(spec,reg,8)
    assert not any(i['code']=='legend_frame_gap_mismatch' for i in audit_scene(scene))
    assert abs(scene.layout_evidence['legend_frame_gap_checks'][0]['gap_pt']-3)<.01
    spec['paths'][0]['points'][2][1]+=4;spec['paths'][0]['points'][3][1]+=4
    scene=primitive(spec,reg,8)
    assert any(i['code']=='legend_frame_gap_mismatch' for i in audit_scene(scene))


def test_legend_right_gap_uses_longest_actual_ink(reg):
    spec={'kind':'scene','width_pt':120,'height_pt':70,'nodes':[],
          'paths':[{'id':'frame','points':[[10,10],[110,10],[110,50],[10,50],[10,10]],'semantic_role':'decorative'}],
          'texts':[{'id':'short','text':'Short','x':20,'y':20,'align':'left'},
                   {'id':'long','text':'Long legend text','x':20,'y':35,'align':'left'}]}
    scene=primitive(spec,reg,8)
    right=max(t['position']['bbox'][2] for t in scene.texts)+4.5+.25
    spec['paths'][0]['points']=[[10,10],[right,10],[right,50],[10,50],[10,10]]
    spec['legend_frame_gap_checks']=[{'frame_id':'frame','text_ids':['short','long'],'side':'right','gap_pt':4.5}]
    scene=primitive(spec,reg,8)
    assert not any(i['code']=='legend_frame_gap_mismatch' for i in audit_scene(scene))
    assert abs(scene.layout_evidence['legend_frame_gap_checks'][0]['gap_pt']-4.5)<.01
    spec['paths'][0]['points'][1][0]+=5;spec['paths'][0]['points'][2][0]+=5
    assert any(i['code']=='legend_frame_gap_mismatch' for i in audit_scene(primitive(spec,reg,8)))


def test_vertical_axis_gap_is_measured_between_actual_ink_edges(reg):
    spec={'width_pt':140,'height_pt':100,'nodes':[],'paths':[],
          'texts':[{'id':'tick','text':'0.95','x':60,'y':40},
                   {'id':'title','text':'Rate','x':25,'y':40,'rotation':90}]}
    scene=primitive(spec,reg,8);tick,title=scene.texts
    current=tick['position']['bbox'][0]-title['position']['bbox'][2]
    spec['texts'][1]['x']+=current-3
    spec['axis_label_gap_checks']=[{'title_id':'title','tick_ids':['tick'],'side':'left'}]
    scene=primitive(spec,reg,8)
    assert not any(i['code']=='axis_label_gap_mismatch' for i in audit_scene(scene))
    assert abs(scene.layout_evidence['axis_label_gap_checks'][0]['gap_pt']-3)<.01
    spec['texts'][1]['x']-=5
    scene=primitive(spec,reg,8)
    assert any(i['code']=='axis_label_gap_mismatch' for i in audit_scene(scene))


def test_tick_clearance_measures_from_butt_cap_to_text_ink(reg):
    spec={'width_pt':140,'height_pt':100,'nodes':[],
          'paths':[{'id':'tickmark','points':[[70,30],[70,33]],'semantic_role':'data-annotation'}],
          'texts':[{'id':'tick','text':'0.95','x':70,'y':45}],
          'axis_tick_gap_checks':[{'path_id':'tickmark','text_id':'tick','side':'bottom'}]}
    scene=primitive(spec,reg,8);current=scene.texts[0]['position']['bbox'][1]-33
    spec['texts'][0]['y']+=2.5-current
    scene=primitive(spec,reg,8)
    assert not any(i['code']=='axis_tick_gap_mismatch' for i in audit_scene(scene))
    assert abs(scene.layout_evidence['axis_tick_gap_checks'][0]['gap_pt']-2.5)<.01
    spec['texts'][0]['y']+=3
    scene=primitive(spec,reg,8)
    assert any(i['code']=='axis_tick_gap_mismatch' for i in audit_scene(scene))


def test_right_side_colorbar_title_gap(reg):
    spec={'width_pt':140,'height_pt':100,'nodes':[],'paths':[],
          'texts':[{'id':'tick','text':'100','x':80,'y':40},
                   {'id':'title','text':'Rate','x':120,'y':40,'rotation':90}],
          'axis_label_gap_checks':[{'title_id':'title','tick_ids':['tick'],'side':'right'}]}
    scene=primitive(spec,reg,8);tick,title=scene.texts
    gap=title['position']['bbox'][0]-tick['position']['bbox'][2]
    spec['texts'][1]['x']+=3-gap
    scene=primitive(spec,reg,8)
    assert not any(i['code']=='axis_label_gap_mismatch' for i in audit_scene(scene))
    spec['texts'][1]['x']-=2
    scene=primitive(spec,reg,8)
    assert any(i['code']=='axis_label_gap_mismatch' for i in audit_scene(scene))


def test_right_colorbar_tick_gap_uses_outer_stroke(reg):
    spec={'width_pt':140,'height_pt':100,'nodes':[],
          'paths':[{'id':'mark','points':[[70,30],[72,30]],'semantic_role':'data-annotation'}],
          'texts':[{'id':'tick','text':'100','x':90,'y':30}],
          'axis_tick_gap_checks':[{'path_id':'mark','text_id':'tick','side':'right'}]}
    scene=primitive(spec,reg,8);gap=scene.texts[0]['position']['bbox'][0]-72
    spec['texts'][0]['x']+=2.5-gap
    scene=primitive(spec,reg,8)
    assert not any(i['code']=='axis_tick_gap_mismatch' for i in audit_scene(scene))
    spec['texts'][0]['x']-=2
    scene=primitive(spec,reg,8)
    assert any(i['code']=='axis_tick_gap_mismatch' for i in audit_scene(scene))


def test_axis_ink_gaps_scale_with_whole_artwork(reg):
    spec={'width_pt':140,'height_pt':100,'nodes':[],
          'paths':[{'id':'mark','points':[[70,30],[70,33]],'semantic_role':'decorative'}],
          'texts':[{'id':'tick','text':'10','x':70,'y':42}, {'id':'title','text':'Time','x':70,'y':60}],
          'axis_tick_gap_checks':[{'path_id':'mark','text_id':'tick','side':'bottom'}],
          'axis_label_gap_checks':[{'title_id':'title','tick_ids':['tick']}]}
    initial=primitive(spec,reg,8);tick,title=initial.texts
    spec['texts'][0]['y']+=35.5-tick['position']['bbox'][1]
    initial=primitive(spec,reg,8);tick,title=initial.texts
    spec['texts'][1]['y']+=tick['position']['bbox'][3]+3-title['position']['bbox'][1]
    scene=scale_scene(primitive(spec,reg,8),.8)
    issues=audit_scene(scene)
    assert not any(i['code'] in ('axis_tick_gap_mismatch','axis_label_gap_mismatch') for i in issues)
    assert scene.layout_evidence['axis_tick_gap_checks'][0]['gap_pt']==pytest.approx(2)
    assert scene.layout_evidence['axis_label_gap_checks'][0]['gap_pt']==pytest.approx(2.4)
def test_new_ticks_check_confirmed_length_without_affecting_source_ticks(reg):
    from journal_pdf.scene import Scene,audit_scene
    scene=Scene(reg,8).finish(100,100)
    scene.line('new-tick',[[30,30],[30,32.5]],semantic_role='decorative')
    scene.line('source-tick',[[40,30],[40,34]],semantic_role='decorative')
    scene.new_tick_length_checks=[{'path_id':'new-tick','length_pt':2.5,'reason':None}]
    issues=audit_scene(scene)
    assert not any(i['code']=='new_tick_length_mismatch' for i in issues)
    scene.paths[0]['points'][1][1]=33
    assert any(i['code']=='new_tick_length_mismatch' for i in audit_scene(scene))


def test_new_tick_spec_default_and_documented_exception(reg):
    from journal_pdf.layouts import primitive
    from journal_pdf.common import FigureError
    spec={'kind':'scene','width_pt':40,'height_pt':40,
          'paths':[{'id':'tick','points':[[10,10],[10,12.5]],'semantic_role':'decorative'}],
          'new_tick_length_checks':[{'path_id':'tick'}]}
    scene=primitive(spec,reg,8)
    assert scene.new_tick_length_checks[0]['length_pt']==2.5
    spec['new_tick_length_checks'][0]['length_pt']=3
    with pytest.raises(FigureError):primitive(spec,reg,8)
    spec['new_tick_length_checks'][0]['reason']='避免刻度与原图元素重叠'
    assert primitive(spec,reg,8).new_tick_length_checks[0]['reason']
