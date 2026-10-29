from types import SimpleNamespace
import pytest
from journal_pdf.confirmed_spacing import audit_confirmed_spacing,parse_confirmed_spacing,polygon_stroke_bounds,horizontal_stroke_bounds
from journal_pdf.common import FigureError


def scene(rule,first,second,side=None):
    check={'rule':rule,'first_id':'a','second_id':'b'}
    if side:check['side']=side
    return SimpleNamespace(size=8,nodes=first.get('nodes',[])+second.get('nodes',[]),
        paths=first.get('paths',[])+second.get('paths',[]),assets=first.get('assets',[])+second.get('assets',[]),
        texts=first.get('texts',[])+second.get('texts',[]),confirmed_spacing_checks=[check])


def node(identifier,rect):return {'nodes':[{'id':identifier,'rect':rect,'width':.5}]}
def label(identifier,rect):return {'texts':[{'id':identifier,'position':{'bbox':rect}}]}
def asset(identifier,rect):return {'assets':[{'id':identifier,'rect':rect}]}
def line(identifier):return {'paths':[{'id':identifier,'points':[[5,10],[15,10]],'width':.5,'endpoint_nodes':[]}]}


@pytest.mark.parametrize(('rule','first','second','side'),[
    ('legend_key_text',line('a'),label('b',[18,7,30,13]),None),
    ('legend_key_text',{'paths':[{'id':'a','points':[[5,5],[5,15],[10,15],[10,5]],'width':.5,'closed':True}]},
     label('b',[13.25,7,30,13]),None),
    ('image_grid_vertical',asset('a',[0,0,20,20]),asset('b',[0,24,20,44]),None),
    ('caption_lines',label('a',[0,0,20,8]),label('b',[0,11,20,19]),None),
    ('container_horizontal',node('a',[0,0,30,30]),node('b',[5,5,20,20]),'left'),
    ('title_to_frame',label('a',[0,0,20,8]),node('b',[0,11.25,20,20]),None),
    ('sibling_frames',node('a',[0,0,10,10]),node('b',[13,0,23,10]),'horizontal'),
    ('container_vertical',node('a',[0,0,30,30]),node('b',[5,3.5,20,20]),'top'),
])
def test_confirmed_defaults_match_actual_visible_edges(rule,first,second,side):
    result=audit_confirmed_spacing(scene(rule,first,second,side))
    assert not result['issues']
    assert result['checks'][0]['actual_pt']==pytest.approx(result['checks'][0]['expected_pt'])


def test_incorrect_gap_is_not_silently_accepted():
    result=audit_confirmed_spacing(scene('image_grid_vertical',asset('a',[0,0,20,20]),asset('b',[0,23,20,43])))
    assert result['issues'][0]['code']=='confirmed_spacing_mismatch'


def test_documented_exception_is_explicit_and_checked():
    instance=scene('image_grid_vertical',asset('a',[0,0,20,20]),asset('b',[0,23,20,43]))
    with pytest.raises(FigureError):
        parse_confirmed_spacing([{'rule':'image_grid_vertical','first_id':'a','second_id':'b','gap_pt':3}])
    instance.confirmed_spacing_checks=parse_confirmed_spacing([{'rule':'image_grid_vertical','first_id':'a',
          'second_id':'b','gap_pt':3,'reason':'内容无法装入版面'}])
    result=audit_confirmed_spacing(instance)
    assert not result['issues'] and result['checks'][0]['reason']=='内容无法装入版面'


def test_unaligned_objects_do_not_count_as_a_valid_pair():
    instance=scene('image_grid_vertical',asset('a',[0,0,20,20]),asset('b',[40,24,60,44]))
    assert audit_confirmed_spacing(instance)['issues'][0]['code']=='confirmed_spacing_alignment_invalid'


def test_triangle_miter_extends_past_half_stroke_width():
    bounds=polygon_stroke_bounds([[2.3,0],[0,4.2],[4.6,4.2]],.5)
    assert bounds[2]>4.6+.25


def test_dashed_sample_trailing_blank_is_not_ink():
    bounds=horizontal_stroke_bounds({'points':[[10,20],[30,20]],'width':.5,'dash':[6,1.5,1,1.5]})
    assert bounds[2]==pytest.approx(28.5)


def test_new_spacing_rules_check_actual_edges():
    rules=[
        ('container_title',node('a',[0,0,30,30]),label('b',[5,3.25,20,10]),'top'),
        ('image_row_label',label('a',[0,5,10,12]),asset('b',[16,0,30,20]),None),
        ('stage_arrow_before',node('a',[0,0,20,10]),{'paths':[{'id':'b','points':[[5,11.5],[15,11.5],[15,14],[5,14]],'closed':True,'width':.5}]},None),
        ('stage_arrow_after',{'paths':[{'id':'a','points':[[5,0],[15,0],[15,2.5],[5,2.5]],'closed':True,'width':.5}]},node('b',[0,4,20,14]),None),
    ]
    for rule,first,second,side in rules:
        parsed=parse_confirmed_spacing([{'rule':rule,'first_id':'a','second_id':'b',**({'side':side} if side else {})}])
        instance=scene(rule,first,second,side);instance.confirmed_spacing_checks=parsed
        assert not audit_confirmed_spacing(instance)['issues']


def test_connector_label_uses_nearest_relevant_line_stroke():
    path={'paths':[{'id':'a','points':[[0,0],[10,0],[10,20],[25,20]],'width':.5}]}
    check={'rule':'connector_label','first_id':'a','second_id':'b','side':'right'}
    instance=scene('connector_label',path,label('b',[13.25,7,20,14]))
    instance.confirmed_spacing_checks=parse_confirmed_spacing([check])
    result=audit_confirmed_spacing(instance)
    assert not result['issues']
    assert result['checks'][0]['actual_pt']==pytest.approx(3.)
