import math
from contextlib import closing
import pytest
from journal_pdf.scene import Scene, audit_scene
from journal_pdf.layouts import primitive
from journal_pdf.editorial import ARROW_LENGTH
from journal_pdf.common import FigureError, digest_file
from journal_pdf.assets import Assets
from journal_pdf.render import compile_figure, render_one
from PIL import Image
import pymupdf as fitz


@pytest.mark.parametrize('size',[6,7.5,8])
def test_generated_connection_reserves_arrow_space_before_placing_boxes(reg,size):
    # Given adjacent measured boxes and an explicit directed connection.
    spec={'nodes':[{'id':'a','text':'输入'},{'id':'b','text':'输出'}],
          'measured_groups':[{'id':'row','nodes':['a','b'],'axis':'row','origin':[10,10]}],
          'connections':[{'id':'ab','from':'a','to':'b','from_port':'right','to_port':'left','arrow':True,'auto_route':True}],
          'width_pt':180,'height_pt':70}
    # When the existing primitive entry generates it.
    scene=primitive(spec,reg,size)
    # Then arrow space and its exact terminal exist without manual coordinates.
    path=scene.paths[0]
    assert math.dist(path['points'][-2],path['points'][-1])==pytest.approx(ARROW_LENGTH)
    assert scene.nodes[1]['rect'][0]-scene.nodes[0]['rect'][2]>=ARROW_LENGTH
    assert not audit_scene(scene)


def test_curved_boundary_ports_are_computed_at_explicit_fractions(reg):
    from journal_pdf.connection_layout import generate_connection
    # Given a confirmed ellipse-to-diamond connection with fractional ports.
    scene=Scene(reg)
    a=scene.shape('a',[10,10,70,70],'ellipse')
    b=scene.shape('b',[130,10,190,70],'diamond')
    # When generated, then the true curved/angled boundaries are used.
    generate_connection(scene,{'a':a,'b':b},{'id':'ab','from':'a','to':'b','from_port':'right',
                        'to_port':'left','from_fraction':.25,'to_fraction':.25,'arrow':True})
    scene.finish(210,90)
    assert scene.paths[0]['points'][0][0]<70
    assert scene.paths[0]['points'][-1][0]>130
    assert not audit_scene(scene)


def test_port_failure_explains_expected_point_and_arrow_space(reg):
    # Given a malformed explicit path, when audited, then report all actionable errors.
    scene=Scene(reg)
    scene.shape('a',[10,10,40,40]);scene.shape('b',[70,10,100,40])
    scene.line('bad',[[42,25],[45,25],[69,25]],arrow=True,exact_terminal=True,
               endpoint_nodes=[{'node':'a','side':'right','fraction':.5},'b'])
    scene.finish(120,60)
    issues=audit_scene(scene)
    port=next(i for i in issues if i['code']=='arrow_endpoint_boundary_mismatch')
    assert port['expected_point']==[40,25]
    assert port['delta_pt']==[-2,0]
    assert any(i['code']=='arrow_terminal_not_exact' and 'required_pt' in i for i in issues)


def mixed_spec(tmp_path):
    source=tmp_path/'source';source.mkdir()
    image=source/'photo.png';Image.new('L',(30,20),128).save(image)
    spec={'id':'mixed-link','author':'Synthetic','kind':'scene','version':1,'synthetic':True,
          'width_pt':270,'height_pt':100,'policy':{'column':'single','design_font_size_pt':8,'export_crop_padding_pt':4},
          'sources':[{'path':'photo.png','sha256':digest_file(image)}],
          'nodes':[{'id':'left','rect':[10,10,80,85],'container':True},
                   {'id':'right','rect':[180,10,250,85],'container':True},
                   {'id':'a','text':'输入'},{'id':'b','text':'输出'}],
          'measured_groups':[{'id':'la','nodes':['a'],'axis':'row','origin':[20,25]},
                             {'id':'rb','nodes':['b'],'axis':'row','origin':[190,25]}],
          'texts':[{'id':'lt','text':'输入分区','x':45,'y':17},{'id':'rt','text':'输出分区','x':215,'y':17}],
          'assets':[{'id':'photo','path':'photo.png','source_kind':'raster','clip':[0,0,30,20],'target':[190,55,220,75]}],
          'connections':[{'id':'ab','from':'a','to':'b','from_port':'right','to_port':'left','arrow':True,'auto_route':True}],
          'mixed_layout':[{'id':'panels','axis':'row','origin':[10,10],
                           'groups':[{'container':'left','nodes':['a'],'texts':['lt'],'assets':[]},
                                     {'container':'right','nodes':['b'],'texts':['rt'],'assets':['photo']}]}]}
    return source,spec


def test_mixed_group_moves_image_text_container_and_connection_together(reg,tmp_path):
    # Given a source-bound image and two confirmed regions.
    source,spec=mixed_spec(tmp_path)
    # When compiled through the existing entry after embedding assets.
    with closing(Assets()) as assets:
        scene=compile_figure(spec,reg,assets,source)
    # Then all members share one translation and the arrow remains bound.
    nodes={n['id']:n for n in scene.nodes}
    dx=nodes['right']['rect'][0]-180
    assert dx<0
    assert scene.assets[0]['rect'][0]==pytest.approx(190+dx)
    assert next(t for t in scene.texts if t['id']=='rt')['x']==pytest.approx(215+dx)
    assert nodes['b']['rect'][0]==pytest.approx(190+dx)
    assert not audit_scene(scene)


def test_undeclared_image_is_not_silently_left_behind(reg,tmp_path):
    # Given an incomplete semantic group, when laid out, then name the missing object.
    source,spec=mixed_spec(tmp_path);spec['mixed_layout'][0]['groups'][1]['assets']=[]
    with closing(Assets()) as assets,pytest.raises(FigureError) as error:
        compile_figure(spec,reg,assets,source)
    assert error.value.code=='mixed_layout_unbound_members'
    assert 'photo' in str(error.value.details)


def test_mixed_render_preserves_source_and_passes_actual_pdf_checks(reg,tmp_path):
    # Given the complete confirmed scene, when rendered, then verify the real artifact.
    source,spec=mixed_spec(tmp_path);original=digest_file(source/'photo.png')
    with closing(Assets()) as assets:
        report=render_one(spec,reg,assets,source,tmp_path/'output')
    assert report['mechanical_checks_passed']
    assert digest_file(source/'photo.png')==original
    assert report['pdf_audit']['text_multiset_exact']
    with fitz.open(tmp_path/'output'/report['output_pdf']) as pdf:
        images=pdf[0].get_images()
        assert len(images)==1
        raw=pdf.extract_image(images[0][0])
        import io
        pixels=Image.open(io.BytesIO(raw['image'])).convert('L')
        assert pixels.size==(30,20)
        assert pixels.getextrema()==(128,128)


def test_mixed_failure_rolls_back_every_member_and_canvas(reg,tmp_path):
    from copy import deepcopy
    from journal_pdf.mixed_layout import apply_mixed_layout
    # Given a compiled scene and a second ambiguous operation after a valid move.
    source,spec=mixed_spec(tmp_path);declarations=spec.pop('mixed_layout')
    with closing(Assets()) as assets:
        scene=compile_figure(spec|{'policy':{'column':'double'}},reg,assets,source)
        snapshot=deepcopy((scene.nodes,scene.texts,scene.paths,scene.width,scene.height))
        asset_rect=scene.assets[0]['rect'][:]
        bad=deepcopy(declarations[0]);bad['groups'][1]['assets']=[]
        # When a later declaration fails, then the earlier movement is also undone.
        with pytest.raises(FigureError):apply_mixed_layout(scene,[*declarations,bad])
        assert (scene.nodes,scene.texts,scene.paths,scene.width,scene.height)==snapshot
        assert scene.assets[0]['rect']==asset_rect


def test_mixed_layout_rejects_new_collision_with_unmoved_label(reg,tmp_path):
    source,spec=mixed_spec(tmp_path)
    # Given a free label in the future image position, outside both original regions.
    spec['texts'].append({'id':'obstacle','text':'固定注记','x':125,'y':65})
    with closing(Assets()) as assets,pytest.raises(FigureError) as error:
        compile_figure(spec,reg,assets,source)
    assert error.value.code=='mixed_layout_collision'


def test_bidirectional_generation_reserves_two_terminals(reg):
    spec={'nodes':[{'id':'a','text':'输入'},{'id':'b','text':'输出'}],
          'measured_groups':[{'id':'row','nodes':['a','b'],'axis':'row','origin':[10,10]}],
          'connections':[{'id':'ab','from':'a','to':'b','from_port':'right','to_port':'left','both':True,'auto_route':True}],
          'width_pt':180,'height_pt':70}
    scene=primitive(spec,reg,8);points=scene.paths[0]['points']
    assert math.dist(points[0],points[1])==pytest.approx(ARROW_LENGTH)
    assert math.dist(points[-2],points[-1])==pytest.approx(ARROW_LENGTH)
    assert not audit_scene(scene)


def test_generation_reports_all_independent_connection_errors(reg):
    spec={'width_pt':130,'height_pt':70,'nodes':[{'id':'a','rect':[10,10,40,40],'container':True},
          {'id':'b','rect':[44,10,74,40],'container':True}],
          'connections':[{'id':'short','from':'a','to':'b','from_port':'right','to_port':'left','arrow':True,'auto_route':True},
                         {'id':'missing','from':'absent','to':'b','from_port':'right','to_port':'left','arrow':True,'auto_route':True}]}
    with pytest.raises(FigureError) as error:primitive(spec,reg,8)
    assert error.value.code=='connection_generation_failed'
    assert {i['id'] for i in error.value.details['issues']}=={'short','missing'}
    assert next(i for i in error.value.details['issues'] if i['id']=='short')['required_pt']==pytest.approx(ARROW_LENGTH)
