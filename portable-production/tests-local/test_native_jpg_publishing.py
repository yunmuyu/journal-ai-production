"""Native JPG end-to-end regressions using only generated, public test pixels.

The probe, source-bound raster reconstruction, editorial gate and review binding
are real. No customer images, fonts, production records or gate mocks are used.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from localflow.core import Config, FlowError, hash_file, hash_json, json_file, write_json
from localflow.probing import probe
from localflow.publishing import accept, audit_jpg_compatibility, publish, review, target_for_artifact
from localflow.raster_candidates import render_raster
from localflow.rendering import check_candidate
from journal_preflight.editorial_route import COMMON_CHECKS, ROUTE_CHECKS


def setup_job(tmp_path, *, target_basename=None, source_is_target=False, width_mm=None):
    delivery = tmp_path / 'delivery'
    author = delivery / 'editor' / 'author'
    author.mkdir(parents=True)
    sources = author if source_is_target else tmp_path / 'sources'
    sources.mkdir(exist_ok=True)
    source = sources / ('author-图1.jpg' if source_is_target else 'source.png')
    image = Image.new('RGB', (320, 120), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 319, 119), outline='black', width=3)
    draw.line((5, 100, 60, 20, 200, 70, 315, 10), fill=(23, 90, 160), width=4)
    draw.text((15, 40), 'Synthetic A / B 1.0', fill='black')
    image.save(source)
    digest = hash_file(source)
    config = Config(delivery, tmp_path / 'state', tmp_path / 'fonts-not-needed.json', tmp_path / 'cache')
    manifest = tmp_path / 'manifest.json'
    write_json(manifest, {'source_root': str(sources), 'files': [{'id': 'source', 'path': source.name}]})
    probe_id = probe(config, manifest)['probe_id']
    route = 'raster_grayscale_single_column'
    figure = {'id': 'figure-1', 'sources': [{'id': 'source', 'sha256': digest}],
        'decision': {'proposed': {'route': route, 'column': 'single'}, 'route': route,
            'column': 'single', 'reason': 'Synthetic full-canvas test with explicitly retained original geometry.', 'overrides': []},
        'evidence': [{'id': 'review-1', 'source_id': 'source', 'source_sha256': digest,
            'method': 'synthetic fixture', 'location': 'whole image',
            'observation': 'Generated test border, line and text all belong to this same source.'}],
        'checks': {name: {'status': 'recorded_satisfied', 'evidence_ids': ['review-1']}
            for name in COMMON_CHECKS + ROUTE_CHECKS[route]}, 'author_issues': []}
    output = {'author_rel': 'editor/author', 'figure_number': '1'}
    if target_basename is not None:
        output['target_basename'] = target_basename
    constraints = {'confirmed': {'split': 'single', 'processing_method': 'full-canvas-grayscale',
        'backend': 'raster-preprocess', 'output_format': 'jpg', 'column': 'single', 'expected_outputs': [output],
        'editorial_route_contract': {'schema_version': 'editorial-route/1', 'figures': [figure]},
        'editorial_figure_id': 'figure-1', 'editorial_targets': [{'id': 'figure-1', 'author_rel': 'editor/author', 'figure_number': '1'}]}}
    spec = {'id': 'synthetic-raster', 'author': 'author', 'author_rel': 'editor/author', 'figure_number': '1',
        'processing_method': 'full-canvas-grayscale', 'source_path': source.name,
        'sources': [{'path': source.name, 'sha256': digest, 'role': 'source'}], 'policy': {'column': 'single'}}
    if target_basename is not None:
        spec['target_basename'] = target_basename
    if width_mm is not None:
        spec['policy']['width_mm'] = width_mm
    spec_path, constraints_path = tmp_path / 'spec.json', tmp_path / 'constraints.json'
    write_json(spec_path, spec)
    write_json(constraints_path, constraints)
    return config, source, spec_path, constraints_path, probe_id


def build(job):
    config, _, spec, constraints, pid = job
    result = render_raster(config, spec, constraints, pid)
    cid = result['candidate_id']
    candidate, report, path = check_candidate(config, cid)
    return cid, candidate, report, path


def review_record(job, cid, candidate, report):
    config = job[0]
    output = json_file(job[3])['confirmed']['expected_outputs'][0]
    return {'candidate_id': cid, 'output_sha256': candidate['output_sha256'],
        'constraints_sha256': candidate['constraints_sha256'],
        'source_hashes': {row['path']: row['sha256'] for row in report['source_bindings']},
        **output, 'reviewer': 'synthetic-reviewer',
        'content': {'conclusion': 'approved', 'evidence': ['The generated border and all synthetic line and text content were checked.']},
        'visual': {'conclusion': 'approved', 'evidence': ['The native single-column JPEG has the same full canvas and no added crop.']}}


def approved(job):
    cid, candidate, report, path = build(job)
    record_path = job[0].state_root / 'test-review.json'
    write_json(record_path, review_record(job, cid, candidate, report))
    reviewed = review(job[0], cid, record_path)
    assert reviewed['acceptance'] == 'not_recorded'
    return cid, candidate, report, path


@pytest.mark.parametrize('basename', [None, 'author-图1.jpg', 'author-图1.jpeg'])
def test_native_jpg_chain_is_atomic_idempotent_and_not_approved(tmp_path, basename):
    job = setup_job(tmp_path, target_basename=basename)
    config = job[0]
    before = hash_file(job[1])
    cid, candidate, report, artifact = approved(job)
    result = publish(config, cid, 'editor/author', '1', target_basename=basename)
    target = Path(result['target'])
    assert target.name == (basename or 'author-图1.jpg')
    assert result['status'] == 'published-candidate' and result['acceptance'] == 'not_recorded'
    assert target.read_bytes() == artifact.read_bytes()
    assert not list(config.state_root.glob('accepted/**/*.json'))
    assert hash_file(job[1]) == before
    with Image.open(target) as image:
        assert image.format == 'JPEG' and image.mode == 'L' and image.size == (320, 120)
    assert audit_jpg_compatibility(target, report)['width_mm'] == pytest.approx(80)
    assert publish(config, cid, 'editor/author', '1', target_basename=basename)['status'] == 'already-published'
    assert not list(target.parent.glob('.publish-*'))
    result = accept(config, 'editor/author', '1', candidate['output_sha256'], 'explicit-test-human',
        'Explicit synthetic acceptance of the source and final full-canvas JPG.')
    assert result['status'] == 'accepted'
    assert publish(config, cid, 'editor/author', '1', target_basename=basename)['status'] == 'already-accepted'
    assert accept(config, 'editor/author', '1', candidate['output_sha256'], 'explicit-test-human',
        'Explicit synthetic acceptance of the source and final full-canvas JPG.')['status'] == 'already-accepted'


def test_exact_hash_replacement_archives_native_jpg(tmp_path):
    job = setup_job(tmp_path)
    cid, candidate, _, _ = approved(job)
    target = job[0].delivery_root / 'editor/author/author-图1.jpg'
    target.write_bytes(b'previous manual bytes')
    old = hash_file(target)
    with pytest.raises(FlowError, match='不同内容'):
        publish(job[0], cid, 'editor/author', '1')
    with pytest.raises(FlowError):
        publish(job[0], cid, 'editor/author', '1', '0' * 64)
    publish(job[0], cid, 'editor/author', '1', old)
    archived = job[0].state_root / 'archive/editor/author' / target.name / f'{old}.jpg'
    assert hash_file(archived) == old
    assert hash_file(target) == candidate['output_sha256']


@pytest.mark.parametrize('suffix', ['.pdf', '.jpeg', '.JPG'])
def test_cross_format_and_casefold_collisions_fail_closed(tmp_path, suffix):
    job = setup_job(tmp_path)
    cid, _, _, _ = approved(job)
    other = job[0].delivery_root / 'editor/author' / ('author-图1' + suffix)
    other.write_bytes(b'protected collision')
    with pytest.raises(FlowError) as exc:
        publish(job[0], cid, 'editor/author', '1')
    assert exc.value.code in ('format_conflict', 'filename_collision')
    assert other.read_bytes() == b'protected collision'
    assert 'author-图1.jpg' not in {entry.name for entry in other.parent.iterdir()}


def test_dangling_output_symlink_is_not_replaced(tmp_path):
    job = setup_job(tmp_path)
    cid, _, _, _ = approved(job)
    target = job[0].delivery_root / 'editor/author/author-图1.jpg'
    target.symlink_to(tmp_path / 'missing')
    with pytest.raises(FlowError):
        publish(job[0], cid, 'editor/author', '1')
    assert target.is_symlink()


def test_source_is_never_overwritten_even_with_exact_expected_hash(tmp_path):
    job = setup_job(tmp_path, source_is_target=True)
    original = job[1].read_bytes()
    cid, _, _, _ = approved(job)
    with pytest.raises(FlowError) as exc:
        publish(job[0], cid, 'editor/author', '1', hash_file(job[1]))
    assert exc.value.code == 'source_protected'
    assert job[1].read_bytes() == original


@pytest.mark.parametrize('state', ['changed', 'missing'])
def test_accepted_target_never_replaced_or_recreated(tmp_path, state):
    job = setup_job(tmp_path)
    cid, candidate, _, _ = approved(job)
    target = Path(publish(job[0], cid, 'editor/author', '1')['target'])
    accept(job[0], 'editor/author', '1', candidate['output_sha256'], 'explicit-human',
        'This is an explicit test acceptance, not a mechanical promotion.')
    if state == 'changed':
        target.write_bytes(b'changed after acceptance')
    else:
        target.unlink()
    with pytest.raises(FlowError) as exc:
        publish(job[0], cid, 'editor/author', '1', hash_file(target) if target.exists() else None)
    assert exc.value.code == 'accepted_target'


def test_accepted_other_format_marker_still_protects_missing_file(tmp_path):
    job = setup_job(tmp_path)
    cid, _, _, _ = approved(job)
    write_json(job[0].state_root / 'accepted/editor/author/author-图1.pdf.json', {'sha256': 'a' * 64})
    with pytest.raises(FlowError) as exc:
        publish(job[0], cid, 'editor/author', '1')
    assert exc.value.code == 'accepted_target'


@pytest.mark.parametrize('field', ['source_hashes', 'constraints_sha256', 'candidate_id'])
def test_review_cannot_be_rebound(tmp_path, field):
    job = setup_job(tmp_path)
    cid, candidate, report, _ = build(job)
    record = review_record(job, cid, candidate, report)
    record[field] = {} if field == 'source_hashes' else 'f' * 64
    path = tmp_path / 'review.json'
    write_json(path, record)
    with pytest.raises(FlowError) as exc:
        review(job[0], cid, path)
    assert exc.value.code == 'review_binding'


def test_forged_persisted_review_does_not_skip_binding_checks(tmp_path):
    job = setup_job(tmp_path)
    cid, candidate, report, _ = approved(job)
    record = review_record(job, cid, candidate, report)
    record['source_hashes'] = {}
    write_json(job[0].state_root / 'reviews' / f'{cid}.json', {'record': record, 'record_sha256': hash_json(record)})
    with pytest.raises(FlowError) as exc:
        publish(job[0], cid, 'editor/author', '1')
    assert exc.value.code == 'review_binding'


@pytest.mark.parametrize('mutation', ['source', 'constraints', 'spec', 'jpg', 'png', 'receipt', 'report'])
def test_changed_bound_inputs_or_outputs_block_publication(tmp_path, mutation):
    job = setup_job(tmp_path)
    cid, _, _, artifact = approved(job)
    paths = {'source': job[1], 'constraints': job[3], 'spec': job[0].state_root / 'candidates' / cid / 'spec.json',
        'jpg': artifact, 'png': artifact.with_name('grayscale.png'), 'receipt': artifact.with_name('audit.json'),
        'report': artifact.with_name('report.json')}
    paths[mutation].write_bytes(b'changed after review')
    with pytest.raises((FlowError, OSError)):
        publish(job[0], cid, 'editor/author', '1')
    assert not list((job[0].delivery_root / 'editor/author').glob('*.jpg'))


@pytest.mark.parametrize('mutation', ['missing_contract', 'missing_check', 'wrong_route'])
def test_actual_editorial_gate_blocks_incomplete_or_wrong_route(tmp_path, mutation):
    job = setup_job(tmp_path)
    constraints = json_file(job[3])
    confirmed = constraints['confirmed']
    if mutation == 'missing_contract':
        del confirmed['editorial_route_contract']
    elif mutation == 'missing_check':
        del confirmed['editorial_route_contract']['figures'][0]['checks']['full_canvas']
    else:
        fig = confirmed['editorial_route_contract']['figures'][0]
        fig['decision']['route'] = fig['decision']['proposed']['route'] = 'structural_redraw'
        fig['checks'] = {name: {'status': 'recorded_satisfied', 'evidence_ids': ['review-1']}
            for name in COMMON_CHECKS + ROUTE_CHECKS['structural_redraw']}
    write_json(job[3], constraints)
    cid, candidate, report, _ = build(job)
    record = review_record(job, cid, candidate, report)
    path = tmp_path / 'review.json'
    write_json(path, record)
    with pytest.raises(FlowError) as exc:
        review(job[0], cid, path)
    assert exc.value.code.startswith('editorial_')
    write_json(job[0].state_root / 'reviews' / f'{cid}.json', {'record': record, 'record_sha256': hash_json(record)})
    with pytest.raises(FlowError) as exc:
        publish(job[0], cid, 'editor/author', '1')
    assert exc.value.code.startswith('editorial_')


@pytest.mark.parametrize('kind', ['renamed_png', 'rgb', 'no_resolution', 'corrupt'])
def test_accept_reads_jpeg_bytes_not_filename(tmp_path, kind):
    job = setup_job(tmp_path)
    target = job[0].delivery_root / 'editor/author/author-图1.jpg'
    if kind == 'renamed_png':
        target.write_bytes(job[1].read_bytes())
    elif kind == 'corrupt':
        target.write_bytes(b'\xff\xd8not actually an image')
    else:
        Image.new('RGB' if kind == 'rgb' else 'L', (20, 10)).save(target, format='JPEG')
    with pytest.raises(FlowError) as exc:
        accept(job[0], 'editor/author', '1', hash_file(target), 'explicit-human', 'Explicit test review cannot permit structurally invalid image bytes.')
    assert exc.value.code == 'jpg_audit'
    assert not list(job[0].state_root.glob('accepted/**/*.json'))


@pytest.mark.parametrize('name', ['../author-图1.jpg', 'C:\\temp\\author-图1.jpg', 'author-图2.jpg', 'author-图1.pdf', 'author\n-图1.jpg'])
def test_jpg_target_identity_rejects_unsafe_or_mismatched_names(tmp_path, name):
    with pytest.raises(FlowError):
        target_for_artifact(tmp_path, '1', output_format='jpg', target_basename=name)


def test_accept_refuses_ambiguous_native_targets(tmp_path):
    job = setup_job(tmp_path)
    cid, candidate, _, _ = approved(job)
    target = Path(publish(job[0], cid, 'editor/author', '1')['target'])
    target.with_suffix('.pdf').write_bytes(b'other same-figure delivery')
    with pytest.raises(FlowError) as exc:
        accept(job[0], 'editor/author', '1', candidate['output_sha256'], 'human', 'Ambiguous deliveries require manual target resolution first.')
    assert exc.value.code == 'format_conflict'


def test_failed_atomic_replace_keeps_original_and_cleans_temp(tmp_path, monkeypatch):
    import localflow.publishing as module
    job = setup_job(tmp_path)
    cid, _, _, _ = approved(job)
    target = job[0].delivery_root / 'editor/author/author-图1.jpg'
    target.write_bytes(b'previous bytes')
    current = hash_file(target)
    original_replace = module.os.replace
    def fail_publish(source, dest):
        if Path(source).name.startswith('.publish-'):
            raise OSError('synthetic atomic replace failure')
        return original_replace(source, dest)
    monkeypatch.setattr(module.os, 'replace', fail_publish)
    with pytest.raises(OSError, match='atomic replace'):
        publish(job[0], cid, 'editor/author', '1', current)
    assert hash_file(target) == current
    assert not list(target.parent.glob('.publish-*'))
    assert not (job[0].state_root / 'publications' / f'{cid}.json').exists()


def test_missing_publication_receipt_is_recovered_idempotently(tmp_path, monkeypatch):
    import localflow.publishing as module
    job = setup_job(tmp_path)
    cid, candidate, _, _ = approved(job)
    original_write = module.write_json
    def fail_receipt(path, value):
        if path.parent.name == 'publications':
            raise OSError('synthetic receipt interruption')
        return original_write(path, value)
    with monkeypatch.context() as patch:
        patch.setattr(module, 'write_json', fail_receipt)
        with pytest.raises(OSError, match='receipt interruption'):
            publish(job[0], cid, 'editor/author', '1')
    target = job[0].delivery_root / 'editor/author/author-图1.jpg'
    assert hash_file(target) == candidate['output_sha256']
    assert publish(job[0], cid, 'editor/author', '1')['status'] == 'already-published'
    assert (job[0].state_root / 'publications' / f'{cid}.json').is_file()


def test_external_target_change_during_staging_is_not_overwritten(tmp_path, monkeypatch):
    import localflow.publishing as module
    job = setup_job(tmp_path)
    cid, _, _, _ = approved(job)
    target = job[0].delivery_root / 'editor/author/author-图1.jpg'
    original = module._audit_artifact
    def mutate_target(path, output_format, report=None):
        original(path, output_format, report)
        if path.name.startswith('.publish-'):
            target.write_bytes(b'external edit during staging')
    monkeypatch.setattr(module, '_audit_artifact', mutate_target)
    with pytest.raises(FlowError) as exc:
        publish(job[0], cid, 'editor/author', '1')
    assert exc.value.code == 'target_changed'
    assert target.read_bytes() == b'external edit during staging'
    assert not list(target.parent.glob('.publish-*'))


def test_cli_native_jpg_path_needs_no_font_file(tmp_path, capsys):
    from localflow.cli import main
    job = setup_job(tmp_path)
    config = tmp_path / 'config.json'
    write_json(config, {'delivery_root': str(job[0].delivery_root), 'state_root': str(job[0].state_root),
        'font_profile': str(job[0].font_profile), 'cache_root': str(job[0].cache_root), 'workbench_enabled': False})
    assert not job[0].font_profile.exists()
    assert main(['--config', str(config), 'render-raster', str(job[2]), '--constraints', str(job[3]), '--probe-id', job[4]]) == 0
    result = json.loads(capsys.readouterr().out)
    candidate, _, artifact = check_candidate(job[0], result['candidate_id'])
    assert candidate['output_format'] == 'jpg' and artifact.suffix == '.jpg'


def test_context_source_is_bound_without_guessing_image_pair(tmp_path):
    job = setup_job(tmp_path)
    config, source, spec_path, constraints_path, _ = job
    context = source.parent / 'context.txt'
    context.write_text('Synthetic Figure 1 caption context, not a replacement image.')
    manifest_path = tmp_path / 'manifest-context.json'
    write_json(manifest_path, {'source_root': str(source.parent), 'files': [
        {'id': 'source', 'path': source.name}, {'id': 'context', 'path': context.name}]})
    pid = probe(config, manifest_path)['probe_id']
    spec = json_file(spec_path)
    spec['sources'].append({'path': context.name, 'sha256': hash_file(context), 'role': 'caption-context'})
    write_json(spec_path, spec)
    constraints = json_file(constraints_path)
    fig = constraints['confirmed']['editorial_route_contract']['figures'][0]
    fig['sources'].append({'id': 'context', 'sha256': hash_file(context)})
    fig['evidence'].append({'id': 'context-1', 'source_id': 'context', 'source_sha256': hash_file(context),
        'method': 'synthetic fixture', 'location': 'Figure 1 caption', 'observation': 'Context explicitly paired with this image only.'})
    fig['checks']['source_identity']['evidence_ids'].append('context-1')
    write_json(constraints_path, constraints)
    job = (config, source, spec_path, constraints_path, pid)
    cid, _, report, _ = approved(job)
    assert {s['path'] for s in report['source_bindings']} == {source.name, context.name}
    assert publish(config, cid, 'editor/author', '1')['status'] == 'published-candidate'
    context.write_text('Changed caption after candidate review.')
    with pytest.raises(FlowError):
        check_candidate(config, cid)


def test_context_sources_require_explicit_image_selection(tmp_path):
    job = setup_job(tmp_path)
    source = job[1]
    context = source.parent / 'context.txt'
    context.write_text('Synthetic context')
    manifest = tmp_path / 'context-manifest.json'
    write_json(manifest, {'source_root': str(source.parent), 'files': [
        {'id': 'source', 'path': source.name}, {'id': 'context', 'path': context.name}]})
    pid = probe(job[0], manifest)['probe_id']
    spec = json_file(job[2])
    del spec['source_path']
    spec['sources'].append({'path': context.name, 'sha256': hash_file(context), 'role': 'context'})
    write_json(job[2], spec)
    with pytest.raises(FlowError):
        render_raster(job[0], job[2], job[3], pid)


def test_forged_hashes_cannot_authorize_different_jpeg_pixels(tmp_path):
    job = setup_job(tmp_path)
    cid, candidate, report, artifact = build(job)
    with Image.open(artifact) as old:
        exif = old.getexif()
    Image.new('L', (320, 120), 127).save(artifact, format='JPEG', quality=95, subsampling=0, exif=exif)
    changed = hash_file(artifact)
    receipt_path = artifact.with_name('audit.json')
    receipt = json_file(receipt_path)
    receipt['outputs']['jpeg']['sha256'] = changed
    write_json(receipt_path, receipt)
    report.update(output_sha256=changed, native_receipt_sha256=hash_file(receipt_path), raster_audit=receipt)
    report_path = artifact.with_name('report.json')
    write_json(report_path, report)
    candidate.update(output_sha256=changed, report_sha256=hash_file(report_path), native_receipt_sha256=hash_file(receipt_path))
    write_json(job[0].state_root / 'candidates' / cid / 'candidate.json', candidate)
    with pytest.raises(FlowError) as exc:
        check_candidate(job[0], cid)
    assert exc.value.code == 'raster_audit'


def test_original_constraints_cannot_be_rewritten_with_duplicate_keys(tmp_path):
    job = setup_job(tmp_path)
    raw = job[3].read_text()
    job[3].write_text(raw.replace('"column": "single"', '"column": "single", "column": "single"', 1))
    with pytest.raises(FlowError) as exc:
        build(job)
    assert exc.value.code == 'invalid_json'


@pytest.mark.parametrize('subdir', ['reviews', 'archive', 'accepted', 'publications'])
def test_state_output_symlink_cannot_escape_root(tmp_path, subdir):
    job = setup_job(tmp_path)
    cid, _, _, _ = approved(job)
    config = job[0]
    outside = tmp_path / 'outside'
    outside.mkdir()
    path = config.state_root / subdir
    if subdir == 'reviews':
        record = path / f'{cid}.json'
        record.rename(outside / record.name)
        path.rmdir()
    path.symlink_to(outside, target_is_directory=True)
    target = config.delivery_root / 'editor/author/author-图1.jpg'
    if subdir == 'archive':
        target.write_bytes(b'previous bytes requiring archive')
    with pytest.raises(FlowError):
        publish(config, cid, 'editor/author', '1', hash_file(target) if target.exists() else None)
    assert not (outside / 'editor').exists()


def test_conflicting_publication_record_blocks_before_target_write(tmp_path):
    job = setup_job(tmp_path)
    cid, _, _, _ = approved(job)
    target = job[0].delivery_root / 'editor/author/author-图1.jpg'
    target.write_bytes(b'original bytes')
    write_json(job[0].state_root / 'publications' / f'{cid}.json', {'target': 'different target'})
    with pytest.raises(FlowError) as exc:
        publish(job[0], cid, 'editor/author', '1', hash_file(target))
    assert exc.value.code == 'publication_changed'
    assert target.read_bytes() == b'original bytes'


@pytest.mark.parametrize('confirmed_width', [None, 80, 79.125])
def test_nondefault_physical_width_needs_exact_confirmed_value(tmp_path, confirmed_width):
    job = setup_job(tmp_path, width_mm=79.125)
    constraints = json_file(job[3])
    if confirmed_width is not None:
        constraints['confirmed']['width_mm'] = confirmed_width
        write_json(job[3], constraints)
    if confirmed_width != 79.125:
        with pytest.raises(FlowError) as exc:
            build(job)
        assert exc.value.code == 'constraint_conflict'
        return
    cid, _, report, _ = approved(job)
    target = Path(publish(job[0], cid, 'editor/author', '1')['target'])
    assert audit_jpg_compatibility(target, report)['width_mm'] == pytest.approx(79.125)
    assert report['source_dimensions'] == [320, 120]


def test_batch_membership_cannot_reassign_candidate_figure(tmp_path):
    job = setup_job(tmp_path)
    constraints = json_file(job[3])
    confirmed = constraints['confirmed']
    confirmed['split'] = 'multi'
    confirmed['expected_outputs'].append({'author_rel': 'editor/author', 'figure_number': '2'})
    other = copy.deepcopy(confirmed['editorial_route_contract']['figures'][0])
    other['id'] = 'figure-2'
    confirmed['editorial_route_contract']['figures'].append(other)
    confirmed['editorial_targets'].append({'id': 'figure-2', 'author_rel': 'editor/author', 'figure_number': '2'})
    write_json(job[3], constraints)
    cid, candidate, report, _ = build(job)
    record = review_record(job, cid, candidate, report)
    record['figure_number'] = '2'
    path = tmp_path / 'wrong-review.json'
    write_json(path, record)
    with pytest.raises(FlowError) as caught:
        review(job[0], cid, path)
    assert caught.value.code == 'review_target_binding'
    assert not (job[0].state_root / 'reviews' / f'{cid}.json').exists()
    # Even a pre-existing, correctly hashed bad review cannot bypass publication.
    write_json(job[0].state_root / 'reviews' / f'{cid}.json',
        {'record': record, 'record_sha256': hash_json(record)})
    with pytest.raises(FlowError) as caught:
        publish(job[0], cid, 'editor/author', '2')
    assert caught.value.code == 'review_target_binding'
    assert not list(job[0].delivery_root.rglob('*.jpg'))


@pytest.mark.parametrize('output_format', ['pdf', 'jpg'])
def test_shared_review_validation_binds_current_figure_for_every_format(tmp_path, output_format):
    from localflow.publishing import _validate_review
    job = setup_job(tmp_path)
    cid, candidate, report, _ = build(job)
    record = review_record(job, cid, candidate, report)
    folder = job[0].state_root / 'candidates' / cid
    constraints = json_file(folder / 'constraints.json')
    constraints['confirmed']['expected_outputs'].append({'author_rel': 'editor/author', 'figure_number': '2'})
    write_json(folder / 'constraints.json', constraints)
    record['figure_number'] = '2'
    with pytest.raises(FlowError) as caught:
        _validate_review(job[0], candidate, report, record, output_format)
    assert caught.value.code == 'review_target_binding'


@pytest.mark.parametrize('output_format', ['pdf', 'jpg'])
def test_shared_review_cannot_change_explicit_filename_identity(tmp_path, output_format):
    from localflow.publishing import _validate_review
    job = setup_job(tmp_path)
    cid, candidate, report, _ = build(job)
    record = review_record(job, cid, candidate, report)
    record['author'] = 'different-author'
    record['target_basename'] = f'different-author-图1.{output_format}'
    folder = job[0].state_root / 'candidates' / cid
    constraints = json_file(folder / 'constraints.json')
    constraints['confirmed']['expected_outputs'].append({key: record[key]
        for key in ('author_rel', 'figure_number', 'author', 'target_basename')})
    write_json(folder / 'constraints.json', constraints)
    with pytest.raises(FlowError) as caught:
        _validate_review(job[0], candidate, report, record, output_format)
    assert caught.value.code == 'review_target_binding'
