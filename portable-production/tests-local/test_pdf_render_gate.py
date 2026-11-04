from pathlib import Path

import pymupdf as fitz
import pytest

from localflow.core import FlowError
from localflow.pdf_compat import audit_pdf_compatibility
from localflow.pdf_render import audit_pdf_render


def test_rejects_broken_flate_stream_even_when_page_count_is_readable(tmp_path: Path) -> None:
    # Given: a synthetic vector page with a corrupt compressed content stream.
    path = tmp_path / "broken.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=100)
        page.draw_rect(fitz.Rect(10, 10, 60, 60))
        stream = page.get_contents()[0]
        doc.update_stream(stream, b"not a zlib stream", compress=False)
        doc.xref_set_key(stream, "Filter", "/FlateDecode")
        doc.save(path)
    with fitz.open(path) as doc:
        assert len(doc) == 1
    # When / Then: compatibility must not promote a readable but unrenderable file.
    with pytest.raises(FlowError, match="PDF.*渲染"):
        audit_pdf_compatibility(path)


def test_valid_vector_pdf_records_actual_render_coverage(tmp_path: Path) -> None:
    # Given: two synthetic pages with no external fonts or manuscript assets.
    path = tmp_path / "valid.pdf"
    with fitz.open() as doc:
        for _ in range(2):
            page = doc.new_page(width=100, height=100)
            page.draw_rect(fitz.Rect(10, 10, 60, 60))
        doc.save(path)
    # When
    report = audit_pdf_compatibility(path)
    # Then
    assert report["render_check"]["passed"] is True
    assert report["render_check"]["rendered_pages"] == 2


def test_rejects_corrupt_embedded_font_instead_of_system_substitution(tmp_path: Path) -> None:
    # Given: embed a library-provided font, then damage only its font stream.
    path = tmp_path / "broken-font.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_font(fontname="fixture", fontbuffer=fitz.Font("cjk").buffer)
        page.insert_text((30, 30), "Synthetic font", fontname="fixture")
        descriptor = next(x for x in range(1, doc.xref_length())
                          if doc.xref_get_key(x, "Type") == ("name", "/FontDescriptor"))
        font_stream = next(int(doc.xref_get_key(descriptor, k)[1].split()[0])
                           for k in ("FontFile", "FontFile2", "FontFile3")
                           if doc.xref_get_key(descriptor, k)[0] == "xref")
        doc.update_stream(font_stream, b"not compressed font data", compress=False)
        doc.xref_set_key(font_stream, "Filter", "/FlateDecode")
        doc.save(path)
    # When
    report = audit_pdf_render(path)
    # Then
    assert not report.passed
    assert "zlib" in report.error


def test_rejects_missing_pdf_without_false_success(tmp_path: Path) -> None:
    # Given / When
    report = audit_pdf_render(tmp_path / "missing.pdf")
    # Then
    assert not report.passed
    assert report.rendered_pages == 0


@pytest.mark.parametrize("corrupt_content", [False, True])
def test_classifies_outline_diagnostics_without_allowing_repaired_pages(
    tmp_path: Path, corrupt_content: bool,
) -> None:
    # Given: a vector page whose outline Last points to a child, not a sibling.
    path = tmp_path / "outline.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=150, height=100)
        page.draw_rect(fitz.Rect(10, 10, 60, 60))
        doc.set_toc([[1, "Parent", 1], [2, "Child", 1]])
        outline = int(doc.xref_get_key(doc.pdf_catalog(), "Outlines")[1].split()[0])
        first = int(doc.xref_get_key(outline, "First")[1].split()[0])
        doc.xref_set_key(outline, "Last", doc.xref_get_key(first, "First")[1])
        if corrupt_content:
            stream = page.get_contents()[0]
            doc.update_stream(stream, b"not a zlib stream", compress=False)
            doc.xref_set_key(stream, "Filter", "/FlateDecode")
        doc.save(path)
    # When: the public wrapper must preserve the worker's diagnostic category.
    report = audit_pdf_render(path)
    # Then: both are blocked; mixed decoder errors must not become structure-only.
    assert not report.passed
    assert report.rendered_pages == report.page_count == 1
    expected = "pdf_decoder" if corrupt_content else "pdf_structure"
    assert report.diagnostic_kind == expected
    with pytest.raises(FlowError) as error:
        audit_pdf_compatibility(path)
    assert error.value.code == expected
