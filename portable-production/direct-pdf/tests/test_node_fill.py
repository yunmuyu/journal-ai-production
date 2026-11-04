import pytest

from journal_pdf.common import FigureError
from journal_pdf.scene import Scene, audit_scene


def test_filled_bar_carries_explicit_gray_level(reg):
    # Given a bar that must read as a gray step on a black-and-white page.
    scene = Scene(reg).finish(80, 40)
    bar = scene.shape('bar', [10, 10, 30, 35], 'rectangle', fill=.26)
    # Then the level is recorded as declared, not inferred.
    assert bar['fill'] == pytest.approx(.26)
    assert audit_scene(scene) == []


@pytest.mark.parametrize('fill', [-.01, 1.01, True, 'dark', float('nan')])
def test_fill_rejects_anything_but_a_real_gray_level(reg, fill):
    # Given a fill that is not a 0..1 gray level.
    scene = Scene(reg).finish(80, 40)
    # When shaping a bar with it.
    with pytest.raises(FigureError) as captured:
        scene.shape('bar', [10, 10, 30, 35], 'rectangle', fill=fill)
    # Then it is rejected instead of reaching the renderer.
    assert captured.value.as_dict()['code'] == 'node_fill_invalid'


def test_containers_stay_unfilled(reg):
    # Given a layer container that would hide its own contents if filled.
    scene = Scene(reg).finish(80, 40)
    # When declaring a fill on it.
    with pytest.raises(FigureError) as captured:
        scene.shape('layer', [5, 5, 75, 35], 'rectangle', container=True, fill=.9)
    # Then the container contract still holds.
    assert captured.value.as_dict()['code'] == 'node_fill_container'


def test_filled_bar_reaches_the_pdf(reg, tmp_path):
    import pymupdf as fitz
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one

    # Given a public scene spec with two filled bars.
    spec = {'id': 'fill-e2e', 'author': 'Synthetic', 'kind': 'scene', 'synthetic': True,
            'width_pt': 80, 'height_pt': 50, 'policy': {'column': 'single'},
            'nodes': [{'id': 'dark', 'shape': 'rectangle', 'rect': [10, 10, 30, 40], 'fill': .26},
                      {'id': 'light', 'shape': 'rectangle', 'rect': [40, 10, 60, 25], 'fill': .7}]}
    assets = Assets()
    try:
        # When the public renderer produces the PDF.
        source_root = tmp_path / 'source'
        source_root.mkdir()
        result = render_one(spec, reg, assets, source_root, tmp_path / 'output')
    finally:
        assets.close()
    # Then both bars keep their own gray level instead of collapsing to one.
    with fitz.open(tmp_path / 'output' / result['output_pdf']) as document:
        levels = sorted(round(drawing['fill'][0], 3)
                        for drawing in document[0].get_drawings() if drawing.get('fill'))
        assert levels == [.26, .7]
