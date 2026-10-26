"""A provenance-only text binding must never paint a dummy PDF viewport."""
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import compile_figure
from test_registered_pdf_text import fixture


def binding_spec(tmp_path):
    pdf,svg,registration,rows=fixture(tmp_path)
    registration['svg_path']=svg.name
    return {'id':'text-binding','author':'Synthetic','kind':'scene','width_pt':140,'height_pt':90,
            'sources':[{'path':pdf.name,'sha256':registration['pdf_sha256']},
                       {'path':svg.name,'sha256':registration['svg_sha256']}],
            'texts':[{'id':'native','text':'Native','x':70,'y':45}],
            'source_text_bindings':[{'id':'annotation','path':pdf.name,'page':0,
                                     'clip':[0,0,100,80],'text_registration':registration,
                                     'text_replacements':rows}]}


def test_registered_binding_preserves_text_evidence_without_drawing_asset(reg,tmp_path):
    # Given a complete source registration and matching editable text.
    spec=binding_spec(tmp_path);assets=Assets()
    try:
        # When compiling its explicit provenance-only binding.
        scene=compile_figure(spec,reg,assets,tmp_path)
        # Then the source evidence is recorded, with no paint or viewport.
        assert not scene.assets
        records=scene.layout_evidence['source_text_bindings']
        assert records[0]['target_text_ids']==['native']
        assert records[0]['draws_source_geometry'] is False
    finally:assets.close()


def test_text_binding_actual_pdf_has_no_dummy_viewport_or_source_graphic(reg,tmp_path):
    import pymupdf as fitz
    from journal_pdf.render import render_one
    # Given source artwork and a text-only source binding.
    source=tmp_path/'source';source.mkdir()
    spec=binding_spec(source)
    spec['policy']={'export_crop_padding_pt':4}
    assets=Assets()
    try:
        # When rendering a real PDF through the normal pipeline.
        result=render_one(spec,reg,assets,source,tmp_path/'out')
        # Then only the requested text is painted; provenance cannot add borders.
        with fitz.open(tmp_path/'out'/result['output_pdf']) as doc:
            assert doc[0].get_text().strip()=='Native'
            assert not doc[0].get_drawings()
            assert doc[0].rect.height<20
        assert result['pdf_audit']['text_multiset_exact']
        assert result['layout']['layout_evidence']['source_text_bindings'][0]['draws_source_geometry'] is False
    finally:assets.close()


@pytest.mark.parametrize('corruption',['source','target','hash'])
def test_registered_binding_rejects_changed_source_target_or_hash(reg,tmp_path,corruption):
    # Given a binding whose content or provenance has been changed.
    spec=binding_spec(tmp_path)
    if corruption=='source':spec['source_text_bindings'][0]['text_replacements'][0]['source_text']='Changed'
    elif corruption=='target':spec['texts'][0]['text']='Changed'
    else:spec['source_text_bindings'][0]['text_registration']['pdf_sha256']='0'*64
    assets=Assets()
    try:
        # When compiling, then source and target verification must reject it.
        with pytest.raises(FigureError):compile_figure(spec,reg,assets,tmp_path)
    finally:assets.close()
