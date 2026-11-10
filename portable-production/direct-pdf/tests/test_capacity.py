"""Capacity is a source-bound observation of this plan, never a decision write."""
from copy import deepcopy
import json
import pytest
from journal_pdf.assets import Assets
from journal_pdf.capacity import check_capacity
from journal_pdf.cli import main
from journal_pdf.common import FigureError, PT_PER_MM, digest_file, digest_json
from journal_pdf.render import render_one


def scene(width=309, column='single'):
    return {'version': 1, 'id': 'capacity-plan', 'author': 'Synthetic', 'synthetic': True,
            'kind': 'scene', 'width_pt': width, 'height_pt': 50,
            'texts': [{'id': 'a', 'text': 'A', 'x': 20, 'y': 25}],
            'policy': {'column': column, 'design_font_size_pt': 8}}


def inspect(spec, reg, root):
    assets = Assets()
    try:
        return check_capacity(spec, reg, assets, root)
    finally:
        assets.close()


def test_measured_single_column_failure_matches_render_without_producing_pdf(reg, tmp_path):
    spec = scene()
    # A real source identity is checked before the layout, even for capacity-only.
    source = tmp_path/'source'; source.mkdir()
    identity = source/'original.txt'; identity.write_text('synthetic source identity')
    spec.pop('synthetic')
    spec['sources'] = [{'path': identity.name, 'sha256': digest_file(identity)}]
    original = deepcopy(spec)
    with pytest.raises(FigureError) as error:
        inspect(spec, reg, source)
    assert error.value.code == 'layout_reflow_required'
    capacity = error.value.details['capacity']
    assert capacity['figure_id'] == spec['id']
    assert capacity['spec_hash'] == digest_json(original)
    assert capacity['source_bindings'] == {identity.name: digest_file(identity)}
    assert capacity['layout_width_pt'] == 309
    assert capacity['available_width_pt'] == pytest.approx(80*PT_PER_MM - 4 - .5)
    assert capacity['proposed_font_size_pt'] == pytest.approx(5.754605916978825)
    assert capacity['minimum_width_mm_for_font_rule'] == pytest.approx((309*6/8+4.5)/PT_PER_MM)
    assert capacity['status'] == 'blocked-font'
    assert '5.75 pt' in capacity['summary'] and '80 mm' in capacity['summary']
    assert 'not a global minimum' in capacity['scope']
    assets = Assets()
    try:
        with pytest.raises(FigureError) as rendered:
            render_one(spec, reg, assets, source, tmp_path/'output')
    finally:
        assets.close()
    assert rendered.value.details['capacity'] == capacity
    assert spec == original
    assert not (tmp_path/'output').exists()
    assert not list(tmp_path.rglob('*.pdf'))


def test_fitting_plan_is_layout_only_not_publication_approval(reg, tmp_path):
    spec = scene(width=226); before = deepcopy(spec)
    result = inspect(spec, reg, tmp_path)
    capacity = result['capacity']
    assert result['pdf_produced'] is False
    assert result['ready_for_publication'] is False
    assert capacity['status'] == 'layout-checked'
    assert 6 <= capacity['proposed_font_size_pt'] < 8
    assert capacity['geometry_issues'] == []
    assert 'raster-internal typography are not measured' in capacity['scope']
    assert spec == before
    assert not list(tmp_path.rglob('*.pdf'))


def test_explicit_double_column_is_measured_as_requested_without_single_probe(reg, tmp_path):
    spec = scene(column='double'); before = deepcopy(spec)
    result = inspect(spec, reg, tmp_path)
    assert result['capacity']['requested_column'] == 'double'
    assert result['capacity']['column_mm'] == 160
    assert result['capacity']['proposed_font_size_pt'] == 8
    assert '双栏160 mm' in result['capacity']['summary']
    assert spec == before


def test_auto_does_not_switch_to_double_column(reg, tmp_path):
    spec = scene(column='auto'); before = deepcopy(spec)
    with pytest.raises(FigureError) as error:
        inspect(spec, reg, tmp_path)
    assert error.value.details['capacity']['requested_column'] == 'auto'
    assert error.value.details['capacity']['column_mm'] == 80
    assert spec == before


def test_report_uses_actual_rebuilt_font_instead_of_nominal_eight(reg, tmp_path):
    spec = {'id': 'responsive-graph', 'synthetic': True, 'kind': 'graph', 'direction': 'LR',
            'nodes': [{'id': 'a', 'text': '测试'*6},
                      {'id': 'b', 'text': '处理'*6}],
            'edges': [{'from': 'a', 'to': 'b'}], 'policy': {'column': 'single', 'design_font_size_pt': 8}}
    before = deepcopy(spec)
    capacity = inspect(spec, reg, tmp_path)['capacity']
    assert 6 <= capacity['layout_font_size_pt'] < 8
    assert capacity['whole_artwork_scale'] == 1
    assert capacity['proposed_font_size_pt'] == capacity['layout_font_size_pt']
    assert spec == before


def test_arrow_geometry_failure_keeps_real_measured_values(reg, tmp_path):
    spec = scene(width=130)
    spec['paths'] = [{'id': 'short', 'points': [[10, 40], [14, 40]], 'arrow': True}]
    with pytest.raises(FigureError) as error:
        inspect(spec, reg, tmp_path)
    assert error.value.code == 'no_feasible_layout'
    capacity = error.value.details['capacity']
    assert capacity['status'] == 'blocked-geometry'
    issue = next(i for i in capacity['geometry_issues'] if i['code'] == 'arrow_terminal_length')
    assert issue['actual_pt'] == 4
    assert issue['required_pt'] == pytest.approx(3*PT_PER_MM)
    assert 'arrow_terminal_length' in capacity['summary']
    assert capacity['proposed_font_size_pt'] == 8


def test_changed_source_blocks_capacity_without_a_stale_report(reg, tmp_path):
    spec = scene(width=130)
    source = tmp_path/'original.txt'; source.write_text('before')
    spec['sources'] = [{'path': source.name, 'sha256': digest_file(source)}]
    source.write_text('after')
    with pytest.raises(FigureError) as error:
        inspect(spec, reg, tmp_path)
    assert error.value.code == 'source_hash_mismatch'
    assert 'capacity' not in error.value.details


@pytest.mark.parametrize('column,expected_code', [('single', 2), ('double', 0)])
def test_capacity_cli_uses_existing_policy_and_does_not_write_inputs(profile, tmp_path, capsys, column, expected_code):
    spec = scene(column=column)
    source = tmp_path/'source'; source.mkdir()
    target = tmp_path/'plan.json'; target.write_text(json.dumps(spec))
    before = target.read_bytes()
    code = main(['capacity', str(target), '--source-root', str(source), '--profile', str(profile),
                 '--cache', str(tmp_path/'font-cache')])
    assert code == expected_code
    captured = capsys.readouterr()
    if code:
        result = json.loads(captured.err)
        assert result['error']['capacity']['status'] == 'blocked-font'
    else:
        result = json.loads(captured.out)
        assert result['capacity']['column_mm'] == 160
        assert result['pdf_produced'] is False
    assert target.read_bytes() == before
    assert not list(tmp_path.rglob('*.pdf'))


def test_capacity_cannot_claim_fitting_after_violating_registered_original_route(reg, tmp_path):
    from test_source_route_contract import render_fixture
    source = tmp_path/'source'; spec = render_fixture(source)
    result = inspect(spec, reg, source)
    assert result['capacity']['source_route_audit']['status'] == 'checked'
    spec['paths'][0]['points'] = [[30,20],[32,20],[32,5],[40,5],[40,20],[50,20]]
    with pytest.raises(FigureError) as error:
        inspect(spec, reg, source)
    assert error.value.code == 'source_route_bends_changed'
    assert not list(tmp_path.rglob('out/*.pdf'))
