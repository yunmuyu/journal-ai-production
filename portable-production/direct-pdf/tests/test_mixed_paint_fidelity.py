"""Synthetic regressions only: no author PDF or machine paths are fixtures."""
from io import BytesIO
from pathlib import Path

import pymupdf as fitz
import pytest
from pypdf import PdfReader,PdfWriter
from pypdf.generic import (ArrayObject,ContentStream,DecodedStreamObject,
                           DictionaryObject,NameObject,NumberObject)

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.source_mixed_body import image_records,consume_images
from journal_pdf.source_icons import audit_icon_paths
from test_source_mixed_body import mixed_source


def duplicate_color_images(path:Path):
    """Two real resources share RGB bytes, but not dimensions or SMask."""
    writer=PdfWriter();page=writer.add_blank_page(width=100,height=80)
    def image(width,height,alpha):
        mask=DecodedStreamObject();mask.set_data(bytes([alpha]*6))
        mask.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
                     NameObject('/Width'):NumberObject(width),NameObject('/Height'):NumberObject(height),
                     NameObject('/BitsPerComponent'):NumberObject(8),NameObject('/ColorSpace'):NameObject('/DeviceGray')})
        value=DecodedStreamObject();value.set_data(bytes([90,140,200]*6))
        value.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
                      NameObject('/Width'):NumberObject(width),NameObject('/Height'):NumberObject(height),
                      NameObject('/BitsPerComponent'):NumberObject(8),NameObject('/ColorSpace'):NameObject('/DeviceRGB'),
                      NameObject('/SMask'):writer._add_object(mask)})
        return writer._add_object(value)
    a=image(2,3,64);b=image(3,2,192)
    xobjects=DictionaryObject({NameObject('/a'):a,NameObject('/b'):b})
    form=DecodedStreamObject();form.set_data(b'/b Do\n')
    form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
                 NameObject('/BBox'):ArrayObject([NumberObject(v) for v in [0,0,1,1]]),
                 NameObject('/Resources'):DictionaryObject({NameObject('/XObject'):xobjects})})
    resources=DictionaryObject({NameObject('/a'):a,NameObject('/b'):b,NameObject('/form'):writer._add_object(form)})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):resources})
    stream=DecodedStreamObject();stream.set_data(b'''q 30 0 0 20 10 50 cm /a Do Q
q .3 .7 .1 rg 15 50 10 10 re f Q
q 10 5 -2 18 50 45 cm /b Do Q
q 8 8 20 30 re W n 15 0 0 10 10 20 cm /a Do Q
q 15 0 0 15 70 10 cm /form Do Q
''')
    page[NameObject('/Contents')]=writer._add_object(stream)
    with path.open('wb') as output:writer.write(output)


def test_real_do_instances_disambiguate_equal_rgb_different_masks_dimensions_and_forms(tmp_path):
    source=tmp_path/'same-rgb.pdf';duplicate_color_images(source)
    with fitz.open(source) as doc:
        records=image_records(doc,doc[0])
        assert [(row['width'],row['height']) for row in records]==[(2,3),(3,2),(2,3),(3,2)]
        assert len({row['decoded_rgb_sha256'] for row in records})==1
        assert len({row['smask_sha256'] for row in records})==2
        assert records[0]['xref']==records[2]['xref']!=records[1]['xref']
        assert records[2]['clip_paths'] and records[3]['clip_paths']
    assets=Assets()
    try:
        body=assets.source_mixed_body(source,0,[0,0,100,80])
        assert body.audit['image_resource_count']==2
        assert body.audit['image_instance_count']==4
        assert body.audit['nontext_paint_order_preserved'] is True
        assert body.audit['original_image_clipping_preserved'] is True
        assert body.audit['embedded_image_semantic_review_required'] is True
        assert body.audit['source_text_scope']=='native_pdf_text_only'
        with fitz.open() as output:
            page=output.new_page(width=210,height=170)
            assets.place(page,body,[5,5,205,165])
            data=output.tobytes(garbage=3,deflate=True)
        with fitz.open(stream=data,filetype='pdf') as saved:
            proof=audit_icon_paths(saved[0],[{'id':'body','asset':body,'rect':[5,5,205,165]}])
            assert proof['image_ownership']['matched_instance_count']==4
            assert proof['mixed_paint_order_and_clipping_verified'] is True
    finally:assets.close()


def test_image_clipping_changes_are_fatal_even_when_ctm_pixels_and_smask_are_unchanged(tmp_path):
    source=tmp_path/'clip.pdf';duplicate_color_images(source)
    with fitz.open(source) as doc:
        expected=image_records(doc,doc[0])
        stream=doc[0].get_contents()[0]
        original=doc.xref_stream(stream)
        changed=original.replace(b'8 8 20 30 re',b'9 8 20 30 re')
        assert changed!=original
        doc.update_stream(stream,changed)
        with pytest.raises(FigureError) as error:consume_images(expected,image_records(doc,doc[0]))
        assert error.value.code=='source_mixed_image_changed'


def test_saved_mixed_output_rejects_reordered_vector_and_image_paints(tmp_path):
    source=tmp_path/'mixed.pdf';rows=mixed_source(source);assets=Assets()
    try:
        body=assets.source_mixed_body(source,0,[0,0,100,80],text_replacements=rows)
        with fitz.open() as output:
            page=output.new_page(width=100,height=80);assets.place(page,body,[0,0,100,80])
            reader=PdfReader(BytesIO(output.tobytes()));writer=PdfWriter(clone_from=reader)
        changed=False
        def reorder(owner):
            nonlocal changed
            for reference in owner.get('/Resources',{}).get('/XObject',{}).values():
                child=reference.get_object()
                if child.get('/Subtype')!='/Form':continue
                stream=ContentStream(child,writer);ops=stream.operations
                # The prepared body has a vector q/Q group followed by images.
                if any(op==b'Do' for _,op in ops) and any(op==b'S' for _,op in ops):
                    assert ops[0][1]==b'q'
                    depth=0;end=None
                    for index,(_,op) in enumerate(ops):
                        if op==b'q':depth+=1
                        elif op==b'Q':depth-=1
                        if depth==0:end=index+1;break
                    assert end and end<len(ops)
                    stream.operations=ops[end:]+ops[:end]
                    child.set_data(stream.get_data());changed=True
                else:reorder(child)
        reorder(writer.pages[0]);assert changed
        buf=BytesIO();writer.write(buf)
        with fitz.open(stream=buf.getvalue(),filetype='pdf') as saved:
            with pytest.raises(FigureError) as error:
                audit_icon_paths(saved[0],[{'id':'body','asset':body,'rect':[0,0,100,80]}])
            assert error.value.code=='source_mixed_paint_order'
    finally:assets.close()
