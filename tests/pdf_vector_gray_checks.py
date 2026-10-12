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
from pypdf.generic import DictionaryObject, ArrayObject, NameObject, NumberObject, FloatObject, DecodedStreamObject
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
    page[NameObject('/Contents')]=writer._add_object(content)
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
print('PDF gray geometry, unknown structure and source safety passed')
