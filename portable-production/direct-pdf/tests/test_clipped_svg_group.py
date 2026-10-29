import json
import hashlib

import pymupdf as fitz
import pytest

from journal_pdf.common import FigureError
from journal_pdf.source_svg_groups import prepare_svg_group


def _source(tmp_path, *, clip=True, transform=''):
    source = tmp_path/'chart.svg'
    attr = ' clip-path="url(#plot)"' if clip else ''
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100pt" height="80pt" viewBox="0 0 100 80">'
        '<defs><clipPath id="plot"><rect x="10" y="10" width="80" height="60"/></clipPath></defs>'
        f'<g id="bar" {transform}><path d="M -1000 30 L 70 30 L 70 50 L -1000 50 Z" '
        f'style="fill:#336699;stroke:#000000;stroke-width:1"{attr}/></g></svg>',
        encoding='utf-8',
    )
    return source


def test_clipped_source_bar_requires_explicit_proven_viewport(tmp_path):
    source = _source(tmp_path)
    with pytest.raises(FigureError, match='裁区'):
        prepare_svg_group(source, 'bar', [10, 10, 90, 70])
    asset = prepare_svg_group(source, 'bar', [10, 10, 90, 70], clipped_viewport=True)
    receipt = json.loads(asset.receipt_json)
    assert receipt['source_clip_path_contained'] is True
    assert receipt['geometry_unchanged'] is True
    with fitz.open(stream=asset.data, filetype='pdf') as doc:
        assert len(doc[0].get_drawings()) == 1
        assert doc[0].rect == fitz.Rect(0, 0, 80, 60)


@pytest.mark.parametrize('kwargs', [{'clip': False}, {'transform': 'transform="scale(2)"'}])
def test_clipped_viewport_refuses_unproven_outside_graphics(tmp_path, kwargs):
    source = _source(tmp_path, **kwargs)
    with pytest.raises(FigureError):
        prepare_svg_group(source, 'bar', [10, 10, 90, 70], clipped_viewport=True)


def test_clipped_viewport_rejects_clip_that_cuts_source_clip(tmp_path):
    source = _source(tmp_path)
    with pytest.raises(FigureError):
        prepare_svg_group(source, 'bar', [11, 10, 90, 70], clipped_viewport=True)


def test_clipped_viewport_rejects_css_that_can_override_clip(tmp_path):
    source = _source(tmp_path)
    content = source.read_text(encoding='utf-8').replace('<defs>', '<style>path{clip-path:none}</style><defs>')
    source.write_text(content, encoding='utf-8')
    with pytest.raises(FigureError):
        prepare_svg_group(source, 'bar', [10, 10, 90, 70], clipped_viewport=True)


def test_clipped_group_survives_actual_pdf_source_path_audit(tmp_path, reg):
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one

    input_dir = tmp_path/'input'
    input_dir.mkdir()
    source = _source(input_dir)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    spec = {'version': 1, 'id': 'clip', 'author': 'synthetic', 'kind': 'scene', 'synthetic': True,
            'width_pt': 110, 'height_pt': 85,
            'sources': [{'path': source.name, 'sha256': digest, 'role': 'source'}],
            'nodes': [], 'paths': [], 'texts': [],
            'assets': [{'id': 'bar', 'path': source.name, 'source_kind': 'svg',
                        'source_svg_group': True, 'group_id': 'bar', 'clip': [10,10,90,70],
                        'target': [5,5,85,65], 'clipped_viewport': True}],
            'policy': {'column': 'single', 'design_font_size_pt': 8}}
    assets = Assets()
    try:
        result = render_one(spec, reg, assets, input_dir, tmp_path/'out')
        report = json.loads((tmp_path/'out'/'synthetic'/'clip'/'report.json').read_text(encoding='utf-8'))
        assert result['status'] == 'candidate-rendered'
        assert report['pdf_audit']['source_svg_group_paths']['placement_count'] == 1
        assert report['assets'][0]['source_clip_path_contained'] is True
    finally:
        assets.close()
