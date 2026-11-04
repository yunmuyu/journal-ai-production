import pytest

from journal_pdf.assets import unit_length_svg_transform


@pytest.mark.parametrize('transform', ['', 'translate(10 20)', 'matrix(1,0,0,-1,0,595.2)', 'translate(2) matrix(0,1,-1,0,0,0)'])
def test_length_preserving_transform_keeps_stroke_units(transform):
    assert unit_length_svg_transform(transform)


@pytest.mark.parametrize('transform', ['matrix(2,0,0,2,0,0)', 'matrix(1,1,0,1,0,0)', 'scale(1)', 'matrix(1,0,0,-1,0,nan)', 'translate(1,2,3)'])
def test_scale_shear_or_unrecognized_transform_still_rejects(transform):
    assert not unit_length_svg_transform(transform)
