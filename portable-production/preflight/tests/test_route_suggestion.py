"""Synthetic first-route decisions; no manuscript fixtures or OCR."""
import copy
import json
import subprocess
import sys

import pytest

from journal_preflight.route_suggestion import suggest_route


def review(structure='plot'):
    return {'source_snapshot': {'source': 'a'*64}, 'structure': structure,
            'text_requirement': 'replace', 'data_preservation': 'required',
            'topology': 'not_applicable',
            'evidence': [{'source_id': 'source', 'source_sha256': 'a'*64,
                          'location': 'whole synthetic figure', 'observation': 'Axes and original data geometry recorded.'}]}


def case():
    return {'id': 'synthetic-pair', 'paired': True,
            'hashes': {'source': 'b'*64, 'word': 'c'*64, 'final': 'd'*64},
            'structure': 'plot', 'observed_method': 'plot_reletter',
            'method_basis': 'observed_difference', 'scope': 'Only observed axis lettering changes.',
            'observation_evidence': ['Paired original, Word placement and final show retained data geometry.']}


def test_first_route_does_not_require_method_and_does_not_certify_observation():
    # Given: source facts and paired historical evidence, without query.method.
    source = review()
    before = copy.deepcopy(source)
    # When: making a proposal.
    result = suggest_route(source, [case()])
    # Then: suggestion stays separate from editorial readiness and acceptance.
    assert result['candidate_route'] == 'plot_reletter'
    assert result['case_refs'][0]['method_basis'] == 'observed_difference'
    assert result['case_refs'][0]['differences'] == []
    assert result['ready_for_processing'] is False
    assert result['semantics_independently_verified'] is False
    assert source == before


@pytest.mark.parametrize('structure,text,data,topology,expected', [
    ('node_link','replace','not_applicable','reconstructable','structural_redraw'),
    ('plot','replace','required','not_applicable','plot_reletter'),
    ('photo','none','required','not_applicable','raster_grayscale_single_column'),
    ('ui','preserve_native','required','not_applicable','raster_grayscale_single_column'),
    ('mixed','replace','required','unknown','unresolved'),
    ('unknown','unknown','unknown','unknown','unresolved'),
    ('plot','replace','unknown','not_applicable','unresolved'),
    ('node_link','replace','required','reconstructable','unresolved'),
    ('ui','replace','required','not_applicable','unresolved'),
])
def test_joint_facts_determine_only_supported_candidates(structure,text,data,topology,expected):
    source = review(structure)
    source.update(text_requirement=text,data_preservation=data,topology=topology)
    result = suggest_route(source, [case()])
    assert result['candidate_route'] == expected
    if expected == 'unresolved': assert result['blocking']


def test_override_preserved_but_does_not_waive_conflicting_text_needs():
    source = review()
    override = {'route': 'raster_grayscale_single_column', 'provenance': {
        'actor': 'user', 'reference': 'synthetic-message', 'quote': 'Retain grayscale route.',
        'recorded_at': '2026-10-26T00:00:00Z', 'source_snapshot': source['source_snapshot']}}
    result = suggest_route(source, [case()], user_override=override)
    assert result['candidate_route'] == override['route']
    assert result['proposed_route'] == 'plot_reletter'
    assert result['blocking']


def test_cli_entry_writes_non_ready_proposal(tmp_path):
    source, cases, output = (tmp_path / name for name in ('source.json','cases.json','proposal.json'))
    source.write_text(json.dumps(review()))
    cases.write_text(json.dumps([case()]))
    result = subprocess.run([sys.executable,'-m','journal_preflight','suggest-route',str(source),
                             '--cases',str(cases),'--out',str(output)],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())['ready_for_processing'] is False

@pytest.mark.parametrize('change', ['unpaired','bad_hash','empty_observation','unknown_method','stale_source','stale_override'])
def test_unbound_evidence_cannot_enter_route_proposal(change):
    from journal_preflight.editorial_route import ContractError
    source, historical = review(), case()
    override = None
    if change == 'unpaired': historical['paired'] = False
    elif change == 'bad_hash': historical['hashes']['word'] = 'missing'
    elif change == 'empty_observation': historical['observation_evidence'] = []
    elif change == 'unknown_method': historical['observed_method'] = 'svg-means-redraw'
    elif change == 'stale_source': source['evidence'][0]['source_sha256'] = 'f'*64
    else:
        override = {'route': 'plot_reletter', 'provenance': {'actor': 'user',
            'reference': 'message', 'quote': 'Keep data.', 'recorded_at': '2026-10-26T00:00:00Z',
            'source_snapshot': {'source': 'f'*64}}}
    with pytest.raises(ContractError):
        suggest_route(source, [historical], user_override=override)


def test_case_method_is_not_prefiltered_and_disagreement_is_visible():
    historical = case()
    historical.update(observed_method='structural_redraw', method_basis='historical_record')
    result = suggest_route(review(), [historical])
    assert result['candidate_route'] == 'plot_reletter'
    assert result['case_refs'][0]['method_basis'] == 'historical_record'
    assert result['case_refs'][0]['applicability'] == 'contrast_only'
    assert result['case_refs'][0]['differences']
    assert result['blocking']
