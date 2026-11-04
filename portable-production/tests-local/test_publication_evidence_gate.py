import pytest

from localflow.core import FlowError, hash_json
from localflow.publishing import _check_source_and_visibility, _check_editorial_notices


def valid_report():
    return {
        'final_visibility_audit': {'status': 'checked', 'activation': 'explicit-full-scene', 'checked_assets': [], 'checked_paths': [], 'checked_nodes': [], 'checked_texts': []},
        'source_structure_audit': {'status': 'checked'},
        'original_asset_reference_coverage': {'status': 'not-applicable'},
        'assets': [],
        'layout': {'texts': [], 'paths': [], 'assets': [], 'nodes': []},
    }


def test_missing_visibility_blocks_delivery():
    report = valid_report()
    report['final_visibility_audit'] = {'status': 'not-checked'}
    with pytest.raises(FlowError, match='遮挡'):
        _check_source_and_visibility({'kind': 'scene'}, report)


def test_partial_visibility_blocks_delivery():
    report = valid_report()
    report['final_visibility_audit']['activation'] = 'source-bound-objects'
    with pytest.raises(FlowError, match='遮挡'):
        _check_source_and_visibility({'kind': 'scene'}, report)


def test_rebuilt_scene_requires_original_structure():
    report = valid_report()
    report['source_structure_audit'] = {'status': 'not-checked'}
    with pytest.raises(FlowError, match='结构'):
        _check_source_and_visibility({'kind': 'scene'}, report)


def test_structural_redraw_requires_contract_for_non_scene_templates():
    report = valid_report()
    report['source_structure_audit'] = {'status': 'not-checked'}
    with pytest.raises(FlowError, match='结构'):
        _check_source_and_visibility({'kind': 'network'}, report, 'structural_redraw')


def test_partial_original_asset_coverage_blocks_delivery():
    report = valid_report()
    report['original_asset_reference_coverage'] = {'status': 'partial'}
    with pytest.raises(FlowError, match='素材'):
        _check_source_and_visibility({'kind': 'chart'}, report)


def test_checked_evidence_allows_delivery_gate_to_continue():
    _check_source_and_visibility({'kind': 'scene'}, valid_report())


@pytest.mark.parametrize('code', ['legend_background_unverified', 'legend_data_overlap_unverified', 'source_text_coverage'])
def test_unresolved_warning_cannot_be_hidden_by_candidate_status(code):
    with pytest.raises(FlowError):
        _check_editorial_notices({'status': 'candidate-rendered', 'warnings': [{'code': code}]})


def test_asset_coverage_cannot_be_not_applicable_when_assets_exist():
    report = valid_report()
    report['assets'] = [{'id': 'icon'}]
    with pytest.raises(FlowError, match='素材'):
        _check_source_and_visibility({'kind': 'scene'}, report)


def test_visibility_must_cover_each_text():
    report = valid_report()
    report['layout']['texts'] = [{'id': 'title'}]
    with pytest.raises(FlowError, match='遮挡'):
        _check_source_and_visibility({'kind': 'scene'}, report)


def test_visibility_must_cover_visible_nodes():
    report = valid_report()
    report['layout']['nodes'] = [{'id': 'box', 'width': 0.5, 'gray': 0}]
    with pytest.raises(FlowError, match='遮挡'):
        _check_source_and_visibility({'kind': 'scene'}, report)


def test_warning_requires_exact_bound_evidence():
    warning = {'code': 'legend_data_overlap_unverified', 'id': 'legend-1'}
    report = {'status': 'candidate-editorial-review', 'warnings': [warning]}
    with pytest.raises(FlowError):
        _check_editorial_notices(report, [{'warning_sha256': hash_json(warning), 'evidence': 'short'}])
    with pytest.raises(FlowError):
        _check_editorial_notices(report, [{'warning_sha256': hash_json({'code': warning['code']}), 'evidence': 'Different warning does not match this candidate.'}])
    _check_editorial_notices(report, [{'warning_sha256': hash_json(warning), 'evidence': 'Checked this legend against the synthetic source and output.'}])


@pytest.mark.parametrize('resolved', [{'warning_sha256': 'x'}, [{'warning_sha256': []}],
    [{'warning_sha256':'x'}, {'warning_sha256':'x'}]])
def test_malformed_warning_evidence_fails_closed(resolved):
    with pytest.raises(FlowError):
        _check_editorial_notices({'status':'candidate-rendered', 'warnings':[]}, resolved)
