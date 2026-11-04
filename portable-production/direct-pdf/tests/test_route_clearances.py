from types import SimpleNamespace
import pytest
from journal_pdf.common import FigureError
from journal_pdf.route_clearances import parse_route_clearances,audit_route_clearances


def route(identifier,points,width=.5,**extra):
    return {'id':identifier,'points':points,'width':width,'dash':[],'arrow':False,'both':False,**extra}


def make_scene(paths,nodes,checks,size=8):
    return SimpleNamespace(paths=paths,nodes=nodes,route_clearance_checks=parse_route_clearances(checks),size=size)


def test_parallel_clearance_is_a_minimum_not_an_exact_spacing():
    checks=[{'kind':'line_line','first_id':'a','first_segment':0,'second_id':'b','second_segment':0}]
    a=route('a',[[10,0],[10,20]])
    for x,valid in [(13.4,False),(13.5,True),(17,True)]:
        result=audit_route_clearances(make_scene([a,route('b',[[x,0],[x,20]])],[],checks))
        assert (not result['issues']) is valid
        assert result['checks'][0]['actual_pt']==pytest.approx(x-10.5)


def test_line_frame_clearance_and_recorded_exception():
    checks=[{'kind':'line_frame','first_id':'a','first_segment':0,'second_id':'box'}]
    node={'id':'box','kind':'rectangle','rect':[13,0,23,20],'width':.5}
    line=route('a',[[10,0],[10,20]])
    assert audit_route_clearances(make_scene([line],[node],checks))['issues']
    checks[0].update(min_pt=2,reason='避免遮挡文字')
    result=audit_route_clearances(make_scene([line],[node],checks))
    assert not result['issues'] and result['checks'][0]['reason']=='避免遮挡文字'
    assert result['checks'][0]['actual_pt']==pytest.approx(2.5)


def test_bad_exceptions_and_shared_or_intersecting_lines_cannot_pass():
    check={'kind':'line_line','first_id':'a','first_segment':0,'second_id':'b','second_segment':0}
    with pytest.raises(FigureError):parse_route_clearances([{**check,'min_pt':1}])
    a=route('a',[[10,0],[10,20]],shared_net='same')
    b=route('b',[[15,0],[15,20]],shared_net='same')
    assert audit_route_clearances(make_scene([a,b],[],[check]))['issues']
    b=route('b',[[10,0],[10,20]])
    assert audit_route_clearances(make_scene([a,b],[],[{**check,'min_pt':0,'reason':'必要'}]))['issues']


def test_unsupported_geometry_and_arrowhead_are_not_claimed_as_clear():
    check={'kind':'line_line','first_id':'a','first_segment':0,'second_id':'b','second_segment':0}
    a=route('a',[[10,0],[10,20]],arrow=True)
    b=route('b',[[15,0],[15,20]])
    assert audit_route_clearances(make_scene([a,b],[],[check]))['issues']
    a=route('a',[[10,0],[20,10]])
    assert audit_route_clearances(make_scene([a,b],[],[check]))['issues']


def test_frame_actually_connected_to_route_is_not_called_independent():
    line=route('a',[[10,0],[10,20],[20,20]],endpoint_nodes=['other',{'node':'box','side':'left','fraction':.5}])
    node={'id':'box','kind':'rectangle','rect':[20,10,30,30],'width':.5}
    check={'kind':'line_frame','first_id':'a','first_segment':0,'second_id':'box'}
    assert audit_route_clearances(make_scene([line],[node],[check]))['issues']


def test_shared_vertex_without_net_metadata_is_not_called_independent():
    a=route('a',[[10,0],[10,20],[15,20]])
    b=route('b',[[15,0],[15,20]])
    check={'kind':'line_line','first_id':'a','first_segment':0,'second_id':'b','second_segment':0}
    assert audit_route_clearances(make_scene([a,b],[],[check]))['issues']


def test_t_junction_without_shared_vertex_is_not_called_independent():
    a=route('a',[[10,0],[10,20],[15,20]])
    b=route('b',[[15,0],[15,30]])
    check={'kind':'line_line','first_id':'a','first_segment':0,'second_id':'b','second_segment':0}
    assert audit_route_clearances(make_scene([a,b],[],[check]))['issues']


def test_scene_spec_executes_minimum_clearance(reg):
    from journal_pdf.layouts import primitive
    from journal_pdf.scene import audit_scene
    spec={'width_pt':80,'height_pt':80,'nodes':[{'id':'box','rect':[30,10,50,50]}],
          'paths':[{'id':'a','points':[[10,10],[10,50]],'semantic_role':'decorative'},
                   {'id':'b','points':[[15,10],[15,50]],'semantic_role':'decorative'}],
          'route_clearance_checks':[{'kind':'line_line','first_id':'a','first_segment':0,'second_id':'b','second_segment':0},
                                    {'kind':'line_frame','first_id':'b','first_segment':0,'second_id':'box'}]}
    scene=primitive(spec,reg,8)
    assert not any(i['code'].startswith('route_clearance_') for i in audit_scene(scene))
    assert [c['actual_pt'] for c in scene.layout_evidence['route_clearance_checks']]==pytest.approx([4.5,14.5])
