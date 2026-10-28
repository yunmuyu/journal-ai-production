import copy
import pytest

from journal_pdf.layouts import DIAGRAMS
from journal_pdf.scene import audit_scene
from journal_pdf.common import FigureError


def example():
    return {'columns': [
        {'id': 'a', 'blocks': [{'id': 'input', 'kind': 'stage', 'title': '输入',
                              'items': [{'id': 'a1', 'text': '资料一'}, {'id': 'a2', 'text': '资料二'}]}]},
        {'id': 'b', 'blocks': [{'id': 'parse', 'kind': 'stage', 'title': '解析',
                              'items': [{'id': 'b1', 'text': '布局分析'}, {'id': 'b2', 'text': '语义解析'}]}]}],
        'edges': [{'id': 'group-edge', 'from': 'input', 'to': 'parse', 'from_port': 'right', 'to_port': 'left'}]}


def test_group_connection_stays_single_edge(reg):
    # Given two multi-member stages linked by one semantic relation.
    spec = example()
    before = copy.deepcopy(spec)
    # When the shared measured layout renders the grouped relation.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    # Then no member-to-member edges are invented, and public audit passes.
    assert spec == before
    assert len([path for path in scene.paths if path['arrow']]) == 1
    assert len(scene.layout_evidence['edge_bindings']) == 1
    assert not audit_scene(scene)


def test_long_text_changes_measured_stage_width(reg):
    spec = example()
    small = DIAGRAMS['stage-grid'](spec, reg, 8)
    spec['columns'][0]['blocks'][0]['items'][0]['text'] = '更长的实际文字尺寸用于测量'
    large = DIAGRAMS['stage-grid'](spec, reg, 8)
    assert large.width > small.width


def test_unknown_endpoint_rejected(reg):
    spec = example()
    spec['edges'][0]['to'] = 'missing'
    with pytest.raises(FigureError):
        DIAGRAMS['stage-grid'](spec, reg, 8)


def test_reject_coordinates(reg):
    spec = example()
    spec['columns'][0]['blocks'][0]['rect'] = [0, 0, 50, 20]
    with pytest.raises(FigureError):
        DIAGRAMS['stage-grid'](spec, reg, 8)


def test_explicit_alignment_cycle_fails(reg):
    spec = example()
    spec['columns'][0]['blocks'][0]['after'] = ['parse']
    spec['columns'][1]['blocks'][0]['align_with'] = 'input'
    with pytest.raises(FigureError) as error:
        DIAGRAMS['stage-grid'](spec, reg, 8)
    assert error.value.code == 'stage_grid_constraints_cycle'


def test_merge_corridor_clears_wider_target_column_frame(reg):
    spec = {'columns': [
        {'id':'a', 'blocks':[{'id':'one','kind':'node','text':'输入一'},
                            {'id':'two','kind':'node','text':'输入二'}]},
        {'id':'b', 'blocks':[{'id':'target','kind':'node','text':'合并'},
                            {'id':'frame','kind':'stage','title':'较宽容器',
                             'items':[{'id':'item','text':'必须避开的容器边界'}]}]}],
        'edges':[{'id':str(i),'from':name,'to':'target','from_port':'right','to_port':'left','merge':'shared'}
                 for i,name in enumerate(['one','two'])]}
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    frame = next(n for n in scene.nodes if n['id']=='frame')
    bus = next(p for p in scene.paths if p['id']=='shared:bus')
    assert bus['points'][0][0] <= frame['rect'][0]-3
    assert len([p for p in scene.paths if p['arrow']]) == 1
    assert len(scene.layout_evidence['edge_bindings']) == 2
    assert not audit_scene(scene)


@pytest.mark.parametrize('fill', [-0.1, 1.1, float('nan'), float('inf'), True])
def test_invalid_fill_rejected(reg, fill):
    spec = example()
    spec['columns'][0]['blocks'][0]['fill'] = fill
    with pytest.raises(FigureError):
        DIAGRAMS['stage-grid'](spec, reg, 8)


def test_cover_keeps_all_member_text_and_source_ports(reg):
    spec = {'columns':[
        {'id':'a','blocks':[{'id':'group','kind':'stage','title':'术语库','cover':['last'],
                            'items':[{'id':'term','text':'术语'}]}]},
        {'id':'b','blocks':[{'id':'first','kind':'node','text':'第一路'},
                            {'id':'middle','kind':'node','text':'中间处理\n更多说明'},
                            {'id':'last','kind':'node','text':'第二路'}]}],
        'edges':[{'id':'edge-'+name,'from':'group','to':name,'from_port':'right','to_port':'left','source_align':'target'}
                 for name in ['first','last']]}
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    assert {t['content'] for t in scene.texts} == {'术语库','术语','第一路','中间处理\n更多说明','第二路'}
    assert not audit_scene(scene)


def test_backward_column_edge_rejected(reg):
    spec = example()
    spec['edges'][0].update({'from':'parse','to':'input','from_port':'left','to_port':'right'})
    with pytest.raises(FigureError):
        DIAGRAMS['stage-grid'](spec, reg, 8)


def test_split_fanout_reaches_each_declared_member(reg):
    # Given one source that fans out to two declared members of the next stage.
    spec = example()
    spec['edges'] = [
        {'id': 'split-b1', 'from': 'input', 'to': 'b1',
         'from_port': 'right', 'to_port': 'left', 'split': 'bus'},
        {'id': 'split-b2', 'from': 'input', 'to': 'b2',
         'from_port': 'right', 'to_port': 'left', 'split': 'bus'},
    ]
    # When the shared measured layout renders the fan-out.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    # Then each declared member gets its own arrowhead on a shared bus.
    assert len([path for path in scene.paths if path['arrow']]) == 2
    assert all(row.get('shared_net') == 'bus' for row in scene.layout_evidence['edge_bindings'])
    assert not audit_scene(scene)


def test_member_endpoint_without_split_stays_single_edge(reg):
    spec = example()
    spec['edges'] = [{'id': 'one-member', 'from': 'a1', 'to': 'b1',
                      'from_port': 'right', 'to_port': 'left'}]
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    assert len([path for path in scene.paths if path['arrow']]) == 1
    assert not audit_scene(scene)


def test_split_requires_one_shared_source(reg):
    spec = example()
    spec['edges'] = [
        {'id': 'split-a', 'from': 'input', 'to': 'b1',
         'from_port': 'right', 'to_port': 'left', 'split': 'bus'},
        {'id': 'split-b', 'from': 'a1', 'to': 'b2',
         'from_port': 'right', 'to_port': 'left', 'split': 'bus'},
    ]
    with pytest.raises(FigureError):
        DIAGRAMS['stage-grid'](spec, reg, 8)


def test_split_with_single_leg_rejected(reg):
    spec = example()
    spec['edges'] = [{'id': 'split-one', 'from': 'input', 'to': 'b1',
                      'from_port': 'right', 'to_port': 'left', 'split': 'bus'}]
    with pytest.raises(FigureError):
        DIAGRAMS['stage-grid'](spec, reg, 8)


def test_short_column_centres_on_the_tall_column(reg):
    # Given a one-block column beside a four-item stage.
    spec = {'columns': [
        {'id': 'a', 'blocks': [{'id': 'inp', 'kind': 'node', 'text': '输入'}]},
        {'id': 'b', 'blocks': [{'id': 'st', 'kind': 'stage', 'title': '解析',
                                'items': [{'id': f'x{i}', 'text': f'条目{i}'} for i in range(4)]}]}],
        'edges': [{'id': 'e', 'from': 'inp', 'to': 'st',
                   'from_port': 'right', 'to_port': 'left'}]}
    # When the layout runs, the short column centres on the overall band.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    inp = next(n for n in scene.nodes if n['id'] == 'inp')
    st = next(n for n in scene.nodes if n['id'] == 'st')
    short_mid = (inp['rect'][1] + inp['rect'][3]) / 2
    tall_mid = (st['rect'][1] + st['rect'][3]) / 2
    # Then it is not top-aligned.
    assert abs(short_mid - tall_mid) < 0.01
    assert inp['rect'][1] > st['rect'][1] + 1


def test_blocks_are_unfilled_by_default(reg):
    # Given stage and node blocks without an explicit fill.
    spec = example()
    # When the layout runs.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    # Then no drawn node carries a fill; gray must be declared per block.
    assert all('fill' not in node for node in scene.nodes)


def test_nested_group_boxes_render_inside_out(reg):
    # Given a container whose body holds a heading and a second nested container.
    spec = {'columns': [{'id': 'a', 'blocks': [{
        'id': 'out', 'kind': 'group', 'title': '输出', 'items': [
            {'id': 'body', 'kind': 'group', 'items': [
                {'id': 'head', 'kind': 'label', 'text': '知识单元'},
                {'id': 'leaf', 'kind': 'node', 'text': '文本'},
                {'id': 'meta', 'kind': 'group', 'title': '元数据体系', 'items': [
                    {'id': 'meta-body', 'kind': 'node', 'text': '来源\n业务标签'}]}]}]}]}],
        'edges': []}
    # When the layout runs.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    rects = {node['id']: node['rect'] for node in scene.nodes if node.get('container')}
    # Then three containers nest strictly, each inside its parent.
    assert set(rects) == {'out', 'body', 'meta'}
    for outer, inner in (('out', 'body'), ('body', 'meta')):
        assert rects[outer][0] < rects[inner][0] and rects[outer][2] > rects[inner][2]
        assert rects[outer][1] < rects[inner][1] and rects[outer][3] > rects[inner][3]
    assert not audit_scene(scene)


def test_note_without_fill_is_text_only(reg):
    # 图幅要求「零灰底」时，note 不写 fill 就只落文字，不生成任何形状
    spec = {'columns': [{'id': 'a', 'blocks': [{'id': 'n', 'kind': 'note', 'text': '实现解耦'}]}], 'edges': []}
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    assert not [n for n in scene.nodes if n['id'] == 'n']
    assert any(t['id'].startswith('n') for t in scene.texts)


def test_note_with_fill_draws_hairline_patch(reg):
    spec = {'columns': [{'id': 'a', 'blocks': [{'id': 'n', 'kind': 'note', 'text': '实现解耦', 'fill': 0.93}]}],
            'edges': []}
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    node = next(n for n in scene.nodes if n['id'] == 'n')
    assert node['fill'] == 0.93
    assert node['width'] <= 0.1


def test_panel_edge_draws_one_centred_arrow(reg):
    # Given two panels and one declared panel-to-panel flow.
    spec = {'columns': [
        {'id': 'a', 'blocks': [{'id': 'left', 'kind': 'node', 'text': '输入'}]},
        {'id': 'b', 'blocks': [{'id': 'right', 'kind': 'node', 'text': '核心'}]}],
        'panels': [{'id': 'p1', 'title': '左面板', 'blocks': ['left']},
                   {'id': 'p2', 'title': '右面板', 'blocks': ['right']}],
        'policy': {'column_gap': 12, 'panel_gap': 12},
        'edges': [{'id': 'flow', 'from_panel': 'p1', 'to_panel': 'p2', 'label': '数据流', 'label_vertical': True}]}
    # When rendered, the arrow sits between the two frames at the figure centre.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    arrows = [path for path in scene.paths if path['arrow']]
    assert len(arrows) == 1
    left = next(n for n in scene.nodes if n['id'] == 'p1')['rect']
    right = next(n for n in scene.nodes if n['id'] == 'p2')['rect']
    assert abs(arrows[0]['points'][0][0] - left[2]) < 0.01
    assert abs(arrows[0]['points'][-1][0] - right[0]) < 0.01
    assert not audit_scene(scene)


def test_span_block_covers_every_band(reg):
    # Given a block that spans both rows while its neighbours stay in one row each.
    spec = {'columns': [
        {'id': 'a', 'blocks': [{'id': 'tall', 'kind': 'node', 'text': '核心', 'band': 1, 'span': True}]},
        {'id': 'b', 'blocks': [{'id': 'top', 'kind': 'node', 'text': '上', 'band': 1},
                               {'id': 'bottom', 'kind': 'node', 'text': '下', 'band': 2}]}],
        'edges': []}
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    tall = next(n for n in scene.nodes if n['id'] == 'tall')['rect']
    top = next(n for n in scene.nodes if n['id'] == 'top')['rect']
    bottom = next(n for n in scene.nodes if n['id'] == 'bottom')['rect']
    assert tall[1] <= top[1] + 0.01
    assert tall[3] >= bottom[3] - 0.01


def test_stretched_node_fills_its_band(reg):
    # Given a tall column of three boxes and a one-line block beside it.
    spec = {'columns': [
        {'id': 'a', 'blocks': [{'id': 'plug', 'kind': 'node', 'text': '插件', 'stretch': True}]},
        {'id': 'b', 'blocks': [{'id': f'p{i}', 'kind': 'node', 'text': f'策略{i}'} for i in range(3)]}],
        'edges': []}
    # When laid out, the short block grows to the band height instead of staying natural.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    plug = next(n for n in scene.nodes if n['id'] == 'plug')['rect']
    last = next(n for n in scene.nodes if n['id'] == 'p2')['rect']
    assert plug[1] <= last[1] + 0.01
    assert plug[3] >= last[3] - 0.01


def test_straight_edge_keeps_one_segment(reg):
    # Given a tall target so the source's outlet height is inside it.
    spec = {'columns': [
        {'id': 'a', 'blocks': [{'id': 'mid', 'kind': 'node', 'text': '策略'}]},
        {'id': 'b', 'blocks': [{'id': 'tall', 'kind': 'node', 'text': '配置', 'stretch': True}]}],
        'edges': [{'id': 'go', 'from': 'mid', 'to': 'tall', 'from_port': 'right',
                   'to_port': 'left', 'straight': True}]}
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    paths = [p for p in scene.paths if p['id'] == 'go']
    assert len(paths) == 1 and len(paths[0]['points']) == 2
    assert abs(paths[0]['points'][0][1] - paths[0]['points'][1][1]) < 0.01
    assert not audit_scene(scene)


def test_straight_edge_rejects_target_that_does_not_cover_source(reg):
    spec = {'columns': [
        {'id': 'a', 'blocks': [{'id': 'low', 'kind': 'node', 'text': '下'}, {'id': 'x', 'kind': 'node', 'text': '垫'}]},
        {'id': 'b', 'blocks': [{'id': 'small', 'kind': 'node', 'text': '小'}]}],
        'edges': [{'id': 'go', 'from': 'low', 'to': 'small', 'from_port': 'right',
                   'to_port': 'left', 'straight': True}]}
    with pytest.raises(FigureError):
        DIAGRAMS['stage-grid'](spec, reg, 8)


def test_row_members_share_equal_height(reg):
    # Given a row container mixing a two-line and a one-line node.
    spec = {'columns': [{'id': 'a', 'blocks': [{
        'id': 'row', 'kind': 'group', 'direction': 'row', 'items': [
            {'id': 'tall', 'kind': 'node', 'text': '标准\n术语'},
            {'id': 'short', 'kind': 'node', 'text': '近义词'}]}]}],
        'edges': []}
    # When the layout runs.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    rects = {n['id']: n['rect'] for n in scene.nodes}
    # Then both members are stretched to the same height (同行等高).
    assert abs((rects['tall'][3] - rects['tall'][1]) - (rects['short'][3] - rects['short'][1])) < 1e-6
    assert not audit_scene(scene)


def test_frameless_group_registers_rect_but_draws_nothing(reg):
    # Given a group declared frame:false (source shows the pair without an outer box).
    spec = {'columns': [{'id': 'a', 'blocks': [{
        'id': 'pair', 'kind': 'group', 'frame': False, 'direction': 'row', 'items': [
            {'id': 'p1', 'kind': 'node', 'text': '术语库'},
            {'id': 'p2', 'kind': 'node', 'text': '文本输入'}]}]}],
        'edges': []}
    # When the layout runs.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    nodes = {n['id']: n for n in scene.nodes}
    # Then the group still registers its extent (union of members) for arrow endpoints,
    # but the shape is marked invisible so no stroke and no fill reaches the PDF.
    assert nodes['pair']['invisible'] is True
    union = [min(nodes['p1']['rect'][0], nodes['p2']['rect'][0]),
             min(nodes['p1']['rect'][1], nodes['p2']['rect'][1]),
             max(nodes['p1']['rect'][2], nodes['p2']['rect'][2]),
             max(nodes['p1']['rect'][3], nodes['p2']['rect'][3])]
    assert all(abs(a - b) < 1.0 for a, b in zip(nodes['pair']['rect'], union))
    assert not audit_scene(scene)


def test_vertical_merge_draws_bracket_into_target(reg):
    # Given two members of a frameless row group merging into one target below.
    spec = {'columns': [{'id': 'a', 'blocks': [
        {'id': 'inputs', 'kind': 'group', 'frame': False, 'direction': 'row', 'items': [
            {'id': 'i1', 'kind': 'node', 'text': '术语库'},
            {'id': 'i2', 'kind': 'node', 'text': '文本输入'}]},
        {'id': 'emb', 'kind': 'node', 'text': 'Embedding模型'}]}],
        'edges': [
            {'id': 'e1', 'from': 'i1', 'to': 'emb', 'from_port': 'bottom', 'to_port': 'top', 'merge': 'm'},
            {'id': 'e2', 'from': 'i2', 'to': 'emb', 'from_port': 'bottom', 'to_port': 'top', 'merge': 'm'}]}
    # When the layout runs.
    scene = DIAGRAMS['stage-grid'](spec, reg, 8)
    legs = [p for p in scene.paths if p.get('semantic_role') == 'merge-leg']
    buses = [p for p in scene.paths if p.get('semantic_role') == 'bus']
    outlets = [p for p in scene.paths if p['id'].endswith(':outlet')]
    # Then the bracket is two stubs, one horizontal bus and one arrowed outlet,
    # the outlet ends on the target top port, and its terminal respects ARROW_LENGTH.
    assert len(legs) == 2 and len(buses) == 1 and len(outlets) == 1
    outlet = outlets[0]
    assert outlet['arrow'] is True
    terminal = abs(outlet['points'][-1][1] - outlet['points'][-2][1])
    assert terminal >= 3 * 72 / 25.4 - 1e-6
    assert not audit_scene(scene)


def test_icon_source_outside_root_is_rejected(reg, tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside.png'
    outside.write_bytes(b'not an image')
    spec = {'columns': [{'id': 'a', 'blocks': [{'id': 'item', 'kind': 'node', 'text': 'x',
             'icon': {'path': str(outside), 'clip': [0, 0, 1, 1], 'width_pt': 8}}]}], 'edges': []}
    with pytest.raises(FigureError) as error:
        DIAGRAMS['stage-grid'](spec, reg, 8, object(), root)
    assert error.value.code == 'source_outside_root'


def test_stage_grid_public_renderer_creates_pdf(reg, tmp_path):
    import pymupdf as fitz
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one

    spec = example() | {'id': 'stage-grid-e2e', 'author': 'Synthetic', 'kind': 'stage-grid',
                        'synthetic': True, 'policy': {'column': 'double'}}
    source = tmp_path / 'source'
    source.mkdir()
    assets = Assets()
    try:
        result = render_one(spec, reg, assets, source, tmp_path / 'output')
    finally:
        assets.close()
    with fitz.open(tmp_path / 'output' / result['output_pdf']) as document:
        assert len(document) == 1
        text = document[0].get_text()
        assert '输入' in text and '解析' in text
        assert len(document[0].get_drawings()) > 2


def test_decorative_path_crossing_text_remains_reported(reg):
    from journal_pdf.scene import Scene
    scene = Scene(reg, 8)
    scene.text('label', 'Text', 50, 50)
    scene.poly('line', [[40, 50], [60, 50]], closed=False, semantic_role='decorative')
    scene.finish(100, 100)
    assert any(issue['code'] == 'text_path_collision' for issue in audit_scene(scene))


def test_filled_polygon_retains_opacity_in_pdf(tmp_path):
    import pymupdf as fitz
    from journal_pdf.render import draw_path
    doc = fitz.open()
    page = doc.new_page(width=100, height=100)
    draw_path(page, {'id': 'poly', 'points': [[10, 10], [80, 10], [40, 80]],
                     'arrow': False, 'both': False, 'dash': [], 'width': .5,
                     'closed': True, 'fill': .5, 'gray': 0, 'opacity': .4})
    path = tmp_path / 'polygon.pdf'
    doc.save(path)
    doc.close()
    with fitz.open(path) as rendered:
        drawing = rendered[0].get_drawings()[0]
        assert drawing['fill'] == pytest.approx((.5, .5, .5), abs=.01)
        assert drawing['fill_opacity'] == pytest.approx(.4, abs=.01)


def test_filled_path_cannot_silently_drop_arrow(reg):
    spec = {'width_pt': 100, 'height_pt': 100, 'paths': [
        {'id': 'p', 'points': [[10, 10], [80, 10], [40, 80]],
         'fill': .5, 'closed': True, 'arrow': True}]}
    with pytest.raises(FigureError):
        DIAGRAMS['scene'](spec, reg, 8)


def test_polygon_closing_edge_is_checked_for_text_collision(reg):
    from journal_pdf.scene import Scene
    scene = Scene(reg, 8)
    scene.text('label', 'Text', 25, 50)
    scene.poly('poly', [[10, 10], [80, 10], [40, 90]], fill=.5, closed=True)
    scene.finish(100, 100)
    assert any(issue['code'] == 'text_path_collision' for issue in audit_scene(scene))
