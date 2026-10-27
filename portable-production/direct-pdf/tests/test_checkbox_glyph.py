import pytest

from journal_pdf.common import FigureError
from journal_pdf.scene import Scene, audit_scene


def test_checkbox_is_a_real_symbol_node_with_declared_state(reg):
    # Given a checkbox symbol drawn as a bare glyph instead of a text box.
    scene = Scene(reg).finish(60, 40)
    unchecked = scene.shape('cb-off', [10, 10, 17, 17], 'checkbox')
    checked = scene.shape('cb-on', [30, 10, 37, 17], 'checkbox', checked=True)
    # Then its state is recorded and the scene audits clean.
    assert unchecked['kind'] == 'checkbox' and unchecked['checked'] is False
    assert checked['checked'] is True
    assert audit_scene(scene) == []


@pytest.mark.parametrize('kind,checked,error', [
    ('rectangle', True, 'checkbox_state_unsupported'),
    ('roundrect', True, 'checkbox_state_unsupported'),
    ('checkbox', 'yes', 'checkbox_state_invalid'),
    ('checkbox', 1, 'checkbox_state_invalid'),
])
def test_checkbox_state_cannot_be_borrowed_by_other_shapes(reg, kind, checked, error):
    # Given a state flag that does not belong to the declared shape.
    scene = Scene(reg).finish(60, 40)
    # When declaring it anyway.
    with pytest.raises(FigureError) as captured:
        scene.shape('n', [10, 10, 20, 20], kind, checked=checked)
    # Then it is rejected instead of silently dropped.
    assert captured.value.as_dict()['code'] == error


def test_checkbox_cannot_pose_as_a_container(reg):
    # Given a symbol glyph declared as a container.
    scene = Scene(reg).finish(60, 40)
    # When shaping it.
    with pytest.raises(FigureError) as captured:
        scene.shape('c', [10, 10, 50, 30], 'checkbox', container=True)
    # Then the container contract is not extended to symbols.
    assert captured.value.as_dict()['code'] == 'checkbox_container_invalid'


def test_checked_glyph_renders_two_strokes_and_unchecked_one(reg, tmp_path):
    import pymupdf as fitz
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one

    # Given a public scene whose spec carries both checkbox states.
    spec = {'id': 'checkbox-glyph-e2e', 'author': 'Synthetic', 'kind': 'scene', 'synthetic': True,
            'width_pt': 60, 'height_pt': 40, 'policy': {'column': 'single'},
            'nodes': [{'id': 'off', 'shape': 'checkbox', 'rect': [10, 12, 17, 19]},
                      {'id': 'on', 'shape': 'checkbox', 'rect': [30, 12, 37, 19], 'checked': True}]}
    assets = Assets()
    try:
        # When the public renderer produces the PDF.
        source_root = tmp_path / 'source'
        source_root.mkdir()
        result = render_one(spec, reg, assets, source_root, tmp_path / 'output')
    finally:
        assets.close()
    # Then the unchecked glyph stays one square and the checked one adds the inner square.
    with fitz.open(tmp_path / 'output' / result['output_pdf']) as document:
        squares = [item[1] for drawing in document[0].get_drawings()
                   for item in drawing['items'] if item[0] == 're']
        assert len(squares) == 3
        # The inner square sits strictly inside the checked glyph, never outside it.
        outer = [s for s in squares if abs(s.width - 7) < .2 and abs(s.height - 7) < .2]
        inner = [s for s in squares if s.width < 5.5]
        assert len(outer) == 2 and len(inner) == 1
        assert outer[1].contains(inner[0]) or outer[0].contains(inner[0])
