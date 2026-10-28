from pathlib import Path
import struct
import pymupdf as fitz
import pytest
from figure_audit.guard import run
from figure_audit.spacing import Spacing
from figure_audit.emf import Emf


def test_spacing_observation_never_claims_an_editorial_failure():
    level, _ = Spacing().judge('tick_to_axis', 100, 8)
    assert level == 'INFO'


def test_guard_does_not_treat_missing_source_as_complete(tmp_path):
    path = tmp_path / 'out.pdf'
    with fitz.open() as doc:
        doc.new_page()
        doc.save(path)
    result = run(path, None, None, 'trace', 1, 0, None)
    assert result['status'] != 'PASS'


def test_guard_rejects_multipage_input(tmp_path):
    path = tmp_path / 'out.pdf'
    with fitz.open() as doc:
        doc.new_page()
        doc.new_page()
        doc.save(path)
    with pytest.raises(ValueError):
        run(path, None, None, 'trace', 1, 0, None)


def test_emf_rejects_truncated_record(tmp_path):
    path = tmp_path / 'bad.emf'
    header = bytearray(88)
    struct.pack_into('<II', header, 0, 1, 88)
    struct.pack_into('<iiii', header, 8, 0, 0, 100, 100)
    struct.pack_into('<iiii', header, 24, 0, 0, 1000, 1000)
    header[40:44] = b' EMF'
    struct.pack_into('<ii', header, 72, 100, 100)
    struct.pack_into('<ii', header, 80, 10, 10)
    path.write_bytes(header + struct.pack('<II', 27, 20))
    with pytest.raises(ValueError):
        Emf(path)


def test_shape_check_with_no_output_paths_does_not_crash():
    from figure_audit.guard import R, c_trace
    with fitz.open() as source, fitz.open() as output:
        src = source.new_page()
        src.draw_rect(fitz.Rect(10, 10, 90, 90))
        page = output.new_page()
        result = R(Path('out.pdf'), Path('src.pdf'))
        c_trace(result, page, src, 'trace', .06)
        assert result.issues[-1]['level'] != 'PASS'


def test_emf_unsupported_records_are_reported(tmp_path):
    path = tmp_path / 'sample.emf'
    header = bytearray(88)
    struct.pack_into('<II', header, 0, 1, 88)
    struct.pack_into('<iiii', header, 8, 0, 0, 100, 100)
    struct.pack_into('<iiii', header, 24, 0, 0, 1000, 1000)
    header[40:44] = b' EMF'
    struct.pack_into('<ii', header, 72, 100, 100)
    struct.pack_into('<ii', header, 80, 10, 10)
    path.write_bytes(header + struct.pack('<II', 999, 8) + struct.pack('<II', 14, 8))
    assert Emf(path).unsupported_records == {999: 1}


def test_spacing_output_cannot_overwrite_input(tmp_path):
    from figure_audit.spacing import main
    pdf = tmp_path / 'input.pdf'
    with fitz.open() as doc:
        doc.new_page()
        doc.save(pdf)
    original = pdf.read_bytes()
    with pytest.raises(ValueError):
        main([str(pdf), '--out', str(pdf)])
    assert pdf.read_bytes() == original


def test_spacing_ledger_is_bound_to_pdf_bytes(tmp_path):
    import hashlib
    pdf = tmp_path / 'input.pdf'
    with fitz.open() as doc:
        doc.new_page()
        doc.save(pdf)
    report = Spacing().measure(pdf)
    assert report['pdf_sha256'] == hashlib.sha256(pdf.read_bytes()).hexdigest()


def test_guard_flags_page_wider_than_column():
    from figure_audit.guard import R, c_page
    with fitz.open() as doc:
        page = doc.new_page(width=80.5 * 72 / 25.4, height=100)
        result = R(Path('out.pdf'), None)
        c_page(result, page, 80)
        assert result.issues[-1]['level'] == 'FAIL'


def test_matching_paths_only_gives_advisory_evidence():
    from figure_audit.guard import R, c_trace
    with fitz.open() as source, fitz.open() as output:
        src = source.new_page()
        page = output.new_page()
        src.draw_rect(fitz.Rect(10, 10, 90, 90))
        page.draw_rect(fitz.Rect(10, 10, 90, 90))
        result = R(Path('out.pdf'), Path('src.pdf'))
        c_trace(result, page, src, 'trace', .06)
        assert result.issues[-1]['level'] != 'PASS'


def test_empty_pdf_does_not_claim_text_or_fonts_were_checked(tmp_path):
    path = tmp_path / 'empty.pdf'
    with fitz.open() as doc:
        doc.new_page()
        doc.save(path)
    result = run(path, None, 80, 'trace', None, 0, None)
    checks = {issue['code']: issue['level'] for issue in result['issues']}
    assert checks['S4'] == 'SKIP'
    assert checks['S11'] == 'SKIP'


def test_guard_cli_reports_incomplete_to_automation(tmp_path):
    import json
    import os
    import subprocess
    import sys
    pdf = tmp_path / 'input.pdf'
    report = tmp_path / 'report.json'
    with fitz.open() as doc:
        doc.new_page()
        doc.save(pdf)
    result = subprocess.run([sys.executable, '-m', 'figure_audit.guard', '--out', str(pdf),
                             '--json', str(report)], capture_output=True, env=os.environ.copy())
    assert result.returncode == 3
    assert json.loads(report.read_text(encoding='utf-8'))['status'] == 'INCOMPLETE'


def test_fingerprint_rejects_multipage_and_cannot_overwrite_input(tmp_path):
    from figure_audit import fingerprint
    first = tmp_path / 'one.pdf'
    second = tmp_path / 'two.pdf'
    multi = tmp_path / 'multi.pdf'
    for path, count in ((first, 1), (second, 1), (multi, 2)):
        with fitz.open() as doc:
            for _ in range(count):
                doc.new_page()
            doc.save(path)
    with pytest.raises(ValueError):
        fingerprint.fp(multi)
    original = first.read_bytes()
    with pytest.raises(ValueError):
        fingerprint.main([str(first), str(second), '--json', str(first)])
    assert first.read_bytes() == original


def test_fingerprint_equal_does_not_certify_layout():
    from figure_audit import fingerprint
    values = {'file': 'sample', 'n_frames': 0, 'n_bars': 0, 'n_groups': 0,
              'bars_per_group': [], 'group_axis': 'none'}
    message = fingerprint.report(fingerprint.compare(values, values), values, values)
    assert '未改动版式结构' not in message
