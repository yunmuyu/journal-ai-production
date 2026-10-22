import pymupdf as fitz
import pytest

from journal_pdf.fonts import draw_text
from journal_pdf.scene import Scene, audit_scene


def test_chinese_stays_upright_and_english_word_turns_clockwise_in_actual_pdf(reg, tmp_path):
    scene = Scene(reg, 8)
    node = scene.box('root', '逸友App', 8, 8, vertical_text=True, text_role='literal')
    scene.finish(node['rect'][2]+8, node['rect'][3]+8)
    assert not audit_scene(scene)
    text = scene.texts[0]
    glyphs = text['measurement']['glyphs']
    assert [g['rotation'] for g in glyphs] == [0, 0, 270, 270, 270]
    assert glyphs[2]['x'] == pytest.approx(glyphs[3]['x'])
    assert glyphs[2]['y'] < glyphs[3]['y'] < glyphs[4]['y']
    reg.prepare_document_fonts(scene.texts)
    pdf = tmp_path/'mixed.pdf'
    with fitz.open() as d:
        page = d.new_page(width=scene.width, height=scene.height)
        draw_text(page, reg, text)
        d.save(pdf)
    with fitz.open(pdf) as d:
        lines = [l for b in d[0].get_text('dict')['blocks'] for l in b.get('lines', [])]
        app = next(l for l in lines if ''.join(s['text'] for s in l['spans']) == 'App')
        assert app['dir'] == pytest.approx((0., 1.))
        for ch in ('逸', '友'):
            line = next(l for l in lines if any(s['text'] == ch for s in l['spans']))
            assert line['dir'] == pytest.approx((1., 0.))
