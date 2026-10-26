import copy
import pytest

from journal_pdf.common import FigureError, PT_PER_MM
from journal_pdf.layouts import tree
from journal_pdf.render import compile_figure
from journal_pdf.scene import audit_scene


def spec():
    return {'kind': 'tree', 'tree_layout': 'bilateral', 'root': '服务平台',
            'root_vertical': True, 'policy': {'column': 'single'},
            'branches': [
                {'text': '账户管理', 'side': 'left', 'wrap_chars': 2,
                 'children': [{'text': '基本信息', 'wrap_chars': 2,
                               'children': ['头像', '昵称', '邮箱']}, '安全设置']},
                {'text': '首页', 'side': 'right',
                 'children': ['搜索', {'text': '附近', 'children': ['定位']}]}]}


def centers(scene):
    return {n['id']: ((n['rect'][0]+n['rect'][2])/2,
                      (n['rect'][1]+n['rect'][3])/2) for n in scene.nodes}


def test_bilateral_tree_measures_leaves_inward_and_preserves_nested_edges(reg):
    scene = tree(spec(), reg, 8)
    assert scene.template == 'bilateral-tree'
    c = centers(scene)
    assert c['b0-0-0'][0] < c['b0-0'][0] < c['b0'][0] < c['root'][0]
    assert c['root'][0] < c['b1'][0] < c['b1-1'][0] < c['b1-1-0'][0]
    assert c['b0-0'][1] == pytest.approx((c['b0-0-0'][1]+c['b0-0-2'][1])/2, abs=.1)
    assert scene.layout_evidence['parent_map']['b1-1-0'] == 'b1-1'
    assert len(scene.layout_evidence['parent_map']) == len(scene.nodes)-1
    assert not audit_scene(scene)


def test_larger_outer_leaf_moves_inner_columns_without_overlap(reg):
    original = tree(spec(), reg, 8)
    changed = spec()
    changed['branches'][0]['children'][0]['children'][1] = '用户账户联系信息'
    scene = tree(changed, reg, 8)
    assert scene.width > original.width
    assert centers(scene)['root'][0] > centers(original)['root'][0]
    assert scene.layout_evidence['parent_map'] == original.layout_evidence['parent_map']
    assert not audit_scene(scene)


def test_bilateral_tree_fits_single_column_without_dropping_nodes(reg):
    scene = compile_figure(spec(), reg, None, None)
    assert scene.width <= 80*PT_PER_MM
    assert scene.size >= 6
    assert len(scene.nodes) == 11
    assert scene.layout_evidence['column_mm'] == 80


@pytest.mark.parametrize('side', ['up', None, 1])
def test_bilateral_tree_requires_explicit_root_branch_sides(reg, side):
    value = spec()
    value['branches'][0]['side'] = side
    with pytest.raises(FigureError) as error:
        tree(value, reg, 8)
    assert error.value.code == 'tree_side'


def test_bilateral_descendant_cannot_switch_side(reg):
    value = spec()
    value['branches'][0]['children'][0]['side'] = 'right'
    with pytest.raises(FigureError) as error:
        tree(value, reg, 8)
    assert error.value.code == 'tree_side'


def test_unknown_tree_layout_is_not_silently_ignored(reg):
    value = spec()
    value['tree_layout'] = 'typo'
    with pytest.raises(FigureError) as error:
        tree(value, reg, 8)
    assert error.value.code == 'tree_layout'


def test_bilateral_budget_returns_typed_error(reg):
    value = spec()
    value['branches'][0]['children'] = ['叶子']*100
    with pytest.raises(FigureError) as error:
        tree(value, reg, 8)
    assert error.value.code == 'tree_budget'


def test_legacy_tree_layout_is_unchanged(reg):
    value = {'root': '平台', 'branches': [{'text': '模块', 'children': ['功能']} ]}
    a = tree(value, reg, 8)
    b = tree(copy.deepcopy(value), reg, 8)
    assert a.template == 'hierarchy-tree'
    assert a.nodes == b.nodes and a.paths == b.paths


def test_agent_entry_keeps_sides_nested_refs_and_orientation():
    from journal_pdf.agent_spec import compile_reply_figure
    source = {'id': 's', 'snapshot': 'x.png', 'sha256': 'a'*64}
    page = {'id': 'p', 'kind': 'raster', 'geometry': {
        'shapes': [{'id': str(i)} for i in range(5)], 'regions': []}}
    leaf = lambda i, text: {'ref': str(i), 'text': text}
    reply = {'id': 'tree', 'kind': 'diagram', 'model': 'tree',
             'tree_layout': 'bilateral', 'root_vertical': True,
             'review': {'source_checked': True, 'labels_checked': True, 'topology_checked': True},
             'structure': {'root': leaf(0, '平台'), 'branches': [
                 {'text': leaf(1, '账户'), 'side': 'left', 'wrap_chars': 1,
                  'children': [{'text': leaf(2, '信息'), 'children': [leaf(3, '昵称')]}]},
                 {'text': leaf(4, '首页'), 'side': 'right'}]}}
    value = compile_reply_figure(reply, source, page)
    assert value['tree_layout'] == 'bilateral' and value['root_vertical'] is True
    assert value['branches'][0]['side'] == 'left'
    assert value['branches'][0]['children'][0]['children'] == ['昵称']
    assert len(value['source_scope']['refs']) == 5
    reply['structure']['branches'][0]['side'] = 'up'
    with pytest.raises(FigureError) as error:
        compile_reply_figure(reply, source, page)
    assert error.value.code == 'tree_side'


def test_explicit_vertical_labels_survive_public_text_normalization(reg):
    value = spec()
    value['root'] = '逸友App'
    value['branches'][0].update(text='我的', wrap_chars=1)
    scene = tree(value, reg, 8)
    labels = {t['owner']: t['measurement']['text'] for t in scene.texts}
    assert labels['root'] == '逸\n友\nApp'
    assert labels['b0'] == '我\n的'
    assert labels['b0-0'] == '基本\n信息'
    assert not audit_scene(scene)


@pytest.mark.parametrize('kind,model', [('diagram', 'graph'), ('diagram', 'cycle'), ('raster-chart', None)])
def test_tree_options_cannot_be_silently_ignored_by_another_route(kind, model):
    from journal_pdf.agent_spec import compile_reply_figure
    reply = {'id': 'x', 'kind': kind, 'model': model, 'tree_layout': 'bilateral',
             'review': {'source_checked': True, 'labels_checked': True}}
    with pytest.raises(FigureError) as error:
        compile_reply_figure(reply, {'id': 's', 'snapshot': 's', 'sha256': 'a'*64}, {'id': 'p'})
    assert error.value.code == 'tree_options'


def test_literal_measurement_retains_breaks_without_changing_default_normalization(reg):
    assert reg.measure('我\n的', 8)['text'] == '我的'
    assert reg.measure('我\n的', 8, role='literal')['text'] == '我\n的'
    assert reg.measure('我\n的', 8)['text'] == '我的'
