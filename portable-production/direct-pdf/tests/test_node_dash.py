import pymupdf as fitz
import pytest

from journal_pdf.scene import Scene
from journal_pdf.render import draw_node
from journal_pdf.editorial import scale_scene
from journal_pdf.common import FigureError


def test_optional_node_dash_survives_saved_pdf_and_scale():
    scene = Scene(None)
    node = scene.shape('group', [10, 10, 100, 50], 'ellipse', container=True, dash=[5.25, 3.75])
    scene.finish(110, 60)
    scale_scene(scene, .8)
    assert node['dash'] == pytest.approx([4.2, 3.0])
    with fitz.open() as doc:
        page = doc.new_page(width=110, height=60)
        draw_node(page, node)
        with fitz.open(stream=doc.tobytes(), filetype='pdf') as saved:
            row = saved[0].get_drawings()[0]
            assert row['width'] == .5
            assert row['dashes'] == '[ 4.2 3 ] 0'
            assert len(row['items']) == 4
            assert all(item[0] == 'c' for item in row['items'])


@pytest.mark.parametrize('dash', [[0, 0], [-1, 2], [float('nan'), 2], [True, 2], '5 3'])
def test_bad_node_dash_rejected(dash):
    with pytest.raises(FigureError):
        Scene(None).shape('group', [10, 10, 100, 50], 'ellipse', dash=dash)


def test_default_node_keeps_legacy_fields():
    node = Scene(None).shape('plain', [1, 1, 10, 10])
    assert 'dash' not in node
