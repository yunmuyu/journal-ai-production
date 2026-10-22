"""Publication consumes measured font policy; low-level previews remain available."""
import json
from pathlib import Path
import pytest
import test_localflow as fixtures
from localflow.core import FlowError, write_json, hash_file, hash_json
from localflow.probing import probe
from localflow.rendering import render, check_candidate
from localflow.publishing import review, publish


@pytest.mark.parametrize('size', [6, 7.5])
def test_real_preview_without_default_start_cannot_enter_publication(size):
    fixture = fixtures.LocalFlowTest()
    fixture.setUp()
    try:
        spec = json.loads(fixture.spec.read_text())
        spec['policy']['design_font_size_pt'] = size
        write_json(fixture.spec, spec)
        pid = probe(fixture.config, fixture.manifest)['probe_id']
        result = render(fixture.config, fixture.spec, fixture.constraints, pid)
        cid = result['candidate_id']
        candidate, report, artifact = check_candidate(fixture.config, cid)
        assert artifact.is_file()  # Legitimate low-level preview not forbidden.
        assert report['layout']['layout_evidence']['initial_design_font_size_pt'] == size
        assert report['layout']['layout_evidence']['priority'].startswith('explicit-design-size-input')
        record = {'candidate_id': cid, 'output_sha256': candidate['output_sha256'],
            'constraints_sha256': candidate['constraints_sha256'],
            'source_hashes': {r['path']: r['sha256'] for r in report['source_bindings']},
            'author_rel': '编辑/作者', 'figure_number': '1', 'reviewer': 'synthetic reviewer',
            'content': {'conclusion': 'approved', 'evidence': ['Synthetic source checked for this regression, not real approval.']},
            'visual': {'conclusion': 'approved', 'evidence': ['Synthetic preview checked for this regression, not real approval.']}}
        path = Path(fixture.temp.name) / 'review.json'
        write_json(path, record)
        with pytest.raises(FlowError) as error:
            review(fixture.config, cid, path)
        assert error.value.code == 'publication_font_policy'
        # A forged persisted visual approval cannot replace the policy evidence.
        write_json(fixture.config.state_root / 'reviews' / f'{cid}.json',
                   {'record': record, 'record_sha256': hash_json(record)})
        with pytest.raises(FlowError) as error:
            publish(fixture.config, cid, '编辑/作者', '1')
        assert error.value.code == 'publication_font_policy'
        assert not list(fixture.author.glob('*.pdf'))
    finally:
        fixture.tearDown()


def test_plot_publication_does_not_accept_scene_labels_or_empty_axis_audit():
    from localflow.publishing import _check_chart_semantics
    report = {'kind': 'scene', 'layout': {'texts': [
        {'id': 'xtitle', 'role': 'label'}, {'id': 'ytitle', 'role': 'label'}]},
        'pdf_audit': {'axis_unit_notation': {'ok': True, 'checks': []}}}
    with pytest.raises(FlowError) as error:
        _check_chart_semantics({'kind': 'scene'}, report)
    assert error.value.code == 'publication_chart_semantics'
    report['kind'] = 'chart'
    with pytest.raises(FlowError):
        _check_chart_semantics({'kind': 'chart'}, report)


@pytest.mark.parametrize('mutation', ['empty', 'generic_roles', 'missing_axis', 'not_in_pdf', 'pending_semantics', None])
def test_chart_publication_requires_both_measured_axis_title_checks(mutation):
    from localflow.publishing import _check_chart_semantics
    report = {'kind': 'chart', 'layout': {'texts': [
        {'id': 'xtitle', 'role': 'axis-title'}, {'id': 'ytitle', 'role': 'axis-title'}]},
        'pdf_audit': {'axis_unit_notation': {'ok': True, 'checks': [
            {'id': name, 'actual_pdf_contains_expected': True, 'scene_matches_rule': True,
             'status': 'already-normalized'} for name in ('xtitle', 'ytitle')]}}}
    checks = report['pdf_audit']['axis_unit_notation']['checks']
    if mutation == 'empty': checks.clear()
    elif mutation == 'generic_roles': report['layout']['texts'][0]['role'] = 'label'
    elif mutation == 'missing_axis': checks.pop()
    elif mutation == 'not_in_pdf': checks[0]['actual_pdf_contains_expected'] = False
    elif mutation == 'pending_semantics': checks[0]['status'] = 'semantic_review_needed'
    if mutation is None:
        _check_chart_semantics({'kind': 'chart'}, report)
    else:
        with pytest.raises(FlowError) as error:
            _check_chart_semantics({'kind': 'chart'}, report)
        assert error.value.code == 'publication_chart_semantics'


def test_actual_8pt_scene_cannot_publish_as_registered_plot():
    from journal_preflight.editorial_route import COMMON_CHECKS, ROUTE_CHECKS
    fixture = fixtures.LocalFlowTest()
    fixture.setUp()
    try:
        spec = json.loads(fixture.spec.read_text())
        spec = {key: spec[key] for key in ('id', 'author', 'author_rel', 'figure_number', 'processing_method', 'sources')}
        spec.update(version=1, kind='scene', width_pt=100, height_pt=40,
            texts=[{'id': 'x', 'text': 'x (s)', 'x': 50, 'y': 12},
                   {'id': 'y', 'text': 'y (V)', 'x': 50, 'y': 28}],
            policy={'column': 'single', 'design_font_size_pt': 8})
        write_json(fixture.spec, spec)
        constraints = json.loads(fixture.constraints.read_text())
        row = constraints['confirmed']['editorial_route_contract']['figures'][0]
        row['decision']['route'] = row['decision']['proposed']['route'] = 'plot_reletter'
        row['checks'] = {name: {'status': 'recorded_satisfied', 'evidence_ids': ['test-review']}
                         for name in COMMON_CHECKS + ROUTE_CHECKS['plot_reletter']}
        write_json(fixture.constraints, constraints)
        pid = probe(fixture.config, fixture.manifest)['probe_id']
        cid = render(fixture.config, fixture.spec, fixture.constraints, pid)['candidate_id']
        candidate, report, artifact = check_candidate(fixture.config, cid)
        assert report['pdf_audit']['axis_unit_notation']['ok'] is True
        assert report['pdf_audit']['axis_unit_notation']['checks'] == []
        # This was the bypass: generic labels gave a vacuously successful audit.
        record_path = Path(fixture.temp.name) / 'unused-review.json'
        write_json(record_path, {})
        with pytest.raises(FlowError) as error:
            review(fixture.config, cid, record_path)
        assert error.value.code == 'publication_chart_semantics'
        assert artifact.exists() and not list(fixture.author.glob('*.pdf'))
    finally:
        fixture.tearDown()


@pytest.mark.parametrize('matches_current_source', [False, True])
def test_real_font_exception_must_bind_candidate_source(matches_current_source):
    fixture = fixtures.LocalFlowTest()
    fixture.setUp()
    try:
        spec = json.loads(fixture.spec.read_text())
        spec['policy']['design_font_size_pt'] = 6
        source_sha = spec['sources'][0]['sha256'] if matches_current_source else 'b' * 64
        exception = {'source_sha256': source_sha, 'reply_sha256': 'c' * 64,
            'design_font_size_pt': 6, 'reason': 'Synthetic explicit size exception binding regression.',
            'evidence_ref': 'synthetic-record:external-size-exception'}
        spec['ingest_provenance'] = {'source_file_sha256': source_sha, 'reply_hash': 'c' * 64,
            'production_font_policy': {'design_font_size_pt': 6,
                'basis': 'explicit-production-policy-exception', 'exception': exception}}
        write_json(fixture.spec, spec)
        pid = probe(fixture.config, fixture.manifest)['probe_id']
        cid = render(fixture.config, fixture.spec, fixture.constraints, pid)['candidate_id']
        candidate, report, artifact = check_candidate(fixture.config, cid)
        record = {'candidate_id': cid, 'output_sha256': candidate['output_sha256'],
            'constraints_sha256': candidate['constraints_sha256'],
            'source_hashes': {r['path']: r['sha256'] for r in report['source_bindings']},
            'author_rel': '编辑/作者', 'figure_number': '1', 'reviewer': 'synthetic reviewer',
            'content': {'conclusion': 'approved', 'evidence': ['Synthetic test source and topology evidence recorded.']},
            'visual': {'conclusion': 'approved', 'evidence': ['Synthetic test output checked; not customer acceptance.']}}
        path = Path(fixture.temp.name) / 'review.json'
        write_json(path, record)
        if matches_current_source:
            assert review(fixture.config, cid, path)['status'] == 'agent-reviewed'
            assert publish(fixture.config, cid, '编辑/作者', '1')['status'] == 'published-candidate'
        else:
            with pytest.raises(FlowError) as error:
                review(fixture.config, cid, path)
            assert error.value.code == 'publication_font_policy'
            write_json(fixture.config.state_root / 'reviews' / f'{cid}.json',
                       {'record': record, 'record_sha256': hash_json(record)})
            with pytest.raises(FlowError) as error:
                publish(fixture.config, cid, '编辑/作者', '1')
            assert error.value.code == 'publication_font_policy'
            assert artifact.is_file() and not list(fixture.author.glob('*.pdf'))
    finally:
        fixture.tearDown()


def test_real_chart_with_nonempty_axis_audits_can_publish(tmp_path):
    import os
    from dataclasses import replace
    from test_native_jpg_publishing import setup_job, review_record
    from journal_preflight.editorial_route import COMMON_CHECKS, ROUTE_CHECKS
    from localflow.core import json_file
    job = list(setup_job(tmp_path))
    profile = Path(os.environ.get('JFW_TEST_FONT_PROFILE', fixtures.RELEASE / 'fonts.local.json'))
    job[0] = replace(job[0], font_profile=profile)
    original = json_file(job[2])
    spec = {key: original[key] for key in ('id', 'author', 'author_rel', 'figure_number', 'sources')}
    spec.update(version=1, kind='chart', source_kind='raster', source=job[1].name,
        processing_method='reletter', plot_clip=[10, 20, 310, 110], axis_frame_source=[10, 20, 310, 110],
        plot_width_pt=100, x_ticks=[{'text': '0', 'position': 10}, {'text': '1', 'position': 310}],
        y_ticks=[{'text': '0', 'position': 110}, {'text': '1', 'position': 20}],
        x_title='Time(s)', y_title='Voltage(V)',
        series=[{'id': 'synthetic-series', 'label': 'A', 'swatch_clip': [10, 0, 40, 10]}],
        legend_placement='outside-top', legend_frame=False,
        mask_semantic_evidence={'approved_empty_background': True, 'reason': 'Synthetic separate swatch region outside plot.'},
        tick_length_source_units=0, policy={'column': 'single', 'design_font_size_pt': 8})
    write_json(job[2], spec)
    constraints = json_file(job[3])
    confirmed = constraints['confirmed']
    confirmed.update(processing_method='reletter', backend='direct-pdf', output_format='pdf')
    figure = confirmed['editorial_route_contract']['figures'][0]
    figure['decision']['route'] = figure['decision']['proposed']['route'] = 'plot_reletter'
    figure['checks'] = {name: {'status': 'recorded_satisfied', 'evidence_ids': ['review-1']}
                        for name in COMMON_CHECKS + ROUTE_CHECKS['plot_reletter']}
    write_json(job[3], constraints)
    cid = render(job[0], job[2], job[3], job[4])['candidate_id']
    candidate, report, artifact = check_candidate(job[0], cid)
    assert len(report['pdf_audit']['axis_unit_notation']['checks']) == 2
    record = review_record(job, cid, candidate, report)
    path = tmp_path / 'chart-review.json'
    write_json(path, record)
    assert review(job[0], cid, path)['status'] == 'agent-reviewed'
    result = publish(job[0], cid, 'editor/author', '1')
    assert result['status'] == 'published-candidate'
    assert Path(result['target']).read_bytes() == artifact.read_bytes()
