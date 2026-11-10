import pymupdf as fitz
import pytest
from journal_pdf.export_padding import normalize_pdf_padding
from journal_pdf.common import FigureError


@pytest.mark.parametrize('crop', [False, True])
def test_edge_touching_artwork_gets_all_four_margins_without_rescaling(tmp_path, crop):
    source, result = tmp_path/'source.pdf', tmp_path/'result.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=80)
        page.draw_rect(page.rect, fill=(0, 0, 0), color=None)
        if crop:
            page.set_cropbox(fitz.Rect(10, 20, 90, 60))
        doc.save(source)
    receipt = normalize_pdf_padding(source, result)
    assert receipt['pages'][0]['measured_margins_pt'] == pytest.approx([.25]*4, abs=.065)
    assert receipt['pages'][0]['source_view_pixels_identical']


def test_blank_page_does_not_produce_deliverable(tmp_path):
    source, result = tmp_path/'blank.pdf', tmp_path/'result.pdf'
    with fitz.open() as doc:
        doc.new_page(width=100, height=100)
        doc.save(source)
    with pytest.raises(FigureError):
        normalize_pdf_padding(source, result)
    assert not result.exists()


def test_fractional_media_origin_does_not_overflow_cropbox(tmp_path):
    source, result = tmp_path/'fractional.pdf', tmp_path/'result.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=112.56, height=16.497811)
        page.draw_rect(page.rect, fill=(0, 0, 0), color=None)
        doc.save(source)
    receipt = normalize_pdf_padding(source, result)
    assert receipt['pages'][0]['measured_margins_pt'] == pytest.approx([.25]*4, abs=.065)
    assert receipt['pages'][0]['source_view_pixels_identical']

@pytest.mark.parametrize('padding',[0,.1,.25,2,12])
@pytest.mark.parametrize('kind',['text','thin-line','clipped'])
def test_fractional_artwork_retains_text_paths_and_requested_margin(tmp_path,padding,kind):
    source,result=tmp_path/'source.pdf',tmp_path/'result.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100.37,height=80.19)
        if kind=='text':page.insert_text((10.137,40.293),'Agjy 1.25',fontsize=8)
        elif kind=='thin-line':page.draw_line((10.137,20.293),(90.187,60.219),width=.01)
        else:
            page.draw_rect(page.rect,fill=(0,0,0),color=None)
            page.set_cropbox(fitz.Rect(10.137,20.293,90.187,60.219))
        doc.save(source)
    receipt=normalize_pdf_padding(source,result,padding)
    assert receipt['pages'][0]['measured_margins_pt']==pytest.approx([padding]*4,abs=.065)
    assert receipt['rescaled'] is False
    with fitz.open(source) as before,fitz.open(result) as after:
        assert before[0].get_text()==after[0].get_text()
        if kind=='text':
            assert before[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]['size']==after[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]['size']
        if kind=='thin-line':assert before[0].get_drawings()[0]['width']==after[0].get_drawings()[0]['width']

@pytest.mark.parametrize('rotation',[90,180,270])
def test_rotated_pages_fail_closed_without_output(tmp_path,rotation):
    source,result=tmp_path/'source.pdf',tmp_path/'result.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.insert_text((10,40),'Rotation')
        page.set_rotation(rotation)
        doc.save(source)
    with pytest.raises(FigureError) as error:normalize_pdf_padding(source,result)
    assert error.value.code=='export_rotation_unsupported'
    assert not result.exists()

def test_failed_saved_margin_verification_never_replaces_existing_output(tmp_path,monkeypatch):
    import journal_pdf.export_padding as module
    source,result=tmp_path/'source.pdf',tmp_path/'result.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_rect(fitz.Rect(10,10,90,70),fill=(0,0,0))
        doc.save(source)
    result.write_bytes(b'existing deliverable')
    original=module.ink_rect
    calls=0
    def changed(page):
        nonlocal calls
        calls+=1
        return original(page) if calls==1 else fitz.Rect(0,0,page.rect.width,page.rect.height)
    monkeypatch.setattr(module,'ink_rect',changed)
    with pytest.raises(FigureError) as error:normalize_pdf_padding(source,result)
    assert error.value.code=='export_padding_mismatch'
    assert result.read_bytes()==b'existing deliverable'
    assert not list(tmp_path.glob('.padding-*'))


@pytest.mark.parametrize('padding',[.25,2])
@pytest.mark.parametrize('offset', [0, .03, .07, .11, .19, .43])
def test_r48_fractional_positions_match_requested_target(tmp_path, offset, padding):
    import pymupdf as fitz
    source, target = tmp_path / 'source.pdf', tmp_path / 'result.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=90, height=70)
        page.draw_line((10+offset, 10+offset), (75+offset, 55+offset), width=.5)
        page.insert_text((20+offset, 30+offset), 'A', fontsize=8)
        doc.save(source)
    receipt = normalize_pdf_padding(source, target, padding)
    assert receipt['pages'][0]['measured_margins_pt'] == pytest.approx([padding]*4,abs=.065)
    assert receipt['pages'][0]['source_view_pixels_identical']
    assert receipt['rescaled'] is False

@pytest.mark.parametrize('page_count',[1,5])
def test_resampled_raster_edges_are_corrected_without_relaxing_tolerance(tmp_path,page_count):
    from PIL import Image,ImageDraw
    from journal_pdf.export_padding import ink_rect
    image=Image.new('RGB',(600,400),'white');draw=ImageDraw.Draw(image)
    draw.line([(30,20),(30,350),(560,350)],fill='black',width=2)
    draw.line([(30,300),(170,240),(560,300)],fill='black',width=2)
    raster=tmp_path/'image.png';image.save(raster)
    source,target=tmp_path/'source.pdf',tmp_path/'result.pdf'
    with fitz.open() as doc:
        for _ in range(page_count):
            page=doc.new_page(width=210,height=150)
            page.insert_image(fitz.Rect(5,5,205,5+400/3),filename=raster)
            crop=(ink_rect(page)+(-.5,-.5,.5,.5)) & page.rect
            page.set_cropbox(crop)
        doc.save(source)
    receipt=normalize_pdf_padding(source,target)
    assert 1<=receipt['normalization_attempts']<=4
    assert receipt['tolerance_pt']==.065
    for page in receipt['pages']:
        assert page['measured_margins_pt']==pytest.approx([.25]*4,abs=.065)
        assert page['source_view_pixels_identical']
        assert page['rescaled'] is False
