"""EMF mapping/clip state regressions checked against real Windows GDI."""
import struct
import sys

import pytest
from figure_audit.emf_parser import Emf
from figure_audit.errors import AuditInputError
from test_figure_audit_contract import _emf_fixture, _emf_record


def pair(x, y):
    return struct.pack('<ii', x, y)


def line():
    return [_emf_record(27, pair(0, 0)), _emf_record(54, pair(10, 10))]


def test_scaled_extents_mapping_and_restore(tmp_path):
    r=[_emf_record(17,struct.pack('<I',8)),_emf_record(9,pair(100,100)),
       _emf_record(11,pair(200,300)),_emf_record(33),
       _emf_record(31,struct.pack('<iiii',3,2,2,1)),
       _emf_record(32,struct.pack('<iiii',1,2,2,1)),*line(),
       _emf_record(34,struct.pack('<i',-1)),*line()]
    e=Emf(_emf_fixture(tmp_path,r))
    assert e.polys[0]['pts']==pytest.approx([(0,0),(60,30)])
    assert e.polys[1]['pts']==pytest.approx([(0,0),(20,30)])
    assert 31 not in e.unsupported_records and 32 not in e.unsupported_records


def test_mm_text_ignores_extent_changes_and_mode_switch_resets_them(tmp_path):
    r=[_emf_record(9,pair(99,88)),_emf_record(11,pair(77,66)),
       _emf_record(17,struct.pack('<I',8)),*line(),
       _emf_record(9,pair(100,100)),_emf_record(11,pair(200,300)),
       _emf_record(17,struct.pack('<I',1)),_emf_record(17,struct.pack('<I',8)),*line()]
    e=Emf(_emf_fixture(tmp_path,r))
    assert e.polys[0]['pts']==pytest.approx([(0,0),(10,10)])
    assert e.polys[1]['pts']==pytest.approx([(0,0),(10,10)])


def test_switch_from_metric_to_anisotropic_retains_extents(tmp_path):
    r=[_emf_record(17,struct.pack('<I',2)),_emf_record(17,struct.pack('<I',8)),*line()]
    # Fixture device is 100 px / 10 mm; metric mode gives 100 logical units
    # over 100 device pixels, with the vertical axis reversed.
    assert Emf(_emf_fixture(tmp_path,r)).polys[0]['pts']==pytest.approx([(0,0),(10,-10)])


def test_extent_scaling_truncates_and_invalid_operations_are_noops(tmp_path):
    r=[_emf_record(17,struct.pack('<I',8)),_emf_record(9,pair(-5,5)),
       _emf_record(11,pair(20,20)),_emf_record(32,struct.pack('<iiii',1,2,1,2)),
       _emf_record(31,struct.pack('<iiii',0,1,1,1)),*line()]
    e=Emf(_emf_fixture(tmp_path,r))
    assert e.polys[0]['pts']==pytest.approx([(0,0),(-100,100)])


def test_extent_overflow_does_not_claim_known_coordinates(tmp_path):
    r=[_emf_record(17,struct.pack('<I',8)),_emf_record(11,pair(2**30,100)),
       _emf_record(31,struct.pack('<iiii',4,1,1,1)),*line()]
    p=Emf(_emf_fixture(tmp_path,r)).polys[0]
    assert p['coordinate_status']=='unknown' and p['clip_status']=='unknown'


def test_exclusion_offset_restore_and_reset(tmp_path):
    rect=lambda *v:struct.pack('<iiii',*v)
    r=[_emf_record(30,rect(0,0,100,100)),_emf_record(29,rect(20,20,40,40)),
       _emf_record(33),_emf_record(26,pair(3,4)),*line(),
       _emf_record(34,struct.pack('<i',-1)),*line(),
       _emf_record(75,struct.pack('<II',0,5)),*line()]
    e=Emf(_emf_fixture(tmp_path,r))
    assert e.polys[0]['clip_exclusions'][0]==pytest.approx([(23,24),(43,24),(43,44),(23,44)])
    assert e.polys[1]['clip_exclusions'][0]==pytest.approx([(20,20),(40,20),(40,40),(20,40)])
    assert not e.polys[2]['clip_regions'] and not e.polys[2]['clip_exclusions']
    assert e.polys[2]['clip_status']=='partial'


def test_reset_does_not_erase_unknown_meta_clip(tmp_path):
    r=[_emf_record(28),_emf_record(75,struct.pack('<II',0,5)),*line()]
    assert Emf(_emf_fixture(tmp_path,r)).polys[0]['clip_status']=='unknown'


@pytest.mark.parametrize('kind',[29,30])
def test_clip_after_reset_and_unknown_mapping_remains_unknown(tmp_path,kind):
    r=[_emf_record(115,struct.pack('<I',1)),_emf_record(75,struct.pack('<II',0,5)),
       _emf_record(kind,struct.pack('<iiii',1,2,5,6)),*line()]
    p=Emf(_emf_fixture(tmp_path,r)).polys[0]
    assert p['coordinate_status']=='unknown' and p['clip_status']=='unknown'


@pytest.mark.parametrize('record',[_emf_record(31,pair(1,2)),_emf_record(29,pair(1,2)),_emf_record(75),
                                   _emf_record(75,struct.pack('<II',16,5))])
def test_short_mapping_or_clip_record_is_rejected(tmp_path,record):
    with pytest.raises(AuditInputError):
        Emf(_emf_fixture(tmp_path,[record]))


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_world_transform_is_rejected(tmp_path,value):
    transform=struct.pack('<6f',1,0,0,1,value,0)
    with pytest.raises(AuditInputError):
        Emf(_emf_fixture(tmp_path,[_emf_record(35,transform)]))


def test_world_transform_composition_overflow_is_rejected(tmp_path):
    xf=struct.pack('<6f',1e38,0,0,1e38,0,0)
    records=[_emf_record(35,xf)] + [_emf_record(36,xf+struct.pack('<I',2)) for _ in range(9)]
    with pytest.raises(AuditInputError):
        Emf(_emf_fixture(tmp_path,records))


def test_exclusions_are_in_json_output(tmp_path):
    import json
    from figure_audit.emf import to_json
    source=_emf_fixture(tmp_path,[_emf_record(29,struct.pack('<iiii',10,20,30,40)),*line()])
    out=tmp_path/'result.json';to_json(source,out)
    report=json.loads(out.read_text(encoding='utf-8'))
    assert report['complete'] is False
    assert report['polys'][0]['clip_exclusions_mm'][0][0]==pytest.approx([1,2])


@pytest.mark.skipif(sys.platform!='win32',reason='Requires Windows GDI')
def test_scaled_extents_match_windows_gdi(tmp_path):
    import ctypes as c
    from ctypes import wintypes as w
    g=c.WinDLL('gdi32',use_last_error=True)
    g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
    g.DeleteDC.argtypes=[w.HDC];g.SetMapMode.argtypes=[w.HDC,c.c_int]
    g.SetWindowExtEx.argtypes=[w.HDC,c.c_int,c.c_int,c.c_void_p]
    g.SetViewportExtEx.argtypes=[w.HDC,c.c_int,c.c_int,c.c_void_p]
    g.ScaleWindowExtEx.argtypes=[w.HDC,c.c_int,c.c_int,c.c_int,c.c_int,c.c_void_p]
    g.ScaleViewportExtEx.argtypes=[w.HDC,c.c_int,c.c_int,c.c_int,c.c_int,c.c_void_p]
    g.LPtoDP.argtypes=[w.HDC,c.POINTER(w.POINT),c.c_int]
    dc=g.CreateCompatibleDC(None)
    try:
        assert dc and g.SetMapMode(dc,8)
        assert g.SetWindowExtEx(dc,100,100,None) and g.SetViewportExtEx(dc,200,300,None)
        assert g.ScaleViewportExtEx(dc,3,2,2,1,None) and g.ScaleWindowExtEx(dc,1,2,2,1,None)
        pts=(w.POINT*2)(w.POINT(0,0),w.POINT(10,10));assert g.LPtoDP(dc,pts,2)
        r=[_emf_record(17,struct.pack('<I',8)),_emf_record(9,pair(100,100)),
           _emf_record(11,pair(200,300)),_emf_record(31,struct.pack('<iiii',3,2,2,1)),
           _emf_record(32,struct.pack('<iiii',1,2,2,1)),*line()]
        assert Emf(_emf_fixture(tmp_path,r)).polys[0]['pts']==pytest.approx([(p.x,p.y) for p in pts])
    finally:
        if dc:g.DeleteDC(dc)


@pytest.mark.skipif(sys.platform!='win32',reason='Requires Windows GDI')
@pytest.mark.parametrize('mode',[2,3,4,5,6])
def test_predefined_mapping_modes_match_windows_gdi(tmp_path, mode):
    import ctypes as c
    from ctypes import wintypes as w
    g=c.WinDLL('gdi32',use_last_error=True)
    g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
    g.DeleteDC.argtypes=[w.HDC];g.SetMapMode.argtypes=[w.HDC,c.c_int]
    g.GetDeviceCaps.argtypes=[w.HDC,c.c_int]
    g.GetWindowExtEx.argtypes=[w.HDC,c.POINTER(w.SIZE)]
    g.LPtoDP.argtypes=[w.HDC,c.POINTER(w.POINT),c.c_int]
    dc=g.CreateCompatibleDC(None)
    try:
        assert dc and g.SetMapMode(dc,mode)
        extent=w.SIZE();assert g.GetWindowExtEx(dc,c.byref(extent))
        pts=(w.POINT*2)(w.POINT(0,0),w.POINT(extent.cx,extent.cy));assert g.LPtoDP(dc,pts,2)
        r=[_emf_record(17,struct.pack('<I',mode)),_emf_record(27,pair(0,0)),
           _emf_record(54,pair(extent.cx,extent.cy))]
        path=_emf_fixture(tmp_path,r)
        data=bytearray(path.read_bytes())
        struct.pack_into('<iiii',data,72,g.GetDeviceCaps(dc,8),g.GetDeviceCaps(dc,10),
                         g.GetDeviceCaps(dc,4),g.GetDeviceCaps(dc,6))
        path.write_bytes(data)
        assert Emf(path).polys[0]['pts']==pytest.approx([(p.x,p.y) for p in pts])
    finally:
        if dc:g.DeleteDC(dc)


@pytest.mark.skipif(sys.platform!='win32',reason='Requires Windows GDI')
def test_exclusion_and_offset_match_windows_gdi(tmp_path):
    import ctypes as c
    from ctypes import wintypes as w
    g=c.WinDLL('gdi32',use_last_error=True)
    g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
    g.DeleteDC.argtypes=[w.HDC]
    g.IntersectClipRect.argtypes=[w.HDC,c.c_int,c.c_int,c.c_int,c.c_int]
    g.ExcludeClipRect.argtypes=[w.HDC,c.c_int,c.c_int,c.c_int,c.c_int]
    g.OffsetClipRgn.argtypes=[w.HDC,c.c_int,c.c_int]
    g.CreateRectRgn.argtypes=[c.c_int,c.c_int,c.c_int,c.c_int];g.CreateRectRgn.restype=w.HRGN
    g.GetClipRgn.argtypes=[w.HDC,w.HRGN]
    g.PtInRegion.argtypes=[w.HRGN,c.c_int,c.c_int]
    g.DeleteObject.argtypes=[w.HANDLE]
    dc=g.CreateCompatibleDC(None)
    region=g.CreateRectRgn(0,0,0,0)
    try:
        assert dc and region and g.IntersectClipRect(dc,0,0,100,100)>0
        assert g.ExcludeClipRect(dc,20,20,40,40)>0 and g.OffsetClipRgn(dc,3,4)>0
        assert g.GetClipRgn(dc,region)==1
        r=[_emf_record(30,struct.pack('<iiii',0,0,100,100)),
           _emf_record(29,struct.pack('<iiii',20,20,40,40)),_emf_record(26,pair(3,4)),*line()]
        p=Emf(_emf_fixture(tmp_path,r)).polys[0]
        inc=p['clip_regions'][0];exc=p['clip_exclusions'][0]
        def inside(poly,x,y):
            return min(q[0] for q in poly)<=x<max(q[0] for q in poly) and min(q[1] for q in poly)<=y<max(q[1] for q in poly)
        for x,y in [(4,5),(25,25),(43,25),(102,103),(103,104),(10,40)]:
            assert bool(g.PtInRegion(region,x,y)) == (inside(inc,x,y) and not inside(exc,x,y))
    finally:
        if region:g.DeleteObject(region)
        if dc:g.DeleteDC(dc)
