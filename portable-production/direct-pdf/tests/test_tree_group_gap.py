import pytest
from journal_pdf.layouts import tree
from journal_pdf.scene import audit_scene

@pytest.mark.parametrize('size', [8, 7, 6])
def test_right_tree_compacts_groups_with_different_child_counts(reg, size):
    spec={'root':'系统','branches':[{'text':'甲','children':['一','二','三']},{'text':'乙','children':['四']},{'text':'丙','children':['五','六']}]}
    s=tree(spec,reg,size)
    boxes={n['id']:n['rect'] for n in s.nodes}
    for i in range(2):
        group=[v for k,v in boxes.items() if k==f'branch{i}' or k.startswith(f'leaf{i}-')]
        following=[v for k,v in boxes.items() if k==f'branch{i+1}' or k.startswith(f'leaf{i+1}-')]
        assert min(x[1] for x in following)-max(x[3] for x in group)-.5==pytest.approx(6*size/8)
    assert boxes['leaf0-1'][1]-boxes['leaf0-0'][3]-.5==pytest.approx(3*size/8)
    assert not audit_scene(s)


def test_audit_rejects_expanded_right_tree_group_gap(reg):
    spec={'root':'系统','branches':[{'text':'甲','children':['一','二']},{'text':'乙','children':['三','四']}]}
    s=tree(spec,reg,8)
    for n in s.nodes:
        if n['id']=='branch1' or n['id'].startswith('leaf1-'):
            n['rect'][1]+=13; n['rect'][3]+=13
    assert any(issue['code']=='tree_group_gap' for issue in audit_scene(s))


def test_audit_rejects_expanded_sibling_gap(reg):
    s=tree({'root':'系统','branches':[{'text':'甲','children':['一','二']}]},reg,8)
    node=next(n for n in s.nodes if n['id']=='leaf0-1')
    node['rect'][1]+=1; node['rect'][3]+=1
    assert any(issue['code']=='tree_sibling_gap' for issue in audit_scene(s))


def test_bilateral_groups_and_siblings_have_distinct_gaps(reg):
    s=tree({'root':'系统','tree_layout':'bilateral','branches':[{'text':'甲','side':'right','children':['一','二']},{'text':'乙','side':'right','children':['三','四']}]},reg,8)
    box={n['id']:n['rect'] for n in s.nodes}
    assert box['b0-1'][1]-box['b0-0'][3]-.5==pytest.approx(3)
    assert box['b1-0'][1]-box['b0-1'][3]-.5==pytest.approx(6)
    assert not audit_scene(s)


def test_bilateral_audit_rejects_expanded_group_gap(reg):
    s=tree({'root':'系统','tree_layout':'bilateral','branches':[{'text':'甲','side':'right','children':['一','二']},{'text':'乙','side':'right','children':['三','四']}]},reg,8)
    for n in s.nodes:
        if n['id']=='b1' or n['id'].startswith('b1-'):
            n['rect'][1]+=3; n['rect'][3]+=3
    assert any(issue['code']=='tree_group_gap' for issue in audit_scene(s))


@pytest.mark.parametrize('layout', ['right','bilateral'])
def test_tree_spacing_pair_can_be_selected_without_confusing_groups(reg,layout):
    branches=[{'text':'甲','children':['一','二']},{'text':'乙','children':['三','四']}]
    if layout=='bilateral':
        for b in branches:b['side']='right'
    s=tree({'root':'系统','tree_layout':layout,'tree_spacing_pt':[3,6],'branches':branches},reg,8)
    b={n['id']:n['rect'] for n in s.nodes}
    a,c,d=('leaf0-0','leaf0-1','leaf1-0') if layout=='right' else ('b0-0','b0-1','b1-0')
    assert b[c][1]-b[a][3]-.5==pytest.approx(3)
    assert b[d][1]-b[c][3]-.5==pytest.approx(6)
    assert not audit_scene(s)


@pytest.mark.parametrize('layout', ['right','bilateral'])
def test_legacy_spacing_is_rejected(reg,layout):
    from journal_pdf.common import FigureError
    branches=[{'text':'甲','children':['一','二']}]
    if layout=='bilateral':branches[0]['side']='right'
    with pytest.raises(FigureError,match='3'):
        tree({'root':'系统','tree_layout':layout,'tree_spacing_pt':[2.5,5],'branches':branches},reg,8)

def test_right_tree_optional_arrows_preserve_semantic_branches(reg):
    s=tree({'root':'系统','arrows':True,'branches':[{'text':'甲','children':['一','二']},{'text':'乙','children':['三']}]},reg,8)
    assert len([p for p in s.paths if p['arrow']])==5
    assert not audit_scene(s)
    assert all(p['exact_terminal'] for p in s.paths if p['arrow'])

def test_tree_wraps_long_labels_before_reducing_eight_point(reg):
    from journal_pdf.render import compile_figure
    spec={'kind':'tree','root':'VR仿真教育实训平台应用架构','arrows':True,'branches':[
        {'text':'同江电排站巡查VR实训','children':['数据反馈','设备运行模拟']},
        {'text':'电排站水泵拆解维修VR实训','children':['水泵维修准备','水泵拆解过程']}],
        'policy':{'column':'single','design_font_size_pt':8}}
    scene=compile_figure(spec,reg,None,None,export_padding_pt=8)
    assert scene.size==pytest.approx(8)
    assert scene.width<=80*72/25.4-16-.5
    assert ''.join(next(t for t in scene.texts if t['id']=='root:text')['content'].splitlines())==spec['root']
    assert any('\n' in t['content'] for t in scene.texts if t['id'].startswith('branch'))
    assert len([p for p in scene.paths if p['arrow']])==6

def test_tree_does_not_reflow_when_eight_point_already_fits(reg):
    from journal_pdf.render import compile_figure
    spec={'kind':'tree','root':'系统','branches':[{'text':'输入','children':['数据']}],
          'policy':{'column':'single','design_font_size_pt':8}}
    scene=compile_figure(spec,reg,None,None)
    assert scene.size==pytest.approx(8)
    assert 'automatic_text_reflow' not in scene.layout_evidence
    assert scene.layout_evidence['layout_build_count']==1

def test_measured_grid_rejects_large_gaps(reg):
    from journal_pdf.scene import Scene,audit_scene
    s=Scene(reg,8);s.template='primitive-scene';a=s.box('a','甲',5,5);b=s.box('b','乙',a['rect'][2]+3.5,5)
    for n in (a,b):n['measurement_contract']={'mode':'measured-group','group':'g','axis':'both'}
    s.measurement_groups['g']={'axis':'both','nodes':['a','b'],'grid_columns':2};s.finish(100,50)
    assert not [x for x in audit_scene(s) if x['code']=='measured_group_spacing']
    b['rect'][0]+=5;b['rect'][2]+=5
    assert any(x['code']=='measured_group_spacing' for x in audit_scene(s))

def test_measured_group_requires_spacing_or_explicit_reason(reg):
    from journal_pdf.layouts import primitive
    from journal_pdf.common import FigureError
    spec={'width_pt':80,'height_pt':40,'nodes':[{'id':'a','rect':[5,5,25,20],'text':'甲'}],
          'measured_node_groups':[{'id':'g','nodes':['a']}]}
    with pytest.raises(FigureError,match='间距'):
        primitive(spec,reg,8)
    spec['measured_node_groups'][0]['spacing_exemption_reason']='只有一个节点'
    assert primitive(spec,reg,8).measurement_groups['g']['nodes']==['a']

def test_compact_container_fits_declared_contents(reg):
    from journal_pdf.layouts import primitive
    spec={'width_pt':120,'height_pt':80,'nodes':[{'id':'region','rect':[0,0,110,70],'container':True},{'id':'a','rect':[30,30,50,45]}],
          'texts':[{'id':'title','text':'标题','x':40,'y':22}],
          'compact_containers':[{'id':'region','nodes':['a'],'texts':['title'],'padding_pt':[6,3,6,6]}]}
    scene=primitive(spec,reg,8);region=next(n for n in scene.nodes if n['id']=='region')['rect'];label=next(t for t in scene.texts if t['id']=='title')['position']['bbox']
    assert region[0]==pytest.approx(min(29.75,label[0])-6)
    assert region[1]==pytest.approx(min(29.75,label[1])-3)
    assert region[2]==pytest.approx(max(50.25,label[2])+6)
    assert region[3]==pytest.approx(max(45.25,label[3])+6)
