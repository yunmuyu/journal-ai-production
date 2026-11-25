import json

import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError, digest_file
from journal_pdf.render import render_one
from journal_pdf.scene import Scene
from journal_pdf.source_route_contract import audit_source_routes
from test_source_structure_contract import structure_fixture


def declaration(points, components, *, arrow='end', line='solid', arrow_style='standard'):
    return {'points': points, 'components': components, 'arrow': arrow,
            'arrow_style': arrow_style, 'line': line}


def fixture(root):
    root.mkdir()
    (root / 'original.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><path d="M10 10H40V40H70"/></svg>')
    source = digest_file(root / 'original.svg')
    contract = {'version': 1, 'source_sha256': source,
                'transform': {'kind': 'uniform', 'matrix': [1, 0, 0, 1, 0, 0]},
                'routes': {'ab': declaration([[10, 10], [40, 10], [40, 40], [70, 40]], ['ab']),
                           'cd': declaration([[80, 10], [100, 10]], ['cd'])}}
    spec = {'policy': {}, 'source_route_contract': 'routes.json'}
    bindings = [{'path': 'original.svg', 'sha256': source, 'role': 'original-artwork'}]
    scene = Scene(None)
    scene.layout_evidence['whole_artwork_scale'] = 1
    for key, route in contract['routes'].items():
        scene.line(key, route['points'], arrow=True)
    return spec, scene, contract, bindings


def write_contract(root, contract, bindings):
    path = root / 'routes.json'
    path.write_text(json.dumps(contract), encoding='utf8')
    bindings[:] = [b for b in bindings if b['role'] != 'route-contract']
    bindings.append({'path': 'routes.json', 'sha256': digest_file(path), 'role': 'route-contract'})


def check(root, spec, scene, contract, bindings):
    write_contract(root, contract, bindings)
    return audit_source_routes(spec, scene, root, bindings)


@pytest.mark.parametrize('mutation,code', [
    ('bend', 'source_route_geometry_changed'),
    ('dogleg', 'source_route_bends_changed'),
    ('straighten', 'source_route_bends_changed'),
    ('endpoint', 'source_route_geometry_changed'),
    ('reverse', 'source_route_geometry_changed'),
    ('one-edge-translate', 'source_route_geometry_changed'),
    ('both', 'source_route_style_changed'),
    ('dash', 'source_route_style_changed'),
    ('hollow', 'source_route_style_changed'),
    ('fill', 'source_route_style_changed'),
    ('closed', 'source_route_style_changed'),
    ('extra-decorative', 'source_route_inventory'),
    ('missing', 'source_route_inventory'),
])
def test_source_geometry_not_just_topology(tmp_path, mutation, code):
    root = tmp_path / 'source'; spec, scene, contract, bindings = fixture(root)
    path = scene.paths[0]
    if mutation == 'bend':
        # The same endpoints, node identities, direction and number of bends.
        path['points'][1][0] += 5; path['points'][2][0] += 5
    elif mutation == 'dogleg':
        path['points'][1:1] = [[20, 10], [20, 5], [30, 5], [30, 10]]
    elif mutation == 'straighten':
        path['points'] = [path['points'][0], path['points'][-1]]
    elif mutation == 'endpoint':
        path['points'][-1][0] += 1
    elif mutation == 'reverse':
        path['points'].reverse()
    elif mutation == 'one-edge-translate':
        path['points'] = [[x+3, y+2] for x, y in path['points']]
    elif mutation == 'both':
        path['both'] = True
    elif mutation == 'dash':
        path['dash'] = [2, 2]
    elif mutation == 'hollow':
        path['arrow_style'] = 'block-outline'
    elif mutation == 'fill':
        path['fill'] = 0
    elif mutation == 'closed':
        path['closed'] = True
    elif mutation == 'extra-decorative':
        scene.line('extra', [[5, 80], [40, 80]], semantic_role='decorative')
    elif mutation == 'missing':
        scene.paths.pop()
    with pytest.raises(FigureError) as error:
        check(root, spec, scene, contract, bindings)
    assert error.value.code == code


@pytest.mark.parametrize('kind,matrix', [
    ('uniform', [.8, 0, 0, .8, 3, 7]),
    ('affine', [.8, .2, -.1, .9, 3, 7]),
    ('affine', [-1, 0, 0, 1, 110, 7]),
])
def test_one_explicit_transform_and_compiler_scale_apply_to_every_route(tmp_path, kind, matrix):
    root = tmp_path / 'source'; spec, scene, contract, bindings = fixture(root)
    contract['transform'] = {'kind': kind, 'matrix': matrix}
    a, b, c, d, tx, ty = matrix
    scene.layout_evidence['whole_artwork_scale'] = .9
    for path in scene.paths:
        path['points'] = [[(a*x+c*y+tx)*.9, (b*x+d*y+ty)*.9] for x, y in path['points']]
    report = check(root, spec, scene, contract, bindings)
    assert report['route_count'] == 2
    assert report['effective_matrix'] == pytest.approx([v*.9 for v in matrix])
    assert all(r['max_delta_pt'] < 1e-12 for r in report['routes'])


@pytest.mark.parametrize('mutation', ['uniform-shear', 'uniform-stretch', 'uniform-negative', 'singular', 'nan', 'boolean', 'per-route'])
def test_transform_cannot_allow_per_route_fitting_or_degenerate_geometry(tmp_path, mutation):
    root = tmp_path / 'source'; spec, scene, contract, bindings = fixture(root)
    if mutation == 'uniform-shear':
        contract['transform']['matrix'][1] = .2
    elif mutation == 'uniform-stretch':
        contract['transform']['matrix'][3] = 2
    elif mutation == 'uniform-negative':
        contract['transform']['matrix'][0] = contract['transform']['matrix'][3] = -1
    elif mutation == 'singular':
        contract['transform'] = {'kind': 'affine', 'matrix': [1, 2, 2, 4, 0, 0]}
    elif mutation == 'nan':
        contract['transform']['matrix'][4] = float('nan')
    elif mutation == 'boolean':
        contract['transform']['matrix'][0] = True
    elif mutation == 'per-route':
        contract['routes']['ab']['transform'] = [1, 0, 0, 1, 5, 0]
    with pytest.raises(FigureError) as error:
        check(root, spec, scene, contract, bindings)
    assert error.value.code == 'source_route_schema'


@pytest.mark.parametrize('mutation,code', [
    ('omit-pointer', 'source_route_missing'),
    ('required', 'source_route_missing'),
    ('unbound', 'source_route_unbound'),
    ('wrong-original', 'source_route_original_unbound'),
    ('wrong-role', 'source_route_original_unbound'),
    ('changed', 'source_route_changed'),
    ('duplicate', 'source_route_schema'),
    ('tolerance', 'source_route_schema'),
    ('scale', 'source_route_scale_unproven'),
    ('invalid-policy', 'source_route_schema'),
])
def test_source_evidence_cannot_be_silently_bypassed(tmp_path, mutation, code):
    root = tmp_path / 'source'; spec, scene, contract, bindings = fixture(root)
    if mutation == 'wrong-original':
        contract['source_sha256'] = '0'*64
    elif mutation == 'tolerance':
        contract['tolerance_pt'] = 50
    write_contract(root, contract, bindings)
    if mutation == 'omit-pointer':
        del spec['source_route_contract']
    elif mutation == 'required':
        del spec['source_route_contract']; bindings.pop()
        spec['policy']['require_source_route_contract'] = True
    elif mutation == 'unbound':
        bindings.pop()
    elif mutation == 'wrong-role':
        bindings[0]['role'] = 'derived'
    elif mutation == 'changed':
        (root / 'routes.json').write_text('{}')
    elif mutation == 'duplicate':
        (root / 'routes.json').write_text('{"version":1,"version":1}')
        bindings[-1]['sha256'] = digest_file(root / 'routes.json')
    elif mutation == 'scale':
        scene.layout_evidence.clear()
    elif mutation == 'invalid-policy':
        spec['policy']['require_source_route_contract'] = 1
    with pytest.raises(FigureError) as error:
        audit_source_routes(spec, scene, root, bindings)
    assert error.value.code == code


@pytest.mark.parametrize('disconnected', [False, True])
def test_shared_stem_is_verified_as_complete_original_routes(tmp_path, disconnected):
    root = tmp_path / 'source'; spec, scene, contract, bindings = fixture(root)
    scene.paths = []; scene._ids.clear()
    scene.line('shared', [[10, 10], [40, 10]])
    scene.line('down', [[40, 10], [40, 40], [70, 40]], arrow=True)
    scene.line('up', [[40, 10], [40, 5], [70, 5]], arrow=True)
    contract['routes'] = {
        'down': declaration([[10, 10], [40, 10], [40, 40], [70, 40]], ['shared', 'down']),
        'up': declaration([[10, 10], [40, 10], [40, 5], [70, 5]], ['shared', 'up'])}
    if disconnected:
        scene.paths[1]['points'][0][0] += .01
        with pytest.raises(FigureError) as error:
            check(root, spec, scene, contract, bindings)
        assert error.value.code == 'source_route_disconnected'
    else:
        report = check(root, spec, scene, contract, bindings)
        assert report['route_count'] == 2 and report['path_count'] == 3


def test_collinear_samples_are_safe_but_collinear_backtracking_is_not(tmp_path):
    root = tmp_path / 'source'; spec, scene, contract, bindings = fixture(root)
    scene.paths[0]['points'][1:1] = [[20, 10]]
    contract['routes']['ab']['points'].insert(2, [40, 20])
    assert check(root, spec, scene, contract, bindings)['status'] == 'checked'
    scene.paths[0]['points'][1:2] = [[30, 10], [20, 10]]
    with pytest.raises(FigureError) as error:
        check(root, spec, scene, contract, bindings)
    assert error.value.code == 'source_route_bends_changed'


def test_short_segment_cannot_reverse_within_point_tolerance(tmp_path):
    root = tmp_path / 'source'; spec, scene, contract, bindings = fixture(root)
    contract['routes'] = {'short': declaration([[10, 10], [10.1, 10]], ['short'], arrow='none')}
    scene.paths = []; scene.line('short', [[10.1, 10], [10, 10]])
    with pytest.raises(FigureError) as error:
        check(root, spec, scene, contract, bindings)
    assert error.value.code == 'source_route_direction_changed'


def test_legacy_scene_explicitly_reports_not_checked(tmp_path):
    report = audit_source_routes({'policy': {}}, Scene(None), tmp_path, [])
    assert report == {'status': 'not-checked', 'route_count': 0, 'path_count': 0}


def render_fixture(root):
    spec = structure_fixture(root)
    # This gate is independently useful without an existing topology contract.
    spec.pop('source_structure_contract'); spec['sources'].pop()
    contract = {'version': 1, 'source_sha256': spec['sources'][0]['sha256'],
                'transform': {'kind': 'uniform', 'matrix': [1, 0, 0, 1, 0, 0]},
                'routes': {'ab': declaration([[30, 20], [50, 20]], ['ab'])}}
    write_contract(root, contract, spec['sources'])
    spec['source_route_contract'] = 'routes.json'
    return spec


@pytest.mark.parametrize('design_width', [100, 270])
def test_public_render_reports_route_audit_and_reopens_actual_pdf(tmp_path, reg, design_width):
    root = tmp_path / 'source'; spec = render_fixture(root)
    spec['width_pt'] = design_width
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, root, tmp_path / 'out')
        assert report['source_route_audit']['status'] == 'checked'
        assert report['source_structure_audit']['status'] == 'not-checked'
        assert report['final_visibility_audit']['checked_paths'] == ['ab']
        assert report['final_visibility_audit']['source_topology_checked'] is False
        scale = report['layout']['layout_evidence']['whole_artwork_scale']
        assert report['source_route_audit']['effective_matrix'] == pytest.approx([scale, 0, 0, scale, 0, 0])
        assert (scale < 1) == (design_width == 270)
    finally:
        assets.close()


def test_public_render_rejects_topologically_valid_bend_change_before_writing(tmp_path, reg):
    root = tmp_path / 'source'; spec = render_fixture(root)
    # Keep the original endpoints and port bindings while routing around a loop.
    spec['paths'][0]['points'] = [[30, 20], [32, 20], [32, 5], [40, 5], [40, 20], [50, 20]]
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out')
        assert error.value.code == 'source_route_bends_changed'
        assert not list((tmp_path / 'out').rglob('*.pdf'))
    finally:
        assets.close()


def test_route_contract_does_not_skip_invalid_final_visibility_policy(tmp_path, reg):
    root = tmp_path / 'source'; spec = render_fixture(root)
    spec['policy']['require_final_visibility'] = 'yes'
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out')
        assert error.value.code == 'final_visibility_policy'
    finally:
        assets.close()


def test_route_lock_preserves_existing_candidate_when_overwrite_would_reroute(tmp_path, reg):
    root = tmp_path / 'source'; spec = render_fixture(root)
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, root, tmp_path / 'out')
        existing = tmp_path / 'out' / report['output_pdf']
        original_hash = digest_file(existing)
        spec['paths'][0]['points'] = [[30, 20], [32, 20], [32, 5], [40, 5], [40, 20], [50, 20]]
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out', overwrite=True)
        assert error.value.code == 'source_route_bends_changed'
        assert digest_file(existing) == original_hash
    finally:
        assets.close()


def test_route_lock_automatically_checks_saved_pdf_occlusion(tmp_path, reg):
    root = tmp_path / 'source'; spec = render_fixture(root)
    spec['nodes'].append({'id': 'cover', 'rect': [37, 18, 43, 22], 'width': None, 'fill': 1})
    # Even an explicit false cannot disable visibility for locked source routes.
    spec['policy']['require_final_visibility'] = False
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out')
        assert error.value.code == 'final_visibility_changed'
        assert not list((tmp_path / 'out').rglob('*.pdf'))
    finally:
        assets.close()
