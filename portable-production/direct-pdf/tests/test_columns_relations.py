from copy import deepcopy
import pytest
from journal_pdf.columns import columns
from journal_pdf.common import FigureError
from journal_pdf.scene import audit_scene


def relation_spec():
    return {'columns': [
        {'id': 'main', 'title': '主程序', 'nodes': [{'id': 'start', 'text': '开始'}, {'id': 'loop', 'text': '循环监测'}, {'id': 'delay', 'text': '延时监测周期'}], 'edges': [{'from': 'start', 'to': 'loop'}, {'from': 'loop', 'to': 'delay'}], 'scopes': [{'id': 'while', 'nodes': ['loop', 'delay'], 'side': 'right', 'label': 'while(1)'}]},
        {'id': 'irq', 'title': '串口3中断服务', 'nodes': [{'id': 'irqtype', 'text': '接收非空中断？', 'shape': 'diamond'}, {'id': 'irqreturn', 'text': '中断返回', 'shape': 'terminator'}], 'edges': [{'from': 'irqtype', 'to': 'irqreturn'}]},
    ], 'relations': [
        {'id': 'response', 'type': 'cross-column', 'direction': 'LR', 'source': {'column': 'main', 'scope': 'while', 'fraction': .3}, 'target': {'column': 'irq', 'node': 'irqtype', 'port': 'top'}, 'label': '中断响应'},
        {'id': 'return', 'type': 'cross-column', 'direction': 'RL', 'source': {'column': 'irq', 'node': 'irqreturn', 'port': 'left'}, 'target': {'column': 'main', 'scope': 'while', 'fraction': .7}, 'label': '中断返回'},
    ]}


def test_relations_draw_both_directions_with_audited_real_endpoints(reg):
    # Given: independent main/interrupt flows and two explicitly declared relations.
    spec = relation_spec()
    # When: the public columns compositor renders them.
    scene = columns(spec, reg, 8)
    # Then: both arrows are drawn and all public geometry gates accept them.
    paths = {p['id']: p for p in scene.paths}
    assert {'relation:response', 'relation:return'} <= paths.keys()
    assert paths['relation:response']['endpoint_nodes'] == [None, 'irq:irqtype']
    assert paths['relation:return']['endpoint_nodes'] == ['irq:irqreturn', None]
    assert not audit_scene(scene)


@pytest.mark.parametrize('change', ['missing-node', 'invalid-fraction', 'wrong-direction', 'ambiguous-anchor', 'invalid-scope'])
def test_relations_reject_invalid_declared_anchors(reg, change):
    # Given: a relation whose endpoint declaration is invalid.
    spec = deepcopy(relation_spec())
    match change:
        case 'missing-node': spec['relations'][0]['target']['node'] = 'missing'
        case 'invalid-fraction': spec['relations'][0]['source']['fraction'] = 1.5
        case 'wrong-direction': spec['relations'][0]['direction'] = 'RL'
        case 'ambiguous-anchor': spec['relations'][0]['source']['node'] = 'loop'
        case 'invalid-scope': spec['columns'][0]['scopes'][0]['id'] = ''
    # When / Then: compilation rejects the declaration rather than drawing a false edge.
    with pytest.raises(FigureError):
        columns(spec, reg, 8)


def test_relations_reject_route_through_a_node(reg):
    # Given: the response is deliberately attached to the far side of a node.
    spec = relation_spec()
    spec['relations'][0]['target']['port'] = 'right'
    # When / Then: the route cannot pass through the target box to reach that port.
    with pytest.raises(FigureError) as error:
        columns(spec, reg, 8)
    assert error.value.code == 'columns_relation_crosses_node'



def test_undeclared_relations_do_not_draw_scope_or_cross_edges(reg):
    # Given: legacy notes with scope metadata, and the equivalent old graph-only input.
    spec = relation_spec()
    spec['relations'] = [{'id': 'note', 'type': 'asynchronous-event-response', 'from': 'main.loop', 'to': 'irq.irqtype'}]
    legacy = deepcopy(spec)
    legacy['columns'][0].pop('scopes')
    expected = columns(legacy, reg, 8).export()
    # When: no relation explicitly enables a cross-column path.
    actual = columns(spec, reg, 8).export()
    # Then: all geometry and report fields stay unchanged.
    assert actual == expected


def test_scene_child_preserves_explicit_self_loop_and_measurement_groups(reg):
    # Given: an explicit primitive child containing a real self loop and measured group.
    child = {'id': 'main', 'kind': 'scene', 'width_pt': 110, 'height_pt': 90,
             'nodes': [{'id': 'gate', 'text': '监测'}],
             'measured_groups': [{'id': 'g', 'nodes': ['gate'], 'axis': 'column', 'origin': [35, 35]}]}
    from journal_pdf.layouts import primitive
    box = primitive(child, reg, 8).nodes[0]['rect']
    cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
    from journal_pdf.editorial import ARROW_LENGTH
    child['connections'] = [{'id': 'false-loop', 'from': 'gate', 'to': 'gate',
        'from_port': 'left', 'to_port': 'top', 'arrow': True,
        'via': [[20, cy], [20, 20], [cx, 20], [cx, box[1]-ARROW_LENGTH]]}]
    # When: the public compositor explicitly dispatches the primitive child.
    scene = columns({'columns': [child]}, reg, 8)
    # Then: the actual self loop, namespaced measurement contract and audit survive composition.
    assert scene.paths[0]['endpoint_nodes'] == ['main:gate', 'main:gate']
    assert scene.measurement_groups['main:g']['nodes'] == ['main:gate']
    assert not audit_scene(scene)


def test_translation_removes_points_collapsed_by_floating_precision():
    # Given: distinct local points that become equal after a column translation.
    from journal_pdf.columns import _append_child
    from journal_pdf.scene import Scene
    child = Scene(None, 8)
    child.line('p', [[1, 1], [1+1e-15, 1], [12, 1]])
    target = Scene(None, 8)
    # When: the public compositor translates the path to its column.
    _append_child(target, child, 'column', 300, 0)
    # Then: no zero-length segment reaches the public geometry audit.
    points = target.paths[0]['points']
    assert points == [[301, 1], [312, 1]]


def test_relation_labels_bind_to_their_actual_paths(reg):
    # Given: explicit asynchronous response and return relations.
    spec = relation_spec()
    # When: public columns creates their labels.
    scene = columns(spec, reg, 8)
    # Then: every relation label owns exactly its actual relation path.
    labels = [t for t in scene.texts if t['id'].startswith('relation:')]
    assert {t['owner'] for t in labels} == {'relation:response', 'relation:return'}


def test_header_reserves_only_measured_top_entry_clearance(reg):
    # Given: an interrupt top entry whose child node is at a measured local top.
    from journal_pdf.editorial import ARROW_LENGTH
    spec = relation_spec()
    # When: the compositor reserves the title/header space.
    scene = columns(spec, reg, 8)
    title = next(t for t in scene.texts if t['id'] == 'column:irq:title')
    path = next(p for p in scene.paths if p['id'] == 'relation:response')
    # Then: title ink to top-entry line ink is exactly 3pt, with a true 3mm terminal.
    line_y = path['points'][-2][1]
    assert line_y-path['width']/2-title['position']['bbox'][3] == pytest.approx(3)
    assert path['points'][-1][1]-line_y == pytest.approx(ARROW_LENGTH)
