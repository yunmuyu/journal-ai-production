import pymupdf as fitz
import pytest
from journal_pdf.export_padding import normalize_pdf_padding
from journal_pdf.common import FigureError


@pytest.mark.parametrize('crop', [False, True])
def test_edge_touching_artwork_gets_all_four_margins_without_rescaling(tmp_path, crop):
    source, result = tmp_path/'source.pdf', tmp_path/'result.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=80)
        page.draw_rect(page.rect, fill=(0, 0, 0), color=None)
        if crop:
            page.set_cropbox(fitz.Rect(10, 20, 90, 60))
        doc.save(source)
    receipt = normalize_pdf_padding(source, result)
    assert receipt['pages'][0]['measured_margins_pt'] == pytest.approx([2]*4, abs=.25)
    assert receipt['pages'][0]['source_view_pixels_identical']


def test_blank_page_does_not_produce_deliverable(tmp_path):
    source, result = tmp_path/'blank.pdf', tmp_path/'result.pdf'
    with fitz.open() as doc:
        doc.new_page(width=100, height=100)
        doc.save(source)
    with pytest.raises(FigureError):
        normalize_pdf_padding(source, result)
    assert not result.exists()


def test_fractional_media_origin_does_not_overflow_cropbox(tmp_path):
    source, result = tmp_path/'fractional.pdf', tmp_path/'result.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=112.56, height=16.497811)
        page.draw_rect(page.rect, fill=(0, 0, 0), color=None)
        doc.save(source)
    receipt = normalize_pdf_padding(source, result)
    assert receipt['pages'][0]['measured_margins_pt'] == pytest.approx([2]*4, abs=.25)
    assert receipt['pages'][0]['source_view_pixels_identical']
