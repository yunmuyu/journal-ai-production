# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf"]
# ///
# How to run: bundled Python tests/pdf_vector_gray_checks.py
"""Focused structural, rejection and source safety regression."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import sys
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, ArrayObject, NameObject, NumberObject, FloatObject, DecodedStreamObject, ContentStream
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_pdf_vector_gray import prepare, UnsupportedPaint


def fixture(path: Path, variant: str) -> None:
    writer=PdfWriter();page=writer.add_blank_page(100,100)
    f=DictionaryObject({NameObject('/FunctionType'):NumberObject(2),NameObject('/C0'):ArrayObject([FloatObject(.8),FloatObject(.2),FloatObject(.1)]),NameObject('/C1'):ArrayObject([FloatObject(.1),FloatObject(.3),FloatObject(.9)]),NameObject('/N'):FloatObject(1.7),NameObject('/Domain'):ArrayObject([NumberObject(0),NumberObject(1)])})
    shading=DictionaryObject({NameObject('/Function'):f,NameObject('/ShadingType'):NumberObject(2),NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/Coords'):ArrayObject([NumberObject(2),NumberObject(4),NumberObject(50),NumberObject(80)])})
    if variant=='mesh':shading[NameObject('/ShadingType')]=NumberObject(7)
    if variant=='sampled':f[NameObject('/FunctionType')]=NumberObject(0)
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Shading'):DictionaryObject({NameObject('/S1'):shading})})
    content=DecodedStreamObject();content.set_data(b'1 0 0 rg 0 0 20 30 re f /S1 sh')
    if variant=='cmyk':content.set_data(b'1 0 0 0 k 0 0 20 30 re f')
    if variant=='alias':
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/ColorSpace'):DictionaryObject({NameObject('/CSp'):NameObject('/DeviceRGB')})})
        content.set_data(b'/CSp cs 1 0 0 scn 0 0 20 30 re f')
    page[NameObject('/Contents')]=writer._add_object(content)
    if variant in ('form','form-cmyk'):
        if variant=='form-cmyk':content.set_data(b'1 0 0 0 k 0 0 20 30 re f')
        content[NameObject('/Type')]=NameObject('/XObject');content[NameObject('/Subtype')]=NameObject('/Form')
        content[NameObject('/BBox')]=ArrayObject([NumberObject(0),NumberObject(0),NumberObject(100),NumberObject(100)])
        content[NameObject('/Resources')]=page['/Resources']
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/F1'):writer._add_object(content)})})
        invoke=DecodedStreamObject();invoke.set_data(b'q 1 0 0 1 0 0 cm /F1 Do Q q /F1 Do Q')
        page[NameObject('/Contents')]=writer._add_object(invoke)
    with path.open('wb') as output:writer.write(output)


with TemporaryDirectory(prefix='jfw-pdf-gray-') as folder:
    root=Path(folder);source=root/'input.pdf';fixture(source,'valid')
    original=source.read_bytes();digest=sha256(original).hexdigest();target=root/'gray.pdf'
    prepare(source,target,digest)
    before=PdfReader(source).pages[0]['/Resources']['/Shading']['/S1']
    after=PdfReader(target).pages[0]['/Resources']['/Shading']['/S1']
    assert before['/Coords']==after['/Coords']
    assert before['/Function']['/N']==after['/Function']['/N']
    assert before['/Function']['/Domain']==after['/Function']['/Domain']
    for key in ['/C0','/C1']:
        assert after['/Function'][key][0]==after['/Function'][key][1]==after['/Function'][key][2]
    alias_source=root/'alias.pdf';alias_target=root/'alias-gray.pdf';fixture(alias_source,'alias')
    alias_original=alias_source.read_bytes();prepare(alias_source,alias_target,sha256(alias_original).hexdigest())
    import fitz
    with fitz.open(alias_source) as before_doc,fitz.open(alias_target) as after_doc:
        before_paths=before_doc[0].get_drawings();after_paths=after_doc[0].get_drawings()
        assert len(before_paths)==len(after_paths) and [x['rect'] for x in before_paths]==[x['rect'] for x in after_paths]
        color=after_paths[0]['fill'];assert max(color)-min(color)<.001
    assert alias_source.read_bytes()==alias_original
    for variant in ['mesh','sampled','cmyk']:
        invalid=root/(variant+'.pdf');fixture(invalid,variant);output=root/(variant+'-result.pdf')
        try:prepare(invalid,output,sha256(invalid.read_bytes()).hexdigest())
        except UnsupportedPaint:pass
        else:raise AssertionError('Unknown structure was accepted: '+variant)
        assert not output.exists()
    for output,expected in [(root/'wrong.pdf','0'*64),(target,digest),(source,digest)]:
        try:prepare(source,output,expected)
        except UnsupportedPaint:pass
        else:raise AssertionError('Unsafe input/output was accepted')
    assert source.read_bytes()==original
    assert not (root/'wrong.pdf').exists()
    form_source=root/'form.pdf';form_target=root/'form-gray.pdf';fixture(form_source,'form')
    form_original=form_source.read_bytes();prepare(form_source,form_target,sha256(form_original).hexdigest())
    before_pdf=PdfReader(form_source);after_pdf=PdfReader(form_target)
    before_form=before_pdf.pages[0]['/Resources']['/XObject']['/F1'];after_form=after_pdf.pages[0]['/Resources']['/XObject']['/F1']
    assert before_form['/BBox']==after_form['/BBox']
    before_ops=ContentStream(before_form,before_pdf).operations;after_ops=ContentStream(after_form,after_pdf).operations
    assert [row for row in before_ops if row[1]!=b'rg']==[row for row in after_ops if row[1]!=b'rg']
    paint=next(args for args,op in after_ops if op==b'rg');assert paint[0]==paint[1]==paint[2]
    assert before_pdf.pages[0].get_contents().operations==after_pdf.pages[0].get_contents().operations
    assert form_source.read_bytes()==form_original
    invalid=root/'form-cmyk.pdf';fixture(invalid,'form-cmyk');output=root/'form-cmyk-result.pdf'
    try:prepare(invalid,output,sha256(invalid.read_bytes()).hexdigest())
    except UnsupportedPaint:pass
    else:raise AssertionError('CMYK inside Form was accepted')
    assert not output.exists()
print('PDF gray geometry, unknown structure and source safety passed')
