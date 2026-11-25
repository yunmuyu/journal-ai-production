from pathlib import Path
import hashlib
import pymupdf as fitz
import pytest
from journal_pdf.assets import Assets


@pytest.mark.parametrize('nonzero',[False,True])
def test_source_crop_uses_local_page_coordinates_for_zero_and_nonzero_input_crop(tmp_path:Path,nonzero:bool):
    # Given identical visible shapes on source pages with different MediaBox crop origins.
    source=tmp_path/'source.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=200 if nonzero else 100,height=120 if nonzero else 80)
        page.draw_rect(fitz.Rect(80,40,100,60) if nonzero else fitz.Rect(30,20,50,40),width=.7)
        if nonzero:page.set_cropbox(fitz.Rect(50,20,150,100))
        doc.save(source)
    assets=Assets()
    try:
        # When the same local source viewport is selected.
        body=assets.source_vector_body(source,0,[20,10,60,50])
        # Then original path coordinates land at the same local output position.
        assert list(body.doc[0].get_drawings()[0]['rect'])==pytest.approx([10,10,30,30])
        assert all(row['exact'] for row in body.audit['pixels'])
    finally:assets.close()


def test_two_stage_registered_reletter_then_tile_matches_single_native_crop(tmp_path:Path):
    # Given a full relettered original whose derivative has a nonzero CropBox.
    source=tmp_path/'source.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=200,height=120)
        page.draw_rect(fitz.Rect(80,40,100,60),width=.7)
        page.insert_text((120,80),'R1',fontsize=8)
        span=page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        doc.save(source)
    assets=Assets()
    try:
        full=assets.source_vector_body(source,0,[50,20,150,100],text_replacements=[{'source_text':'R1','source_bbox':list(span['bbox']),'target_text_id':'r1'}])
        derivative=tmp_path/'full-fontfree.pdf';derivative.write_bytes(full.data)
        # When native body preparation crops that derivative in its local page coordinates.
        tile=assets.source_vector_body(derivative,0,[20,10,60,50])
        direct=assets.source_vector_body(source,0,[70,30,110,70])
        # Then both stages preserve exactly the direct native path, style and rendered pixels.
        a=tile.doc[0].get_pixmap(dpi=576,alpha=False);b=direct.doc[0].get_pixmap(dpi=576,alpha=False)
        assert hashlib.sha256(a.samples).hexdigest()==hashlib.sha256(b.samples).hexdigest()
        assert tile.doc[0].get_fonts()==[]
    finally:assets.close()


@pytest.mark.parametrize('mixed',[False,True])
@pytest.mark.parametrize('origin',[(-3,-2),(3,2)])
def test_public_preparation_normalizes_nonzero_media_origin_without_moving_visible_artwork(tmp_path,mixed,origin):
    from io import BytesIO
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import RectangleObject
    from journal_pdf.source_icons import path_record
    from test_source_mixed_body import mixed_source
    source=tmp_path/'origin.pdf'
    if mixed:mixed_source(source)
    else:
        with fitz.open() as doc:
            page=doc.new_page(width=100,height=80)
            page.draw_rect(fitz.Rect(20,15,70,65),width=.7)
            page.insert_text((30,50),'R1',fontsize=8);doc.save(source)
    reader=PdfReader(source);writer=PdfWriter(clone_from=reader)
    x,y=origin
    page=writer.pages[0]
    page.mediabox=RectangleObject([x,y,x+100,y+80]);page.cropbox=RectangleObject([x,y,x+100,y+80])
    buf=BytesIO();writer.write(buf);source.write_bytes(buf.getvalue())
    original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    with fitz.open(source) as doc:
        page=doc[0];clip=list(page.rect);paths=[path_record(row) for row in page.get_drawings()]
        replacements=[{'source_text':s['text'],'source_bbox':list(s['bbox']),'target_text_id':'text'+str(i)}
                      for i,s in enumerate(s for b in page.get_text('dict')['blocks'] if b['type']==0 for line in b['lines'] for s in line['spans'] if s['text'].strip())]
    assets=Assets()
    try:
        prepare=assets.source_mixed_body if mixed else assets.source_vector_body
        body=prepare(source,0,clip,text_replacements=replacements)
        # Gray preparation changes colors only, so compare noncolor path geometry.
        assert len(body.doc[0].get_drawings())==len(paths)
        assert [row.coordinates for row in paths]==[path_record(row).coordinates for row in body.doc[0].get_drawings()]
        assert body.doc[0].cropbox_position==fitz.Point(0,0)
        assert not body.doc[0].get_fonts() and not body.doc[0].get_texttrace()
        proof=body.audit['origin_normalization']
        assert proof['local_coordinates_preserved'] is True
        assert proof['displayed_pixels_exact_dpi']==[72,144]
        assert proof['pdf_translation_pt']==[-x,-y]
        assert body.audit['source_sha256']==original_hash
        assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
    finally:assets.close()


def test_nonzero_origin_still_requires_all_native_text_registrations(tmp_path):
    from io import BytesIO
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import RectangleObject
    from journal_pdf.common import FigureError
    source=tmp_path/'origin-text.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80);page.draw_line((10,10),(80,10),width=.5)
        page.insert_text((20,40),'Do not drop this',fontsize=8);doc.save(source)
    writer=PdfWriter(clone_from=PdfReader(source))
    writer.pages[0].mediabox=RectangleObject([-3,-2,97,78])
    writer.pages[0].cropbox=RectangleObject([-3,-2,97,78])
    buf=BytesIO();writer.write(buf);source.write_bytes(buf.getvalue())
    assets=Assets()
    try:
        with pytest.raises(FigureError) as error:assets.source_vector_body(source,0,[0,0,100,80])
        assert error.value.code=='source_icon_contains_text'
    finally:assets.close()


@pytest.mark.parametrize('kind',['rotation','annotation'])
def test_nonzero_origin_rejects_unverified_rotation_or_annotation_normalization(tmp_path,kind):
    from journal_pdf.common import FigureError
    source=tmp_path/'unverified-origin.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=120,height=100)
        page.draw_line((30,30),(70,50),width=.5)
        page.set_cropbox(fitz.Rect(10,10,110,90))
        if kind=='rotation':page.set_rotation(90)
        else:page.add_text_annot((20,20),'Review')
        doc.save(source)
    assets=Assets()
    try:
        with fitz.open(source) as doc:clip=list(doc[0].rect)
        with pytest.raises(FigureError) as error:assets.source_vector_body(source,0,clip)
        assert error.value.code==('source_origin_rotation' if kind=='rotation' else 'source_origin_annotations')
    finally:assets.close()
