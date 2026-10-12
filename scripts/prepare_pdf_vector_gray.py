# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf"]
# ///
# How to run: bundled Python prepare_pdf_vector_gray.py SOURCE.pdf OUTPUT.pdf SHA256
# Uses already installed pypdf; no installation or source overwrite.
"""Prepare RGB PDF paint without rebuilding artwork or flattening gradients."""
from __future__ import annotations

from pathlib import Path
from io import BytesIO
from hashlib import sha256
import sys
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, ContentStream, DictionaryObject, FloatObject, NameObject

class UnsupportedPaint(Exception):
    """An unverified shading layout must not silently enter production."""
    def __init__(self, reason: str) -> None:
        super().__init__(reason)


def gray_rgb(values: ArrayObject) -> ArrayObject:
    """Return equal RGB components, retaining the source RGB colorspace."""
    if len(values)!=3:
        raise UnsupportedPaint('RGB paint requires exactly three components')
    if any(not 0<=float(v)<=1 for v in values):
        raise UnsupportedPaint('RGB components must be finite values in [0,1]')
    luminance=sum(float(v)*w for v,w in zip(values,(.299,.587,.114),strict=True))
    return ArrayObject([FloatObject(luminance)]*3)


def shading_gray(shading: DictionaryObject) -> None:
    """Mutate only real exponential RGB gradient endpoints."""
    if shading.get('/ColorSpace')=='/DeviceGray':
        return
    if shading.get('/ColorSpace')!='/DeviceRGB' or shading.get('/ShadingType') not in (2,3):
        raise UnsupportedPaint('Only DeviceRGB axial/radial shading is verified')
    function=shading['/Function']
    if function.get('/FunctionType')!=2 or '/C0' not in function or '/C1' not in function:
        raise UnsupportedPaint('Only explicit exponential gradient endpoints are verified')
    function[NameObject('/C0')]=gray_rgb(function['/C0'])
    function[NameObject('/C1')]=gray_rgb(function['/C1'])


def resources_gray(resources: DictionaryObject) -> None:
    """Visit direct and pattern shadings; reject unverified Form paint."""
    for value in resources.get('/Shading',{}).values():
        shading_gray(value.get_object())
    for value in resources.get('/Pattern',{}).values():
        pattern=value.get_object()
        if pattern.get('/PatternType')!=2:
            raise UnsupportedPaint('Tiling patterns require separate validation')
        shading_gray(pattern['/Shading'])
    for value in resources.get('/XObject',{}).values():
        form=value.get_object()
        if form.get('/Subtype')!='/Image' or form.get('/ColorSpace')!='/DeviceGray':
            raise UnsupportedPaint('Only existing DeviceGray image XObjects are verified')
        if '/SMask' in form and form['/SMask'].get('/ColorSpace')!='/DeviceGray':
            raise UnsupportedPaint('Only existing DeviceGray alpha masks are verified')


def prepare(source: Path, target: Path, expected_hash: str) -> None:
    """Write a new vector candidate; keep source, image bytes and paths intact."""
    if source.resolve()==target.resolve() or target.exists():
        raise UnsupportedPaint('Output must be a new file distinct from the source')
    data=source.read_bytes()
    if len(expected_hash)!=64 or sha256(data).hexdigest()!=expected_hash:
        raise UnsupportedPaint('Source SHA256 does not match the approved input')
    writer=PdfWriter(clone_from=PdfReader(BytesIO(data)))
    for page in writer.pages:
        resources_gray(page['/Resources'])
        stream=ContentStream(page.get_contents(),writer)
        for args,op in stream.operations:
            if op in (b'k',b'K',b'sc',b'SC'):
                raise UnsupportedPaint('Unverified color paint operator')
            if op in (b'scn',b'SCN') and (len(args)!=1 or not str(args[0]).startswith('/')):
                raise UnsupportedPaint('Only named pattern selections are verified')
            if op in (b'cs',b'CS') and args[0] not in ('/Pattern','/DeviceRGB','/DeviceGray'):
                raise UnsupportedPaint('Unverified content color space')
        stream.operations=[(list(gray_rgb(ArrayObject(args))),op) if op in (b'rg',b'RG') else (args,op) for args,op in stream.operations]
        page.replace_contents(stream)
    with target.open('xb') as output:
        writer.write(output)

if __name__=='__main__':
    if len(sys.argv)!=4:
        raise UnsupportedPaint('Usage: SOURCE.pdf OUTPUT.pdf SHA256')
    prepare(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
