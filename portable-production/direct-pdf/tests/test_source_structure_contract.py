import json

import pymupdf as fitz
import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError, digest_file
from journal_pdf.render import render_one


def structure_fixture(root, *, arrow=True):
    root.mkdir()
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=100)
        for rect in ([10, 10, 30, 30], [50, 10, 70, 30], [50, 50, 70, 70]):
            page.draw_rect(rect, width=.5)
        page.draw_line((30, 20), (50, 20), width=.5)
        if arrow:
            shape = page.new_shape(); shape.draw_polyline([(47, 18), (50, 20), (47, 22)])
            shape.finish(closePath=True, fill=(0,), color=None); shape.commit()
        doc.save(root / 'original.pdf')
    original_hash = digest_file(root / 'original.pdf')
    contract = {
        'version': 1, 'source_sha256': original_hash,
        'nodes': {key: {'shape': 'rectangle', 'visible': True} for key in ('a', 'b', 'c')},
        'paths': {'ab': {'from': {'node': 'a', 'side': 'right', 'fraction': .5},
                         'to': {'node': 'b', 'side': 'left', 'fraction': .5},
                         'arrow': 'end', 'line': 'solid'}},
    }
    if not arrow:
        contract['paths']['ab'].update({'from': None, 'to': None, 'arrow': 'none'})
    (root / 'relations.json').write_text(json.dumps(contract), encoding='utf8')
    return {
        'version': 1, 'id': 'structure', 'author': 'Synthetic', 'kind': 'scene',
        'width_pt': 100, 'height_pt': 90, 'policy': {'column': 'single'},
        'sources': [{'path': 'original.pdf', 'sha256': original_hash, 'role': 'original-artwork'},
                    {'path': 'relations.json', 'sha256': digest_file(root / 'relations.json'), 'role': 'structure-contract'}],
        'source_structure_contract': 'relations.json',
        'nodes': [{'id': 'a', 'rect': [10, 10, 30, 30]},
                  {'id': 'b', 'rect': [50, 10, 70, 30]},
                  {'id': 'c', 'rect': [50, 50, 70, 70]}],
        'paths': [{'id': 'ab', 'points': [[30, 20], [50, 20]], 'arrow': arrow, 'endpoint_nodes': ['a', 'b']}],
        'texts': [], 'assets': [],
    }


@pytest.mark.parametrize('mutation', ['wrong-target', 'missing', 'extra', 'reverse', 'both', 'dash', 'shape', 'white-fill-frame'])
def test_independent_contract_rejects_valid_but_wrong_scene(tmp_path, reg, mutation):
    # Given: an external source-bound contract independent of the candidate.
    root = tmp_path / 'source'; spec = structure_fixture(root)
    if mutation == 'wrong-target':
        spec['paths'][0].update(points=[[30, 20], [50, 60]], endpoint_nodes=['a', 'c'])
    elif mutation == 'missing':
        spec['paths'] = []
    elif mutation == 'extra':
        spec['paths'].append({'id': 'unwanted', 'points': [[10, 80], [70, 80]], 'semantic_role': 'decorative'})
    elif mutation == 'reverse':
        spec['paths'][0].update(points=[[50, 20], [30, 20]], endpoint_nodes=['b', 'a'])
    elif mutation == 'both':
        spec['paths'][0]['both'] = True
    elif mutation == 'dash':
        spec['paths'][0]['dash'] = [2, 2]
    elif mutation == 'shape':
        spec['nodes'][2]['shape'] = 'ellipse'
    elif mutation == 'white-fill-frame':
        spec['nodes'][2].update(width=None, fill=1)
    assets = Assets()
    try:
        # When: generic scene checks see a valid drawing, but its meaning changed.
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out')
        # Then: the original relationship contract blocks it before publication.
        assert error.value.code.startswith('source_structure_')
        assert not list((tmp_path / 'out').rglob('*.pdf'))
    finally:
        assets.close()


def test_separator_cannot_be_replaced_by_filled_polygon(tmp_path, reg):
    root = tmp_path / 'source'; spec = structure_fixture(root, arrow=False)
    spec['paths'] = [{'id': 'ab', 'points': [[30, 20], [50, 20], [50, 25], [30, 25]],
                      'closed': True, 'fill': .5, 'semantic_role': 'decorative'}]
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out')
        assert error.value.code == 'source_structure_line_changed'
    finally:
        assets.close()


@pytest.mark.parametrize('mutation,code', [
    ('omit-pointer', 'source_structure_missing'),
    ('role', 'source_structure_unbound'),
    ('wrong-original', 'source_structure_original_unbound'),
    ('schema', 'source_structure_schema'),
    ('duplicate', 'source_structure_schema'),
])
def test_contract_cannot_be_silently_bypassed(tmp_path, reg, mutation, code):
    root = tmp_path / 'source'; spec = structure_fixture(root)
    path = root / 'relations.json'
    if mutation == 'omit-pointer':
        del spec['source_structure_contract']
        spec['policy']['require_source_structure_contract'] = False
    elif mutation == 'role':
        spec['sources'][1]['role'] = 'derived'
    elif mutation == 'wrong-original':
        value = json.loads(path.read_text()); value['source_sha256'] = '0' * 64
        path.write_text(json.dumps(value))
    elif mutation == 'schema':
        path.write_text('[]')
    elif mutation == 'duplicate':
        path.write_text('{"version":1,"version":1}')
    spec['sources'][1]['sha256'] = digest_file(path)
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            render_one(spec, reg, assets, root, tmp_path / 'out')
        assert error.value.code == code
    finally:
        assets.close()


def test_matching_contract_reports_actual_geometry(tmp_path, reg):
    root = tmp_path / 'source'; spec = structure_fixture(root)
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, root, tmp_path / 'out')
        assert report['source_structure_audit']['status'] == 'checked'
        assert report['source_structure_audit']['path_count'] == 1
        assert report['final_visibility_audit']['checked_paths'] == ['ab']
    finally:
        assets.close()


def test_standard_graph_layout_uses_same_contract_gate(tmp_path, reg):
    root = tmp_path / 'source'; spec = structure_fixture(root)
    spec.update(kind='graph', direction='LR', nodes=[{'id': key, 'text': text}
                for key, text in zip(('a', 'b', 'c'), ('Alpha', 'Beta', 'Gamma'))],
                edges=[{'id': 'ab', 'from': 'a', 'to': 'b'}])
    del spec['paths']
    assets = Assets()
    try:
        report = render_one(spec, reg, assets, root, tmp_path / 'out')
        assert report['source_structure_audit']['status'] == 'checked'
        assert report['final_visibility_audit']['checked_paths'] == ['ab']
    finally:
        assets.close()


@pytest.mark.parametrize('mutation', ['none', 'collapse', 'reverse'])
def test_separate_source_rules_keep_their_vertical_order(tmp_path, reg, mutation):
    root = tmp_path / 'source'; spec = structure_fixture(root, arrow=False)
    with fitz.open(root / 'original.pdf') as original:
        original[0].draw_line((10, 80), (70, 80), width=.5)
        original.saveIncr()
    spec['sources'][0]['sha256'] = digest_file(root / 'original.pdf')
    path = root / 'relations.json'; contract = json.loads(path.read_text())
    contract['source_sha256'] = spec['sources'][0]['sha256']
    contract['paths']['lower'] = {'from': None, 'to': None, 'arrow': 'none', 'line': 'solid'}
    contract['relations'] = [{'type': 'path_order', 'axis': 'y', 'paths': ['ab', 'lower']}]
    path.write_text(json.dumps(contract)); spec['sources'][1]['sha256'] = digest_file(path)
    y = {'none': 80, 'collapse': 20, 'reverse': 5}[mutation]
    spec['paths'].append({'id': 'lower', 'points': [[10, y], [70, y]], 'semantic_role': 'decorative'})
    assets = Assets()
    try:
        if mutation == 'none':
            report = render_one(spec, reg, assets, root, tmp_path / 'out')
            assert report['source_structure_audit']['relation_count'] == 1
        else:
            with pytest.raises(FigureError) as error:
                render_one(spec, reg, assets, root, tmp_path / 'out')
            assert error.value.code == 'source_structure_relation_changed'
    finally:
        assets.close()
