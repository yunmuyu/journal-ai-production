from pathlib import Path

import pymupdf as fitz
import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError, digest_file
from journal_pdf.render import render_one


def artwork(path: Path, *, hole: bool = True):
    with fitz.open() as doc:
        page = doc.new_page(width=60, height=40)
        page.draw_rect((10, 8, 50, 32), color=None, fill=(0.3,))
        if hole:
            page.draw_rect((20, 16, 40, 26), color=None, fill=(1,))
        doc.save(path)


def specification(tmp_path: Path):
    artwork(tmp_path / 'original.pdf')
    artwork(tmp_path / 'prepared.pdf')
    return {
        'version': 1, 'id': 'reference', 'author': 'Synthetic', 'kind': 'scene',
        'width_pt': 100, 'height_pt': 70, 'nodes': [], 'paths': [], 'texts': [],
        'policy': {'require_original_asset_reference': True},
        'sources': [{'path': 'original.pdf', 'sha256': digest_file(tmp_path / 'original.pdf'),
                     'role': 'original-artwork'}],
        'assets': [{'id': 'icon', 'path': 'prepared.pdf', 'source_kind': 'pdf',
                    'clip': [0, 0, 60, 40], 'target': [10, 10, 70, 50],
                    'original_reference': {'path': 'original.pdf', 'page': 0,
                                           'clip': [0, 0, 60, 40]}}],
    }


@pytest.mark.parametrize('mutation,code', [
    ('hole', 'original_asset_pixels_changed'),
    ('crop', 'original_asset_pixels_changed'),
    ('missing', 'original_asset_reference_missing'),
    ('unbound', 'original_asset_reference_unbound'),
    ('extra-frame', 'original_asset_pixels_changed'),
    ('shifted-crop', 'original_asset_pixels_changed'),
    ('disabled-policy', 'original_asset_reference_missing'),
    ('bad-clip', 'original_asset_reference_input'),
])
def test_bad_derivative_is_blocked_before_output(tmp_path, reg, mutation, code):
    # Given: an independently registered original, not the derivative's own hash.
    sources = tmp_path / 'sources'; sources.mkdir()
    spec = specification(sources)
    if mutation == 'hole':
        (sources / 'prepared.pdf').unlink()
        artwork(sources / 'prepared.pdf', hole=False)
    elif mutation == 'crop':
        spec['assets'][0]['clip'] = [10, 8, 50, 32]
        spec['assets'][0]['target'] = [10, 10, 70, 46]
    elif mutation == 'missing':
        del spec['assets'][0]['original_reference']
    elif mutation == 'unbound':
        spec['assets'][0]['original_reference']['path'] = 'prepared.pdf'
    elif mutation == 'extra-frame':
        with fitz.open(sources / 'prepared.pdf') as doc:
            doc[0].draw_rect((2, 2, 58, 38), width=1)
            doc.saveIncr()
    elif mutation == 'shifted-crop':
        spec['assets'][0]['clip'] = [3, 2, 57, 38]
    elif mutation == 'disabled-policy':
        spec['policy']['require_original_asset_reference'] = False
        del spec['assets'][0]['original_reference']
    elif mutation == 'bad-clip':
        spec['assets'][0]['original_reference']['clip'][0] = True
    spec['sources'].append({'path': 'prepared.pdf', 'sha256': digest_file(sources / 'prepared.pdf'), 'role': 'derived'})
    assets = Assets()
    try:
        # When: the public renderer receives the mutated asset.
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, sources, tmp_path / 'out')
        # Then: no candidate PDF is emitted.
        assert error.value.code == code
        assert not list((tmp_path / 'out').rglob('*.pdf'))
    finally:
        assets.close()


def test_prepared_raster_still_requires_original_comparison(tmp_path, reg):
    sources = tmp_path / 'sources'; sources.mkdir()
    spec = specification(sources)
    with fitz.open(sources / 'prepared.pdf') as doc:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(10, 10), alpha=False)
        pix.save(sources / 'prepared.png')
    spec['assets'][0].update(path='prepared.png', source_kind='raster', clip=[0, 0, 600, 400])
    spec['sources'].append({'path': 'prepared.png', 'sha256': digest_file(sources / 'prepared.png'), 'role': 'derived'})
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, sources, tmp_path / 'out')
        assert report['original_asset_references'][0]['changed_fraction'] <= 0.001
    finally:
        assets.close()


def test_complete_derivative_gets_original_receipt(tmp_path, reg):
    sources = tmp_path / 'sources'; sources.mkdir()
    spec = specification(sources)
    spec['sources'].append({'path': 'prepared.pdf', 'sha256': digest_file(sources / 'prepared.pdf'), 'role': 'derived'})
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, sources, tmp_path / 'out')
        assert report['mechanical_checks_passed']
        assert report['original_asset_reference_coverage']['status'] == 'complete'
        pdf = next((tmp_path / 'out').rglob('*.pdf'))
        with fitz.open(pdf) as doc:
            assert len(doc) == 1
        assert report['original_asset_references'][0]['source_sha256'] == spec['sources'][0]['sha256']
    finally:
        assets.close()


def test_deleted_second_dashed_rule_is_blocked(tmp_path, reg):
    sources = tmp_path / 'sources'; sources.mkdir()
    spec = specification(sources)
    for filename, levels in [('original.pdf', (5, 35)), ('prepared.pdf', (5,))]:
        with fitz.open(sources / filename) as doc:
            for y in levels:
                doc[0].draw_line((2, y), (58, y), width=.5, dashes='[2 2] 0')
            doc.saveIncr()
    spec['sources'][0]['sha256'] = digest_file(sources / 'original.pdf')
    spec['sources'].append({'path': 'prepared.pdf', 'sha256': digest_file(sources / 'prepared.pdf'), 'role': 'derived'})
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, sources, tmp_path / 'out')
        assert error.value.code == 'original_asset_pixels_changed'
    finally:
        assets.close()
