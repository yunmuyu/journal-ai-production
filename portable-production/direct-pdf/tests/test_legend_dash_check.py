import pytest

from journal_pdf.layouts import primitive
from journal_pdf.scene import audit_scene


@pytest.mark.parametrize('length,dash,expected', [(10,[2,1.5],False),(16,[2,1.5],True),(16,[],False)])
def test_dashed_legend_sample_needs_visible_uncovered_line(reg,length,dash,expected):
    spec={'width_pt':100,'height_pt':60,
          'nodes':[{'id':'symbol','shape':'rectangle','rect':[22,19,25,22],'fill':0}],
          'paths':[{'id':'legend','points':[[20,20],[20+length,20]],'dash':dash,'semantic_role':'data-annotation'}],
          'legend_dash_checks':[{'path_id':'legend'}]}
    scene=primitive(spec,reg,8)
    issues=audit_scene(scene)
    evidence=scene.layout_evidence['legend_dash_checks'][0]
    assert evidence['mechanical_check_passed'] is expected
    assert any(i['code']=='legend_dash_sample_too_short' for i in issues) is not expected
    assert evidence['uncovered_length_pt']==length-3


@pytest.mark.parametrize('dash,gray,expected',[([4,2],.25,True),([3,2],.25,False),([4,2],0,False)])
def test_scene_legend_must_match_declared_curve_style(reg,dash,gray,expected):
    spec={'width_pt':100,'height_pt':60,'nodes':[],
          'paths':[{'id':'curve','points':[[10,10],[30,30]],'dash':[4,2],'gray':.25,'semantic_role':'data-annotation'},
                   {'id':'legend','points':[[60,10],[80,10]],'dash':dash,'gray':gray,'semantic_role':'data-annotation'}],
          'legend_series_checks':[{'series_path_id':'curve','swatch_path_id':'legend'}]}
    scene=primitive(spec,reg,8)
    issues=audit_scene(scene)
    assert scene.layout_evidence['legend_series_checks'][0]['line_style_matches'] is expected
    assert any(i['code']=='legend_series_style_mismatch' for i in issues) is not expected
