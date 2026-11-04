from pathlib import Path

import fitz
import pytest
from PIL import Image

from case_helpers import candidate, make_case
from task_quality.gate import postcheck, precheck
from task_quality.storage import GateError, ref


@pytest.mark.parametrize('embedded', [False, True])
def test_colored_pdf_candidate_is_rejected_even_when_its_source_is_colored(
    tmp_path: Path, embedded: bool,
) -> None:
    contract = make_case(tmp_path)
    source = Path(contract['source']['path'])
    colored = tmp_path / 'colored.pdf'
    with fitz.open(source) as doc:
        if embedded:
            image = tmp_path / 'image.png'
            Image.new('RGB', (20, 20), 'red').save(image)
            doc[0].insert_image(fitz.Rect(30, 30, 60, 60), filename=str(image))
        else:
            doc[0].draw_rect(fitz.Rect(30, 30, 60, 60), color=None, fill=(1, 0, 0))
        doc.save(colored)
    contract['source'] = ref(colored)
    contract['source_inputs'] = [ref(colored)]
    precheck(contract)
    with pytest.raises(GateError, match='nonneutral_pixels'):
        postcheck(contract, candidate(contract))


def test_gray_pdf_reports_rgb_neutrality_at_300_dpi(tmp_path: Path) -> None:
    contract = make_case(tmp_path)
    precheck(contract)
    postcheck(contract, candidate(contract))
    from task_quality.checks import measure
    from task_quality.models import Contract
    parsed = Contract.parse(contract)
    result = measure(parsed.outputs[0], parsed.workspace / 'fig1.pdf')
    assert result['nonneutral_pixels'] == 0
    assert result['color_audit_dpi'] == 300
