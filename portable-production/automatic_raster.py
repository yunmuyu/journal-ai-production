"""Independent reproducibility checks for routine raster candidates, not acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from raster import render
from task_quality.checks import measure, preview
from task_quality.gate import candidate_record, envelope
from task_quality.models import Contract, FileRef, GateError, fields, text
from task_quality.storage import checked, child, read, ref, state, task_lock


def check(raw, plan_path: Path, self_check_path: Path):
    contract = Contract.parse(raw)
    if contract.route != 'raster' or len(contract.outputs) != 1:
        raise GateError('automatic_route', 'Only one routine raster output is supported')
    with task_lock(contract):
        envelope(contract, raw)
        candidate = candidate_record(contract)
        if candidate['status'] != 'candidate' or candidate['manual_status'] != 'pending':
            raise GateError('automatic_state', 'Expected pending candidate')
        if set(candidate['coverage_pending']).intersection(contract.mechanical):
            raise GateError('mechanical_pending', 'Automatic checks cannot waive pending mechanics')
        plan_ref = ref(plan_path)
        if plan_ref not in raw['source_inputs']:
            raise GateError('plan_unbound', 'Raster plan must be a frozen source input')
        plan = read(plan_path)
        output = contract.outputs[0]
        actual = child(contract.workspace, output.path)
        if Path(plan['output']).resolve() != actual or plan['width_mm'] != output.width_mm:
            raise GateError('plan_output_mismatch', str(actual))
        for source in plan['inputs']:
            source_ref = dict(path=source['path'], sha256=source['sha256'])
            if source_ref not in raw['source_inputs']:
                raise GateError('plan_source_unbound', source['path'])
            checked(FileRef.parse(source_ref))
        actual_ref = ref(actual)
        if actual_ref not in candidate['references']:
            raise GateError('candidate_output_unbound', str(actual))
        measurements = measure(output, actual)
        self_ref = ref(self_check_path)
        note = fields(read(self_check_path), 'producer candidate_sha256 observations evidence')
        required = {'source_content', 'readability', 'grayscale_semantics'}
        if note['producer'] != contract.producer or note['candidate_sha256'] != ref(state(contract) / 'candidate.json')['sha256']:
            raise GateError('self_check_binding', 'Producer or candidate changed')
        if type(note['observations']) is not dict or set(note['observations']) != required:
            raise GateError('self_check_missing', 'Three explicit observations are required')
        for observation in note['observations'].values():
            text(observation)
        hashes = {contract.source.sha256, actual_ref['sha256'], *[p['sha256'] for p in candidate['previews']]}
        if type(note['evidence']) is not list or not hashes.issubset(set(note['evidence'])):
            raise GateError('self_check_binding', 'Current source/output/previews must be referenced')
        with tempfile.TemporaryDirectory(prefix='jfw-auto-raster-') as scratch:
            root = Path(scratch)
            replay = dict(plan, output=str(root / 'replay.jpg'))
            regenerated = render(replay)
            if regenerated['output']['sha256'] != actual_ref['sha256']:
                raise GateError('raster_replay_mismatch', 'Actual JPEG differs from frozen source processing plan')
            # Recreate each preview through the same public generator, never trust the supplied image.
            for original, expected_path in [(contract.source.path, state(contract) / 'source.preview.png'),
                    (actual, state(contract) / (output.id + '.preview.png'))]:
                rebuilt = preview(original, root / (expected_path.name))
                expected = ref(expected_path)
                if expected not in candidate['previews'] or rebuilt['sha256'] != expected['sha256']:
                    raise GateError('preview_binding_mismatch', str(expected_path))
        envelope(contract, raw)
        candidate_record(contract)
        if ref(self_check_path) != self_ref or ref(actual) != actual_ref or ref(plan_path) != plan_ref:
            raise GateError('automatic_inputs_changed', 'Inputs changed during automatic check')
        return dict(kind='automatic-candidate', status='candidate', manual_status='pending',
            manualStatus='pending', measurements=measurements, selfCheck=self_ref,
            candidate=ref(state(contract) / 'candidate.json'),
            limitation='Source-processing reproducibility and machine checks only; producer observations are not independent visual proof; user review remains pending')


if __name__ == '__main__':
    try:
        result = check(read(Path(sys.argv[1])), Path(sys.argv[2]), Path(sys.argv[3]))
        print(json.dumps(dict(ok=True, result=result), ensure_ascii=False))
    except Exception as error:
        print(json.dumps(dict(ok=False, error=str(error)), ensure_ascii=False))
        sys.exit(1)
