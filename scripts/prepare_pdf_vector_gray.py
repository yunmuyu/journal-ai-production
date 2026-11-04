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
from tempfile import TemporaryDirectory
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


def content_gray(stream: ContentStream) -> None:
    """Convert verified RGB paint while preserving every geometric operator."""
    for args,op in stream.operations:
        if op in (b'k',b'K',b'sc',b'SC'):
            raise UnsupportedPaint('Unverified color paint operator')
        if op in (b'scn',b'SCN') and (len(args)!=1 or not str(args[0]).startswith('/')):
            raise UnsupportedPaint('Only named pattern selections are verified')
        if op in (b'cs',b'CS') and args[0] not in ('/Pattern','/DeviceRGB','/DeviceGray'):
            raise UnsupportedPaint('Unverified content color space')
    stream.operations=[(list(gray_rgb(ArrayObject(args))),op) if op in (b'rg',b'RG') else (args,op) for args,op in stream.operations]


def resources_gray(resources: DictionaryObject, writer: PdfWriter, visited: set[int]) -> None:
    """Visit shared Form streams and shadings without flattening source paths."""
    for value in resources.get('/Shading',{}).values():
        shading_gray(value.get_object())
    for value in resources.get('/Pattern',{}).values():
        pattern=value.get_object()
        if pattern.get('/PatternType')!=2:
            raise UnsupportedPaint('Tiling patterns require separate validation')
        shading_gray(pattern['/Shading'])
    for value in resources.get('/XObject',{}).values():
        form=value.get_object()
        if id(form) in visited:
            continue
        visited.add(id(form))
        if form.get('/Subtype')=='/Form':
            resources_gray(form.get('/Resources',DictionaryObject()),writer,visited)
            stream=ContentStream(form,writer)
            content_gray(stream)
            form.set_data(stream.get_data())
            continue
        if form.get('/Subtype')!='/Image' or form.get('/ColorSpace')!='/DeviceGray':
            raise UnsupportedPaint('Only existing DeviceGray image XObjects are verified')
        if '/SMask' in form and form['/SMask'].get('/ColorSpace')!='/DeviceGray':
            raise UnsupportedPaint('Only existing DeviceGray alpha masks are verified')


def prepare_device_alias_gray(source: Path, target: Path, expected_hash: str) -> None:
    """Reuse the existing stateful normalizer only for a narrow, verified device-alias page."""
    from normalize_svg_color import inspect_pdf
    reader=PdfReader(source)
    if len(reader.pages)!=1:raise UnsupportedPaint('Device alias fallback requires one page')
    page=reader.pages[0];resources=page['/Resources']
    if any(resources.get(k) for k in ('/XObject','/Pattern','/Shading')):
        raise UnsupportedPaint('Device alias fallback requires pure vectors without XObjects or patterns')
    stream=ContentStream(page.get_contents(),reader);aliases=resources.get('/ColorSpace',{});seen_alias=False
    for args,op in stream.operations:
        if op in (b'k',b'K'):raise UnsupportedPaint('CMYK is not supported by this entry')
        if op in (b'cs',b'CS'):
            if len(args)!=1:raise UnsupportedPaint('Color space selector requires one name')
            name=args[0]
            if name in ('/DeviceRGB','/DeviceGray'):continue
            value=aliases.get(name)
            if value is None:raise UnsupportedPaint('Unresolved color space alias')
            value=value.get_object()
            if value not in ('/DeviceRGB','/DeviceGray'):raise UnsupportedPaint('Only direct device aliases are supported')
            seen_alias=True
    if not seen_alias:raise UnsupportedPaint('No verified device alias')
    with TemporaryDirectory(prefix='jfw-alias-gray-',dir=target.parent) as folder:
        temporary=Path(folder)/'normalized.pdf'
        proof=inspect_pdf(source,temporary,True)
        if not proof.get('geometryPreserved') or proof.get('geometryHashBefore')!=proof.get('geometryHashAfter'):
            raise UnsupportedPaint('Alias normalization did not preserve geometry')
        if sha256(source.read_bytes()).hexdigest()!=expected_hash:raise UnsupportedPaint('Source changed during normalization')
        with target.open('xb') as output:output.write(temporary.read_bytes())


def prepare(source: Path, target: Path, expected_hash: str) -> None:
    """Write a new vector candidate; keep source, image bytes and paths intact."""
    if source.resolve()==target.resolve() or target.exists():
        raise UnsupportedPaint('Output must be a new file distinct from the source')
    data=source.read_bytes()
    if len(expected_hash)!=64 or sha256(data).hexdigest()!=expected_hash:
        raise UnsupportedPaint('Source SHA256 does not match the approved input')
    writer=PdfWriter(clone_from=PdfReader(BytesIO(data)))
    visited: set[int]=set()
    try:
        for page in writer.pages:
            resources_gray(page['/Resources'],writer,visited)
            stream=ContentStream(page.get_contents(),writer)
            content_gray(stream)
            page.replace_contents(stream)
    except UnsupportedPaint as error:
        if str(error)!='Unverified content color space':raise
        prepare_device_alias_gray(source,target,expected_hash)
        return
    with target.open('xb') as output:
        writer.write(output)

if __name__=='__main__':
    if len(sys.argv)!=4:
        raise UnsupportedPaint('Usage: SOURCE.pdf OUTPUT.pdf SHA256')
    prepare(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
