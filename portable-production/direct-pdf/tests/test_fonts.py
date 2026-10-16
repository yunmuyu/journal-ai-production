import json,os,shutil
from pathlib import Path
import pytest
from journal_pdf.fonts import FontRegistry,position_text
from journal_pdf.common import FigureError


def test_warm_cache_has_zero_scan_and_zero_rehash(profile,tmp_path,monkeypatch):
    def banned(*a,**k):raise AssertionError("字体目录不应被遍历")
    monkeypatch.setattr(os,"walk",banned)
    monkeypatch.setattr(Path,"rglob",banned)
    cache=tmp_path/'cache'
    a=FontRegistry(profile,cache);a.measure("训练集 Loss");cold=dict(a.stats);a.close()
    b=FontRegistry(profile,cache);b.measure("训练集 Loss")
    assert b.stats['directory_scans']==0 and b.stats['hash_reads']==0
    assert b.stats['face_inspections']==0 and b.stats['measure_disk_hits']==1
    assert cold['hash_reads']>0
    b.close()


def test_changed_configured_file_invalidates_only_that_face(profile,tmp_path):
    d=json.loads(profile.read_text());paths={}
    for s in d['faces'].values():
        old=s['path']
        if old not in paths:
            dest=tmp_path/Path(old).name;shutil.copy2(old,dest);paths[old]=dest
        s['path']=str(paths[old])
    p=tmp_path/'profile.json';p.write_text(json.dumps(d));cache=tmp_path/'cache'
    a=FontRegistry(p,cache);a.close()
    changed=Path(d['faces']['latin']['path']);st=changed.stat();os.utime(changed,ns=(st.st_atime_ns,st.st_mtime_ns+1000000000))
    b=FontRegistry(p,cache)
    assert b.stats['hash_reads']==1 and b.stats['face_inspections']==1 and b.stats['directory_scans']==0
    b.close()


def test_missing_font_never_falls_back(profile,tmp_path):
    d=json.loads(profile.read_text());d['faces']['cn']['path']=str(tmp_path/'missing.ttf')
    p=tmp_path/'profile.json';p.write_text(json.dumps(d))
    with pytest.raises(FigureError,match="不存在"):FontRegistry(p,tmp_path/'cache')


def test_character_roles_and_italics(reg):
    assert reg.choose('汉')=='cn'
    assert reg.choose('（')=='punct'
    for c in 'A1=':assert reg.choose(c)=='latin'
    assert reg.choose('K','italic')=='latin_italic'
    with pytest.raises(FigureError):reg.choose('K','bold')


def test_missing_glyph_is_blocked(reg):
    with pytest.raises(FigureError) as e:reg.measure('\U0010ffff')
    assert e.value.code=='missing_glyph'


@pytest.mark.parametrize('size',[5.9,8.1,float('nan'),float('inf'),True])
def test_bad_font_sizes(reg,size):
    with pytest.raises(FigureError):reg.measure('A',size)


def test_real_glyph_ink_is_not_font_global_bbox(reg):
    a=reg.measure('i');b=reg.measure('W')
    assert a['width']<b['width']/2
    assert reg.measure('汉')['width']<9


def test_each_multiline_line_is_centered(reg):
    m=reg.measure('训练集\nLoss');centers=[]
    for line in {g['line'] for g in m['glyphs']}:
        bounds=[g['ink'] for g in m['glyphs'] if g['line']==line and not g['ch'].isspace()]
        centers.append((min(b[0] for b in bounds)+max(b[2] for b in bounds))/2)
    assert abs(centers[0]-centers[1])<1e-6


def test_rotation_uses_actual_ink(reg):
    m=reg.measure('Accuracy');p=position_text(m,20,50,rotation=90)
    b=p['bbox'];assert abs((b[0]+b[2])/2-20)<1e-6
    assert abs((b[1]+b[3])/2-50)<1e-6
    assert abs((b[3]-b[1])-m['width'])<1e-6


def test_partial_runs_keep_styles(reg):
    m=reg.measure([{'text':'K','style':'italic'},{'text':'=50'}])
    assert m['glyphs'][0]['face']=='latin_italic'
    assert all(g['face']=='latin' for g in m['glyphs'][1:])
