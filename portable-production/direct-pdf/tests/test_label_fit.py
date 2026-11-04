"""Labels wrap before they tilt, and the choice is measured rather than guessed."""
import pytest

from journal_pdf.common import FigureError
from journal_pdf.label_fit import plan
from journal_pdf.layouts import primitive


def widths(reg, text, size=7.0):
    return reg.measure(text, size)['width']


def test_a_label_that_fits_stays_on_one_horizontal_line(reg):
    # Given room for the whole label.
    room = widths(reg, '命令注入') + 2
    # When fitting it.
    result = plan('命令注入', width_pt=room, measure=reg.measure, size=7.0)
    # Then it is neither wrapped nor tilted.
    assert result['lines'] == ['命令注入']
    assert result['angle'] == 0
    assert result['reason'] == 'single-line-horizontal-fits'


def test_a_long_model_name_wraps_at_its_last_separator(reg):
    # Given a model name that cannot sit on one line inside a 43pt label column.
    room = 43.0
    assert widths(reg, 'DeepSeek-V4-Flash') > room
    # When fitting it.
    result = plan('DeepSeek-V4-Flash', width_pt=room, measure=reg.measure, size=7.0)
    # Then it breaks after the version prefix and stays horizontal.
    assert result['lines'] == ['DeepSeek-V4-', 'Flash']
    assert result['angle'] == 0
    assert result['reason'] == 'wrapped-two-lines-horizontal-fits'
    assert max(widths(reg, line) for line in result['lines']) <= room


def test_wrapping_never_starts_a_line_with_a_closing_punctuation(reg):
    # Given a Chinese label whose only balanced break would strand a comma.
    result = plan('阻断率，误报率', width_pt=widths(reg, '阻断率，误'), measure=reg.measure, size=7.0)
    # Then no line begins with the forbidden character.
    assert all(not line.startswith('，') for line in result['lines'])


def test_a_chinese_label_wraps_between_characters(reg):
    # Given a four-character Chinese label in a narrow single-column slot.
    room = widths(reg, '命令') + 1
    # When fitting it.
    result = plan('命令注入', width_pt=room, measure=reg.measure, size=7.0)
    # Then it breaks evenly into two horizontal lines.
    assert result['lines'] == ['命令', '注入']
    assert result['angle'] == 0


def test_tilting_is_only_used_when_wrapping_cannot_fit(reg):
    # Given a slot narrower than any single wrapped line, with tilting allowed.
    room = widths(reg, 'SQL') + 2
    # When fitting with candidate angles.
    result = plan('SQL注入', width_pt=room, measure=reg.measure, size=7.0,
                  max_lines=1, allow_angles=(0, 30, 45, 60, 90))
    # Then it tilts and reports which angle bought the fit.
    assert result['angle'] > 0
    assert result['reason'].startswith('tilted-')
    assert result['lines'] == ['SQL注入']


def test_a_label_that_cannot_fit_raises_instead_of_shrinking_type(reg):
    # Given a slot too narrow for the label at any allowed angle.
    with pytest.raises(FigureError) as captured:
        plan('DeepSeek-V4-Flash', width_pt=6.0, measure=reg.measure, size=7.0, max_lines=1)
    # Then the caller is told to fix the layout, and no font size is negotiated.
    error = captured.value.as_dict()
    assert error['code'] == 'label_does_not_fit'
    assert error['measured_width_pt'] > 6.0


@pytest.mark.parametrize('kwargs,code', [
    ({'width_pt': 0}, 'label_fit_width'),
    ({'width_pt': float('nan')}, 'label_fit_width'),
    ({'width_pt': 30, 'max_lines': 0}, 'label_fit_max_lines'),
    ({'width_pt': 30, 'allow_angles': (120,)}, 'label_fit_angle'),
])
def test_fit_parameters_are_validated(reg, kwargs, code):
    with pytest.raises(FigureError) as captured:
        plan('XSS', measure=reg.measure, size=7.0, **kwargs)
    assert captured.value.as_dict()['code'] == code


def scene_spec(texts):
    return {'id': 'fit-demo', 'author': 'Synthetic', 'kind': 'scene', 'nodes': [], 'paths': [],
            'texts': texts, 'width_pt': 120, 'height_pt': 60,
            'policy': {'column': 'single', 'design_font_size_pt': 7}}


def test_scene_text_honours_a_declared_fit_width(reg):
    # Given a scene text that declares only how much room it has.
    spec = scene_spec([{'id': 'row', 'text': 'DeepSeek-V4-Flash', 'x': 58, 'y': 30,
                        'align': 'right', 'fit': {'width_pt': 43}}])
    # When compiling it.
    scene = primitive(spec, reg, 7.0)
    # Then the stored text is the wrapped form and the decision is on record.
    assert scene.texts[0]['content'] == 'DeepSeek-V4-\nFlash'
    evidence = scene.layout_evidence['label_fit'][0]
    assert evidence['lines'] == ['DeepSeek-V4-', 'Flash']
    assert evidence['angle'] == 0
    assert evidence['availability_pt'] == 43


def test_scene_text_anchor_top_lands_the_ink_below_the_given_y(reg):
    # Given a column label anchored by its top edge instead of its centre.
    spec = scene_spec([{'id': 'col', 'text': '命令注入', 'x': 60, 'y': 50, 'align': 'center',
                        'fit': {'width_pt': 30, 'max_lines': 1, 'anchor': 'top'}}])
    # When compiling it.
    scene = primitive(spec, reg, 7.0)
    # Then the measured ink starts at the declared top edge.
    assert scene.texts[0]['position']['bbox'][1] == pytest.approx(50, abs=1.5)


@pytest.mark.parametrize('fit,code', [
    ({}, 'label_fit_declaration'),
    ({'width_pt': 30, 'unexpected': 1}, 'label_fit_declaration'),
    ({'width_pt': 30, 'anchor': 'middle'}, 'label_fit_declaration'),
    ('30', 'label_fit_declaration'),
])
def test_fit_declaration_is_validated_at_the_scene_boundary(reg, fit, code):
    spec = scene_spec([{'id': 't', 'text': 'XSS', 'x': 30, 'y': 30, 'fit': fit}])
    with pytest.raises(FigureError) as captured:
        primitive(spec, reg, 7.0)
    assert captured.value.as_dict()['code'] == code
