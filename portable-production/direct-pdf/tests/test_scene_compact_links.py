import pytest

from journal_pdf.common import FigureError
from journal_pdf.layouts import primitive
from journal_pdf.scene import audit_scene


def example():
    return {
        'width_pt': 180, 'height_pt': 150,
        'nodes': [
            {'id': 'region', 'rect': [10, 10, 140, 60], 'container': True},
            {'id': 'target', 'text': '转接工装', 'rect': [48, 110, 88.28125, 122.775]},
        ],
        'paths': [
            {'id': 'up', 'points': [[58, 110], [58, 68.503937007874], [58, 60]], 'arrow': True,
             'exact_terminal': True, 'endpoint_nodes': [{'node': 'target', 'side': 'top', 'fraction': 0.2483}, {'node': 'region', 'side': 'bottom', 'fraction': 0.36923}]},
            {'id': 'down', 'points': [[78, 60], [78, 101.496062992126], [78, 110]], 'arrow': True,
             'exact_terminal': True, 'endpoint_nodes': [{'node': 'region', 'side': 'bottom', 'fraction': 0.52308}, {'node': 'target', 'side': 'top', 'fraction': 0.74476}]},
        ],
        'compact_links': [{'anchor': 'region', 'target': 'target', 'paths': ['up', 'down']}],
    }


def test_linked_node_and_reciprocal_arrows_compact_together(reg):
    s = primitive(example(), reg, 8)
    nodes = {n['id']: n for n in s.nodes}
    assert nodes['target']['rect'][1] - nodes['region']['rect'][3] == pytest.approx(12)
    assert all(p['points'][0][1] in (60, 72) and p['points'][-1][1] in (60, 72) for p in s.paths)
    assert next(t for t in s.texts if t['owner'] == 'target')['y'] < 90
    assert not audit_scene(s)


def test_compact_links_rejects_unowned_attachment(reg):
    spec = example()
    spec['paths'].append({'id': 'extra', 'points': [[68, 110], [68, 60]], 'endpoint_nodes': ['target', 'region']})
    with pytest.raises(FigureError, match='连接'):
        primitive(spec, reg, 8)


def test_partial_grid_is_measured_and_laid_out_at_three_points(reg):
    spec = {'width_pt': 300, 'height_pt': 120,
            'nodes': [{'id': str(i), 'text': text, 'rect': [10 + 50*i, 10, 50 + 50*i, 25]}
                      for i, text in enumerate(['甲', '乙乙', '丙', '丁', '戊'])],
            'measured_node_groups': [{'id': 'grid', 'nodes': [str(i) for i in range(5)],
                                      'grid_columns': 3}]}
    s = primitive(spec, reg, 8)
    n = {node['id']: node for node in s.nodes}
    assert n['1']['rect'][0] - n['0']['rect'][2] - .5 == pytest.approx(3)
    assert n['3']['rect'][1] - n['0']['rect'][3] - .5 == pytest.approx(3)
    assert n['3']['rect'][0] == pytest.approx(n['0']['rect'][0])
    assert not audit_scene(s)


def test_measured_row_defaults_to_three_point_ink_gap(reg):
    spec = {'width_pt': 180, 'height_pt': 60,
            'nodes': [{'id': 'a', 'text': '甲'}, {'id': 'b', 'text': '乙'}],
            'measured_groups': [{'id': 'row', 'axis': 'row', 'origin': [5, 5], 'nodes': ['a', 'b']}]}
    s = primitive(spec, reg, 8)
    a, b = s.nodes
    assert b['rect'][0] - a['rect'][2] - .5 == pytest.approx(3)


def test_compact_links_rejects_crossing_other_node(reg):
    spec = example()
    spec['nodes'].append({'id': 'obstacle', 'rect': [45, 70, 90, 90]})
    with pytest.raises(FigureError, match='碰撞'):
        primitive(spec, reg, 8)


def test_ungrouped_adjacent_boxes_cannot_touch_or_bypass_spacing(reg):
    from journal_pdf.scene import Scene
    s=Scene(reg,8);s.template='primitive-scene'
    a=s.box('a','温度\n采集电路',10,10)
    b=s.box('b','在位\n采集电路',10,a['rect'][3]+.3)
    s.finish(100,100)
    assert any(issue['code']=='primitive_box_gap' for issue in audit_scene(s))
    dy=3.5-.3;b['rect'][1]+=dy;b['rect'][3]+=dy
    t=next(t for t in s.texts if t['owner']=='b')
    from journal_pdf.fonts import position_text
    t['y']+=dy;t['position']=position_text(t['measurement'],t['x'],t['y'],t['align'],0)
    assert not any(issue['code']=='primitive_box_gap' for issue in audit_scene(s))


def test_primitive_automatically_moves_box_and_link_when_gap_is_short(reg):
    def wh(text):
        m=reg.measure(text,8);return m['width']+9,m['height']+5.4
    w,h=wh('温度\n采集电路');w2,h2=wh('在位\n采集电路');w3,h3=wh('控制')
    y2=10+h+.3;cy=y2+h2/2;other_y=75;other_cy=other_y+h3/2;xend=120
    spec={'width_pt':200,'height_pt':120,'nodes':[
        {'id':'a','text':'温度\n采集电路','rect':[10,10,10+w,10+h]},
        {'id':'b','text':'在位\n采集电路','rect':[10,y2,10+w2,y2+h2]},
        {'id':'out','text':'控制','rect':[xend,other_y,xend+w3,other_y+h3]}],
        'paths':[{'id':'line','points':[[10+w2,cy],[10+w2+9,cy],[10+w2+9,other_cy],[xend,other_cy]],
                  'arrow':True,'endpoint_nodes':['b','out']}]}
    scene=primitive(spec,reg,8);nodes={n['id']:n for n in scene.nodes}
    assert nodes['b']['rect'][1]-nodes['a']['rect'][3]-.5==pytest.approx(3)
    assert scene.paths[0]['points'][0][1]==pytest.approx((nodes['b']['rect'][1]+nodes['b']['rect'][3])/2)
    assert scene.layout_evidence['automatic_box_spacing'][0]['paths']==['line']
    assert not audit_scene(scene)


def test_container_row_moves_children_and_title_to_six_point_group_gap(reg):
    spec = {'width_pt': 250, 'height_pt': 100,
            'nodes': [{'id': 'left', 'rect': [0, 0, 60, 60], 'container': True},
                      {'id': 'right', 'rect': [120, 0, 200, 60], 'container': True},
                      {'id': 'a', 'text': '甲', 'rect': [10, 20, 27, 33]},
                      {'id': 'b', 'text': '乙', 'rect': [145, 20, 162, 33]}],
            'texts': [{'id': 'title', 'text': '标题', 'x': 153, 'y': 10}],
            'compact_containers': [{'id': 'left', 'nodes': ['a'], 'texts': [], 'padding_pt': [3, 3, 3, 3]},
                                   {'id': 'right', 'nodes': ['b'], 'texts': ['title'], 'padding_pt': [3, 3, 3, 3]}],
            'compact_container_rows': [{'containers': ['left', 'right']}]}
    s = primitive(spec, reg, 8)
    n = {node['id']: node for node in s.nodes}
    assert n['right']['rect'][0] - n['left']['rect'][2] - .5 == pytest.approx(6)
    assert n['b']['rect'][0] < 100
    assert next(t for t in s.texts if t['id'] == 'title')['x'] < 100


def test_container_bands_share_width_and_keep_bottom_group_gap(reg):
    spec = {'width_pt': 240, 'height_pt': 160,
            'nodes': [{'id': 'top', 'rect': [0, 0, 150, 50], 'container': True},
                      {'id': 'left', 'rect': [0, 70, 60, 120], 'container': True},
                      {'id': 'right', 'rect': [70, 70, 110, 120], 'container': True},
                      {'id': 'wide', 'text': '很长的标题文字', 'rect': [10, 15, 100, 30]},
                      {'id': 'a', 'text': '甲', 'rect': [10, 85, 27, 98]},
                      {'id': 'b', 'text': '乙', 'rect': [75, 85, 92, 98]}],
            'compact_containers': [{'id': 'top', 'nodes': ['wide'], 'texts': [], 'padding_pt': [3, 3, 3, 3]},
                                   {'id': 'left', 'nodes': ['a'], 'texts': [], 'padding_pt': [3, 3, 3, 3]},
                                   {'id': 'right', 'nodes': ['b'], 'texts': [], 'padding_pt': [3, 3, 3, 3]}],
            'texts': [{'id': 'heading', 'text': '总标题', 'x': 30, 'y': 5}],
            'compact_container_rows': [{'containers': ['left', 'right']}],
            'equal_width_container_bands': [{'bands': [['top'], ['left', 'right']], 'titles': ['heading']}]}
    s = primitive(spec, reg, 8)
    n = {node['id']: node for node in s.nodes}
    assert n['top']['rect'][0] == pytest.approx(n['left']['rect'][0])
    assert n['top']['rect'][2] == pytest.approx(n['right']['rect'][2])
    assert n['right']['rect'][0] - n['left']['rect'][2] - .5 == pytest.approx(6)
    assert next(t for t in s.texts if t['id'] == 'heading')['x'] == pytest.approx((n['top']['rect'][0]+n['top']['rect'][2])/2)
    del spec['equal_width_container_bands']
    s = primitive(spec, reg, 8)
    n = {node['id']: node for node in s.nodes}
    assert n['right']['rect'][2] == pytest.approx(n['top']['rect'][2])
    assert next(t for t in s.texts if t['id'] == 'heading')['x'] == pytest.approx((n['top']['rect'][0]+n['top']['rect'][2])/2)
    spec['texts'].append({'id': 'other-heading', 'text': '其他标题', 'x': 35, 'y': 5})
    with pytest.raises(FigureError, match='多个独立文字'):
        primitive(spec, reg, 8)



def test_container_auto_compaction_keeps_crossing_connections_inside(reg):
    from journal_pdf.scene_container_fit import compact_container_bottoms
    from journal_pdf.scene import Scene
    s=Scene(reg,8);s.template='primitive-scene'
    s.shape('region',[40,5,140,130],container=True)
    a=s.box('a','模块',70,35);b=s.box('b','模块',5,75)
    s.line('cross',[[b['rect'][2],(b['rect'][1]+b['rect'][3])/2],[140,(b['rect'][1]+b['rect'][3])/2]],endpoint_nodes=None)
    s.finish(150,140)
    compact_container_bottoms(s)
    region=s.nodes[0]['rect']
    assert region[3] < 110
    assert region[3] > s.paths[0]['points'][-1][1]
    assert a['rect'][3] < region[3]


def test_offset_centres_do_not_get_silently_replaced_with_offcentre_ports(reg):
    from journal_pdf.scene_straighten import straighten_connections
    from journal_pdf.scene import Scene
    s=Scene(reg,8);s.template='primitive-scene'
    a=s.box('a','模块',10,10);b=s.box('b','模块',16,80)
    ax=(a['rect'][0]+a['rect'][2])/2;bx=(b['rect'][0]+b['rect'][2])/2
    s.line('line',[[ax,a['rect'][3]],[ax,60],[bx,60],[bx,b['rect'][1]]],arrow=True,both=True,endpoint_nodes=['a','b'])
    s.finish(100,110);straighten_connections(s)
    assert len({round(p[0],4) for p in s.paths[0]['points']}) == 2
    assert s.paths[0]['endpoint_nodes']==['a','b']
    assert s.paths[0]['both'] and not audit_scene(s)


def test_align_connected_node_straightens_and_preserves_other_bound_path(reg):
    from journal_pdf.scene_straighten import align_connected_nodes
    from journal_pdf.scene import Scene
    s=Scene(reg,8);s.template='primitive-scene'
    a=s.box('a','模块',10,10);b=s.box('b','模块',100,60)
    ay=(a['rect'][1]+a['rect'][3])/2;by=(b['rect'][1]+b['rect'][3])/2
    s.line('ab',[[a['rect'][2],ay],[70,ay],[70,by],[b['rect'][0],by]],arrow=True,both=True,endpoint_nodes=['a','b'])
    s.line('other',[[b['rect'][2],by],[150,by],[150,100]],endpoint_nodes=['b',None])
    s.finish(180,120);align_connected_nodes(s,[{'path':'ab','source':'a','target':'b'}])
    assert s.paths[0]['points'][0][1] == pytest.approx(s.paths[0]['points'][-1][1])
    assert s.paths[1]['points'][0][1] == pytest.approx(s.paths[1]['points'][1][1])
    assert s.paths[1]['points'][-1] == [150,100]
    assert not audit_scene(s)


def test_parallel_containers_keep_bottoms_aligned_when_compacting(reg):
    from journal_pdf.scene_container_fit import compact_container_bottoms
    from journal_pdf.scene import Scene
    s=Scene(reg,8);s.template='primitive-scene'
    s.shape('left',[0,0,80,140],container=True);s.shape('right',[90,0,170,140],container=True)
    s.box('a','模块',10,90);s.box('b','模块',100,35);s.finish(180,150)
    compact_container_bottoms(s)
    left,right=s.nodes[:2]
    assert left['rect'][3] == pytest.approx(right['rect'][3])
    assert left['rect'][3] < 140
