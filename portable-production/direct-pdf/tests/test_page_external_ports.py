import copy
import pytest

from journal_pdf.scene import Scene,audit_scene
from journal_pdf.editorial import scale_scene


def declaration(side='right',fraction=.5,inset=1):
    return {'page':'external','side':side,'fraction':fraction,'inset_pt':inset}


def endpoint_issues(scene):
    return [row for row in audit_scene(scene) if 'endpoint' in row['code'] or 'external' in row['code']]


@pytest.mark.parametrize('side,start,end',[('right',[60,50],[99,50]),('left',[40,50],[1,50]),('top',[50,40],[50,1]),('bottom',[50,60],[50,99])])
def test_explicit_page_boundary_requires_no_synthetic_node(reg,side,start,end):
    scene=Scene(reg).finish(100,100);scene.shape('inside',[40,40,60,60])
    scene.line('open-output',[start,end],arrow=True,endpoint_nodes=['inside',declaration(side)])
    assert endpoint_issues(scene)==[]
    assert len(scene.nodes)==1
    assert scene.layout_evidence['page_external_ports'][0]['verified']


def test_real_wu1_output_point_binds_to_page_right_edge(reg):
    scene=Scene(reg).finish(448,198);y=108.53203125
    scene.shape('output-stack-group',[420,y-5,435.75,y+5])
    scene.line('output-forward',[[435.75,y],[447,y]],arrow=True,
               endpoint_nodes=['output-stack-group',declaration(fraction=y/198)])
    assert endpoint_issues(scene)==[]


@pytest.mark.parametrize('value',[None,{'page':'unknown','side':'right','fraction':.5,'inset_pt':1},
    declaration('diagonal'),declaration(inset=-1),declaration(inset=1.01),declaration(inset=True),
    declaration(inset=float('nan')),declaration(fraction=1.1),declaration(fraction=True),
    {'page':'external','side':'right','fraction':.5}])
def test_unregistered_or_invalid_external_declaration_remains_rejected(reg,value):
    scene=Scene(reg).finish(100,100);scene.shape('inside',[40,40,60,60])
    scene.line('open-output',[[60,50],[99,50]],arrow=True,endpoint_nodes=['inside',value])
    assert endpoint_issues(scene)


@pytest.mark.parametrize('end,value',[([80,50],declaration()),([80,50],declaration(inset=20)),([101,50],declaration(inset=0))])
def test_internal_dangling_or_outside_point_cannot_masquerade_as_page_output(reg,end,value):
    scene=Scene(reg).finish(100,100);scene.shape('inside',[40,40,60,60])
    scene.line('false-open',[[60,50],end],arrow=True,endpoint_nodes=['inside',value])
    assert endpoint_issues(scene)


def test_parallel_border_line_is_not_an_outward_external_output(reg):
    scene=Scene(reg).finish(100,100);scene.shape('inside',[89,15,99,25])
    scene.line('parallel',[[99,20],[99,50]],arrow=True,endpoint_nodes=['inside',declaration()])
    assert endpoint_issues(scene)


def test_external_declaration_on_nonarrow_is_not_silently_ignored(reg):
    scene=Scene(reg).finish(100,100);scene.shape('inside',[40,40,60,60])
    scene.line('plain-internal',[[60,50],[80,50]],endpoint_nodes=['inside',declaration()])
    assert endpoint_issues(scene)


def test_whole_scene_fit_scales_only_new_page_inset_geometry(reg):
    scene=Scene(reg,8).finish(100,100);scene.shape('inside',[40,40,60,60])
    value=declaration();scene.line('open-output',[[60,50],[99,50]],arrow=True,endpoint_nodes=['inside',value])
    original=copy.deepcopy(value);scale_scene(scene,.8)
    assert endpoint_issues(scene)==[]
    assert value==original
    assert scene.paths[0]['points'][-1]==[79.2,40]
