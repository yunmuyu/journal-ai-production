import copy

import pymupdf as fitz
from PIL import Image, ImageDraw
import pytest

from journal_pdf.assets import Assets
from journal_pdf.agent_spec import compile_reply_figure
from journal_pdf.charts import tick_content
from journal_pdf.common import FigureError, digest_file
from journal_pdf.render import compile_figure, render_one
from journal_pdf.scientific_text import power_of_ten


@pytest.mark.parametrize('exponent,expected', [(-3, '-3'), (-2, '-2'), (-1, '-1'),
                                               (0, '0'), (2, '2'), (12, '12')])
def test_power_of_ten_has_true_reduced_superscript(exponent, expected):
    base, script = power_of_ten(exponent)
    assert base == {'text': '10', 'style': 'regular'}
    assert script == {'text': expected, 'style': 'regular', 'scale': 0.7,
                      'baseline_shift_pt': -3.2}
    assert '−' not in script['text']
    assert not any(char in script['text'] for char in '⁻⁰¹²³⁴⁵⁶⁷⁸⁹')


def test_explicit_fractional_base_size_and_script_scale():
    assert power_of_ten(-12, base_size_pt=7.5, exponent_scale=0.6)[1] == {
        'text': '-12', 'style': 'regular', 'scale': 0.6, 'baseline_shift_pt': -3.0,
    }
    first = power_of_ten(-1)
    first[1]['text'] = 'changed'
    assert power_of_ten(-1)[1]['text'] == '-1'


@pytest.mark.parametrize('value', [True, False, 1.0, -1.5, '−1', '-1', None, [], {}])
def test_exponent_requires_explicit_integer_semantics(value):
    with pytest.raises(FigureError) as caught:
        power_of_ten(value)
    assert caught.value.code == 'scientific_exponent_invalid'


@pytest.mark.parametrize('value', [True, False, 0, 5.9, 8.1, float('inf'),
                                  float('-inf'), float('nan'), '8', None, [], {}])
def test_invalid_base_size_is_not_silently_coerced(value):
    with pytest.raises(FigureError) as caught:
        power_of_ten(-1, base_size_pt=value)
    assert caught.value.code == 'font_size_out_of_policy'


@pytest.mark.parametrize('value', [True, False, 0, -0.7, 1, 1.2, float('inf'),
                                  float('nan'), '0.7', None, [], {}])
def test_script_must_be_finite_positive_and_smaller_than_base(value):
    with pytest.raises(FigureError) as caught:
        power_of_ten(-1, exponent_scale=value)
    assert caught.value.code == 'scientific_exponent_scale_invalid'


@pytest.mark.parametrize('text', ['10⁻¹', '10^−1', '10^-1'])
def test_explicit_log_tick_preserves_value_with_editorial_unary_sign(text):
    tick = {'text': text, 'power10': -1, 'position': 99}
    original = copy.deepcopy(tick)
    assert tick_content(tick) == power_of_ten(-1)
    assert tick == original
    assert tick_content(tick, 7.5) == power_of_ten(-1, 7.5)


@pytest.mark.parametrize('tick,code', [
    ({'text': '10⁻¹', 'power10': -2}, 'tick_power10_mismatch'),
    ({'text': '0.1', 'power10': -1}, 'tick_power10_mismatch'),
    ({'text': '10-1', 'power10': -1}, 'tick_power10_mismatch'),
    ({'text': '10⁻¹', 'power10': True}, 'scientific_exponent_invalid'),
    ({'text': '10⁻¹', 'power10': -1, 'number': '10'}, 'tick_semantics_conflict'),
    ({'text': '10⁻¹', 'power10': -1, 'suffix': ''}, 'tick_semantics_conflict'),
])
def test_log_tick_semantics_reject_mismatch_and_ambiguous_coercion(tick, code):
    with pytest.raises(FigureError) as caught:
        tick_content(tick)
    assert caught.value.code == code


def test_unannotated_log_tick_is_not_guessed():
    with pytest.raises(FigureError) as caught:
        tick_content({'text': '10⁻¹'})
    assert caught.value.code == 'numeric_label_not_number'


def _semantic_chart_fixture(source_root):
    # These coordinates describe synthetic source evidence only. Output label
    # positions and the font size are derived by the existing production entry.
    source_root.mkdir()
    path = source_root / 'synthetic.png'
    image = Image.new('RGB', (500, 400), 'white')
    draw = ImageDraw.Draw(image)
    draw.line([(50, 30), (50, 330), (450, 330)], fill='black', width=2)
    draw.line([(100, 60), (140, 60)], fill='black', width=2)
    image.save(path)
    source = {'id': 'source-1', 'snapshot': path.name, 'sha256': digest_file(path)}
    page = {
        'id': 'image-1', 'kind': 'raster',
        'geometry': {
            'axes': [{
                'id': 'axis', 'frame': [50, 30, 450, 330],
                'plot_clip': [48, 28, 454, 334],
                'x_ticks': [{'id': 'x0', 'position': 50, 'label_candidate': True},
                            {'id': 'x1', 'position': 450, 'label_candidate': True}],
                'y_ticks': [{'id': f'y{index}', 'position': 30 + index * 150,
                             'label_candidate': True} for index in range(3)],
            }],
            'legend_rows': [{'id': 'legend', 'rect': [100, 50, 180, 70],
                             'swatch_clip': [100, 59, 141, 62]}],
        },
    }
    reply = {
        'id': 'scientific-tick-typography', 'author': 'Synthetic',
        'kind': 'raster-chart', 'axis_ref': 'axis',
        'review': {'source_checked': True, 'labels_checked': True,
                   'inward_ticks_confirmed': True},
        'x_ticks': [{'ref': 'x0', 'text': '0'}, {'ref': 'x1', 'text': '1'}],
        'y_ticks': [{'ref': f'y{index}', 'text': text, 'power10': -index - 1}
                    for index, text in enumerate(('10⁻¹', '10⁻²', '10⁻³'))],
        'x_title': '注入物理噪声概率（%）',
        # BER is an explicit quantity abbreviation, not a unit guessed by the
        # generic unit parser from arbitrary parentheses.
        'y_title': '误码率/BER',
        'legend_rows': [{'ref': 'legend', 'series_id': 'one', 'label': 'One'}],
        'mask_review': {'approved_empty_background': True,
                        'reason': 'Synthetic legend swatch on an otherwise blank background'},
    }
    return reply, source, page


@pytest.mark.parametrize('replacement,code', [
    ({'power10': -2}, 'tick_power10_mismatch'),
    ({'power10': -1.0}, 'scientific_exponent_invalid'),
    ({'number': '10'}, 'tick_semantics_conflict'),
    ({'position': 999}, 'tick_schema'),
])
def test_production_entry_rejects_conflicting_or_unbound_log_tick_semantics(tmp_path, replacement, code):
    reply, source, page = _semantic_chart_fixture(tmp_path / 'source')
    reply['y_ticks'][0].update(replacement)
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code == code


def test_both_chart_axes_measure_and_draw_scripts_at_current_fractional_size(reg, tmp_path):
    reply, source, page = _semantic_chart_fixture(tmp_path / 'source')
    reply['policy'] = {'design_font_size_pt': 7.5}
    reply['x_ticks'][0].update({'text': '10⁻¹', 'power10': -1})
    from journal_pdf.common import digest_json
    with pytest.raises(FigureError) as caught:
        compile_reply_figure(reply, source, page)
    assert caught.value.code == 'production_font_policy_required'
    exception = {'reply_sha256': digest_json(reply), 'source_sha256': source['sha256'],
                 'design_font_size_pt': 7.5,
                 'reason': 'Synthetic regression of measured scripts under an explicit size exception',
                 'evidence_ref': 'synthetic-test:approved-fractional-size'}
    spec = compile_reply_figure(reply, source, page, production_policy_exception=exception)
    assets = Assets()
    try:
        scene = compile_figure(spec, reg, assets, tmp_path / 'source')
    finally:
        assets.close()
    assert scene.size == 7.5
    for object_id in ('xtick0', 'ytick0', 'ytick1', 'ytick2'):
        text = next(item for item in scene.texts if item['id'] == object_id)
        glyphs = text['measurement']['glyphs']
        assert [glyph['size'] for glyph in glyphs] == pytest.approx([7.5, 7.5, 5.25, 5.25])
        assert [glyph['y'] for glyph in glyphs] == pytest.approx([0, 0, -3, -3])


def test_production_entry_exports_default8_and_reduced_mathematical_scripts(reg, tmp_path):
    source = tmp_path / 'source'
    reply, source_evidence, page_evidence = _semantic_chart_fixture(source)
    before = copy.deepcopy(reply)
    spec = compile_reply_figure(reply, source_evidence, page_evidence)
    assert reply == before and 'policy' not in reply
    assert spec['policy']['design_font_size_pt'] == 8
    assert [tick['position'] for tick in spec['y_ticks']] == [30, 180, 330]
    assert [tick['text'] for tick in spec['y_ticks']] == ['10⁻¹', '10⁻²', '10⁻³']
    assets = Assets()
    try:
        result = render_one(spec, reg, assets, source, tmp_path / 'output')
    finally:
        assets.close()
    assert result['layout']['layout_evidence']['whole_artwork_scale'] == 1
    assert all(item['font_size_pt'] == 8 for item in result['layout']['texts'])
    with fitz.open(tmp_path / 'output' / result['output_pdf']) as document:
        page = document[0]
        spans = [span for block in page.get_text('dict')['blocks']
                 for line in block.get('lines', []) for span in line['spans']]
        bases = [span for span in spans if span['text'] == '10']
        scripts = [span for span in spans if span['text'] in ('-1', '-2', '-3')]
        assert len(bases) == len(scripts) == 3
        assert all(span['size'] == pytest.approx(8) for span in bases)
        assert all(span['size'] == pytest.approx(5.6) for span in scripts)
        for base, script in zip(bases, scripts):
            assert base['origin'][1] - script['origin'][1] == pytest.approx(3.2, abs=0.001)
            assert script['origin'][0] > base['origin'][0]
        text = ''.join(page.get_text().split())
        assert '注入物理噪声概率/%' in text
        assert '误码率/BER' in text
        assert '（' not in text and '）' not in text and '−' not in text
        ordinary_spans = [span for span in spans if span not in bases and span not in scripts]
        assert ordinary_spans and all(span['size'] == pytest.approx(8) for span in ordinary_spans)
