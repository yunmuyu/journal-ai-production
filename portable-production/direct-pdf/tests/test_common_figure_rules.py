"""Synthetic regressions for the owner's 2026-11 vector-production corrections."""
from copy import deepcopy

import pymupdf as fitz
import pytest

from journal_pdf.assets import Assets
from journal_pdf.editorial import scale_scene
from journal_pdf.scene import Scene
from journal_pdf.scene_straighten import straighten_connections
from journal_pdf.render import render_one


@pytest.mark.parametrize('run', [
    {'text': 'f(x)', 'style': 'italic'},
    {'text': 'f(x)', 'face': 'latin_italic'},
    {'text': 'f（x）', 'style': 'italic'},
])
def test_parentheses_upright_without_erasing_variable_style_or_script(reg, run):
    run.update(scale=.7, baseline_shift_pt=2)
    original=deepcopy(run)
    measured=reg.measure([run],8,role='formula')
    for glyph in measured['glyphs']:
        assert glyph['face'].endswith('_italic') == (glyph['ch'] not in '()（）')
        assert glyph['size']==pytest.approx(5.6)
        assert glyph['y']==2
    assert run==original


def test_real_pdf_upright_parentheses_and_italic_variable(reg,tmp_path):
    spec={'id':'parentheses','author':'Synthetic','synthetic':True,'kind':'scene',
          'width_pt':100,'height_pt':50,'texts':[{'id':'label','x':50,'y':25,
          'text':[{'text':'f(x)','style':'italic'}]}]}
    assets=Assets();source=tmp_path/'source';source.mkdir()
    try:result=render_one(spec,reg,assets,source,tmp_path/'out')
    finally:assets.close()
    assert result['pdf_audit']['editable_text_font_styles_exact']
    with fitz.open(tmp_path/'out'/result['output_pdf']) as doc:
        for span in doc[0].get_texttrace():
            for char in span['chars']:
                assert ('Italic' in span['font']) == (chr(char[0]) in 'fx')


@pytest.mark.parametrize('factor',[1,.75])
def test_final_vector_strokes_include_legend_but_not_raster_pixels(reg,factor):
    scene=Scene(reg)
    scene.shape('marker',[0,0,10,10],width=.2)['source_legend_marker']=True
    scene.shape('fill-only',[20,0,30,10],width=None,fill=.5)
    scene.line('swatch',[[0,20],[30,20]],width=.2)
    scene.paths[-1]['source_legend_swatch']=True
    sentinel=object()
    scene.assets.append({'asset':sentinel,'rect':[0,30,40,50]})
    scene.finish(100,100)
    scale_scene(scene,factor)
    assert scene.nodes[0]['width']==.5 and scene.paths[0]['width']==.5
    assert scene.nodes[1]['width'] is None
    assert scene.assets[0]['asset'] is sentinel


def route_scene(reg, horizontal=True):
    scene=Scene(reg)
    scene.shape('a',[10,10,30,30])
    scene.shape('b',[70,10,90,30] if horizontal else [10,70,30,90])
    points=[[30,20],[40,20],[40,45],[60,45],[60,20],[70,20]] if horizontal else [[20,30],[20,40],[45,40],[45,60],[20,60],[20,70]]
    scene.line('edge',points,arrow=True,endpoint_nodes=['a','b'])
    scene.finish(110,110)
    return scene


@pytest.mark.parametrize('horizontal',[True,False])
def test_direct_connection_is_centre_bound_and_does_not_move_nodes(reg,horizontal):
    scene=route_scene(reg,horizontal);nodes=deepcopy(scene.nodes)
    straighten_connections(scene)
    path=scene.paths[0]
    axis=1 if horizontal else 0
    assert all(p[axis]==20 for p in path['points'])
    assert all(p['fraction']==.5 for p in path['endpoint_nodes'])
    assert scene.nodes==nodes


@pytest.mark.parametrize('protected',['shared-net','explicit-ports','source','obstacle'])
def test_straightening_does_not_break_constraints(reg,protected):
    scene=route_scene(reg)
    if protected=='shared-net':scene.paths[0]['shared_net']='bus'
    elif protected=='explicit-ports':scene.paths[0]['endpoint_nodes']=[{'node':'a','side':'right','fraction':.5},{'node':'b','side':'left','fraction':.5}]
    elif protected=='source':scene.paths[0]['source_bound']=True
    else:scene.shape('obstacle',[45,15,55,25])
    before=deepcopy(scene.paths)
    straighten_connections(scene)
    assert scene.paths==before


@pytest.mark.parametrize('protection',['explicit','fidelity'])
def test_compile_entry_preserves_source_bound_route(reg,tmp_path,protection):
    from journal_pdf.render import compile_figure
    points=[[30,20],[40,20],[40,45],[60,45],[60,20],[70,20]]
    spec={'id':'protected','kind':'scene','synthetic':True,'width_pt':110,'height_pt':110,
          'straighten_connections':True,
          'nodes':[{'id':'a','rect':[10,10,30,30]},{'id':'b','rect':[70,10,90,30]}],
          'paths':[{'id':'edge','points':points,'arrow':True,'endpoint_nodes':['a','b']}]}
    if protection=='explicit':spec['paths'][0]['source_bound']=True
    else:
        spec['sources']=[{'sha256':'a'*64}]
        spec['rebuild_fidelity']={'version':1,'source_sha256':'a'*64,
                                  'connections':{'edge':{'segments':5}}}
    assets=Assets()
    try:scene=compile_figure(spec,reg,assets,tmp_path)
    finally:assets.close()
    assert scene.paths[0]['points']==points
    assert scene.paths[0]['source_bound']
