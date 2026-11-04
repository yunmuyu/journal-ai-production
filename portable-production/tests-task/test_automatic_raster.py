import json
from pathlib import Path
import pytest
from PIL import Image
from case_helpers import make_case
from task_quality.gate import precheck, postcheck
from task_quality.storage import ref, read
from automatic_raster import check
from raster import render


def fixture(tmp_path, replace_content=False):
    contract = make_case(tmp_path)
    source = tmp_path / 'source.png'
    Image.new('RGB', (300, 150), (200, 40, 60)).save(source)
    contract.update(route='raster', source=ref(source), source_inputs=[ref(source)],
        manual_review=['source_content', 'visual', 'runtime_provenance', 'readability', 'grayscale_semantics'])
    contract['outputs'][0].update(path='fig1.jpg', format='jpg', width_mm=25.4,
        pixels=[300, 150], dpi=300, stroke_pt=None)
    workspace = Path(contract['workspace'])
    plan = dict(version=1, inputs=[dict(**ref(source), crop=None)],
        layout=dict(mode='single', gap_px=0), output=str(workspace/'fig1.jpg'), width_mm=25.4)
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    contract['source_inputs'].append(ref(plan_path))
    precheck(contract)
    render(plan)
    if replace_content:
        # Fully rebound self-report and postcheck still cannot legitimize unrelated content.
        Image.new('L',(300,150),0).save(workspace/'fig1.jpg',dpi=(300,300))
    artifact = ref(workspace/'fig1.jpg')
    audit = workspace/'audit.json'
    audit.write_text(json.dumps(dict(output_bindings={'fig1':artifact['sha256']},
        coverage=[dict(id=k,status='checked',evidence=[contract['source']]) for k in contract['mechanical']],
        scene=None,source_geometry=dict(status='not-applicable',evidence=[contract['source']],observation='Raster retained'),
        label_path_binding=dict(status='not-applicable',evidence=[contract['source']],observation='No text rewrite'))))
    result = postcheck(contract, dict(artifacts=[artifact],audit=ref(audit)))
    note = tmp_path/'self-check.json'
    note.write_text(json.dumps(dict(producer='maker',candidate_sha256=result['candidate_sha256'],
        observations={k:'Compared original and candidate' for k in ['source_content','readability','grayscale_semantics']},
        evidence=[contract['source']['sha256'],artifact['sha256'],*[p['sha256'] for p in result['previews']]])))
    return contract,plan_path,note


def test_actual_replay_returns_pending_without_fake_independent_receipt(tmp_path):
    contract,plan,note=fixture(tmp_path)
    result=check(contract,plan,note)
    assert result['status']=='candidate' and result['manual_status']=='pending'
    assert not (Path(contract['workspace'])/'.task-quality/receipt.json').exists()


@pytest.mark.parametrize('target',['source','plan','output','audit','preview','selfcheck'])
def test_changed_frozen_or_candidate_evidence_cannot_auto_return(tmp_path,target):
    contract,plan,note=fixture(tmp_path)
    root=Path(contract['workspace'])
    p={'source':Path(contract['source']['path']),'plan':plan,'output':root/'fig1.jpg',
       'audit':root/'audit.json','preview':root/'.task-quality/fig1.preview.png','selfcheck':note}[target]
    p.write_text('{}')
    with pytest.raises(Exception): check(contract,plan,note)


def test_generic_completed_report_cannot_replace_bound_selfcheck(tmp_path):
    contract,plan,note=fixture(tmp_path);note.write_text(json.dumps({'completed':True}))
    with pytest.raises(Exception): check(contract,plan,note)


def test_plausible_resealed_jpg_with_wrong_content_fails_source_replay(tmp_path):
    contract,plan,note=fixture(tmp_path,replace_content=True)
    with pytest.raises(Exception,match='raster_replay_mismatch'):
        check(contract,plan,note)


def test_pdf_never_uses_automatic_raster_gate(tmp_path):
    contract=make_case(tmp_path)
    with pytest.raises(Exception,match='automatic_route'):
        check(contract,tmp_path/'unused',tmp_path/'unused')
