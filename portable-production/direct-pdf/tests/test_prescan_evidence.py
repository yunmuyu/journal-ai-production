import hashlib
import json
import subprocess
import sys

import pymupdf as fitz
import pytest

from figure_audit.errors import AuditInputError
from figure_audit.prescan import inspect_pdf


def make_pdf(path, *, pages=1, text=True):
    with fitz.open() as document:
        for _ in range(pages):
            page = document.new_page(width=360, height=180)
            if text:
                page.insert_text((20, 30), 'Sample label', fontsize=10)
        document.save(path)
    return path


def test_page_width_scaling_is_evidence_not_acceptance(tmp_path):
    path = make_pdf(tmp_path/'source.pdf')
    report = inspect_pdf(path)
    assert report['status'] == 'INCOMPLETE'
    assert report['source_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report['page_width_pt'] == pytest.approx(360)
    assert report['text_sizes'][0]['size_pt'] == pytest.approx(10)
    for estimate, width in zip(report['proportional_estimates'], [80, 160]):
        scale = min(1, width * 72 / 25.4 / 360)
        assert estimate['scale'] == pytest.approx(scale)
        assert estimate['dominant_text_pt'] == pytest.approx(10*scale)
    assert report['proportional_estimates'][1]['scale'] == 1
    assert report['limitations']


def test_unextractable_text_does_not_produce_fake_font_estimate(tmp_path):
    report = inspect_pdf(make_pdf(tmp_path/'blank.pdf', text=False))
    assert report['text_sizes'] == []
    assert all(row['dominant_text_pt'] is None for row in report['proportional_estimates'])
    assert report['status'] == 'INCOMPLETE'


def test_multipage_is_rejected(tmp_path):
    with pytest.raises(AuditInputError):
        inspect_pdf(make_pdf(tmp_path/'multipage.pdf', pages=2))


def test_cli_generates_incomplete_report_and_never_overwrites_inputs(tmp_path):
    source = make_pdf(tmp_path/'source.pdf')
    before = source.read_bytes()
    output = tmp_path/'evidence.json'
    command = [sys.executable, '-m', 'figure_audit.prescan', str(source), '--json', str(output)]
    first = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', check=False)
    assert first.returncode == 3
    assert json.loads(output.read_text(encoding='utf-8'))['status'] == 'INCOMPLETE'
    second = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', check=False)
    assert second.returncode == 2
    unsafe = subprocess.run([sys.executable, '-m', 'figure_audit.prescan', str(source), '--json', str(source)],
                            capture_output=True, text=True, encoding='utf-8', check=False)
    assert unsafe.returncode == 2 and source.read_bytes() == before
