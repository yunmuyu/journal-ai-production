from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from case_helpers import candidate, make_case, review
from task_quality.gate import finalize, postcheck, precheck, verify
from task_quality.models import GateError
from task_quality.storage import ref
from task_quality.typography import audit_typography, pdf_spans


def raster_case(tmp_path):
    contract = make_case(tmp_path)
    contract['route'] = 'raster'
    contract['manual_review'] = ['source_content', 'visual', 'runtime_provenance', 'readability', 'grayscale_semantics']
    contract['outputs'][0].update(path='fig1.jpg', format='jpg', width_mm=25.4,
        pixels=[300, 150], dpi=300, stroke_pt=None,
        delivery_target=str(tmp_path / 'authors' / 'fig1.jpg'))
    return contract


def test_screenshot_route_cannot_dispatch_pdf(tmp_path):
    contract = make_case(tmp_path)
    contract['route'] = 'raster'
    contract['manual_review'] += ['readability', 'grayscale_semantics']
    with pytest.raises(GateError, match='route_format_mismatch'):
        precheck(contract)


def test_diagram_route_cannot_relax_to_jpg(tmp_path):
    contract = raster_case(tmp_path)
    contract['route'] = 'diagram'
    contract['manual_review'] += ['topology', 'label_ownership']
    with pytest.raises(GateError, match='route_format_mismatch'):
        precheck(contract)


def test_pdf_typography_review_cannot_be_omitted(tmp_path):
    contract = make_case(tmp_path)
    contract['manual_review'].remove('typography')
    with pytest.raises(GateError, match='invalid_schema'):
        precheck(contract)


@pytest.mark.parametrize('item', ['readability', 'grayscale_semantics'])
def test_raster_quality_review_cannot_be_omitted(tmp_path, item):
    contract = raster_case(tmp_path)
    contract['manual_review'].remove(item)
    with pytest.raises(GateError, match='invalid_schema'):
        precheck(contract)


def test_actual_colored_jpg_rejected_even_when_report_claims_gray(tmp_path):
    contract = raster_case(tmp_path)
    precheck(contract)
    submission = candidate(contract)
    output = Path(contract['workspace']) / 'fig1.jpg'
    Image.new('RGB', (300, 150), 'red').save(output, dpi=(300, 300))
    # Rebind an otherwise mechanically checked report to the actual wrong bytes.
    import json
    report_path = Path(submission['audit']['path'])
    report = json.loads(report_path.read_text())
    report['output_bindings']['fig1'] = ref(output)['sha256']
    report_path.write_text(json.dumps(report))
    submission.update(artifacts=[ref(output)], audit=ref(report_path))
    with pytest.raises(GateError, match='nonneutral_pixels'):
        postcheck(contract, submission)


def test_small_pixel_text_is_not_a_font_size_gate_and_review_still_required(tmp_path):
    contract = raster_case(tmp_path)
    precheck(contract)
    submission = candidate(contract)
    output = Path(contract['workspace']) / 'fig1.jpg'
    image = Image.new('RGB', (300, 150), 'white')
    ImageDraw.Draw(image).text((5, 5), 'UI label', fill='black', font_size=5)
    image.save(output, dpi=(300, 300))
    import json
    report_path = Path(submission['audit']['path'])
    report = json.loads(report_path.read_text())
    report['output_bindings']['fig1'] = ref(output)['sha256']
    report_path.write_text(json.dumps(report))
    submission.update(artifacts=[ref(output)], audit=ref(report_path))
    # A raster's tiny text has no editable typography contract; no OCR font estimate.
    result = postcheck(contract, submission)
    assert result['manual_status'] == 'pending'
    rejected = review(contract, result)
    next(item for item in rejected['items'] if item['id'] == 'readability')['decision'] = 'rejected'
    with pytest.raises(GateError, match='manual_pending_or_rejected'):
        finalize(contract, rejected)
    finalize(contract, review(contract, result))
    assert verify(contract)['status'] == 'verified'


def text_pdf(tmp_path, size):
    import fitz
    path = tmp_path / 'editable.pdf'
    with fitz.open() as document:
        page = document.new_page(width=200, height=100)
        page.insert_text((10, 30), 'x2', fontsize=size)
        document.save(path)
    return path


def test_actual_small_pdf_body_cannot_pass_with_a_bound_body_role(tmp_path):
    path = text_pdf(tmp_path, 4)
    declared = {'fig1': [dict(**span, role='body') for span in pdf_spans(path)]}
    with pytest.raises(GateError, match='body_font_below_minimum'):
        audit_typography(path, 'fig1', declared)


def test_small_pdf_text_without_roles_is_pending_not_implicitly_a_script(tmp_path):
    path = text_pdf(tmp_path, 4)
    measured, pending = audit_typography(path, 'fig1', None)
    assert pending == ['typography']
    assert measured['small_spans'][0]['size_pt'] == 4


def test_bound_superscript_is_not_rejected_by_smallest_font(tmp_path):
    path = text_pdf(tmp_path, 4)
    declared = {'fig1': [dict(**span, role='superscript') for span in pdf_spans(path)]}
    measured, pending = audit_typography(path, 'fig1', declared)
    assert pending == []
    assert measured['roles'][0]['role'] == 'superscript'


def test_font_roles_cannot_refer_to_other_text(tmp_path):
    path = text_pdf(tmp_path, 4)
    declared = {'fig1': [dict(**span, role='superscript') for span in pdf_spans(path)]}
    declared['fig1'][0]['text'] = 'different content'
    with pytest.raises(GateError, match='text_role_binding_mismatch'):
        audit_typography(path, 'fig1', declared)


def test_normal_pdf_body_retains_actual_font_measurement(tmp_path):
    path = text_pdf(tmp_path, 8)
    measured, pending = audit_typography(path, 'fig1', None)
    assert pending == []
    assert measured['spans'][0]['size_pt'] == 8
