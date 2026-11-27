import pymupdf as fitz

from journal_pdf.export_padding import normalize_pdf_padding


def test_export_saved_page_boxes_use_zero_origin(tmp_path):
    source = tmp_path / 'source.pdf'
    result = tmp_path / 'result.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=160)
        page.insert_text((58, 52), 'Editable text')
        page.draw_rect((55, 70, 145, 100))
        doc.save(source)

    normalize_pdf_padding(source, result)

    with fitz.open(result) as doc:
        page = doc[0]
        assert page.mediabox == page.cropbox == page.rect
        assert page.rect.tl == fitz.Point(0, 0)
        assert page.get_text().strip() == 'Editable text'
