import collections

from journal_pdf.render import numeric_values_missing


def test_multiple_tick_values_on_one_pdf_line_are_recognized():
    expected=collections.Counter(['-0.08','-0.06','0','0.02','0.04'])
    assert numeric_values_missing(expected,'-0.08 -0.06 0 0.02 0.04\n')=={}


def test_numeric_grouping_and_number_boundaries_are_still_enforced():
    assert numeric_values_missing(collections.Counter(['12 345']),'12345\n')=={'12 345':1}
    assert numeric_values_missing(collections.Counter(['0.08'] ),'-0.08\n')=={'0.08':1}
    assert numeric_values_missing(collections.Counter(['12 345','7']),'12 345 7\n')=={}
