import pytest
from journal_pdf.common import FigureError
from journal_pdf.layouts import primitive
from journal_pdf.scene import audit_scene


def spec():
    return {'width_pt':180,'height_pt':110,
        'nodes':[{'id':'switch','text':'交换单元','vertical_text':True,'rect':[10,10,30,30]},
                 *[{'id':f'u{i}','text':text} for i,text in enumerate(('主控单元','接口适配单元','供电单元','仪器单元'))]],
        'measured_groups':[{'id':'units','axis':'column','origin':[80,15],'nodes':['u0','u1','u2','u3']}],
        'multiport_groups':[{'node':'switch','side':'right','targets':['u0','u1','u2','u3'],'both':True}]}


def test_source_node_stretches_for_four_aligned_ports_and_preserves_arrows(reg):
    scene=primitive(spec(),reg,8)
    paths=[p for p in scene.paths if p['id'].startswith('multiport:')]
    assert len(paths)==4 and all(p['both'] for p in paths)
    assert all(p['points'][0][1]==pytest.approx(p['points'][-1][1]) for p in paths)
    assert len({p['points'][0][1] for p in paths})==4
    assert not audit_scene(scene)


def test_multiport_targets_must_be_distinct(reg):
    value=spec();value['multiport_groups'][0]['targets']=['u0','u0']
    with pytest.raises(FigureError):primitive(value,reg,8)


def test_multiport_crossing_another_route_is_reported(reg):
    value=spec();value['paths']=[{'id':'other','points':[[50,5],[50,95]]}]
    scene=primitive(value,reg,8)
    assert any(issue['code']=='multiport_path_crossing' for issue in audit_scene(scene))


def test_multiport_uses_shared_outline_arrow(reg):
    value=spec();value['multiport_groups'][0]['arrow_style']='block-outline'
    scene=primitive(value,reg,8)
    assert all(p['arrow_style']=='block-outline' for p in scene.paths)
    assert not audit_scene(scene)
