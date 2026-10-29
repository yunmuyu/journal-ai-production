from copy import deepcopy

import pytest

from journal_pdf.common import FigureError
from journal_pdf.editorial import scale_scene
from journal_pdf.layouts import primitive
from journal_pdf.scene import audit_scene


def spec_for_width(width=180):
    return {
        'width_pt': 220, 'height_pt': 90,
        'nodes': [{'id': str(i), 'text': t} for i, t in enumerate(['数据服务', '功能服务', '二维地图'])],
        'measured_groups': [{'id': 'row', 'axis': 'row', 'origin': [10, 10],
                             'nodes': ['0', '1', '2'], 'gap_pt': 3,
                             'equal_width': True, 'target_width_pt': width}],
    }


def test_requested_width_stretches_equal_cells_without_changing_gap(reg):
    scene = primitive(spec_for_width(), reg, 8).finish(220, 90)
    rects = [node['rect'] for node in scene.nodes]
    assert rects[-1][2] - rects[0][0] == pytest.approx(180)
    assert [r[2]-r[0] for r in rects] == pytest.approx([58]*3)
    assert [rects[i+1][0]-rects[i][2] for i in range(2)] == pytest.approx([3, 3])
    assert not audit_scene(scene)
    scale_scene(scene, .8)
    assert not audit_scene(scene)


def test_requested_height_aligns_cells_and_rejects_too_small(reg):
    spec = spec_for_width()
    spec['measured_groups'][0]['target_height_pt'] = 22
    scene = primitive(spec, reg, 8)
    assert [n['rect'][3] - n['rect'][1] for n in scene.nodes] == pytest.approx([22, 22, 22])
    assert not audit_scene(scene)
    spec['measured_groups'][0]['target_height_pt'] = 2
    with pytest.raises(FigureError):
        primitive(spec, reg, 8)
    scale_scene(scene, .8)
    assert not audit_scene(scene)


@pytest.mark.parametrize('height', [None, True, -1, 0, float('nan'), float('inf'), 2])
def test_invalid_requested_height_is_rejected(reg, height):
    spec = spec_for_width()
    spec['measured_groups'][0]['target_height_pt'] = height
    with pytest.raises(FigureError):
        primitive(spec, reg, 8)


def test_requested_height_tampering_remains_audited(reg):
    spec = spec_for_width()
    spec['measured_groups'][0]['target_height_pt'] = 22
    scene = primitive(spec, reg, 8)
    scene.nodes[1]['rect'][3] += 1
    assert any(issue['code'] == 'primitive_box_measurement_mismatch' for issue in audit_scene(scene))


@pytest.mark.parametrize('width', [None, True, -1, 0, float('nan'), float('inf'), 30])
def test_invalid_or_too_narrow_requested_width_is_rejected(reg, width):
    with pytest.raises(FigureError):
        primitive(spec_for_width(width), reg, 8)


def test_requested_width_requires_equal_width_row(reg):
    for change in ({'equal_width': False}, {'axis': 'column'}):
        spec = spec_for_width()
        spec['measured_groups'][0].update(change)
        with pytest.raises(FigureError):
            primitive(spec, reg, 8)


def test_geometry_tampering_remains_audited(reg):
    scene = primitive(deepcopy(spec_for_width()), reg, 8).finish(220, 90)
    scene.nodes[1]['rect'][2] += 1
    assert any(issue['code'] == 'primitive_box_measurement_mismatch' for issue in audit_scene(scene))


def test_two_rows_with_different_counts_render_aligned_in_pdf(reg, tmp_path):
    import pymupdf as fitz
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one

    spec = spec_for_width()
    spec.update({'id': 'equal-rows', 'author': 'Synthetic', 'kind': 'scene', 'synthetic': True})
    spec['nodes'].extend([{'id': 'b'+str(i), 'text': t} for i,t in enumerate(['数据服务', '功能服务', '二维地图', '三维场景'])])
    spec['measured_groups'].append({'id': 'row2', 'axis': 'row', 'origin': [10, 45],
                                    'nodes': ['b0', 'b1', 'b2', 'b3'], 'gap_pt': 3,
                                    'equal_width': True, 'target_width_pt': 180})
    source = tmp_path / 'source'
    source.mkdir()
    assets = Assets()
    try:
        result = render_one(spec, reg, assets, source, tmp_path / 'out')
    finally:
        assets.close()
    with fitz.open(tmp_path / 'out' / result['output_pdf']) as document:
        page = document[0]
        rects = [drawing['rect'] for drawing in page.get_drawings() if drawing['type'] == 's']
        rows = sorted({round(rect.y0, 1) for rect in rects})
        assert len(rows) == 2
        bounds = [(min(r.x0 for r in rects if round(r.y0, 1)==y),
                   max(r.x1 for r in rects if round(r.y0, 1)==y)) for y in rows]
        assert bounds[0] == pytest.approx(bounds[1], abs=.02)
        assert bounds[0][1]-bounds[0][0] == pytest.approx(180, abs=.02)
        assert '三维场景' in page.get_text()
