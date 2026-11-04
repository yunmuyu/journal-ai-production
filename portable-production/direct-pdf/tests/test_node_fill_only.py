import pytest

from journal_pdf.common import FigureError
from journal_pdf.scene import Scene, audit_scene


def test_fill_only_node_keeps_no_stroke(reg):
    # Given a color-bar band that must butt against its neighbours without a seam.
    scene = Scene(reg).finish(60, 30)
    band = scene.shape('band', [10, 10, 20, 28], 'rectangle', width=None, fill=.6)
    # Then the node records "fill only" instead of silently using a hairline stroke.
    assert band['width'] is None and band['fill'] == pytest.approx(.6)
    assert audit_scene(scene) == []


@pytest.mark.parametrize('width', [-1, float('inf'), True, 'thin'])
def test_stroke_width_stays_a_real_number_or_none(reg, width):
    # Given a stroke width that is neither a real length nor explicit None.
    scene = Scene(reg).finish(60, 30)
    # When shaping the node.
    with pytest.raises(FigureError) as captured:
        scene.shape('band', [10, 10, 20, 28], 'rectangle', width=width, fill=.6)
    # Then it is rejected.
    assert captured.value.as_dict()['code'] == 'node_width_invalid'


def test_fill_only_band_renders_without_stroke_color(reg, tmp_path):
    import pymupdf as fitz
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one

    # Given a scene with one stroked bar and one fill-only band.
    spec = {'id': 'fill-only-e2e', 'author': 'Synthetic', 'kind': 'scene', 'synthetic': True,
            'width_pt': 60, 'height_pt': 40, 'policy': {'column': 'single'},
            'nodes': [{'id': 'stroked', 'shape': 'rectangle', 'rect': [8, 8, 20, 30], 'fill': .3},
                      {'id': 'band', 'shape': 'rectangle', 'rect': [30, 8, 40, 30], 'fill': .6, 'width': None}]}
    assets = Assets()
    try:
        # When the public renderer produces the PDF.
        source_root = tmp_path / 'source'
        source_root.mkdir()
        result = render_one(spec, reg, assets, source_root, tmp_path / 'output')
    finally:
        assets.close()
    # Then only the stroked bar carries an outline color.
    with fitz.open(tmp_path / 'output' / result['output_pdf']) as document:
        outlined = [d for d in document[0].get_drawings() if d.get('color')]
        filled = [d for d in document[0].get_drawings() if d.get('fill')]
        assert len(outlined) == 1 and len(filled) == 2
