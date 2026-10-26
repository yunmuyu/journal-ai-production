import copy
import pytest

from journal_pdf.agent_spec import compile_reply_figure
from journal_pdf.common import FigureError
from journal_pdf.grouped_chains import grouped_chains
from journal_pdf.scene import audit_scene


def fixture(counts=(3, 3), length=1, bridge=True, side='right'):
    nodes = [{'id': f'{g}{i}', 'text': ('处理' + str(i)) * length}
             for g, count in zip(('a', 'b'), counts) for i in range(count)]
    groups = [{'id': g + '-group', 'title': ('发送' if g == 'a' else '接收') * length,
               'direction': ('LR' if side == 'right' else 'RL') if g == 'a' else ('RL' if side == 'right' else 'LR'),
               'nodes': [f'{g}{i}' for i in range(count)]}
              for g, count in zip(('a', 'b'), counts)]
    pairs = [(a, b) for group in groups for a, b in zip(group['nodes'], group['nodes'][1:])]
    ends = [groups[0]['nodes'][-1], groups[1]['nodes'][0]]
    if bridge:
        nodes.append({'id': 'channel', 'text': '外部节点' * length})
        pairs += [(ends[0], 'channel'), ('channel', ends[1])]
    else:
        pairs.append(tuple(ends))
    return {'nodes': nodes, 'groups': groups, 'bridge': {'node': 'channel', 'side': side} if bridge else None,
            'edges': [{'id': f'e{i}', 'from': a, 'to': b, 'label': ('4-bi原始' if i == 0 else '信号') * length}
                      for i, (a, b) in enumerate(pairs)]}


@pytest.mark.parametrize('counts', [(1, 1), (2, 5), (5, 2), (3, 3)])
@pytest.mark.parametrize('length', [1, 3])
@pytest.mark.parametrize('bridge,side', [(True, 'right'), (True, 'left'), (False, 'right'), (False, 'left')])
def test_measured_chains_variations(reg, counts, length, bridge, side):
    spec = fixture(counts, length, bridge, side)
    before = copy.deepcopy(spec)
    scene = grouped_chains(spec, reg, 8)
    assert spec == before
    assert scene.size == 8 and not audit_scene(scene)
    assert {(e['from'], e['to']) for e in spec['edges']} == {
        (e['from'], e['to']) for e in scene.layout_evidence['edge_bindings']}
    assert {t['source_content'] for t in scene.texts} >= {e['label'] for e in spec['edges']}
    assert len([n for n in scene.nodes if n['container']]) == 2
    assert all(t['measurement']['size'] == 8 for t in scene.texts)
    c = scene.layout_evidence['constraints']
    assert c['chosen_row_center_delta_pt'] == max(c['group_envelope_delta_pt'], c['bridge_delta_pt'])
    for path in scene.paths:
        assert all(a[0] == b[0] or a[1] == b[1] for a, b in zip(path['points'], path['points'][1:]))


def test_measured_geometry_changes_with_ink(reg):
    small = grouped_chains(fixture(length=1), reg, 8)
    large = grouped_chains(fixture(length=5), reg, 8)
    assert large.width > small.width
    assert large.layout_evidence['constraints']['outside_corridor_pt'] > small.layout_evidence['constraints']['outside_corridor_pt']


def semantic_fixture():
    spec = fixture()
    objects = [{'id': n['id'], 'text': n['text']} for n in spec['nodes']]
    objects += [{'id': g['id'], 'text': g['title']} for g in spec['groups']]
    objects += [{'id': e['id'], 'text': e['label']} for e in spec['edges']]
    reply = {'id': 'synthetic', 'kind': 'diagram', 'model': 'grouped-chains',
             'review': {'source_checked': True, 'labels_checked': True, 'topology_checked': True},
             'nodes': [{'id': n['id'], 'ref': n['id']} for n in spec['nodes']],
             'edges': [{k: v for k, v in e.items() if k != 'label'} | {'label_ref': e['id']} for e in spec['edges']],
             'structure': {'groups': [dict(g, title={'ref': g['id']}) for g in spec['groups']], 'bridge': spec['bridge']}}
    return reply, {'id': 'source', 'snapshot': 'synthetic.pdf', 'sha256': 'a' * 64}, {'id': 'page', 'kind': 'pdf', 'objects': objects}


def test_semantic_native_text_complete_and_unchanged(reg):
    reply, source, page = semantic_fixture()
    spec = compile_reply_figure(reply, source, page)
    assert spec['policy']['design_font_size_pt'] == 8
    scene = grouped_chains(spec, reg, 8)
    assert {t['source_content'] for t in scene.texts} == {o['text'] for o in page['objects']}
    assert scene.texts and any(t['source_content'] == '4-bi原始' for t in scene.texts)


@pytest.mark.parametrize('where,key,value', [('structure', 'origin', [0, 0]), ('structure', 'gap_pt', 70),
                                            ('group', 'font_size', 7), ('group', 'origin', [1, 2])])
def test_semantic_rejects_layout_knobs(where, key, value):
    reply, source, page = semantic_fixture()
    target = reply['structure'] if where == 'structure' else reply['structure']['groups'][0]
    target[key] = value
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code == 'grouped_chains_schema'


def test_semantic_catches_omitted_and_reused_title():
    reply, source, page = semantic_fixture()
    reply['structure']['groups'][0]['title']['ref'] = reply['nodes'][0]['ref']
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code == 'duplicate_node_ref'
    reply, source, page = semantic_fixture()
    page['objects'].append({'id': 'missing', 'text': '不可遗漏'})
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code == 'unaccounted_source_text'


@pytest.mark.parametrize('mutation', ['reverse', 'extra-edge', 'same-direction', 'extra-node', 'shape', 'port'])
def test_unsupported_topologies_fail_closed(reg, mutation):
    spec = fixture()
    if mutation == 'reverse':
        spec['edges'][0]['from'], spec['edges'][0]['to'] = spec['edges'][0]['to'], spec['edges'][0]['from']
    elif mutation == 'extra-edge': spec['edges'].append({'from': 'a0', 'to': 'b0'})
    elif mutation == 'same-direction': spec['groups'][1]['direction'] = 'LR'
    elif mutation == 'extra-node': spec['nodes'].append({'id': 'orphan', 'text': '无归属'})
    elif mutation == 'shape': spec['nodes'][0]['shape'] = 'ellipse'
    elif mutation == 'port': spec['edges'][0]['from_port'] = 'top'
    with pytest.raises(FigureError) as caught:
        grouped_chains(spec, reg, 8)
    assert caught.value.code == 'grouped_chains_unsupported'


def test_multiline_source_ink_and_titles(reg):
    spec = fixture(counts=(2, 4))
    for node in spec['nodes']:
        node['text'] = 'Interface\n多行源文'
    for group in spec['groups']:
        group['title'] = 'Container\n原文标题'
    for edge in spec['edges']:
        edge['label'] = 'Data\n原文标签'
    scene = grouped_chains(spec, reg, 8)
    assert not audit_scene(scene)
    assert any(t['source_content'] == 'Interface\n多行源文' for t in scene.texts)


def test_audit_failure_is_not_hidden_by_local_adjustment(reg, monkeypatch):
    monkeypatch.setattr('journal_pdf.grouped_chains.audit_scene', lambda _: [{'code': 'synthetic_obstruction'}])
    with pytest.raises(FigureError) as caught:
        grouped_chains(fixture(), reg, 8)
    assert caught.value.code == 'grouped_chains_no_feasible_layout'
    assert caught.value.details['issues'] == [{'code': 'synthetic_obstruction'}]


def test_grouped_native_connector_direction_still_enforced():
    reply, source, page = semantic_fixture()
    edge = reply['edges'][0]
    page['objects'].append({'id': 'native-edge', 'kind': 'native-connector', 'from_ref': edge['from'],
                            'to_ref': edge['to'], 'head': 'triangle', 'tail': 'none'})
    edge['ref'] = 'native-edge'
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code == 'native_arrow_direction_mismatch'


def test_unlabelled_edges_reuse_exact_terminal_contract(reg):
    spec = fixture()
    for edge in spec['edges']:
        edge.pop('label')
    scene = grouped_chains(spec, reg, 8)
    assert all(p['exact_terminal'] for p in scene.paths)
    assert not audit_scene(scene)


def test_public_capacity_gate_never_bypassed(reg):
    from journal_pdf.render import compile_figure
    spec = fixture(counts=(1, 1)) | {'kind': 'grouped-chains'}
    scene = compile_figure(spec, reg, None, None)
    assert scene.layout_evidence['initial_design_font_size_pt'] == 8
    assert scene.size >= 6
    oversized = fixture(counts=(5, 5), length=10) | {'kind': 'grouped-chains'}
    with pytest.raises(FigureError) as caught:
        compile_figure(oversized, reg, None, None)
    assert caught.value.code == 'layout_reflow_required'


@pytest.mark.parametrize('dash', [None, [1.5, 2.5], [0, 2]])
def test_source_reviewed_group_dash_survives_scene(reg, dash):
    reply, source, page = semantic_fixture()
    if dash is not None:
        reply['structure']['groups'][0]['dash'] = dash
    spec = compile_reply_figure(reply, source, page)
    scene = grouped_chains(spec, reg, 8)
    first = next(n for n in scene.nodes if n['id'] == 'a-group')
    second = next(n for n in scene.nodes if n['id'] == 'b-group')
    assert first.get('dash') == dash
    assert 'dash' not in second
    evidence = scene.layout_evidence['group_styles'][0]
    assert evidence['dash_pt'] == dash
    assert evidence['basis']['mechanically_verified'] is False
    assert not audit_scene(scene)


@pytest.mark.parametrize('dash', [[], [0, 0], [-1, 2], [True, 2], [float('nan'), 2],
                                 [float('inf'), 2], 'dashed', [1, '2'], None])
def test_invalid_group_dash_rejected_in_compiler(dash):
    reply, source, page = semantic_fixture()
    reply['structure']['groups'][0]['dash'] = dash
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code in ('invalid_node_dash', 'grouped_chains_unsupported')


def native_style_fixture(pattern='[1.5 2.5] 0'):
    reply, source, page = semantic_fixture()
    reply['structure']['groups'][0].update(dash=[1.5, 2.5], style_ref='native-frame')
    page['objects'].append({'id': 'native-frame', 'kind': 'native-path', 'shape_hint': 'rectangle',
                            'geometry': {'dashes': pattern}})
    return reply, source, page


def test_group_dash_native_pattern_binding(reg):
    reply, source, page = native_style_fixture()
    scene = grouped_chains(compile_reply_figure(reply, source, page), reg, 8)
    evidence = scene.layout_evidence['group_styles'][0]['basis']
    assert evidence['mechanically_verified'] is True
    assert evidence['verified_property'] == 'dash-pattern-only'
    assert evidence['source_sha256'] == source['sha256']
    assert evidence['object_ref'] == 'native-frame'


@pytest.mark.parametrize('pattern,code', [('[4 5] 0', 'grouped_chains_style_mismatch'),
    ('[1.5 2.5] 1', 'grouped_chains_style_source'), ('dashed', 'grouped_chains_style_source'),
    ('[x] 0', 'grouped_chains_style_source')])
def test_native_dash_mismatch_or_unsupported_phase_rejected(pattern, code):
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(*native_style_fixture(pattern))
    assert caught.value.code == code


def test_group_dash_scaling_and_actual_pdf_operator(reg):
    import fitz
    from journal_pdf.editorial import scale_scene
    from journal_pdf.render import draw_node
    spec = fixture()
    spec['groups'][0]['dash'] = [1.5, 2.5]
    scene = scale_scene(grouped_chains(spec, reg, 8), 0.875)
    frame = next(n for n in scene.nodes if n['id'] == 'a-group')
    assert frame['dash'] == pytest.approx([1.3125, 2.1875])
    doc = fitz.open()
    page = doc.new_page(width=scene.width, height=scene.height)
    draw_node(page, frame)
    encoded = doc.tobytes()
    doc.close()
    with fitz.open(stream=encoded, filetype='pdf') as reopened:
        drawings = reopened[0].get_drawings()
        assert len(drawings) == 1
        assert drawings[0]['dashes'].replace(' ', '') == '[1.31252.1875]0'


@pytest.mark.parametrize('kind,shape_hint', [('native-text', 'rectangle'), ('native-path', 'ellipse')])
def test_group_style_ref_unsupported_target_does_not_downgrade(kind, shape_hint):
    reply, source, page = native_style_fixture()
    page['objects'][-1].update(kind=kind, shape_hint=shape_hint)
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code == 'grouped_chains_style_source'


def test_verified_solid_group_style(reg):
    reply, source, page = native_style_fixture('[] 0')
    reply['structure']['groups'][0].pop('dash')
    scene = grouped_chains(compile_reply_figure(reply, source, page), reg, 8)
    assert scene.layout_evidence['group_styles'][0]['basis']['mechanically_verified'] is True
    assert 'dash' not in next(n for n in scene.nodes if n['id'] == 'a-group')


def test_native_edge_cannot_invent_unbound_label():
    reply, source, page = semantic_fixture()
    ref = reply['edges'][0].pop('label_ref')
    page['objects'] = [o for o in page['objects'] if o['id'] != ref]
    reply['edges'][0]['label'] = 'INVENTED NATIVE LABEL'
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code == 'native_edge_label_unbound'


def test_native_edge_cannot_contradict_bound_label():
    reply, source, page = semantic_fixture()
    reply['edges'][0]['label'] = 'CHANGED'
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code == 'native_text_changed'


def test_native_edge_explicit_matching_label_is_preserved():
    reply, source, page = semantic_fixture()
    expected = next(o['text'] for o in page['objects'] if o['id'] == reply['edges'][0]['label_ref'])
    reply['edges'][0]['label'] = expected
    assert compile_reply_figure(reply, source, page)['edges'][0]['label'] == expected


def test_raster_edge_reviewed_transcription_remains_available():
    reply = {'id': 'raster', 'kind': 'diagram',
             'review': {'source_checked': True, 'labels_checked': True, 'topology_checked': True},
             'nodes': [{'id': 'a', 'ref': 'ra', 'text': '原文甲'},
                       {'id': 'b', 'ref': 'rb', 'text': '原文乙'}],
             'edges': [{'from': 'a', 'to': 'b', 'label': '已核对转写'}]}
    source = {'id': 'source', 'snapshot': 'synthetic.png', 'sha256': 'a' * 64}
    page = {'id': 'page', 'kind': 'raster', 'geometry': {'shapes': [{'id': 'ra'}, {'id': 'rb'}], 'regions': []}}
    assert compile_reply_figure(reply, source, page)['edges'][0]['label'] == '已核对转写'
