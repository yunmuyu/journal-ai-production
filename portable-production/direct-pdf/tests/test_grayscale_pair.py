from pathlib import Path
import pytest
from journal_pdf.assets import svg_root, geometry_signature, indistinct_solid_pair, distinguish_series_dash
from journal_pdf.common import FigureError


def sample(tmp_path: Path):
    source=tmp_path/'pair.svg'
    source.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g id="one"><path d="M 1 1 L 9 9" style="fill:none;stroke:#0000ff"/></g><g id="two"><path d="M 1 2 L 9 8" style="fill:none;stroke:#ff0000"/></g></svg>''')
    return source


def test_automatic_distinction_changes_style_not_geometry(tmp_path):
    source=sample(tmp_path);assert indistinct_solid_pair(source,['one','two'])==['two']
    root=svg_root(source);before=geometry_signature(root,['one','two'],include_dash=False)
    distinguish_series_dash(root,'two')
    assert geometry_signature(root,['one','two'],include_dash=False)==before
    assert 'stroke-dasharray:7,4' in root.xpath('//*[@id="two"]/*')[0].get('style')


def test_existing_dashes_are_not_overwritten(tmp_path):
    source=sample(tmp_path);root=svg_root(source)
    distinguish_series_dash(root,'two')
    with pytest.raises(FigureError):distinguish_series_dash(root,'two')


def test_curve_identity_must_exist(tmp_path):
    with pytest.raises(FigureError):indistinct_solid_pair(sample(tmp_path),['one','missing'])
