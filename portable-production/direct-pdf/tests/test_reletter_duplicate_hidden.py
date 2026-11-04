import json
import pymupdf as fitz
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError


def make_source(path, labels):
    with fitz.open() as doc:
        p=doc.new_page(width=100,height=80)
        p.draw_line((5,5),(70,5),width=.7)
        for text,point in labels:p.insert_text(point,text,fontsize=8)
        doc.save(path)


def test_exact_duplicate_source_spans_share_one_replacement(tmp_path):
    # Given two identical source painting operations.
    path=tmp_path/'duplicate.pdf'
    make_source(path,[('old',(20,30)),('old',(20,30))])
    with fitz.open(path) as d:
        spans=[s for b in d[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
    row={'source_text':'old','source_bbox':list(spans[0]['bbox']),'target_text_id':'label'}
    assets=Assets()
    try:
        # When a single visible replacement owns both exact duplicates.
        body=assets.source_vector_body(path,0,[0,0,100,80],text_replacements=[row])
        # Then all original glyphs are removed without doubling the target.
        assert len(body.audit['text_replacements'])==1
        assert body.audit['text_replacements'][0]['source_occurrences']==2
        assert not body.doc[0].get_texttrace()
    finally:assets.close()


def test_distinct_overlapping_source_text_is_not_deduplicated(tmp_path):
    # Given distinct labels at identical origins.
    path=tmp_path/'different.pdf'
    make_source(path,[('old',(20,30)),('new',(20,30))])
    with fitz.open(path) as d:
        span=d[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
    assets=Assets()
    try:
        # When only one is registered, the other must still block.
        with pytest.raises(FigureError):
            assets.source_vector_body(path,0,[0,0,100,80],text_replacements=[{'source_text':span['text'],'source_bbox':list(span['bbox']),'target_text_id':'label'}])
    finally:assets.close()


def test_source_body_removes_text_outside_physical_page(tmp_path):
    # Given imported PDF content with invisible text outside its page.
    original=tmp_path/'original.pdf';source=tmp_path/'clipped.pdf'
    make_source(original,[('outside',(20,60))])
    with fitz.open(original) as src,fitz.open() as doc:
        p=doc.new_page(width=100,height=20)
        p.show_pdf_page(p.rect,src,0,clip=fitz.Rect(0,0,100,20))
        doc.save(source)
    assets=Assets()
    try:
        # When keeping the visible vector viewport.
        body=assets.source_vector_body(source,0,[0,0,100,20])
        # Then no hidden original glyph/font survives, and geometry is proven.
        assert not body.doc[0].get_texttrace()
        assert not body.doc[0].get_fonts(full=True)
        assert body.audit['source_path_multiset_preserved']
    finally:assets.close()

def test_duplicate_receipt_can_be_revalidated_and_count_cannot_be_forged(tmp_path):
    path=tmp_path/'duplicate.pdf'
    make_source(path,[('old',(20,30)),('old',(20,30))])
    with fitz.open(path) as doc:
        span=doc[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
    row={'source_text':'old','source_bbox':list(span['bbox']),'target_text_id':'label'}
    assets=Assets()
    try:
        first=assets.source_vector_body(path,0,[0,0,100,80],text_replacements=[row])
        receipt=first.audit['text_replacements']
        second=assets.source_vector_body(path,0,[0,0,100,80],text_replacements=receipt)
        assert first.data==second.data
        bad=[dict(receipt[0],source_occurrences=3)]
        with pytest.raises(FigureError):assets.source_vector_body(path,0,[0,0,100,80],text_replacements=bad)
    finally:assets.close()


def test_negative_offpage_form_text_and_unused_fonts_are_cleaned(tmp_path):
    original=tmp_path/'original.pdf';source=tmp_path/'negative.pdf'
    make_source(original,[('outside',(20,20))])
    with fitz.open(original) as src,fitz.open() as doc:
        p=doc.new_page(width=100,height=20)
        # Import the upper content above the final physical page, including text.
        p.show_pdf_page(fitz.Rect(0,-30,100,50),src,0)
        p.draw_line((5,10),(70,10),width=.7)
        doc.save(source)
    assets=Assets()
    try:
        body=assets.source_vector_body(source,0,[0,0,100,20])
        assert not body.doc[0].get_texttrace()
        assert not body.doc[0].get_fonts(full=True)
        assert body.audit['outside_clip_text_removed']
        assert all(p['nontext_exact'] for p in body.audit['pixels'])
    finally:assets.close()


def test_partial_visible_unregistered_text_is_not_treated_as_hidden(tmp_path):
    source=tmp_path/'partial.pdf'
    make_source(source,[('edge',(20,30))])
    assets=Assets()
    try:
        with pytest.raises(FigureError):
            assets.source_vector_body(source,0,[0,0,100,27])
    finally:assets.close()


def test_unused_form_font_is_pruned_without_offpage_text(tmp_path,profile):
    # Given a visible imported vector Form whose only label will be removed.
    original=tmp_path/'original.pdf';source=tmp_path/'unused-font.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.insert_font(fontname='sourcefont',fontfile=json.loads(profile.read_text())['faces']['cn']['path'])
        page.insert_text((20,30),'旧字',fontname='sourcefont',fontsize=8)
        page.draw_line((5,10),(70,10),width=.7)
        doc.save(original)
    with fitz.open(original) as src,fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.show_pdf_page(page.rect,src,0)
        # Office may retain the same font on a parent Form that only invokes
        # another Form. Native text redaction cleans the child, not this owner.
        font_xref=page.get_fonts(full=True)[0][0]
        owner=page.get_xobjects()[0][0]
        doc.xref_set_key(owner,'Resources/Font',f'<< /UnusedFont {font_xref} 0 R >>')
        doc.save(source)
    with fitz.open(source) as doc:
        span=doc[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
    replacement={'source_text':'旧字','source_bbox':list(span['bbox']),'target_text_id':'label'}
    assets=Assets()
    try:
        # When retaining original geometry and replacing that registered label.
        body=assets.source_vector_body(source,0,[0,0,100,80],text_replacements=[replacement])
        # Then empty font resources are removed and exact paint is still proved.
        assert not body.doc[0].get_fonts(full=True)
        assert not body.doc[0].get_texttrace()
        assert not body.audit['outside_clip_text_removed']
        assert body.audit['source_path_multiset_preserved']
        assert all(row['nontext_exact'] for row in body.audit['pixels'])
    finally:assets.close()
