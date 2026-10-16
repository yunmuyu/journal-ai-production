import json
from pathlib import Path
import pytest,pymupdf as fitz
from journal_pdf.common import FigureError,resolve_source,safe_name,digest_file
from journal_pdf.assets import Assets
from journal_pdf.render import render_one,compile_figure
from journal_pdf.scene import Scene,audit_scene
from journal_pdf.batch import load_batch
from journal_pdf.server import apply_changes

@pytest.mark.parametrize('name',['../bad','a/b','CON:bad','x.','x ',None,'CON','LPT1.txt','a\nb'])
def test_unsafe_ids(name):
    with pytest.raises(FigureError):safe_name(name)


def test_source_path_escape_blocked(tmp_path):
    src=tmp_path/'src';src.mkdir();(tmp_path/'secret').write_text('s')
    with pytest.raises(FigureError):resolve_source(src,'../secret')


def test_exact_pdf_roundtrip(reg,tmp_path,simple_spec):
    source=tmp_path/'sources';source.mkdir();assets=Assets()
    r=render_one(simple_spec,reg,assets,source,tmp_path/'output')
    audit=r['pdf_audit']
    assert audit['text_multiset_exact'] and audit['all_fonts_embedded'] and audit['neutral_rgb_300dpi']
    assert audit['image_resource_count']==0 and audit['vector_drawing_count']>0
    assert not r['ai_required'] and not r['ready_for_publication']
    assert (tmp_path/'output'/r['output_pdf']).is_file()
    assert not list((tmp_path/'output').rglob('*.ai'))
    with pytest.raises(FigureError) as e:render_one(simple_spec,reg,assets,source,tmp_path/'output')
    assert e.value.code=='output_exists';assets.close()


def test_source_hash_mismatch_blocks_without_pdf(reg,tmp_path,simple_spec):
    source=tmp_path/'src';source.mkdir();(source/'a.txt').write_text('actual')
    simple_spec['sources']=[{'path':'a.txt','sha256':'0'*64}]
    a=Assets()
    with pytest.raises(FigureError) as e:render_one(simple_spec,reg,a,source,tmp_path/'out')
    assert e.value.code=='source_hash_mismatch'
    assert not list(tmp_path.rglob('*.pdf'));a.close()


def test_output_cannot_overlap_sources(reg,tmp_path,simple_spec):
    source=tmp_path/'src';source.mkdir();a=Assets()
    with pytest.raises(FigureError) as e:render_one(simple_spec,reg,a,source,source/'results')
    assert e.value.code=='output_source_overlap';a.close()


def test_unknown_figure_kind_not_silently_rendered(reg,tmp_path,simple_spec):
    simple_spec['kind']='unknown';a=Assets()
    with pytest.raises(FigureError):compile_figure(simple_spec,reg,a,tmp_path)
    a.close()


def test_text_collision_is_detected(reg):
    s=Scene(reg);s.text('a','测试',20,20);s.text('b','文字',20,20);s.finish(60,60)
    assert any(i['code']=='text_overlap' for i in audit_scene(s))


def test_line_crosses_ink_detected(reg):
    s=Scene(reg);s.text('a','测试',25,25);s.line('line',[[2,25],[48,25]]);s.finish(50,50)
    assert any(i['code']=='text_path_collision' for i in audit_scene(s))


def test_geometry_overflow_detected(reg):
    s=Scene(reg);s.box('bad','越界',-5,2,20,20);s.finish(50,50)
    assert any(i['code']=='shape_outside_page' for i in audit_scene(s))


def test_bad_batch_export_set(tmp_path,simple_spec):
    (tmp_path/'src').mkdir();(tmp_path/'one.json').write_text(json.dumps(simple_spec))
    b={'source_root':'src','specs':['one.json'],'expected_export_ids':['missing']}
    (tmp_path/'batch.json').write_text(json.dumps(b))
    with pytest.raises(FigureError):load_batch(tmp_path/'batch.json')


def test_gui_edit_is_copy_and_allowlisted(simple_spec):
    n=apply_changes(simple_spec,{'font_size':'7','column':'double'})
    assert n['policy']['font_sizes']==[7] and simple_spec['policy']['font_sizes']==[8,7,6]
    with pytest.raises(FigureError):apply_changes(simple_spec,{'source':'../private'})
    with pytest.raises(FigureError):apply_changes(simple_spec,{'font_size':'5'})


def test_batch_overlap_rejected_before_any_write(profile,tmp_path,simple_spec):
    from journal_pdf.batch import run_batch
    source=tmp_path/'src';source.mkdir()
    (tmp_path/'one.json').write_text(json.dumps(simple_spec))
    batch={'version':1,'source_root':'src','specs':['one.json'],'expected_export_ids':[simple_spec['id']]}
    path=tmp_path/'batch.json';path.write_text(json.dumps(batch))
    with pytest.raises(FigureError) as err:
        run_batch(path,profile,source/'must-not-exist',tmp_path/'cache')
    assert err.value.code=='output_source_overlap'
    assert not list(source.iterdir())


def test_gui_overlap_rejected_before_any_write(profile,tmp_path,simple_spec):
    from journal_pdf.server import serve
    source=tmp_path/'src';source.mkdir()
    (tmp_path/'one.json').write_text(json.dumps(simple_spec))
    path=tmp_path/'batch.json';path.write_text(json.dumps({'version':1,'source_root':'src','specs':['one.json'],'expected_export_ids':[simple_spec['id']]}))
    with pytest.raises(FigureError) as err:
        serve(path,profile,source/'must-not-exist',tmp_path/'cache',18781)
    assert err.value.code=='output_source_overlap'
    assert not list(source.iterdir())


def test_windows_casefold_figure_ids_rejected(tmp_path,simple_spec):
    import copy
    (tmp_path/'src').mkdir();other=copy.deepcopy(simple_spec)
    simple_spec['id']='FigureA';other['id']='figurea'
    for name,spec in [('one.json',simple_spec),('two.json',other)]:
        (tmp_path/name).write_text(json.dumps(spec))
    path=tmp_path/'batch.json';path.write_text(json.dumps({'version':1,'source_root':'src','specs':['one.json','two.json'],'expected_export_ids':['FigureA','figurea']}))
    with pytest.raises(FigureError) as err:load_batch(path)
    assert err.value.code=='casefold_figure_collision'


def test_review_identity_rejects_stale_inputs(profile,tmp_path,simple_spec):
    from journal_pdf.server import validate_review_identity
    from journal_pdf.common import digest_json,read_json
    manifest={'version':1,'specs':['one.json']};specs=[simple_spec];path=tmp_path/'batch.json'
    from journal_pdf.editorial import engine_signature
    r={'engine_signature':engine_signature(),'source_batch':str(path.resolve()),'batch_signature':digest_json({'manifest':manifest,'specs':specs}),
       'font_profile_signature':digest_json(read_json(profile))}
    validate_review_identity(r,path,manifest,specs,profile)
    r['batch_signature']='old'
    with pytest.raises(FigureError) as err:validate_review_identity(r,path,manifest,specs,profile)
    assert err.value.code=='review_inputs_changed'
    r['batch_signature']=digest_json({'manifest':manifest,'specs':specs});r['font_profile_signature']='old'
    with pytest.raises(FigureError) as err:validate_review_identity(r,path,manifest,specs,profile)
    assert err.value.code=='review_font_profile_changed'


def test_empty_failure_gallery_not_claimed_complete():
    from journal_pdf.gallery import gallery_html
    html=gallery_html({'results':[],'failures':[{'id':'blocked-figure','error':{'message':'missing source'}}]})
    assert 'blocked-summary' in html and '本批尚无可查看的成功候选' in html
    assert '先修正制作说明' in html
