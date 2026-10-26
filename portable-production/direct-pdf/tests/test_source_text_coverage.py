import json
from pathlib import Path

import pymupdf as fitz
import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError, digest_file
from journal_pdf.render import render_one


@pytest.mark.parametrize('mode', ['source_vector_body', 'source_mixed_body'])
def test_partial_native_relettering_does_not_certify_retained_source_text(reg, tmp_path: Path, mode: str):
    # Given: one extractable label and a tiny outline H made from filled paths.
    source_root = tmp_path / 'source'
    source_root.mkdir()
    source = source_root / 'body.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=80)
        page.draw_rect(fitz.Rect(5, 5, 95, 75), width=.5)
        for rect in [(30, 40, 30.5, 43), (32, 40, 32.5, 43), (30.5, 41.25, 32, 41.75)]:
            page.draw_rect(fitz.Rect(rect), color=None, fill=(0,))
        page.insert_text((10, 20), 'Native', fontsize=8)
        span = page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        if mode == 'source_mixed_body':
            pix = fitz.Pixmap(fitz.csRGB, (0, 0, 2, 2), False)
            pix.clear_with(100)
            xref = page.insert_image(fitz.Rect(60, 55, 65, 60), pixmap=pix)
            doc.xref_set_key(xref, 'ColorSpace', '/DeviceRGB')
            doc.update_stream(xref, bytes([100] * 12))
        doc.save(source)
    spec = {'id':'coverage', 'author':'Synthetic', 'kind':'scene', 'width_pt':100, 'height_pt':80,
            'policy':{'column':'single', 'design_font_size_pt':8, 'export_crop_padding_pt':4},
            'sources':[{'path':source.name, 'sha256':digest_file(source)}],
            'texts':[{'id':'label', 'text':'Native', 'x':30, 'y':20}],
            'assets':[{'id':'body', 'path':source.name, 'source_kind':'pdf', mode:True,
                       'clip':[0,0,100,80], 'target':[0,0,100,80],
                       'text_replacements':[{'source_text':'Native', 'source_bbox':list(span['bbox']), 'target_text_id':'label'}]}]}
    assets = Assets()
    try:
        # When: all native spans are replaced, but arbitrary source paths remain.
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, source_root, tmp_path / 'output')
        # Then: keep the diagnostic preview and actual mechanical evidence, but
        # refuse full-text approval without pretending to detect outlined glyphs.
        assert error.value.code == 'source_text_coverage'
        folder = tmp_path / 'output/Synthetic/coverage'
        report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
        assert (folder / 'coverage.pdf').is_file()
        assert report['mechanical_checks_passed'] is True
        assert report['pdf_audit']['text_multiset_exact'] is True
        assert report['overall_checks_passed'] is False
        assert report['typography_coverage']['status'] == 'unverified'
        assert report['typography_coverage']['unverified_assets'][0]['id'] == 'body'
        assert report['ready_for_publication'] is False
    finally:
        assets.close()
