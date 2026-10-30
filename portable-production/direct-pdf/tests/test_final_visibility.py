import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError, digest_file
from journal_pdf.render import render_one
from test_original_asset_reference import specification
from test_source_structure_contract import structure_fixture
import json
import pymupdf as fitz
from journal_pdf.render import compile_figure
from journal_pdf.final_visibility import audit_final_visibility


def test_visible_native_line_crossing_is_not_black_overpaint(tmp_path, reg):
    root = tmp_path / 'source'; spec = structure_fixture(root)
    spec.pop('source_structure_contract'); spec['sources'] = [dict(spec['sources'][0], role='source')]
    spec['policy']['require_final_visibility'] = True
    spec['paths'].append({'id': 'cross', 'points': [[40, 5], [40, 35]], 'semantic_role': 'decorative'})
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, root, tmp_path / 'out')
        assert set(report['final_visibility_audit']['checked_paths']) == {'ab', 'cross'}
    finally:
        assets.close()


@pytest.mark.parametrize('cover', [False, True])
def test_visibility_can_check_legacy_scene_without_claiming_source_topology(tmp_path, reg, cover):
    root = tmp_path / 'source'; spec = structure_fixture(root)
    spec.pop('source_structure_contract')
    spec['sources'] = [dict(spec['sources'][0], role='source')]
    spec['policy']['require_final_visibility'] = True
    if cover:
        spec['nodes'].append({'id': 'cover', 'rect': [37, 18, 43, 22], 'width': None, 'fill': 1})
    assets = Assets()
    try:
        if cover:
            with pytest.raises(FigureError) as error:
                render_one(spec, reg, assets, root, tmp_path / 'out')
            assert error.value.code == 'final_visibility_changed'
        else:
            report = render_one(spec, reg, assets, root, tmp_path / 'out')
            assert report['source_structure_audit']['status'] == 'not-checked'
            assert report['final_visibility_audit']['status'] == 'checked'
            assert report['final_visibility_audit']['checked_paths'] == ['ab']
    finally:
        assets.close()


@pytest.mark.parametrize('opaque', [False, True])
def test_pixel_rounded_crop_does_not_include_neighbor_outside_asset(tmp_path, reg, opaque):
    root = tmp_path / 'source'; root.mkdir(); spec = specification(root)
    if opaque:
        for name in ['original.pdf', 'prepared.pdf']:
            with fitz.open(root / name) as doc:
                doc[0].draw_rect(doc[0].rect, fill=(1,), color=None, overlay=False)
                doc.saveIncr()
        spec['sources'][0]['sha256'] = digest_file(root / 'original.pdf')
    spec['assets'][0]['target'] = [10.13, 10.29, 70.13, 50.29]
    spec['sources'].append({'path': 'prepared.pdf', 'sha256': digest_file(root / 'prepared.pdf'), 'role': 'derived'})
    # The compiler normalizes strokes to .5 pt; the left ink edge is 70.25,
    # outside the asset's 70.13 edge but inside the rounded raster crop.
    spec['paths'] = [{'id': 'neighbor', 'points': [[70.5, 12], [70.5, 48]], 'width': .5, 'semantic_role': 'decorative'}]
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, root, tmp_path / 'out')
        assert report['final_visibility_audit']['status'] == 'checked'
    finally:
        assets.close()


@pytest.mark.parametrize('inside', [False, True])
@pytest.mark.parametrize('opaque', [False, True])
def test_asset_transparent_exterior_is_distinct_from_white_inner_detail(tmp_path, reg, inside, opaque):
    root = tmp_path / 'source'; root.mkdir(); spec = specification(root)
    if opaque:
        for name in ['original.pdf', 'prepared.pdf']:
            with fitz.open(root / name) as doc:
                doc[0].draw_rect(doc[0].rect, fill=(1,), color=None, overlay=False)
                doc.saveIncr()
        spec['sources'][0]['sha256'] = digest_file(root / 'original.pdf')
    spec['sources'].append({'path': 'prepared.pdf', 'sha256': digest_file(root / 'prepared.pdf'), 'role': 'derived'})
    spec['nodes'] = [{'id': 'paint', 'rect': [33, 28, 37, 32] if inside else [12, 12, 16, 16], 'width': None, 'fill': 0}]
    assets = Assets()
    try:
        if inside:
            with pytest.raises(FigureError) as error:
                render_one(spec, reg, assets, root, tmp_path / 'out')
            assert error.value.code == 'final_visibility_changed'
        else:
            assert render_one(spec, reg, assets, root, tmp_path / 'out')['final_visibility_audit']['status'] == 'checked'
    finally:
        assets.close()


@pytest.mark.parametrize('overlap', [False, True])
def test_declared_asset_contact_only_allows_exterior_node_boundary(tmp_path, reg, overlap):
    root = tmp_path / 'source'; root.mkdir(); spec = specification(root)
    for name in ['original.pdf', 'prepared.pdf']:
        with fitz.open(root / name) as doc:
            doc[0].draw_rect(doc[0].rect, fill=(.4,), color=None)
            doc.saveIncr()
    spec['sources'][0]['sha256'] = digest_file(root / 'original.pdf')
    spec['sources'].append({'path': 'prepared.pdf', 'sha256': digest_file(root / 'prepared.pdf'), 'role': 'derived'})
    spec['policy']['require_final_visibility'] = True
    spec['nodes'] = [{'id': 'node', 'rect': [60 if overlap else 70, 10, 90, 50]}]
    spec['asset_boundary_contacts'] = [{'asset_id': 'icon', 'node_id': 'node'}]
    assets = Assets()
    try:
        if overlap:
            with pytest.raises(FigureError) as error:
                render_one(spec, reg, assets, root, tmp_path / 'out')
            assert error.value.code == 'final_visibility_contact'
        else:
            report = render_one(spec, reg, assets, root, tmp_path / 'out')
            assert report['final_visibility_audit']['asset_boundary_contacts'] == {'icon': ['node']}
            assert report['source_structure_audit']['status'] == 'not-checked'
    finally:
        assets.close()


@pytest.mark.parametrize('cover', ['white', 'black', 'path'])
def test_final_overlay_cannot_hide_verified_asset(tmp_path, reg, cover):
    root = tmp_path / 'source'; root.mkdir()
    spec = specification(root)
    spec['sources'].append({'path': 'prepared.pdf', 'sha256': digest_file(root / 'prepared.pdf'), 'role': 'derived'})
    if cover == 'path':
        spec['paths'] = [{'id': 'cover', 'points': [[22, 19], [35, 19]], 'semantic_role': 'decorative'}]
    else:
        spec['nodes'] = [{'id': 'cover', 'rect': [22, 19, 35, 24], 'width': None,
                          'fill': 1 if cover == 'white' else 0}]
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out')
        assert error.value.code == 'final_visibility_changed'
        assert not list((tmp_path / 'out').rglob('*.pdf'))
    finally:
        assets.close()


@pytest.mark.parametrize('fill', [0, 1])
def test_final_node_cannot_erase_contracted_connection(tmp_path, reg, fill):
    root = tmp_path / 'source'; spec = structure_fixture(root)
    spec['nodes'].append({'id': 'panel', 'rect': [37, 18, 43, 22], 'width': None, 'fill': fill})
    path = root / 'relations.json'; contract = json.loads(path.read_text())
    # A pure white fill has no own visible ink on white; its occlusion is still checked.
    contract['nodes']['panel'] = {'shape': 'rectangle', 'visible': fill < 1}
    path.write_text(json.dumps(contract))
    spec['sources'][1]['sha256'] = digest_file(path)
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out')
        assert error.value.code == 'final_visibility_changed'
        assert error.value.details['id'] == 'ab'
    finally:
        assets.close()


@pytest.mark.parametrize('mutation', ['covered-text', 'black-covered-text', 'crop'])
def test_reopened_saved_pdf_not_scene_declarations_is_checked(tmp_path, reg, mutation):
    root = tmp_path / 'source'; spec = structure_fixture(root)
    spec['texts'] = [{'id': 'caption', 'text': 'Caption', 'x': 25, 'y': 80}]
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, root, tmp_path / 'out')
        assert report['final_visibility_audit']['checked_texts'] == ['caption']
        target = tmp_path / 'out' / report['output_pdf']
        with fitz.open(target) as doc:
            page = doc[0]
            if mutation in ('covered-text', 'black-covered-text'):
                rect = page.search_for('Caption')[0]
                page.draw_rect(rect, fill=(0 if mutation == 'black-covered-text' else 1,), color=None)
            else:
                crop = page.cropbox; crop.x0 += 15; page.set_cropbox(crop)
            doc.saveIncr()
        scene = compile_figure(spec, reg, assets, root)
        with pytest.raises(FigureError) as error:
            audit_final_visibility(target, scene, reg, assets, [], report['source_structure_audit'])
        assert error.value.code == 'final_visibility_changed'
    finally:
        assets.close()


@pytest.mark.parametrize('wide', [False, True])
@pytest.mark.parametrize('padding', [0, .25, 4])
def test_fractional_placement_and_whole_scene_scaling_remain_valid(tmp_path, reg, wide, padding):
    root = tmp_path / 'source'; root.mkdir(); spec = specification(root)
    spec['assets'][0]['target'] = [10.13, 10.29, 70.13, 50.29]
    spec['policy']['export_crop_padding_pt'] = padding
    spec['texts'] = [{'id': 'caption', 'text': 'Caption', 'x': 25, 'y': 60}]
    spec['sources'].append({'path': 'prepared.pdf', 'sha256': digest_file(root / 'prepared.pdf'), 'role': 'derived'})
    if wide:
        spec['width_pt'] = 260
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, root, tmp_path / 'out')
        assert report['final_visibility_audit']['status'] == 'checked'
        assert report['final_visibility_audit']['checked_texts'] == ['caption']
    finally:
        assets.close()


def test_failed_visibility_check_preserves_existing_candidate(tmp_path, reg):
    root = tmp_path / 'source'; root.mkdir(); spec = specification(root)
    spec['sources'].append({'path': 'prepared.pdf', 'sha256': digest_file(root / 'prepared.pdf'), 'role': 'derived'})
    assets = Assets()
    try:
        result = render_one(spec, reg, assets, root, tmp_path / 'out')
        path = tmp_path / 'out' / result['output_pdf']; before = digest_file(path)
        spec['nodes'] = [{'id': 'cover', 'rect': [22, 19, 35, 24], 'width': None, 'fill': 1}]
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out', overwrite=True)
        assert error.value.code == 'final_visibility_changed'
        assert digest_file(path) == before
    finally:
        assets.close()


@pytest.mark.parametrize('overlap', [False, True])
def test_white_background_is_not_visible_ink_but_can_occlude(tmp_path, reg, overlap):
    root = tmp_path / 'source'; spec = structure_fixture(root)
    rect = [37, 18, 43, 22] if overlap else [10, 50, 30, 70]
    spec['nodes'].append({'id': 'background', 'rect': rect, 'width': .5, 'gray': 1, 'fill': 1})
    path = root / 'relations.json'; contract = json.loads(path.read_text())
    contract['nodes']['background'] = {'shape': 'rectangle', 'visible': False}
    path.write_text(json.dumps(contract)); spec['sources'][1]['sha256'] = digest_file(path)
    assets = Assets()
    try:
        if overlap:
            with pytest.raises(FigureError) as error:
                render_one(spec, reg, assets, root, tmp_path / 'out')
            assert error.value.code == 'final_visibility_changed'
            assert error.value.details['id'] == 'ab'
        else:
            report = render_one(spec, reg, assets, root, tmp_path / 'out')
            assert 'background' not in report['final_visibility_audit']['checked_nodes']
    finally:
        assets.close()
