"""Real-PDF regression for declared styles, including mixed same-letter faces."""
import copy
import json
import os
from pathlib import Path

import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf import render


@pytest.mark.parametrize('tamper', [False, True])
@pytest.mark.parametrize('angle', [0, 90, 30])
def test_real_pdf_gate_checks_each_declared_italic_glyph(reg, tmp_path, monkeypatch, tamper, angle):
    # Given one italic q, another correct italic z, and regular text.
    source = tmp_path / 'source'
    source.mkdir()
    spec = {'id': 'styles', 'author': 'Synthetic', 'synthetic': True,
            'kind': 'scene', 'width_pt': 150, 'height_pt': 80,
            'texts': [{'id': 'label', 'x': 75, 'y': 40, 'rotation': angle,
                       'text': [{'text': 'q', 'style': 'italic'}, {'text': '=0.92 q '},
                                {'text': 'z', 'style': 'italic'}, {'text': '=1'}]}]}
    if tamper:
        original = render.draw_text

        def wrong_q_only(page, registry, item):
            changed = copy.deepcopy(item)
            for glyph in changed['measurement']['glyphs']:
                if glyph['ch'] == 'q':
                    glyph['face'] = 'latin'
            original(page, registry, changed)

        monkeypatch.setattr(render, 'draw_text', wrong_q_only)
    assets = Assets()
    try:
        # When the renderer writes and independently inspects the actual PDF.
        if tamper:
            with pytest.raises(FigureError) as error:
                render.render_one(spec, reg, assets, source, tmp_path / 'out')
            # Then an italic font elsewhere cannot hide q's wrong face.
            assert error.value.code == 'actual_pdf_audit_failed'
            audit = error.value.details['audit']
            assert audit['text_multiset_exact'] and audit['all_fonts_embedded']
            assert not audit['editable_text_font_styles_exact']
            assert audit['text_font_styles']['issues'][0]['character'] == 'q'
        else:
            result = render.render_one(spec, reg, assets, source, tmp_path / 'out')
            assert result['pdf_audit']['editable_text_font_styles_exact']
    finally:
        assets.close()


@pytest.mark.parametrize('font, count, expected', [
    ('ABCDEF+TimesNewRomanPS-ItalicMT', 1, True),
    ('UnknownAlias', 1, False),
    ('TimesNewRomanPS-ItalicMT', 2, False),
])
def test_subset_prefix_is_allowed_but_unknown_or_ambiguous_match_fails(font, count, expected):
    from journal_pdf.pdf_font_styles import audit_pdf_font_styles
    # Given an explicitly placed italic glyph and its candidate trace(s).
    item = {'id': 'q', 'position': {'offset': [10, 20], 'rotation': 0},
            'measurement': {'glyphs': [{'ch': 'q', 'face': 'latin_italic',
                                       'size': 8, 'x': 0, 'y': 0}]}}
    trace = {'font': font, 'size': 8, 'dir': [1, 0],
             'chars': [(ord('q'), 1, [10, 20], [10, 12, 14, 22])]}
    # When checking per-glyph font identity, then only a proven unique match passes.
    audit = audit_pdf_font_styles([item], [trace] * count,
                                 {'latin_italic': 'TimesNewRomanPS-ItalicMT'})
    assert audit['ok'] is expected


def test_real_pdf_supports_all_configured_font_styles(profile, tmp_path):
    from journal_pdf.fonts import FontRegistry
    # Given explicit installed fonts for the optional bold and bolditalic roles.
    bold = Path(os.environ.get('JFW_TEST_TNR_BOLD', 'C:/Windows/Fonts/timesbd.ttf'))
    bolditalic = Path(os.environ.get('JFW_TEST_TNR_BOLDITALIC', 'C:/Windows/Fonts/timesbi.ttf'))
    if not bold.is_file() or not bolditalic.is_file():
        pytest.skip('Explicit bold/bolditalic test font paths unavailable')
    config = json.loads(profile.read_text(encoding='utf-8'))
    config['faces']['latin_bold'] = {'path': str(bold)}
    config['faces']['latin_bolditalic'] = {'path': str(bolditalic)}
    config_path = tmp_path / 'fonts.json'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    registry = FontRegistry(config_path, tmp_path / 'cache')
    assets = Assets()
    source = tmp_path / 'source'
    source.mkdir()
    spec = {'id': 'four-styles', 'author': 'Synthetic', 'synthetic': True,
            'kind': 'scene', 'width_pt': 100, 'height_pt': 60,
            'texts': [{'id': 'styles', 'x': 50, 'y': 30,
                       'text': [{'text': 'q', 'style': style}
                                for style in ['regular', 'italic', 'bold', 'bolditalic']]}]}
    try:
        # When rendering a real mixed-style PDF, then every declared face passes.
        result = render.render_one(spec, registry, assets, source, tmp_path / 'out')
        assert result['pdf_audit']['editable_text_font_styles_exact']
        assert result['pdf_audit']['text_font_styles']['checked_scene_characters'] == 4
    finally:
        assets.close()
        registry.close()
