import pytest
from journal_pdf.common import FigureError
from journal_pdf.layouts import primitive
from journal_pdf.scene import audit_scene


def spec():
    return {'width_pt':80,'height_pt':60,
            'nodes':[{'id':'marker','shape':'ellipse','rect':[14,19,16,21],'fill':0}],
            'paths':[{'id':'swatch','points':[[10,20],[30,20]],'dash':[4,2],'semantic_role':'legend-swatch'}],
            'legend_marker_centers':[{'sample_path_id':'swatch','marker_node_id':'marker'}]}


def test_default_centers_the_marker_without_changing_line_style(reg):
    scene=primitive(spec(),reg,8);node=scene.nodes[0]
    assert (node['rect'][0]+node['rect'][2])/2==pytest.approx(20.)
    assert scene.paths[0]['dash']==[4,2]
    audit_scene(scene)
    assert scene.layout_evidence['legend_marker_centers'][0]['offset_pt']==pytest.approx(0)


def test_original_position_may_be_kept_with_reason_and_review(reg):
    data=spec();data['legend_marker_centers'][0].update(apply=False,reason='原图特殊组合')
    scene=primitive(data,reg,8)
    assert (scene.nodes[0]['rect'][0]+scene.nodes[0]['rect'][2])/2==pytest.approx(15.)
    audit_scene(scene)
    assert any(n['code']=='legend_marker_alignment_review' for n in scene.notes)


def test_moving_marker_with_owned_text_or_without_reason_is_rejected(reg):
    data=spec();data['legend_marker_centers'][0]['apply']=False
    with pytest.raises(FigureError):primitive(data,reg,8)
    data=spec();data['nodes'][0]['text']='甲'
    with pytest.raises(FigureError):primitive(data,reg,8)
