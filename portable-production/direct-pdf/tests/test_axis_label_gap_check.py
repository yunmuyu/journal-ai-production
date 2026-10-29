from journal_pdf.layouts import primitive
from journal_pdf.scene import audit_scene


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
