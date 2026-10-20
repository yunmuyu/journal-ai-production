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
