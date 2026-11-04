"""Optional clip geometry: real GDI region oracle and vector result checks."""
import json
import struct
import subprocess
import sys

import pytest
pytest.importorskip('shapely')
from shapely.geometry import Point, shape
from figure_audit.emf import to_json
from figure_audit.emf_parser import Emf
from figure_audit.errors import AuditInputError
from test_figure_audit_contract import _emf_fixture, _emf_record


def region(mode,rectangles):
    body=b''.join(struct.pack('<iiii',*r) for r in rectangles)
    header=struct.pack('<IIIIiiii',32,1,len(rectangles),len(body),0,0,100,100)
    return _emf_record(75,struct.pack('<II',len(header)+len(body),mode)+header+body)


def drawing():
    return [_emf_record(27,struct.pack('<ii',0,5)),_emf_record(54,struct.pack('<ii',20,5))]


def test_clip_geometry_requires_explicit_device_surface(tmp_path):
    path=_emf_fixture(tmp_path,drawing())
    with pytest.raises(AuditInputError,match='explicit integer playback device bounds'):
        Emf(path,clip_geometry=True)


def test_clip_xor_cuts_line_and_retains_original(tmp_path):
    records=[region(5,[(0,0,10,10)]),region(3,[(5,0,15,10)]),*drawing()]
    source=_emf_fixture(tmp_path,records);out=tmp_path/'clip.json'
    to_json(source,out,clip_geometry=True,clip_device_bounds=(0,0,100,100))
    report=json.loads(out.read_text(encoding='utf-8'));p=report['polys'][0]
    assert p['pts']==[[0,0.5],[2,0.5]]
    assert p['visible_geometry_mm']['status']=='clipped'
    geometry=shape(p['visible_geometry_mm']['stroke_centerline'])
    assert geometry.length==pytest.approx(1.0)
    assert geometry.geom_type=='MultiLineString'
    assert report['complete'] is False


def test_public_cli_writes_clipped_geometry(tmp_path):
    source=_emf_fixture(tmp_path,[region(5,[(0,0,10,10)]),*drawing()]);out=tmp_path/'cli.json'
    subprocess.run([sys.executable,'-m','figure_audit.emf','json',str(source),str(out),
                    '--clip-geometry','--clip-bounds','0','0','100','100'],check=True,capture_output=True)
    report=json.loads(out.read_text(encoding='utf-8'))
    assert report['clip_device_bounds']==[0,0,100,100]
    assert report['polys'][0]['visible_geometry_mm']['status']=='clipped'


def test_clip_filled_polygon_diff_yields_separate_geometry(tmp_path):
    # Synthetic polygon fill uses a selected solid brush and rectangle primitive.
    brush=_emf_record(39,struct.pack('<Iiii',1,0,0,0))
    select=_emf_record(37,struct.pack('<I',1))
    rect=_emf_record(43,struct.pack('<iiii',0,0,20,10))
    records=[brush,select,region(5,[(0,0,20,10)]),region(4,[(5,0,15,10)]),rect]
    source=_emf_fixture(tmp_path,records);out=tmp_path/'fill.json'
    to_json(source,out,clip_geometry=True,clip_device_bounds=(0,0,100,100))
    p=json.loads(out.read_text(encoding='utf-8'))['polys'][0]
    assert shape(p['visible_geometry_mm']['fill']).area==pytest.approx(1.0)


def test_unknown_clip_path_cannot_claim_clipped_geometry(tmp_path):
    records=[_emf_record(67,struct.pack('<I',1)),*drawing()]
    source=_emf_fixture(tmp_path,records);out=tmp_path/'unknown.json'
    to_json(source,out,clip_geometry=True,clip_device_bounds=(0,0,100,100))
    assert json.loads(out.read_text(encoding='utf-8'))['polys'][0]['visible_geometry_mm']['status']=='unknown'


def test_meta_clip_and_restore_are_preserved_across_copy_reset(tmp_path):
    copy_reset=_emf_record(75,struct.pack('<II',0,5))
    records=[region(5,[(0,0,10,10)]),_emf_record(28),_emf_record(33),
             region(5,[(5,0,15,10)]),*drawing(),_emf_record(34,struct.pack('<i',-1)),
             copy_reset,*drawing()]
    e=Emf(_emf_fixture(tmp_path,records),clip_geometry=True,clip_device_bounds=(0,0,100,100))
    first=e.polys[0]['clip_model'];second=e.polys[1]['clip_model']
    assert first.known and second.known
    assert first.effective.geometry.area==pytest.approx(50)
    assert second.effective.geometry.area==pytest.approx(100)


def test_unsupported_clip_path_can_be_reset_but_unknown_meta_cannot(tmp_path):
    reset=_emf_record(75,struct.pack('<II',0,5))
    path=_emf_fixture(tmp_path,[_emf_record(67,struct.pack('<I',1)),reset,*drawing(),
        _emf_record(67,struct.pack('<I',1)),_emf_record(28),reset,*drawing()])
    e=Emf(path,clip_geometry=True,clip_device_bounds=(0,0,100,100))
    assert e.polys[0]['clip_model'].known
    assert not e.polys[1]['clip_model'].known


def test_ellipse_clipping_is_explicitly_unsupported(tmp_path):
    source=_emf_fixture(tmp_path,[_emf_record(42,struct.pack('<iiii',0,0,20,10))]);out=tmp_path/'ellipse.json'
    to_json(source,out,clip_geometry=True,clip_device_bounds=(0,0,100,100))
    assert json.loads(out.read_text(encoding='utf-8'))['polys'][0]['visible_geometry_mm']['status']=='unsupported-ellipse'


def test_text_glyph_clipping_is_explicitly_unsupported(tmp_path):
    text=bytearray(80);struct.pack_into('<II',text,0,84,80)
    struct.pack_into('<ii',text,36,0,0);struct.pack_into('<II',text,44,1,76)
    text[76:78]='A'.encode('utf-16le')
    e=Emf(_emf_fixture(tmp_path,[bytes(text)]),clip_geometry=True,clip_device_bounds=(0,0,100,100))
    assert e.text_list()[0]['visible_geometry_status']=='unsupported-text-glyph'


@pytest.mark.skipif(sys.platform!='win32',reason='Requires Windows GDI')
@pytest.mark.parametrize('mode',[1,2,3,4,5])
def test_region_boolean_operations_match_windows_gdi(tmp_path,mode):
    import ctypes as c
    from ctypes import wintypes as w
    g=c.WinDLL('gdi32',use_last_error=True)
    g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
    g.DeleteDC.argtypes=[w.HDC];g.DeleteObject.argtypes=[w.HANDLE]
    g.CreateRectRgn.argtypes=[c.c_int,c.c_int,c.c_int,c.c_int];g.CreateRectRgn.restype=w.HRGN
    g.CombineRgn.argtypes=[w.HRGN,w.HRGN,w.HRGN,c.c_int]
    g.PtInRegion.argtypes=[w.HRGN,c.c_int,c.c_int]
    a=g.CreateRectRgn(10,10,50,50);b=g.CreateRectRgn(30,30,70,70);result=g.CreateRectRgn(0,0,0,0)
    try:
        # CombineRgn COPY copies its first input; ExtSelectClipRgn COPY uses the new region.
        assert a and b and result and g.CombineRgn(result,b if mode==5 else a,b,mode)>0
        records=[region(5,[(10,10,50,50)]),region(mode,[(30,30,70,70)]),*drawing()]
        e=Emf(_emf_fixture(tmp_path,records),clip_geometry=True,clip_device_bounds=(0,0,100,100))
        clip=e.polys[0]['clip_model'].effective
        for x,y in [(5,5),(20,20),(40,40),(60,60),(20,60),(80,80)]:
            inside=clip.geometry.contains(Point(x,y)) != clip.complement
            assert bool(g.PtInRegion(result,x,y))==inside
    finally:
        for handle in (a,b,result):
            if handle:g.DeleteObject(handle)


@pytest.mark.skipif(sys.platform!='win32',reason='Requires Windows GDI')
def test_region_data_uses_device_not_logical_coordinates(tmp_path):
    import ctypes as c
    from ctypes import wintypes as w
    g=c.WinDLL('gdi32',use_last_error=True)
    g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
    g.DeleteDC.argtypes=[w.HDC];g.DeleteObject.argtypes=[w.HANDLE]
    g.SetMapMode.argtypes=[w.HDC,c.c_int]
    g.SetWindowExtEx.argtypes=[w.HDC,c.c_int,c.c_int,c.c_void_p]
    g.SetViewportExtEx.argtypes=[w.HDC,c.c_int,c.c_int,c.c_void_p]
    g.CreateRectRgn.argtypes=[c.c_int,c.c_int,c.c_int,c.c_int];g.CreateRectRgn.restype=w.HRGN
    g.ExtSelectClipRgn.argtypes=[w.HDC,w.HRGN,c.c_int];g.GetClipRgn.argtypes=[w.HDC,w.HRGN]
    g.PtInRegion.argtypes=[w.HRGN,c.c_int,c.c_int]
    dc=g.CreateCompatibleDC(None);a=g.CreateRectRgn(10,20,30,40);actual=g.CreateRectRgn(0,0,0,0)
    try:
        assert dc and a and actual and g.SetMapMode(dc,8)
        assert g.SetWindowExtEx(dc,100,100,None) and g.SetViewportExtEx(dc,200,300,None)
        assert g.ExtSelectClipRgn(dc,a,5)>0 and g.GetClipRgn(dc,actual)==1
        records=[_emf_record(17,struct.pack('<I',8)),_emf_record(9,struct.pack('<ii',100,100)),
                 _emf_record(11,struct.pack('<ii',200,300)),region(5,[(10,20,30,40)]),*drawing()]
        e=Emf(_emf_fixture(tmp_path,records),clip_geometry=True,clip_device_bounds=(0,0,100,100))
        geometry=e.polys[0]['clip_model'].effective.geometry
        for x,y in [(15,25),(25,35),(35,55),(5,15)]:
            assert bool(g.PtInRegion(actual,x,y)) == geometry.contains(Point(x,y))
    finally:
        for handle in (a,actual):
            if handle:g.DeleteObject(handle)
        if dc:g.DeleteDC(dc)


@pytest.mark.skipif(sys.platform!='win32',reason='Requires Windows GDI')
def test_meta_clip_matches_windows_gdi(tmp_path):
    import ctypes as c
    from ctypes import wintypes as w
    g=c.WinDLL('gdi32',use_last_error=True)
    g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
    g.DeleteDC.argtypes=[w.HDC];g.DeleteObject.argtypes=[w.HANDLE]
    g.CreateRectRgn.argtypes=[c.c_int,c.c_int,c.c_int,c.c_int];g.CreateRectRgn.restype=w.HRGN
    g.ExtSelectClipRgn.argtypes=[w.HDC,w.HRGN,c.c_int];g.SetMetaRgn.argtypes=[w.HDC]
    g.GetClipRgn.argtypes=[w.HDC,w.HRGN];g.GetMetaRgn.argtypes=[w.HDC,w.HRGN]
    g.PtInRegion.argtypes=[w.HRGN,c.c_int,c.c_int]
    dc=g.CreateCompatibleDC(None);a=g.CreateRectRgn(10,10,50,50);b=g.CreateRectRgn(30,30,70,70)
    app=g.CreateRectRgn(0,0,0,0);meta=g.CreateRectRgn(0,0,0,0)
    try:
        assert dc and a and b and app and meta
        assert g.ExtSelectClipRgn(dc,a,5)>0 and g.SetMetaRgn(dc)>0 and g.ExtSelectClipRgn(dc,b,5)>0
        assert g.GetClipRgn(dc,app)==1 and g.GetMetaRgn(dc,meta)==1
        records=[region(5,[(10,10,50,50)]),_emf_record(28),region(5,[(30,30,70,70)]),*drawing()]
        e=Emf(_emf_fixture(tmp_path,records),clip_geometry=True,clip_device_bounds=(0,0,100,100))
        model=e.polys[0]['clip_model'];assert model.known
        for x,y in [(20,20),(40,40),(60,60),(80,80)]:
            expected=bool(g.PtInRegion(app,x,y)) and bool(g.PtInRegion(meta,x,y))
            assert expected==model.effective.geometry.contains(Point(x,y))
    finally:
        for handle in (a,b,app,meta):
            if handle:g.DeleteObject(handle)
        if dc:g.DeleteDC(dc)


@pytest.mark.skipif(sys.platform!='win32',reason='Requires Windows GDI')
def test_sheared_rect_clip_matches_windows_gdi_away_from_edges(tmp_path):
    import ctypes as c
    from ctypes import wintypes as w
    class Xform(c.Structure):
        _fields_=[(name,c.c_float) for name in ('m11','m12','m21','m22','dx','dy')]
    g=c.WinDLL('gdi32',use_last_error=True)
    g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
    g.DeleteDC.argtypes=[w.HDC];g.DeleteObject.argtypes=[w.HANDLE]
    g.SetGraphicsMode.argtypes=[w.HDC,c.c_int];g.SetWorldTransform.argtypes=[w.HDC,c.POINTER(Xform)]
    g.IntersectClipRect.argtypes=[w.HDC,c.c_int,c.c_int,c.c_int,c.c_int]
    g.CreateRectRgn.argtypes=[c.c_int,c.c_int,c.c_int,c.c_int];g.CreateRectRgn.restype=w.HRGN
    g.GetClipRgn.argtypes=[w.HDC,w.HRGN];g.PtInRegion.argtypes=[w.HRGN,c.c_int,c.c_int]
    dc=g.CreateCompatibleDC(None);actual=g.CreateRectRgn(0,0,0,0)
    try:
        assert dc and actual and g.SetGraphicsMode(dc,2)
        assert g.SetWorldTransform(dc,c.byref(Xform(1,.5,.3,1,30,10)))
        assert g.IntersectClipRect(dc,10,10,30,30)>0 and g.GetClipRgn(dc,actual)==1
        records=[_emf_record(35,struct.pack('<6f',1,.5,.3,1,30,10)),
                 _emf_record(30,struct.pack('<iiii',10,10,30,30)),*drawing()]
        e=Emf(_emf_fixture(tmp_path,records),clip_geometry=True,clip_device_bounds=(0,0,100,100))
        geometry=e.polys[0]['clip_model'].effective.geometry
        checked=0
        for x in range(35,75,2):
            for y in range(20,65,2):
                point=Point(x,y)
                if geometry.boundary.distance(point)<2:continue
                checked+=1
                assert bool(g.PtInRegion(actual,x,y))==geometry.contains(point)
        assert checked>100
    finally:
        if actual:g.DeleteObject(actual)
        if dc:g.DeleteDC(dc)
