import copy

import pytest

from journal_pdf.editorial import display_content


@pytest.mark.parametrize(('source', 'expected'), [
    ('−j', '-j'), ('−1', '-1'), ('−0.2', '-0.2'),
    ('a − b', 'a − b'), ('a - b', 'a − b'),
    ('a − −j', 'a − -j'), ('(−j) / √2', '(-j) / √2'),
    ('10^−2', '10^-2'), ('1.25e−3', '1.25e-3'),
    ('a\n−j', 'a\n-j'), ('−1～−2', '-1～-2'),
])
def test_formula_distinguishes_unary_sign_from_subtraction(source, expected):
    assert display_content(source, 'formula') == expected
    assert display_content(expected, 'formula') == expected


def test_rich_formula_classification_crosses_runs_without_changing_style_or_input():
    source = [{'text': 'a', 'style': 'italic'}, {'text': ' - '},
              {'text': '−'}, {'text': 'j', 'style': 'italic'}]
    original = copy.deepcopy(source)
    expected = copy.deepcopy(source)
    expected[1]['text'] = ' − '
    expected[2]['text'] = '-'
    assert display_content(source, 'formula') == expected
    assert source == original


@pytest.mark.parametrize('role', ['axis-tick', 'numeric-value', 'number'])
def test_numeric_display_uses_short_negative_sign_and_keeps_precision(role):
    assert display_content('−1000.002000', role) == '-1 000.002 000'


@pytest.mark.parametrize('role', ['code', 'command', 'path', 'literal'])
def test_literal_roles_are_not_rewritten(role):
    source = [{'text': '−1 a-b C:/x-y', 'style': 'italic'}]
    assert display_content(source, role) == source


@pytest.mark.parametrize('source', ['STM32-F103', '2026-11-03', 'Wi-Fi', 'a-b', '输入-输出'])
def test_ordinary_label_hyphens_are_not_subtraction(source):
    assert display_content(source, 'label') == source


def test_real_matrix_and_fraction_runs_use_short_unary_signs(reg):
    source = [{'text': '−'}, {'text': 'j', 'style': 'italic'}]
    assert reg.measure(source, 8, role='formula')['text'] == '-j'
    assert reg.measure('−1', 8, role='formula')['text'] == '-1'
