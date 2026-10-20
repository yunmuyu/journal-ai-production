from pathlib import Path

import pytest
from PIL import Image

from case_helpers import candidate, make_case, review
from task_quality.gate import finalize, postcheck, precheck, verify
from task_quality.models import GateError


@pytest.mark.parametrize('phase', ['finalize', 'verify'])
@pytest.mark.parametrize('change', ['extra-pdf', 'extra-jpg', 'delete', 'rename'])
def test_sealed_artifact_set_changes_rejected(tmp_path, phase, change):
    contract = make_case(tmp_path)
    precheck(contract)
    result = postcheck(contract, candidate(contract))
    if phase == 'verify':
        finalize(contract, review(contract, result))
        assert verify(contract)['status'] == 'verified'
    workspace = Path(contract['workspace'])
    artifact = workspace / 'fig1.pdf'
    if change == 'extra-pdf':
        (workspace / 'undeclared.pdf').write_bytes(artifact.read_bytes())
    if change == 'extra-jpg':
        Image.new('RGB', (12, 12), 'white').save(workspace / 'undeclared.jpg')
    if change == 'delete':
        artifact.unlink()
    if change == 'rename':
        artifact.rename(workspace / 'renamed.pdf')
    with pytest.raises(GateError, match=r'^artifact_set:'):
        if phase == 'verify':
            verify(contract)
        else:
            finalize(contract, review(contract, result))
