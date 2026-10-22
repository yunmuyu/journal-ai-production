
import pytest

from journal_pdf.layouts import primitive
from journal_pdf.graph_layout import graph
from journal_pdf.scene import audit_scene


def measured_spec():
    return {
        'width_pt': 150, 'height_pt': 150,
        'nodes': [{'id': 'start', 'text': '开始'},
                  {'id': 'process', 'text': '数据采集'},
                  {'id': 'end', 'text': '结束'}],
        'measured_groups': [{'id': 'flow', 'axis': 'column',
                             'nodes': ['start', 'process', 'end'],
                             'origin': [10, 10], 'gap_pt': 12}],
    }


@pytest.mark.parametrize('route', ['measured', 'graph', 'explicit'])
def test_start_end_are_rounded_but_process_stays_rectangular(reg, route):
    spec = measured_spec()
    if route == 'graph':
        spec['edges'] = [{'from': 'start', 'to': 'process'},
                         {'from': 'process', 'to': 'end'}]
        scene = graph(spec, reg, 8)
    elif route == 'explicit':
        spec['measured_groups'] = [
            {'id': node['id'], 'axis': 'column', 'nodes': [node['id']],
             'origin': [10, 10 + index * 40]}
            for index, node in enumerate(spec['nodes'])
        ]
        baseline = primitive(spec, reg, 8)
        spec.pop('measured_groups')
        for node, placed in zip(spec['nodes'], baseline.nodes, strict=True):
            node['rect'] = placed['rect']
        scene = primitive(spec, reg, 8)
    else:
        scene = primitive(spec, reg, 8)
    shapes = {node['id']: node['kind'] for node in scene.nodes}
    assert shapes == {'start': 'terminator', 'process': 'rectangle', 'end': 'terminator'}
    assert not audit_scene(scene)


def test_measured_explicit_terminal_role_and_semantic_roundrect(reg):
    spec = measured_spec()
    spec['nodes'][0].update(text='开始采样', role='start')
    spec['nodes'][2].update(text='采样完成', shape='roundrect', semantic_shape=True, role='end')
    scene = primitive(spec, reg, 8)
    assert [node['kind'] for node in scene.nodes] == ['terminator', 'rectangle', 'terminator']
    assert not audit_scene(scene)


def test_visual_gate_rejects_terminal_replaced_with_small_roundrect(reg):
    scene = primitive(measured_spec(), reg, 8)
    scene.nodes[0]['kind'] = 'roundrect'
    assert any(issue['code'] == 'flow_terminal_shape' for issue in audit_scene(scene))


def test_ordinary_measured_roundrect_does_not_change_process_style(reg):
    spec = measured_spec()
    spec['nodes'][1]['shape'] = 'roundrect'
    scene = primitive(spec, reg, 8)
    assert scene.nodes[1]['kind'] == 'rectangle'


def test_final_pdf_uses_curved_paths_for_start_and_end(reg, tmp_path):
    import pymupdf as fitz
    from journal_pdf.render import draw_node

    scene = primitive(measured_spec(), reg, 8)
    with fitz.open() as document:
        page = document.new_page(width=150, height=150)
        for node in scene.nodes:
            draw_node(page, node)
        output = tmp_path / 'terminals.pdf'
        document.save(output)
    with fitz.open(output) as document:
        drawings = document[0].get_drawings()
        assert [any(item[0] == 'c' for item in row['items']) for row in drawings] == [True, False, True]


def test_terminal_pdf_has_semicircular_ends_not_small_rounded_corners(reg):
    import pymupdf as fitz
    from journal_pdf.render import draw_node

    node = primitive(measured_spec(), reg, 8).nodes[0]
    with fitz.open() as document:
        page = document.new_page(width=150, height=150)
        draw_node(page, node)
        expected = page.new_shape()
        expected.draw_rect(fitz.Rect(node['rect']), radius=.5)
        expected.finish(color=(0,), width=.5, closePath=True)
        expected.commit()
        actual, capsule = page.get_drawings()
        assert actual['items'] == capsule['items']
