from pathlib import Path
import re
from io import BytesIO
import pymupdf as fitz
from PIL import Image
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError

def mixed_source(path:Path):
    image=Image.new('RGBA',(4,3),(220,70,20,128));buf=BytesIO();image.save(buf,format='PNG')
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_rect(fitz.Rect(5,5,90,70),width=.7,color=(.8,.2,.1))
        xref=page.insert_image(fitz.Rect(10,10,30,25),stream=buf.getvalue())
        page.insert_image(fitz.Rect(40,10,60,25),xref=xref)
        doc.xref_set_key(xref,'ColorSpace','/DeviceRGB')
        doc.update_stream(xref,bytes([220,70,20]*12))
        page.insert_text((20,60),'A',fontsize=8)
        span=page.get_text('dict')['blocks'][-1]['lines'][0]['spans'][0]
        doc.save(path)
    return [{'source_text':'A','source_bbox':list(span['bbox']),'target_text_id':'label-a'}]

def test_explicit_mixed_body_retains_all_native_image_instances_and_alpha(tmp_path:Path):
    source=tmp_path/'mixed.pdf';replacements=mixed_source(source);assets=Assets()
    try:
        body=assets.source_mixed_body(source,0,[0,0,100,80],text_replacements=replacements)
        assert body.audit['mode']=='source-mixed-body'
        assert body.audit['image_resource_count']==1
        assert body.audit['image_instance_count']==2
        assert body.audit['path_count']==1
        assert not body.doc[0].get_text().strip() and not body.doc[0].get_fonts()
        assert len(body.doc[0].get_image_info())==2
        assert body.audit['original_smask_preserved']
        image=body.doc[0].get_images()[0]
        assert body.doc.xref_stream(image[0])==bytes([109]*36)
        assert body.doc.xref_stream(image[1])==bytes([128]*12)
    finally:assets.close()

def test_plain_vector_body_still_refuses_mixed_images(tmp_path:Path):
    source=tmp_path/'mixed.pdf';replacements=mixed_source(source);assets=Assets()
    try:
        with pytest.raises(FigureError,match='图片'):
            assets.source_vector_body(source,0,[0,0,100,80],text_replacements=replacements)
    finally:assets.close()

@pytest.mark.parametrize('mutation',['pixel','alpha','alpha-matte','position','missing-instance','size'])
def test_mixed_actual_pdf_rejects_changed_native_image_instance(tmp_path:Path,mutation:str):
    from journal_pdf.source_mixed_body import image_records,consume_images
    source=tmp_path/'mixed.pdf';replacements=mixed_source(source);assets=Assets()
    try:
        body=assets.source_mixed_body(source,0,[0,0,100,80],text_replacements=replacements)
        with fitz.open(stream=body.data,filetype='pdf') as original:
            expected=image_records(original,original[0])
        with fitz.open(stream=body.data,filetype='pdf') as doc:
            page=doc[0];xref=page.get_images()[0][0]
            if mutation in ('pixel','alpha'):
                target=page.get_images()[0][1] if mutation=='alpha' else xref
                data=bytearray(doc.xref_stream(target));data[0]^=127;doc.update_stream(target,bytes(data))
            elif mutation=='alpha-matte':doc.xref_set_key(page.get_images()[0][1],'Matte','[.1 .1 .1]')
            elif mutation=='position':
                data=page.read_contents().replace(b'10 55 cm',b'11 55 cm')
                assert data!=page.read_contents()
                page.set_contents(page.get_contents()[0]);doc.update_stream(page.get_contents()[0],data)
            elif mutation=='missing-instance':
                data=page.read_contents();match=list(re.finditer(rb'/[^\s]+\s+Do',data))[-1]
                data=data[:match.start()]+data[match.end():];page.set_contents(page.get_contents()[0]);doc.update_stream(page.get_contents()[0],data)
            else:doc.xref_set_key(xref,'Width','5')
            mutated=doc.tobytes(garbage=4,deflate=True)
        with fitz.open(stream=mutated,filetype='pdf') as doc:
            with pytest.raises(FigureError):consume_images(expected,image_records(doc,doc[0]))
    finally:assets.close()


def test_mixed_source_requires_registered_text_and_complete_page(tmp_path:Path):
    source=tmp_path/'mixed.pdf';replacements=mixed_source(source);assets=Assets()
    try:
        with pytest.raises(FigureError,match='未登记'):
            assets.source_mixed_body(source,0,[0,0,100,80])
        with pytest.raises(FigureError,match='完整源页'):
            assets.source_mixed_body(source,0,[5,5,90,70],text_replacements=replacements)
    finally:assets.close()

@pytest.mark.parametrize('target',['missing','wrong'])
def test_mixed_scene_requires_exact_editable_replacement(reg,tmp_path:Path,target:str):
    from journal_pdf.render import compile_figure
    source=tmp_path/'mixed.pdf';rows=mixed_source(source);assets=Assets()
    spec={'id':'mixed','author':'test','kind':'scene','width_pt':100,'height_pt':100,'policy':{'design_font_size_pt':6},
          'assets':[{'id':'original','path':'mixed.pdf','source_kind':'pdf','source_mixed_body':True,'clip':[0,0,100,80],'target':[0,0,100,80],'text_replacements':rows}],
          'texts':[] if target=='missing' else [{'id':'label-a','text':'B','x':50,'y':90}]}
    try:
        with pytest.raises(FigureError) as error:compile_figure(spec,reg,assets,tmp_path)
        assert error.value.code=='source_icon_replacement_missing'
    finally:assets.close()


def test_mixed_source_ownership_keeps_new_stroke_gate(tmp_path:Path):
    from journal_pdf.source_icons import audit_icon_paths
    source=tmp_path/'mixed.pdf';rows=mixed_source(source);assets=Assets()
    try:
        asset=assets.source_mixed_body(source,0,[0,0,100,80],text_replacements=rows)
        with fitz.open() as doc:
            page=doc.new_page(width=100,height=100)
            assets.place(page,asset,[0,0,100,80]);page.draw_line((5,90),(95,90),width=.75)
            data=doc.tobytes(garbage=4,deflate=True)
        with fitz.open(stream=data,filetype='pdf') as doc:
            proof=audit_icon_paths(doc[0],[{'id':'original','asset':asset,'rect':[0,0,100,80]}])
        assert proof['matched_path_count']==1
        assert proof['image_ownership']['matched_instance_count']==2
        assert len(proof['stroke_violations'])==1
        assert proof['stroke_violations'][0]['width_pt']==.75
    finally:assets.close()


def test_mixed_saved_pdf_rejects_extra_undeclared_image_instance(tmp_path:Path):
    from journal_pdf.source_icons import audit_icon_paths
    source=tmp_path/'mixed.pdf';rows=mixed_source(source);assets=Assets()
    try:
        asset=assets.source_mixed_body(source,0,[0,0,100,80],text_replacements=rows)
        with fitz.open() as doc:
            page=doc.new_page(width=100,height=100);assets.place(page,asset,[0,0,100,80])
            page.insert_image(fitz.Rect(70,80,90,95),xref=page.get_images()[0][0])
            data=doc.tobytes(garbage=4,deflate=True)
        with fitz.open(stream=data,filetype='pdf') as doc:
            with pytest.raises(FigureError) as error:
                audit_icon_paths(doc[0],[{'id':'original','asset':asset,'rect':[0,0,100,80]}])
            assert error.value.code=='source_mixed_image_changed'
    finally:assets.close()
