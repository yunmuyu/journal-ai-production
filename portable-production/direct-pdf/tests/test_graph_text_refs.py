import copy

import pytest

from journal_pdf.agent_spec import compile_reply_figure
from journal_pdf.common import FigureError


SOURCE = {'id': 'source-1', 'snapshot': 'source-1.pdf', 'sha256': 'a' * 64}
PAGE = {'id': 'page-1', 'kind': 'pdf', 'objects': [
    {'id': 'a1', 'text': '监听 UDP 广播'},
    {'id': 'a2', 'text': '搜索后端 IP 地址'},
    {'id': 'b', 'text': '连接成功？'},
]}
REPLY = {
    'id': '图1', 'kind': 'diagram',
    'review': {'source_checked': True, 'labels_checked': True, 'topology_checked': True},
    'nodes': [
        {'id': 'a', 'refs': ['a1', 'a2'], 'join': '\n', 'shape': 'rectangle'},
        {'id': 'b', 'ref': 'b', 'shape': 'diamond'},
    ],
    'edges': [{'from': 'a', 'to': 'b'}],
}


def test_graph_node_joins_all_native_text_fragments():
    # Given two source text objects within one visual node.
    # When the Agent binds both IDs, Then the exact two lines survive compilation.
    spec = compile_reply_figure(copy.deepcopy(REPLY), SOURCE, PAGE)
    assert spec['nodes'][0]['text'] == '监听 UDP 广播\n搜索后端 IP 地址'
    assert set(spec['source_scope']['refs']) == {'a1', 'a2', 'b'}


@pytest.mark.parametrize('change,code', [
    ({'refs': []}, 'text_join'),
    ({'refs': ['a1', 'a1']}, 'duplicate_node_ref'),
    ({'refs': ['a1'], 'join': '!!!'}, 'text_join'),
    ({'refs': ['a1'], 'text': '改写'}, 'native_text_changed'),
    ({'refs': ['a1'], 'ref': 'a2'}, 'diagram_node_schema'),
    ({'refs': ['a1', 'missing']}, 'candidate_ref_invalid'),
    ({'refs': [['a1']]}, 'text_join'),
])
def test_graph_node_rejects_invalid_multi_ref_binding(change, code):
    # Given a malformed or altered binding.
    reply = copy.deepcopy(REPLY)
    reply['nodes'][0].update(change)
    # When it compiles, Then the unsafe binding is blocked.
    with pytest.raises(FigureError) as exc:
        compile_reply_figure(reply, SOURCE, PAGE)
    assert exc.value.code == code


def test_graph_node_rejects_fragment_reused_by_another_node():
    # Given one text fragment claimed by two nodes.
    reply = copy.deepcopy(REPLY)
    reply['nodes'][1]['ref'] = 'a2'
    # When it compiles, Then the duplicate source use is blocked.
    with pytest.raises(FigureError) as exc:
        compile_reply_figure(reply, SOURCE, PAGE)
    assert exc.value.code == 'duplicate_node_ref'


def test_graph_node_rejects_omitted_fragment():
    # Given a visual node with one fragment omitted.
    reply = copy.deepcopy(REPLY)
    reply['nodes'][0]['refs'] = ['a1']
    # When it compiles, Then source completeness catches the omission.
    with pytest.raises(FigureError) as exc:
        compile_reply_figure(reply, SOURCE, PAGE)
    assert exc.value.code == 'unaccounted_source_text'


def test_graph_node_and_edge_label_cannot_share_source_text():
    reply = copy.deepcopy(REPLY)
    reply['edges'][0]['label_ref'] = 'a2'
    with pytest.raises(FigureError) as exc:
        compile_reply_figure(reply, SOURCE, PAGE)
    assert exc.value.code == 'duplicate_node_ref'


def test_native_connector_with_multi_ref_endpoint_is_ambiguous():
    # Given a connector bound to native objects and a multi-ref node.
    page = copy.deepcopy(PAGE)
    page['objects'].append({'id': 'c', 'kind': 'native-connector', 'from_ref': 'a1',
                            'to_ref': 'b', 'head': 'none', 'tail': 'triangle'})
    reply = copy.deepcopy(REPLY)
    reply['edges'][0]['ref'] = 'c'
    # When topology compiles, Then it does not guess which fragment is the endpoint.
    with pytest.raises(FigureError) as exc:
        compile_reply_figure(reply, SOURCE, page)
    assert exc.value.code == 'native_topology_ambiguous'
