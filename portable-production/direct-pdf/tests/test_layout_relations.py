from copy import deepcopy
import pytest
from journal_pdf.common import FigureError
from journal_pdf.layout_relations import extract_layout_relations, prepare_layout_relations
from journal_pdf.layouts import primitive


def example():
    objects=[]
    for key,rect in [('a',[10,10,50,25]),('b',[11,45,51,60])]:
        objects.extend([{'id':key,'shape_hint':'rectangle','rect':rect},
                        {'id':key+'text','text':key,'rect':[rect[0]+4,rect[1]+4,rect[2]-4,rect[3]-4]}])
    return extract_layout_relations(objects,'a'*64,'page-1','pt-unrotated')


def plan():
    e=example()
    return {'width_pt':150,'height_pt':150,'sources':[{'path':'source.pdf','sha256':'a'*64}],
            'nodes':[{'id':'A','text':'短','rect':[0,0,20,15]}, {'id':'B','text':'比较长的文字','rect':[30,50,90,65]}],
            'source_layout':{'source':{'path':'source.pdf','sha256':'a'*64},'evidence':e,
                             'node_bindings':{'a':'A','b':'B'},'confirmed':[{'candidate':e['candidates'][0]['id'],
                                    'basis':'same semantic column confirmed','origin':[10,10]}]}}


def test_candidates_are_not_automatic_decisions():
    e=example()
    assert len(e['candidates'])==1
    assert e['candidates'][0]['axis']=='column'
    assert e['candidates'][0]['status']=='needs-semantic-confirmation'
    s=plan();s['source_layout']['confirmed']=[]
    assert 'measured_groups' not in prepare_layout_relations(s)


def test_confirmed_column_generates_equal_width_and_three_pt_clearance(reg):
    s=plan();before=deepcopy(s)
    scene=primitive(s,reg,8)
    a,b=scene.nodes
    assert a['rect'][0]==b['rect'][0]
    assert a['rect'][2]-a['rect'][0]==b['rect'][2]-b['rect'][0]
    assert b['rect'][1]-a['rect'][3]-.5==pytest.approx(3)
    assert s==before


def test_confirmed_row_uses_existing_height_and_width_rules(reg):
    s=plan();s['source_layout']['evidence']['candidates'][0]['axis']='row'
    scene=primitive(s,reg,8);a,b=scene.nodes
    assert a['rect'][1]==b['rect'][1]
    assert a['rect'][3]==b['rect'][3]
    assert a['rect'][2]-a['rect'][0]==b['rect'][2]-b['rect'][0]


def test_changed_source_and_connected_nodes_are_explicitly_rejected():
    s=plan();s['sources'][0]['sha256']='b'*64
    with pytest.raises(FigureError,match='哈希'):prepare_layout_relations(s)
    s=plan();s['paths']=[{'endpoint_nodes':['A','B']}]
    with pytest.raises(FigureError,match='端口联动'):prepare_layout_relations(s)


def test_repeated_or_missing_identity_cannot_copy_another_binding():
    s=plan();s['source_layout']['node_bindings']['b']='A'
    with pytest.raises(FigureError,match='唯一'):prepare_layout_relations(s)


def linked_plan():
    s=plan()
    s['nodes'][0]['rect']=[20,20,40,35]
    s['nodes'][1]['rect']=[20,80,40,95]
    s['paths']=[{'id':'link','points':[[30,35],[30,80]],'both':True,'arrow':True,
                 'exact_terminal':True,'endpoint_nodes':['A','B']}]
    return s


def test_connected_column_keeps_straight_ports_and_arrow_gap(reg):
    from journal_pdf.editorial import ARROW_LENGTH
    s=linked_plan();before=deepcopy(s)
    scene=primitive(s,reg,8);a,b=scene.nodes;p=scene.paths[0]
    assert b['rect'][1]-a['rect'][3]==pytest.approx(2*ARROW_LENGTH)
    assert len({round(point[0],6) for point in p['points']})==1
    assert p['both'] is True
    assert p['endpoint_nodes'][0]['side']=='bottom'
    assert p['endpoint_nodes'][1]['side']=='top'
    assert s==before


def test_external_single_corner_moves_with_group(reg):
    s=linked_plan();s['nodes'].append({'id':'C','text':'外框','rect':[100,80,125,95]})
    s['paths']=[{'id':'external','points':[[40,27.5],[112.5,27.5],[112.5,80]],
                 'arrow':True,'both':False,'endpoint_nodes':['A','C']}]
    scene=primitive(s,reg,8);p=scene.paths[0]
    assert p['points'][0][0]==pytest.approx(scene.nodes[0]['rect'][2])
    assert p['points'][-1]==pytest.approx([112.5,80])
    assert p['endpoint_nodes'][0]['side']=='right'
    assert p['endpoint_nodes'][1]['side']=='top'


def test_alignment_conflict_is_not_changed_into_bent_route(reg):
    s=linked_plan()
    s['paths'][0]['points']=[[25,35],[25,80]]
    # Different final widths change the source fractions differently when
    # one endpoint is off-centre; a genuine straight-line conflict must reject.
    s['nodes'][1]['rect']=[15,80,45,95]
    with pytest.raises(FigureError,match='原直线端口冲突'):primitive(s,reg,8)


def test_group_collision_does_not_mutate_input(reg):
    s=linked_plan();s['nodes'].append({'id':'obstacle','text':'挡','rect':[12,12,20,20]})
    before=deepcopy(s)
    with pytest.raises(FigureError,match='碰撞'):primitive(s,reg,8)
    assert s==before


def test_external_port_occupancy_is_calculated_before_column_spacing(reg):
    from journal_pdf.editorial import ARROW_LENGTH
    s=linked_plan();s['source_layout']['confirmed'][0]['origin']=[30,10]
    s['nodes'].append({'id':'C','text':'端口','rect':[0,30,10,50]})
    s['paths']=[{'id':'b-c','points':[[20,87.5],[5,87.5],[5,50]],
                 'arrow':True,'both':False,'endpoint_nodes':['B','C']}]
    scene=primitive(s,reg,8);p=scene.paths[0]
    assert p['points'][0][1]-50==pytest.approx(ARROW_LENGTH)
    a,b=scene.nodes[:2]
    assert b['rect'][1]-a['rect'][3]>3.5


def bus_plan():
    return {'nodes':[{'id':'power','rect':[10,10,30,20]},
                     {'id':'vpx','rect':[90,-30,110,-20]},
                     {'id':'instrument','rect':[10,60,30,70]}],
            'paths':[{'id':'bus','points':[[30,15],[100,15],[100,-20]],'arrow':True,
                      'endpoint_nodes':['power','vpx'],'shared_net':'bus'},
                     {'id':'branch','points':[[30,65],[70,65],[70,15]],'arrow':True,
                      'endpoint_nodes':['instrument',None],'shared_net':'bus'}]}


def test_named_bus_junction_moves_with_bus_and_branch():
    from journal_pdf.layout_relation_paths import adapt_group_paths
    s=bus_plan()
    adapt_group_paths(s,{'power':[10,5,30,15],'instrument':[10,40,30,50]},8)
    branch=s['paths'][1]
    assert branch['points'][0]==pytest.approx([30,45])
    assert branch['points'][-1]==pytest.approx([70,10])
    assert branch['shared_net']=='bus'


def test_named_bus_rejects_point_that_was_never_on_bus():
    from journal_pdf.layout_relation_paths import adapt_group_paths
    s=bus_plan();s['paths'][1]['points'][-1]=[70,12]
    with pytest.raises(FigureError,match='不在已指定总线上'):
        adapt_group_paths(s,{'instrument':[10,40,30,50]},8)
