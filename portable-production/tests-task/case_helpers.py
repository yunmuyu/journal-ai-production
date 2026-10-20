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


def make_case(tmp_path):
    source = tmp_path / 'source.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=240, height=120)
        page.draw_rect(fitz.Rect(10, 10, 200, 90), width=.5)
        doc.save(source)
    for name in ('history.json', 'font.json', 'code.py', 'freeze.txt'):
        (tmp_path / name).write_text('{}', encoding='utf-8')
    frozen = tmp_path / 'frozen.json'
    frozen.write_text(json.dumps([ref(tmp_path / 'freeze.txt')]), encoding='utf-8')
    (tmp_path / 'history.json').write_text(json.dumps(dict(checked=True, conclusion='new', reusable=False, observation='Synthetic prior search: no matching output')), encoding='utf-8')
    workspace = tmp_path / 'task'
    contract = dict(id='task-1', producer='maker', route='source-preserving-chart',
        source=ref(source), source_inputs=[ref(source)], history=dict(evidence=ref(tmp_path / 'history.json'),
        conclusion='new', reusable=False, revision_authorization=''),
        frozen_manifest=ref(frozen), workspace=str(workspace), author_roots=[str(tmp_path / 'authors')],
        runtime=dict(python=ref(Path(sys.executable)), code_root=str(tmp_path),
            code=[ref(tmp_path / 'code.py')], font_profile=ref(tmp_path / 'font.json')),
        outputs=[dict(id='fig1', path='fig1.pdf', delivery_target=str(tmp_path / 'authors' / 'fig1.pdf'), format='pdf', width_mm=84.666667,
            pixels=[], dpi=300, stroke_pt=.5)],
        mechanical=['dimensions', 'coverage'], manual_review=['source_content', 'visual', 'runtime_provenance'],
        allowed_changes=['font'], immutable_content=['labels', 'geometry'],
        failure_policy=dict(max_attempts=3, repair='local-only', time_budget_seconds=None, cost_budget=None))
    return contract


def candidate(contract):
    workspace = Path(contract['workspace'])
    import shutil
    if contract['outputs'][0]['format'] == 'pdf':
        shutil.copyfile(contract['source']['path'], workspace / 'fig1.pdf')
    else:
        Image.new('RGB', (300,150), 'white').save(workspace / 'fig1.jpg', dpi=(300,300))
    report = workspace / 'audit.json'
    report.write_text(json.dumps(dict(output_bindings={item['id']:ref(workspace/item['path'])['sha256'] for item in contract['outputs']}, coverage=[dict(id='dimensions', status='checked', evidence=[contract['source']]),
        dict(id='coverage', status='checked', evidence=[contract['source']])],
        scene=None, source_geometry=dict(status='not-applicable', evidence=[contract['source']], observation='No imported scene; source PDF preserved'), label_path_binding=dict(status='not-applicable', evidence=[contract['source']], observation='No label-path rewriting'))), encoding='utf-8')
    return dict(artifacts=[ref(workspace / 'fig1.pdf')] if (workspace / 'fig1.pdf').exists() else [], audit=ref(report))


def review(contract, result):
    return dict(reviewer='reviewer', candidate_sha256=result['candidate_sha256'],
        items=[dict(id=item, decision='approved', observation='Compared labels and geometry on both previews',
            evidence=[contract['source']['sha256'], *[item['sha256'] for item in result['previews']]]) for item in contract['manual_review']])


