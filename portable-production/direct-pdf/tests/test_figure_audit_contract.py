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


@pytest.mark.parametrize(('width_mm','expected'), [(40,'PASS'), (71.3,'PASS'), (80,'PASS'), (80.1,'FAIL')])
def test_column_width_is_an_upper_bound(width_mm, expected):
    from figure_audit.guard_checks import c_page
    from figure_audit.guard_core import R
    with fitz.open() as doc:
        page=doc.new_page(width=width_mm*72/25.4, height=100)
        result=R(Path('out.pdf'),None)
        c_page(result,page,80)
        assert result.issues[0]['level']==expected


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


def test_spacing_ledger_rejects_missing_measurement(tmp_path, monkeypatch):
    import json
    from figure_audit import spacing
    from figure_audit.guard import R, c_spacing_ledger
    pdf = tmp_path / 'sample.pdf'
    pdf.write_bytes(b'sample')
    result = R(pdf, None)
    monkeypatch.setattr(spacing.Spacing, 'measure', lambda self, path: {
        'items': [{'role': 'tick_to_axis', 'measured_pt': 2.0, 'verdict': 'INFO'}],
        'n_warn': 0, 'n_info': 1, 'size_pt': 8.0, 'pdf_sha256': 'sha'})
    ledger = tmp_path / 'ledger.json'
    ledger.write_text(json.dumps({'pdf_sha256': 'sha', 'items': [
        {'role': 'tick_to_axis', 'origin': 'corpus'}]}), encoding='utf-8')
    c_spacing_ledger(result, pdf, ledger)
    assert next(i for i in result.issues if i['code'] == 'S12b')['level'] == 'FAIL'


def _emf_record(kind, payload=b''):
    return struct.pack('<II', kind, 8 + len(payload)) + payload


def _emf_fixture(tmp_path, records):
    header = bytearray(88)
    struct.pack_into('<II', header, 0, 1, 88)
    struct.pack_into('<iiii', header, 8, 0, 0, 100, 100)
    struct.pack_into('<iiii', header, 24, 0, 0, 1000, 1000)
    header[40:44] = b' EMF'
    struct.pack_into('<ii', header, 72, 100, 100)
    struct.pack_into('<ii', header, 80, 10, 10)
    path = tmp_path / 'sample.emf'
    path.write_bytes(header + b''.join(records) + _emf_record(14))
    return path


def test_emf_maps_window_to_viewport_once(tmp_path):
    pair = lambda x, y: struct.pack('<ii', x, y)
    records = [_emf_record(17, struct.pack('<I', 8)),
               _emf_record(9, pair(100, 100)), _emf_record(11, pair(200, 300)),
               _emf_record(10, pair(10, 20)), _emf_record(12, pair(3, 5)),
               _emf_record(27, pair(10, 20)), _emf_record(54, pair(20, 30))]
    result = Emf(_emf_fixture(tmp_path, records))
    assert result.polys[0]['pts'] == pytest.approx([(3, 5), (23, 35)])


def test_emf_intersect_clip_tracks_device_space_and_restore(tmp_path):
    pair = lambda x, y: struct.pack('<ii', x, y)
    rect = lambda a, b, c, d: struct.pack('<iiii', a, b, c, d)
    records = [_emf_record(17, struct.pack('<I', 8)),
               _emf_record(9, pair(100, 100)), _emf_record(11, pair(200, 200)),
               _emf_record(30, rect(10, 10, 40, 40)), _emf_record(33),
               _emf_record(30, rect(20, 20, 30, 30)),
               _emf_record(27, pair(0, 0)), _emf_record(54, pair(50, 50)),
               _emf_record(34, struct.pack('<i', -1)),
               _emf_record(27, pair(0, 0)), _emf_record(54, pair(50, 50))]
    result = Emf(_emf_fixture(tmp_path, records))
    assert len(result.polys[0]['clip_regions']) == 2
    assert len(result.polys[1]['clip_regions']) == 1
    assert result.polys[0]['clip_regions'][0] == pytest.approx([(20, 20), (80, 20), (80, 80), (20, 80)])


def test_emf_offset_clip_uses_mapped_vector_and_restore(tmp_path):
    pair = lambda x, y: struct.pack('<ii', x, y)
    records = [_emf_record(17, struct.pack('<I', 8)),
               _emf_record(9, pair(100, 100)), _emf_record(11, pair(200, 300)),
               _emf_record(10, pair(10, 20)), _emf_record(12, pair(3, 5)),
               _emf_record(30, struct.pack('<iiii', 10, 20, 40, 40)), _emf_record(33),
               _emf_record(26, pair(3, 4)),
               _emf_record(27, pair(0, 0)), _emf_record(54, pair(1, 1)),
               _emf_record(34, struct.pack('<i', -1)),
               _emf_record(27, pair(0, 0)), _emf_record(54, pair(1, 1))]
    result=Emf(_emf_fixture(tmp_path, records))
    assert result.polys[0]['clip_regions'][0] == pytest.approx([(9,17),(69,17),(69,77),(9,77)])
    assert result.polys[1]['clip_regions'][0] == pytest.approx([(3,5),(63,5),(63,65),(3,65)])
    assert 26 not in result.unsupported_records


def test_emf_offset_clip_when_mapping_unknown_remains_unknown(tmp_path):
    pair = lambda x, y: struct.pack('<ii', x, y)
    result=Emf(_emf_fixture(tmp_path, [_emf_record(115, struct.pack('<I',1)),
        _emf_record(26, pair(3,4)),_emf_record(27,pair(0,0)),_emf_record(54,pair(1,1))]))
    assert result.polys[0]['clip_status']=='unknown'


def test_emf_clip_offset_matches_windows_gdi():
    import sys
    if sys.platform != 'win32':
        pytest.skip('Windows GDI oracle is only available on Windows')
    import ctypes
    from ctypes import wintypes
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC];gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.DeleteDC.argtypes=[wintypes.HDC]
    gdi.SetMapMode.argtypes=[wintypes.HDC,ctypes.c_int]
    gdi.SetWindowExtEx.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
    gdi.SetViewportExtEx.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
    gdi.SetWindowOrgEx.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
    gdi.SetViewportOrgEx.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
    gdi.IntersectClipRect.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int]
    gdi.OffsetClipRgn.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int]
    gdi.CreateRectRgn.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int];gdi.CreateRectRgn.restype=wintypes.HRGN
    gdi.GetClipRgn.argtypes=[wintypes.HDC,wintypes.HRGN]
    gdi.GetRgnBox.argtypes=[wintypes.HRGN,ctypes.POINTER(wintypes.RECT)]
    gdi.DeleteObject.argtypes=[wintypes.HANDLE]
    dc=gdi.CreateCompatibleDC(None);region=gdi.CreateRectRgn(0,0,0,0)
    try:
        assert dc and region
        assert gdi.SetMapMode(dc,8)
        assert gdi.SetWindowExtEx(dc,100,100,None)
        assert gdi.SetViewportExtEx(dc,200,300,None)
        assert gdi.SetWindowOrgEx(dc,10,20,None)
        assert gdi.SetViewportOrgEx(dc,3,5,None)
        assert gdi.IntersectClipRect(dc,10,20,40,40)>0
        assert gdi.OffsetClipRgn(dc,3,4)>0
        assert gdi.GetClipRgn(dc,region)==1
        rect=wintypes.RECT();assert gdi.GetRgnBox(region,ctypes.byref(rect))>0
        assert (rect.left,rect.top,rect.right,rect.bottom)==(9,17,69,77)
    finally:
        if region:gdi.DeleteObject(region)
        if dc:gdi.DeleteDC(dc)


def test_emf_rotated_clip_offset_matches_windows_gdi(tmp_path):
    import sys
    if sys.platform != 'win32':
        pytest.skip('Windows GDI oracle is only available on Windows')
    import ctypes
    from ctypes import wintypes
    class Xform(ctypes.Structure):
        _fields_=[(name,ctypes.c_float) for name in ('m11','m12','m21','m22','dx','dy')]
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC];gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.DeleteDC.argtypes=[wintypes.HDC]
    gdi.SetGraphicsMode.argtypes=[wintypes.HDC,ctypes.c_int]
    gdi.SetWorldTransform.argtypes=[wintypes.HDC,ctypes.POINTER(Xform)]
    gdi.IntersectClipRect.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int]
    gdi.OffsetClipRgn.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int]
    gdi.CreateRectRgn.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int];gdi.CreateRectRgn.restype=wintypes.HRGN
    gdi.GetClipRgn.argtypes=[wintypes.HDC,wintypes.HRGN]
    gdi.GetRgnBox.argtypes=[wintypes.HRGN,ctypes.POINTER(wintypes.RECT)]
    gdi.DeleteObject.argtypes=[wintypes.HANDLE]
    dc=gdi.CreateCompatibleDC(None);region=gdi.CreateRectRgn(0,0,0,0)
    try:
        assert dc and region
        assert gdi.SetGraphicsMode(dc,2)
        assert gdi.SetWorldTransform(dc,ctypes.byref(Xform(0,1,-1,0,100,0)))
        assert gdi.IntersectClipRect(dc,10,20,40,40)>0
        assert gdi.OffsetClipRgn(dc,3,4)>0
        assert gdi.GetClipRgn(dc,region)==1
        rect=wintypes.RECT();assert gdi.GetRgnBox(region,ctypes.byref(rect))>0
        pair=lambda x,y:struct.pack('<ii',x,y)
        records=[_emf_record(35,struct.pack('<6f',0,1,-1,0,100,0)),
                 _emf_record(30,struct.pack('<iiii',10,20,40,40)),_emf_record(26,pair(3,4)),
                 _emf_record(27,pair(0,0)),_emf_record(54,pair(1,1))]
        corners=Emf(_emf_fixture(tmp_path,records)).polys[0]['clip_regions'][0]
        bounds=(min(p[0] for p in corners),min(p[1] for p in corners),
                max(p[0] for p in corners),max(p[1] for p in corners))
        assert bounds==pytest.approx((rect.left,rect.top,rect.right,rect.bottom))
    finally:
        if region:gdi.DeleteObject(region)
        if dc:gdi.DeleteDC(dc)


def test_emf_left_and_right_world_transforms_are_distinct(tmp_path):
    pair = lambda x, y: struct.pack('<ii', x, y)
    translate = struct.pack('<6f', 1, 0, 0, 1, 10, 0)
    scale = struct.pack('<6f', 2, 0, 0, 2, 0, 0)
    records = [_emf_record(35, translate), _emf_record(33),
               _emf_record(36, scale + struct.pack('<I', 2)),
               _emf_record(27, pair(1, 1)), _emf_record(54, pair(2, 1)),
               _emf_record(34, struct.pack('<i', -1)),
               _emf_record(36, scale + struct.pack('<I', 3)),
               _emf_record(27, pair(1, 1)), _emf_record(54, pair(2, 1))]
    result = Emf(_emf_fixture(tmp_path, records))
    assert result.polys[0]['pts'][0] == pytest.approx((12, 2))
    assert result.polys[1]['pts'][0] == pytest.approx((22, 2))


def test_emf_polylineto16_uses_logical_current_position(tmp_path):
    pair = lambda x, y: struct.pack('<ii', x, y)
    points = struct.pack('<iiiiIhh', 0, 0, 100, 100, 1, 7, 8)
    result = Emf(_emf_fixture(tmp_path, [
        _emf_record(27, pair(3, 4)), _emf_record(89, points), _emf_record(54, pair(9, 10))]))
    assert result.polys[0]['pts'] == pytest.approx([(3, 4), (7, 8)])
    assert result.polys[1]['pts'] == pytest.approx([(7, 8), (9, 10)])


def test_emf_unsupported_clip_marks_subsequent_geometry_unknown(tmp_path):
    pair = lambda x, y: struct.pack('<ii', x, y)
    records = [_emf_record(67, struct.pack('<I', 1)),
               _emf_record(27, pair(0, 0)), _emf_record(54, pair(9, 9))]
    result = Emf(_emf_fixture(tmp_path, records))
    assert result.polys[0]['clip_status'] == 'unknown'
    assert result.unsupported_records[67] == 1


def test_emf_zero_text_reference_is_not_current_position_without_updatecp(tmp_path):
    text = bytearray(80)
    struct.pack_into('<II', text, 0, 84, 80)
    struct.pack_into('<ii', text, 36, 0, 0)
    struct.pack_into('<II', text, 44, 1, 76)
    text[76:78] = 'A'.encode('utf-16le')
    result = Emf(_emf_fixture(tmp_path, [_emf_record(27, struct.pack('<ii', 20, 30)), bytes(text)]))
    assert result.texts[0]['ref'] == pytest.approx((0, 0))


def test_emf_unhandled_mapping_changes_mark_coordinates_unknown(tmp_path):
    pair = lambda x, y: struct.pack('<ii', x, y)
    records = [_emf_record(115, struct.pack('<I', 1)),
               _emf_record(27, pair(0, 0)), _emf_record(54, pair(1, 1))]
    result = Emf(_emf_fixture(tmp_path, records))
    assert result.polys[0]['coordinate_status'] == 'unknown'


def test_emf_json_exposes_clip_constraints_in_millimeters(tmp_path):
    import json
    from figure_audit.emf import to_json
    pair = lambda x, y: struct.pack('<ii', x, y)
    records = [_emf_record(30, struct.pack('<iiii', 10, 20, 30, 40)),
               _emf_record(27, pair(0, 0)), _emf_record(54, pair(50, 50))]
    source = _emf_fixture(tmp_path, records)
    report = tmp_path / 'inspect.json'
    to_json(source, report)
    data = json.loads(report.read_text(encoding='utf-8'))
    assert data['complete'] is False
    assert data['polys'][0]['clip_status'] == 'partial'
    corners = data['polys'][0]['clip_regions_mm'][0]
    assert corners[0] == pytest.approx([1, 2])
    assert corners[2] == pytest.approx([3, 4])


def test_emf_restored_dc_restores_current_position(tmp_path):
    pair = lambda x, y: struct.pack('<ii', x, y)
    records = [_emf_record(27, pair(1, 2)), _emf_record(33), _emf_record(27, pair(7, 8)),
               _emf_record(34, struct.pack('<i', -1)), _emf_record(54, pair(3, 4))]
    result = Emf(_emf_fixture(tmp_path, records))
    assert result.polys[0]['pts'] == pytest.approx([(1, 2), (3, 4)])


def test_emf_window_viewport_mapping_matches_windows_gdi(tmp_path):
    import sys
    if sys.platform != 'win32':
        pytest.skip('Windows GDI oracle is only available on Windows')
    import ctypes
    from ctypes import wintypes
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.SetMapMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi.SetWindowExtEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi.SetViewportExtEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi.SetWindowOrgEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi.SetViewportOrgEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi.LPtoDP.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.c_int]
    dc = gdi.CreateCompatibleDC(None)
    assert dc
    try:
        assert gdi.SetMapMode(dc, 8)
        assert gdi.SetWindowExtEx(dc, 100, 100, None)
        assert gdi.SetViewportExtEx(dc, 200, 300, None)
        assert gdi.SetWindowOrgEx(dc, 10, 20, None)
        assert gdi.SetViewportOrgEx(dc, 3, 5, None)
        points = (wintypes.POINT * 2)(wintypes.POINT(10, 20), wintypes.POINT(20, 30))
        assert gdi.LPtoDP(dc, points, 2)
        expected = [(p.x, p.y) for p in points]
    finally:
        assert gdi.DeleteDC(dc)
    pair = lambda x, y: struct.pack('<ii', x, y)
    records = [_emf_record(17, struct.pack('<I', 8)),
               _emf_record(9, pair(100, 100)), _emf_record(11, pair(200, 300)),
               _emf_record(10, pair(10, 20)), _emf_record(12, pair(3, 5)),
               _emf_record(27, pair(10, 20)), _emf_record(54, pair(20, 30))]
    actual = Emf(_emf_fixture(tmp_path, records)).polys[0]['pts']
    assert actual == pytest.approx(expected)


def test_emf_world_transform_order_matches_windows_gdi(tmp_path):
    import sys
    if sys.platform != 'win32':
        pytest.skip('Windows GDI oracle is only available on Windows')
    import ctypes
    from ctypes import wintypes
    class Xform(ctypes.Structure):
        _fields_ = [(name, ctypes.c_float) for name in ('m11', 'm12', 'm21', 'm22', 'dx', 'dy')]
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.SetGraphicsMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi.SetWorldTransform.argtypes = [wintypes.HDC, ctypes.POINTER(Xform)]
    gdi.ModifyWorldTransform.argtypes = [wintypes.HDC, ctypes.POINTER(Xform), wintypes.DWORD]
    gdi.LPtoDP.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.c_int]
    dc = gdi.CreateCompatibleDC(None)
    assert dc
    try:
        assert gdi.SetGraphicsMode(dc, 2)
        expected = []
        for mode in (2, 3):
            assert gdi.SetWorldTransform(dc, ctypes.byref(Xform(1, 0, 0, 1, 10, 0)))
            assert gdi.ModifyWorldTransform(dc, ctypes.byref(Xform(2, 0, 0, 2, 0, 0)), mode)
            point = wintypes.POINT(1, 1)
            assert gdi.LPtoDP(dc, ctypes.byref(point), 1)
            expected.append((point.x, point.y))
    finally:
        assert gdi.DeleteDC(dc)
    pair = lambda x, y: struct.pack('<ii', x, y)
    translate = struct.pack('<6f', 1, 0, 0, 1, 10, 0)
    scale = struct.pack('<6f', 2, 0, 0, 2, 0, 0)
    records = [_emf_record(35, translate), _emf_record(33),
               _emf_record(36, scale + struct.pack('<I', 2)),
               _emf_record(27, pair(1, 1)), _emf_record(54, pair(2, 1)),
               _emf_record(34, struct.pack('<i', -1)),
               _emf_record(36, scale + struct.pack('<I', 3)),
               _emf_record(27, pair(1, 1)), _emf_record(54, pair(2, 1))]
    result = Emf(_emf_fixture(tmp_path, records))
    assert [poly['pts'][0] for poly in result.polys] == pytest.approx(expected)
