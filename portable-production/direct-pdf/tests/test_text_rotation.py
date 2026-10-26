import collections
import math
import pymupdf as fitz
import pytest
from PIL import Image,ImageChops
from journal_pdf.fonts import draw_text
from journal_pdf.scene import Scene,audit_scene


@pytest.mark.parametrize('text',['Model-123','Model-123\n(strategy)'])
@pytest.mark.parametrize('align',['center','left','right'])
@pytest.mark.parametrize('angle',[30,24.6,31.7,-30])
def test_regular_rotated_text_matches_real_pdf_ink_and_direction(reg,tmp_path,text,align,angle):
    s=Scene(reg,8);t=s.text('label',text,90,70,align=align,rotation=angle);s.finish(180,140);reg.prepare_document_fonts(s.texts)
    output=tmp_path/'thirty.pdf'
    with fitz.open() as d:
        p=d.new_page(width=180,height=140);draw_text(p,reg,t);d.save(output)
    with fitz.open(output) as d:
        p=d[0];traces=p.get_texttrace()
        assert collections.Counter(c for c in p.get_text() if not c.isspace())==collections.Counter(c for c in text if not c.isspace())
        for trace in traces:
            assert math.degrees(math.atan2(-trace['dir'][1],trace['dir'][0]))==pytest.approx(angle,abs=.01)
            assert trace['size']==pytest.approx(8,abs=.001)
        pix=p.get_pixmap(matrix=fitz.Matrix(8,8),colorspace=fitz.csRGB)
        image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        ink=ImageChops.difference(image,Image.new('RGB',image.size,'white')).getbbox()
        assert [v/8 for v in ink]==pytest.approx(t['position']['bbox'],abs=.3)
    assert all(g['face']=='latin' for g in t['measurement']['glyphs'])
    bounds=t['position']['bbox']
    assert (bounds[0] if align=='left' else bounds[2] if align=='right' else (bounds[0]+bounds[2])/2)==pytest.approx(90)


def test_neighboring_slanted_labels_do_not_collide_only_because_aabbs_overlap(reg):
    s=Scene(reg,8);a=s.text('a','MMMMMMMM',80,70,rotation=30);b=s.text('b','MMMMMMMM',100,70,rotation=30);s.finish(180,140)
    assert a['position']['bbox'][2]>b['position']['bbox'][0]
    assert not [q for q in audit_scene(s) if q['code']=='text_overlap']


def test_truly_intersecting_slanted_labels_are_rejected(reg):
    s=Scene(reg,8);s.text('a','MMMMMMMM',80,70,rotation=30);s.text('b','MMMMMMMM',81,70,rotation=30);s.finish(180,140)
    assert any(q['code']=='text_overlap' for q in audit_scene(s))

def test_slanted_label_path_checks_use_rotated_ink_but_keep_true_collision(reg):
    s=Scene(reg,8);t=s.text('label','MMMMMMMM',80,70,rotation=30);s.finish(180,140)
    b=t['position']['bbox'];s.line('clear',[[b[0]+1,b[1]+1],[b[0]+5,b[1]+1]])
    assert not [q for q in audit_scene(s) if q['code']=='text_path_collision']
    s.line('cross',[[70,70],[90,70]])
    assert any(q['code']=='text_path_collision' and q['path']=='cross' for q in audit_scene(s))


@pytest.mark.parametrize('angle',[True,float('nan'),float('inf'),'30'])
def test_invalid_angles_are_rejected(reg,angle):
    from journal_pdf.common import FigureError
    with pytest.raises(FigureError):Scene(reg,8).text('invalid','A',50,50,rotation=angle)


@pytest.mark.parametrize('tamper',[False,True])
def test_render_gate_checks_actual_rotation_not_just_declared_angle(reg,tmp_path,monkeypatch,tamper):
    from journal_pdf import render
    from journal_pdf.assets import Assets
    from journal_pdf.common import FigureError
    source=tmp_path/'source';source.mkdir();assets=Assets()
    spec={'id':'angle','author':'Synthetic','synthetic':True,'kind':'scene','width_pt':180,'height_pt':140,
          'texts':[{'id':'label','text':'Model-123','x':90,'y':70,'rotation':30}]}
    if tamper:
        original=render.draw_text
        def wrong_angle(page,registry,item):
            original(page,registry,dict(item,position=dict(item['position'],rotation=0)))
        monkeypatch.setattr(render,'draw_text',wrong_angle)
    try:
        if tamper:
            with pytest.raises(FigureError) as error:render.render_one(spec,reg,assets,source,tmp_path/'out')
            assert error.value.code=='actual_pdf_audit_failed'
            assert error.value.details['audit']['editable_text_rotation_exact'] is False
        else:
            result=render.render_one(spec,reg,assets,source,tmp_path/'out')
            assert result['pdf_audit']['editable_text_rotation_exact'] is True
    finally:assets.close()
