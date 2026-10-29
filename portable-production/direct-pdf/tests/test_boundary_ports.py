import pytest

from journal_pdf.scene import Scene, audit_scene


def endpoint_issues(scene):
    return [item for item in audit_scene(scene) if 'endpoint' in item['code']]


@pytest.mark.parametrize('direction,gap', [('horizontal',21),('vertical',15),('horizontal',8.503937),('vertical',8.503937)])
def test_ordinary_bound_straight_arrow_checks_spacing_without_claiming_every_long_arrow_wrong(reg,direction,gap):
    scene=Scene(reg).finish(150,150)
    scene.shape('first',[20,20,40,40])
    if direction=='horizontal':
        scene.shape('second',[40+gap,20,60+gap,40]);points=[[40,30],[40+gap,30]]
    else:
        scene.shape('second',[20,40+gap,40,60+gap]);points=[[30,40],[30,40+gap]]
    scene.line('direct',points,arrow=True,endpoint_nodes=['first','second'])
    audit_scene(scene)
    entry=next(v for v in scene.layout_evidence['straight_connection_spacing'] if v['id']=='direct')
    assert entry['gap_pt']==pytest.approx(gap)
    assert any(n['code']=='straight_connection_spacing_review' for n in scene.notes)==(gap>10)


def test_explicit_fraction_accepts_real_rect_edge_when_not_midpoint(reg):
    # Given a real collector and a source node.
    scene = Scene(reg).finish(250, 160)
    scene.shape('source', [190, 140, 210, 150])
    scene.shape('collect', [167, 105.16875, 223.0625, 127.575])
    # When a connection declares its actual bottom-edge fractional endpoint.
    scene.line('gateway-collect', [[200, 140], [200, 127.575]], arrow=True,
               endpoint_nodes=['source', {'node': 'collect', 'side': 'bottom',
                                         'fraction': (200 - 167) / 56.0625}])
    # Then the explicitly bound endpoint passes, rather than requiring a fake node.
    assert endpoint_issues(scene) == []
    assert scene.layout_evidence['node_boundary_ports'][0]['verified'] is True


def test_two_offset_boxes_can_connect_straight_at_distinct_edge_fractions(reg, tmp_path):
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one
    import fitz

    spec = {'version': 1, 'id': 'offset-ports', 'author': 'synthetic', 'kind': 'scene', 'synthetic': True,
            'width_pt': 140, 'height_pt': 100, 'policy': {'column': 'single'},
            'nodes': [{'id': 'upper', 'rect': [20, 10, 80, 30]},
                      {'id': 'lower', 'rect': [60, 70, 120, 90]}],
            'paths': [{'id': 'direct', 'points': [[70, 30], [70, 70]], 'arrow': True,
                       'endpoint_nodes': [{'node': 'upper', 'side': 'bottom', 'fraction': 5/6},
                                          {'node': 'lower', 'side': 'top', 'fraction': 1/6}]}]}
    source = tmp_path / 'source'; source.mkdir()
    assets = Assets()
    try:
        result = render_one(spec, reg, assets, source, tmp_path / 'output')
    finally:
        assets.close()
    with fitz.open(tmp_path / 'output' / result['output_pdf']) as document:
        assert len(document[0].get_drawings()) == 4


def test_declared_straight_row_spacing_uses_editor_approved_default(reg):
    from journal_pdf.layouts import primitive

    spec = {'width_pt': 140, 'height_pt': 100,
            'nodes': [{'id': 'a', 'rect': [20, 10, 80, 30]},
                      {'id': 'b', 'rect': [60, 53, 120, 73]}],
            'paths': [{'id': 'vertical', 'points': [[70, 30], [70, 53]], 'arrow': True,
                       'endpoint_nodes': [{'node': 'a', 'side': 'bottom', 'fraction': 5/6},
                                          {'node': 'b', 'side': 'top', 'fraction': 1/6}]}],
            'straight_vertical_spacing': [{'paths': ['vertical'],'gap_pt':23}]}
    scene = primitive(spec, reg, 8)
    assert not any(i['code'].startswith('vertical_spacing_') for i in audit_scene(scene))
    assert scene.layout_evidence['straight_vertical_spacing'][0]['expected_pt'] == 23
    spec['paths'][0]['points'][1][1] = 58
    scene = primitive(spec, reg, 8)
    assert any(i['code'] == 'vertical_spacing_mismatch' for i in audit_scene(scene))


def test_straight_row_default_uses_existing_three_mm(reg):
    from journal_pdf.layouts import primitive
    from journal_pdf.editorial import ARROW_LENGTH
    end=30+ARROW_LENGTH
    spec={'width_pt':100,'height_pt':80,'nodes':[{'id':'a','rect':[20,10,80,30]},
          {'id':'b','rect':[20,end,80,end+20]}],
          'paths':[{'id':'vertical','points':[[50,30],[50,end]],'arrow':True,
                    'endpoint_nodes':['a','b']}],
          'straight_vertical_spacing':[{'paths':['vertical']}]}
    scene=primitive(spec,reg,8)
    assert scene.layout_evidence.get('straight_vertical_spacing') is None
    assert not any(i['code'].startswith('vertical_spacing_') for i in audit_scene(scene))
    assert scene.layout_evidence['straight_vertical_spacing'][0]['expected_pt']==pytest.approx(ARROW_LENGTH)


@pytest.mark.parametrize('declaration', [
    'collect',
    {'node': 'collect', 'side': 'bottom', 'fraction': .2},
    {'node': 'collect', 'side': 'bottom', 'fraction': 1.1},
    {'node': 'collect', 'side': 'bottom', 'fraction': True},
    {'node': 'missing', 'side': 'bottom', 'fraction': .5},
    {'node': 'collect', 'side': 'diagonal', 'fraction': .5},
])
def test_nonmidpoint_requires_exact_valid_declaration(reg, declaration):
    # Given a non-midpoint endpoint and an invalid or absent declaration.
    scene = Scene(reg).finish(250, 160)
    scene.shape('source', [190, 140, 210, 150])
    scene.shape('collect', [167, 105.16875, 223.0625, 127.575])
    # When auditing the real path.
    scene.line('incoming', [[200, 140], [200, 127.575]], arrow=True,
               endpoint_nodes=['source', declaration])
    # Then the endpoint remains rejected.
    assert endpoint_issues(scene)


def test_closed_rectangle_path_is_explicit_boundary_target(reg):
    # Given an actual dashed rectangular group boundary.
    scene = Scene(reg).finish(160, 160)
    scene.shape('source', [30, 110, 50, 130])
    scene.line('layer', [[20, 20], [120, 20], [120, 90], [20, 90], [20, 20]], dash=[4, 2])
    # When its bottom edge is explicitly referenced.
    scene.line('incoming', [[40, 110], [40, 90]], arrow=True,
               endpoint_nodes=['source', {'path': 'layer', 'side': 'bottom', 'fraction': .2}])
    # Then real boundary ownership is retained.
    assert endpoint_issues(scene) == []


def test_asset_endpoint_uses_real_embedded_viewport(reg):
    # Given an embedded source viewport without a decorative node.
    scene = Scene(reg).finish(160, 160)
    scene.shape('source', [20, 60, 40, 80])
    scene.assets.append({'id': 'phone', 'rect': [90, 40, 120, 100]})
    # When its actual left boundary is explicitly referenced.
    scene.line('incoming', [[40, 70], [90, 70]], arrow=True,
               endpoint_nodes=['source', {'asset': 'phone', 'side': 'left', 'fraction': .5}])
    # Then no synthetic node is required.
    assert endpoint_issues(scene) == []


def test_midpoint_default_remains_valid_and_terminal_rule_remains(reg):
    # Given legacy four-midpoint endpoints with an insufficient terminal.
    scene = Scene(reg).finish(100, 100)
    scene.shape('source', [10, 10, 30, 30])
    scene.shape('target', [35, 10, 55, 30])
    scene.line('legacy', [[30, 20], [35, 20]], arrow=True,
               endpoint_nodes=['source', 'target'])
    # When auditing with the new optional declarations unused.
    issues = audit_scene(scene)
    # Then midpoint semantics still pass and the 3 mm terminal is still enforced.
    assert endpoint_issues(scene) == []
    assert any(item['code'] == 'arrow_terminal_length' for item in issues)

@pytest.mark.parametrize('points', [
    [[20, 20], [120, 20], [100, 90], [20, 90], [20, 20]],
    [[20, 20], [120, 20], [120, 90], [20, 90]],
    [[20, 20], [120, 90], [120, 20], [20, 90], [20, 20]],
])
def test_nonrectangular_paths_cannot_be_boundary_targets(reg, points):
    # Given an open, diagonal, or self-crossing path.
    scene = Scene(reg).finish(160, 160)
    scene.shape('source', [30, 110, 50, 130])
    scene.line('layer', points)
    # When declaring its bounding rectangle as a port.
    scene.line('incoming', [[40, 110], [40, 90]], arrow=True,
               endpoint_nodes=['source', {'path': 'layer', 'side': 'bottom', 'fraction': .2}])
    # Then only a real rectangular boundary is accepted.
    assert endpoint_issues(scene)


def test_path_owned_label_retains_collision_checks(reg):
    # Given a label owned by a real connection that crosses its ink.
    scene = Scene(reg).finish(150, 100)
    scene.line('connection', [[10, 50], [140, 50]])
    scene.text('label', 'DATA', 75, 50, owner='connection')
    # When auditing ownership and geometry.
    issues = audit_scene(scene)
    # Then ownership resolves but a collision still rejects the label.
    assert not any(item['code'] == 'text_owner_missing' for item in issues)
    assert any(item['code'] == 'text_path_collision' for item in issues)


def test_missing_owner_is_still_rejected(reg):
    # Given a label naming a nonexistent path.
    scene = Scene(reg).finish(150, 100)
    scene.text('label', 'DATA', 75, 50, owner='missing')
    # When auditing real ownership.
    issues = audit_scene(scene)
    # Then an arbitrary owner does not bypass the check.
    assert any(item['code'] == 'text_owner_missing' for item in issues)


def test_declared_ports_render_through_public_scene_surface(reg, tmp_path):
    import pymupdf as fitz
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one

    # Given a public scene with a real rectangle and a non-midpoint boundary.
    spec = {'id': 'fractional-port-e2e', 'author': 'Synthetic', 'kind': 'scene', 'synthetic': True,
            'width_pt': 150, 'height_pt': 120, 'policy': {'column': 'single'},
            'nodes': [{'id': 'top', 'rect': [20, 10, 120, 30]},
                      {'id': 'bottom', 'rect': [20, 90, 120, 110]}],
            'paths': [{'id': 'data', 'points': [[40, 30], [40, 81.49606299212599], [40, 90]],
                       'arrow': True, 'exact_terminal': True,
                       'endpoint_nodes': [{'node': 'top', 'side': 'bottom', 'fraction': .2},
                                          {'node': 'bottom', 'side': 'top', 'fraction': .2}]}]}
    assets = Assets()
    try:
        # When the existing public renderer produces the PDF.
        source_root = tmp_path / 'source'
        source_root.mkdir()
        result = render_one(spec, reg, assets, source_root, tmp_path / 'output')
    finally:
        assets.close()
    # Then the output has the real frames and connection, without synthetic nodes.
    with fitz.open(tmp_path / 'output' / result['output_pdf']) as document:
        assert len(document[0].get_drawings()) == 4
