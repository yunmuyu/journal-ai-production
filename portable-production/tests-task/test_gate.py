from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import fitz
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from task_quality.gate import precheck, postcheck, finalize, verify
from task_quality.storage import GateError, ref


from case_helpers import make_case, candidate, review


def test_closed_loop(tmp_path):
    contract = make_case(tmp_path)
    first = precheck(contract)
    assert precheck(contract) == first
    result = postcheck(contract, candidate(contract))
    assert result['status'] == 'candidate'
    assert result['manual_status'] == 'pending'
    receipt = finalize(contract, review(contract, result))
    assert receipt['status'] == 'reviewed'
    assert verify(contract)['status'] == 'verified'


@pytest.mark.parametrize('mutation,code', [('source','hash_mismatch'), ('reuse','history_reuse_required'),
    ('unknown','invalid_schema'), ('runtime','runtime_mismatch')])
def test_precheck_rejects(tmp_path, mutation, code):
    contract = make_case(tmp_path)
    if mutation == 'source': contract['source']['sha256'] = '0' * 64
    if mutation == 'reuse': contract['history']['reusable'] = True
    if mutation == 'unknown': contract['surprise'] = True
    if mutation == 'runtime': contract['runtime']['python'] = ref(tmp_path / 'code.py')
    with pytest.raises(GateError, match=code): precheck(contract)


def test_workspace_conflict(tmp_path):
    contract = make_case(tmp_path)
    precheck(contract)
    other = copy.deepcopy(contract)
    other['id'] = 'other'
    with pytest.raises(GateError, match='workspace_conflict'): precheck(other)


@pytest.mark.parametrize('mutation,code', [('missing','artifact_set'), ('width','width_mismatch'),
    ('stroke','stroke_mismatch'), ('coverage','coverage_missing')])
def test_postcheck_rejects(tmp_path, mutation, code):
    contract = make_case(tmp_path)
    if mutation == 'width': contract['outputs'][0]['width_mm'] = 80
    precheck(contract)
    submission = candidate(contract)
    if mutation == 'missing': submission['artifacts'] = []
    if mutation == 'stroke':
        path = Path(contract['workspace']) / 'fig1.pdf'
        path.unlink()
        with fitz.open() as doc:
            page = doc.new_page(width=240, height=120)
            page.draw_rect(fitz.Rect(10,10,200,90), width=1)
            doc.save(path)
        submission['artifacts'] = [ref(path)]
        report_path = Path(submission['audit']['path'])
        report = json.loads(report_path.read_text())
        report['output_bindings']['fig1'] = ref(path)['sha256']
        report_path.write_text(json.dumps(report))
        submission['audit'] = ref(report_path)
    if mutation == 'coverage':
        path = Path(submission['audit']['path'])
        report = json.loads(path.read_text())
        report['coverage'] = []
        path.write_text(json.dumps(report))
        submission['audit'] = ref(path)
    with pytest.raises(GateError, match=code): postcheck(contract, submission)


@pytest.mark.parametrize('mutation', ['self', 'missing', 'pending'])
def test_manual_rejects(tmp_path, mutation):
    contract = make_case(tmp_path)
    precheck(contract)
    result = postcheck(contract, candidate(contract))
    receipt = review(contract, result)
    if mutation == 'self': receipt['reviewer'] = contract['producer']
    if mutation == 'missing': receipt['items'] = []
    if mutation == 'pending': receipt['items'][0]['decision'] = 'pending'
    with pytest.raises(GateError): finalize(contract, receipt)


@pytest.mark.parametrize('target', ['artifact', 'preview', 'audit', 'source', 'freeze'])
def test_verify_detects_changes(tmp_path, target):
    contract = make_case(tmp_path)
    precheck(contract)
    submission = candidate(contract)
    result = postcheck(contract, submission)
    finalize(contract, review(contract, result))
    paths = dict(artifact=submission['artifacts'][0]['path'], audit=submission['audit']['path'],
        source=contract['source']['path'], freeze=str(tmp_path / 'freeze.txt'),
        preview=str(Path(contract['workspace']) / '.task-quality' / 'fig1.preview.png'))
    with Path(paths[target]).open('ab') as stream: stream.write(b'changed')
    with pytest.raises(GateError, match='hash_mismatch'): verify(contract)


def test_jpg_actual_pixels_dpi(tmp_path):
    contract = make_case(tmp_path)
    contract['outputs'] = [dict(id='fig1', path='fig1.jpg', delivery_target=str(tmp_path / 'authors' / 'fig1.jpg'), format='jpg', width_mm=25.4,
        pixels=[300, 150], dpi=300, stroke_pt=None)]
    precheck(contract)
    submission = candidate(contract)
    output = Path(contract['workspace']) / 'fig1.jpg'
    Image.new('RGB', (300,150), 'white').save(output, dpi=(300,300))
    submission['artifacts'] = [ref(output)]
    assert postcheck(contract, submission)['status'] == 'candidate'

def test_existing_frozen_manifest_metadata(tmp_path):
    contract = make_case(tmp_path)
    manifest = Path(contract['frozen_manifest']['path'])
    manifest.write_text(json.dumps([dict(**ref(tmp_path / 'freeze.txt'), status='accepted',
        evidence='historical receipt', author='synthetic', number='1', automatic_acceptance=False)]))
    contract['frozen_manifest'] = ref(manifest)
    assert precheck(contract)['status'] == 'prechecked'


def test_additional_source_change(tmp_path):
    contract = make_case(tmp_path)
    attachment = tmp_path / 'attachment.docx'
    attachment.write_bytes(b'synthetic word identity')
    contract['source_inputs'].append(ref(attachment))
    precheck(contract)
    result = postcheck(contract, candidate(contract))
    finalize(contract, review(contract, result))
    attachment.write_bytes(b'other word version')
    with pytest.raises(GateError, match='hash_mismatch'): verify(contract)


@pytest.mark.parametrize('scenario', ['no-scene', 'text-only', 'missing-owner'])
def test_missing_scene_semantics_stay_pending(tmp_path, scenario):
    contract = make_case(tmp_path)
    contract['route'] = 'diagram'
    contract['manual_review'] += ['topology', 'label_ownership']
    precheck(contract)
    submission = candidate(contract)
    audit_path = Path(submission['audit']['path'])
    report = json.loads(audit_path.read_text())
    for name in ('source_geometry', 'label_path_binding'):
        report[name]['status'] = 'checked'
    if scenario != 'no-scene':
        scene = Path(contract['workspace']) / 'scene.json'
        scene.write_text(json.dumps(dict(nodes=[] if scenario == 'text-only' else [dict(id='box1')],
            paths=[], texts=[dict(id='label1', owner=None)])))
        report['scene'] = ref(scene)
    audit_path.write_text(json.dumps(report))
    submission['audit'] = ref(audit_path)
    result = postcheck(contract, submission)
    assert result['coverage_pending']
    receipt = finalize(contract, review(contract, result))
    assert receipt['automatic_coverage_pending']
    assert receipt['manual_resolutions']
    assert verify(contract)['status'] == 'verified'


def test_nested_workspace_conflict(tmp_path):
    contract = make_case(tmp_path)
    precheck(contract)
    other = copy.deepcopy(contract)
    other['workspace'] = str(Path(contract['workspace']) / 'nested')
    with pytest.raises(GateError, match='workspace_conflict'): precheck(other)


def test_unchecked_history(tmp_path):
    contract = make_case(tmp_path)
    evidence = Path(contract['history']['evidence']['path'])
    evidence.write_text(json.dumps(dict(checked=False, conclusion='new', reusable=False, observation='not searched')))
    contract['history']['evidence'] = ref(evidence)
    with pytest.raises(GateError, match='history_unchecked'): precheck(contract)


def test_cli_phase_success_is_not_ready(tmp_path):
    import subprocess
    contract = make_case(tmp_path)
    path = tmp_path / 'contract.json'
    path.write_text(json.dumps(contract))
    root = Path(__file__).resolve().parents[1]
    process = subprocess.run([sys.executable, '-m', 'task_quality', 'precheck', str(path)],
        cwd=root, capture_output=True, text=True, check=False)
    assert process.returncode == 0
    assert json.loads(process.stdout)['result']['status'] == 'prechecked'
    process = subprocess.run([sys.executable, '-m', 'task_quality', 'verify', str(path)],
        cwd=root, capture_output=True, text=True, check=False)
    assert process.returncode == 1
    assert json.loads(process.stdout)['ok'] is False
    submission_path = tmp_path / 'submission.json'
    submission_path.write_text(json.dumps(candidate(contract)))
    process = subprocess.run([sys.executable, '-m', 'task_quality', 'postcheck', str(path), str(submission_path)],
        cwd=root, capture_output=True, text=True, check=False)
    assert process.returncode == 0, process.stdout
    result = json.loads(process.stdout)['result']
    review_path = tmp_path / 'review.json'
    review_path.write_text(json.dumps(review(contract, result)))
    process = subprocess.run([sys.executable, '-m', 'task_quality', 'finalize', str(path), str(review_path)],
        cwd=root, capture_output=True, text=True, check=False)
    assert process.returncode == 0, process.stdout
    process = subprocess.run([sys.executable, '-m', 'task_quality', 'verify', str(path)],
        cwd=root, capture_output=True, text=True, check=False)
    assert process.returncode == 0, process.stdout
    assert json.loads(process.stdout)['result']['status'] == 'verified'


def test_frozen_target_cannot_be_remade(tmp_path):
    contract = make_case(tmp_path)
    target = Path(contract['outputs'][0]['delivery_target'])
    target.parent.mkdir()
    target.write_bytes(b'accepted output')
    manifest = Path(contract['frozen_manifest']['path'])
    manifest.write_text(json.dumps([dict(**ref(target), status='accepted')]))
    contract['frozen_manifest'] = ref(manifest)
    with pytest.raises(GateError, match='frozen_target'): precheck(contract)


def test_delivery_target_compare_and_swap(tmp_path):
    contract = make_case(tmp_path)
    precheck(contract)
    target = Path(contract['outputs'][0]['delivery_target'])
    target.parent.mkdir()
    target.write_bytes(b'concurrent edit')
    with pytest.raises(GateError, match='delivery_target_changed'): postcheck(contract, candidate(contract))


def test_report_for_different_same_size_pdf_rejected(tmp_path):
    contract = make_case(tmp_path)
    precheck(contract)
    submission = candidate(contract)
    path = Path(contract['workspace']) / 'fig1.pdf'
    path.unlink()
    with fitz.open() as doc:
        page = doc.new_page(width=240, height=120)
        page.draw_rect(fitz.Rect(20,20,200,90), width=.5)
        doc.save(path)
    submission['artifacts'] = [ref(path)]
    with pytest.raises(GateError, match='audit_binding_mismatch'): postcheck(contract, submission)


def test_required_mechanical_pending_cannot_be_reviewed_away(tmp_path):
    contract = make_case(tmp_path)
    precheck(contract)
    submission = candidate(contract)
    path = Path(submission['audit']['path'])
    report = json.loads(path.read_text())
    report['coverage'][0]['status'] = 'pending'
    path.write_text(json.dumps(report))
    submission['audit'] = ref(path)
    result = postcheck(contract, submission)
    with pytest.raises(GateError, match='mechanical_pending'): finalize(contract, review(contract, result))


@pytest.mark.parametrize('mutation', ['empty-observation', 'missing-matching-preview'])
def test_semantic_pending_requires_specific_manual_resolution(tmp_path, mutation):
    contract = make_case(tmp_path)
    contract['route'] = 'diagram'
    contract['manual_review'] += ['topology', 'label_ownership']
    precheck(contract)
    submission = candidate(contract)
    result = postcheck(contract, submission)
    evidence = review(contract, result)
    item = next(row for row in evidence['items'] if row['id'] == 'label_ownership')
    if mutation == 'empty-observation': item['observation'] = ''
    if mutation == 'missing-matching-preview': item['evidence'] = [result['candidate_sha256']]
    with pytest.raises(GateError): finalize(contract, evidence)
