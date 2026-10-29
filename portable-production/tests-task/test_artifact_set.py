from pathlib import Path

import pytest
from PIL import Image

from case_helpers import candidate, make_case, review
from task_quality.gate import finalize, postcheck, precheck, verify
from task_quality.models import GateError


def test_precheck_flags_matching_pdf_and_jpg_for_format_review(tmp_path):
    contract = make_case(tmp_path)
    pdf = contract['outputs'][0]
    contract['outputs'].append(dict(id='fig1_image', path='fig1.jpg',
        delivery_target=str(Path(pdf['delivery_target']).with_suffix('.jpg')),
        format='jpg', width_mm=pdf['width_mm'], pixels=[1000, 500], dpi=300, stroke_pt=None))
    result = precheck(contract)
    assert result['warnings'][0]['code'] == 'multiple_figure_formats'
    assert len(result['warnings'][0]['targets']) == 2
    assert result['status'] == 'prechecked'


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
