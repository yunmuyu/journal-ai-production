import hashlib
import shutil

import pymupdf as fitz

from journal_pdf.assets import Assets
from journal_pdf.render import render_one


def test_scene_text_keeps_new_glyphs_after_imported_pdf(reg, tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    assets = Assets()
    try:
        panel = {
            'version': 1, 'id': 'panel', 'author': 'test', 'kind': 'scene',
            'synthetic': True, 'width_pt': 100, 'height_pt': 40,
            'texts': [{'id': 'old', 'text': 'mAP', 'x': 50, 'y': 20}],
            'policy': {'column': 'single', 'design_font_size_pt': 8},
        }
        result = render_one(panel, reg, assets, source, tmp_path / 'panel-out')
        panel_pdf = tmp_path / 'panel-out' / result['output_pdf']
        imported = source / 'panel.pdf'
        shutil.copyfile(panel_pdf, imported)
        with fitz.open(imported) as document:
            box = list(document[0].rect)
        spec = {
            'version': 1, 'id': 'combined', 'author': 'test', 'kind': 'scene',
            'width_pt': 110, 'height_pt': 80,
            'sources': [{'path': 'panel.pdf', 'sha256': hashlib.sha256(imported.read_bytes()).hexdigest()}],
            'assets': [{'id': 'panel', 'path': 'panel.pdf', 'source_kind': 'pdf',
                        'clip': box, 'target': [0, 0, box[2], box[3]], 'role': 'plot'}],
            'texts': [{'id': 'new', 'text': 'BCD', 'x': 40, 'y': 60}],
            'policy': {'column': 'single', 'design_font_size_pt': 8},
        }
        combined = render_one(spec, reg, assets, source, tmp_path / 'combined-out')
        with fitz.open(tmp_path / 'combined-out' / combined['output_pdf']) as document:
            text = document[0].get_text()
        assert 'mAP' in text and 'BCD' in text
    finally:
        assets.close()
