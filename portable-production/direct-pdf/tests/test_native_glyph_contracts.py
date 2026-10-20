from pathlib import Path
import pymupdf as fitz
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError


@pytest.mark.parametrize('mutation',['duplicate','outside','truncated'])
def test_native_glyph_rejects_ambiguous_or_truncated_selection(tmp_path:Path,mutation:str):
    # Given one original stroked graphic with a bound source index.
    source=tmp_path/'source.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_rect(fitz.Rect(20,20,40,40),width=2)
        doc.save(source)
    indices=[0,0] if mutation=='duplicate' else [99] if mutation=='outside' else [0]
    clip=[20,20,40,40] if mutation=='truncated' else [15,15,45,45]
    assets=Assets()
    try:
        # When invalid provenance or a boundary that cuts real source paint is used.
        with pytest.raises(FigureError) as error:
            assets.source_vector_glyph(source,0,clip,indices)
        # Then the source contract refuses rather than rounding, trimming or deduplicating.
        assert error.value.code in ('source_glyph_indices','source_glyph_extent','source_glyph_ink_extent')
    finally:assets.close()


def test_native_glyph_rejects_unregistered_original_text_inside_selected_extent(tmp_path:Path):
    # Given real original semantic text inside a selected graphic extent.
    source=tmp_path/'source-word.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_rect(fitz.Rect(20,20,40,40),width=.7)
        page.insert_text((25,30),'P4',fontsize=8)
        doc.save(source)
    assets=Assets()
    try:
        # When only path indices are selected and the original word is unregistered.
        with pytest.raises(FigureError) as error:
            assets.source_vector_glyph(source,0,[15,15,45,45],[0])
        # Then the vector selection cannot silently discard source semantics.
        assert error.value.code=='source_icon_contains_text'
    finally:assets.close()


def test_native_glyph_registers_full_source_span_crossing_crop_edge(tmp_path:Path):
    source=tmp_path/'partial-word.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_rect(fitz.Rect(20,20,40,40),width=.7)
        page.insert_text((10,30),'P3',fontsize=8)
        doc.save(source)
        span=page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
    assets=Assets()
    try:
        with pytest.raises(FigureError,match='未登记'):
            assets.source_vector_glyph(source,0,[15,15,45,45],[0])
        body=assets.source_vector_glyph(source,0,[15,15,45,45],[0],text_replacements=[{'source_text':'P3','source_bbox':list(span['bbox']),'target_text_id':'p3'}])
        assert body.audit['text_replacements'][0]['source_bbox']==list(span['bbox'])
        assert not body.doc[0].get_text().strip()
        assert not body.doc[0].get_fonts()
    finally:assets.close()
