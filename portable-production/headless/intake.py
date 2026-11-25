"""Turn source files into a PDF copy without editing the originals."""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

_SOURCE = {'.png', '.jpg', '.jpeg', '.pdf', '.svg', '.docx', '.xlsx', '.emf', '.wmf'}
_NUMBER = re.compile(r'图([1-9]\d*(?:\.[1-9]\d*)?)')


def discover(root: Path, job: dict) -> list[dict]:
    declared = job.get('figures') or {}
    found = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in _SOURCE:
            continue
        if '.headless-work' in path.parts or path.name == 'produce-report.json':
            continue
        author = path.parent.name if path.parent.resolve() != root.resolve() else (job.get('author') or '未署名')
        match = _NUMBER.search(path.stem)
        number = match.group(1) if match else '1'
        ident = f'{author}-图{number}'
        override = declared.get(ident) or declared.get(path.name) or {}
        if override.get('number'):
            number = str(override['number'])
        if override.get('author'):
            author = override['author']
        found.append({
            'id': f'{author}-图{number}',
            'author': author,
            'number': str(number),
            'path': str(path.resolve()),
        })
    return found


def convert_to_pdf(source: Path, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / 'source.pdf'
    if destination.exists():
        raise FileExistsError(destination)
    suffix = source.suffix.lower()
    if suffix == '.pdf':
        shutil.copyfile(source, destination)
        return destination
    if suffix in {'.png', '.jpg', '.jpeg'}:
        _image_pdf(source, destination)
        return destination
    if suffix == '.svg':
        _svg_pdf(source, destination, folder)
        return destination
    if suffix == '.docx':
        _office_image_pdf(source, destination, folder, 'word/media/')
        return destination
    if suffix in {'.xlsx', '.xls'}:
        _office_image_pdf(source, destination, folder, 'xl/media/')
        return destination
    raise RuntimeError(f'尚未接入的来源转换：{suffix}。EMF/WMF 需要本机 Inkscape 或 LibreOffice，本环境不假装已经转成。')


def _image_pdf(source: Path, destination: Path) -> None:
    import pymupdf as fitz
    from PIL import Image
    with Image.open(source) as image:
        gray = image.convert('L')
        buffer = folder_bytes(gray)
        width, height = gray.size
    document = fitz.open()
    page = document.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=buffer)
    document.save(destination)
    document.close()


def folder_bytes(image) -> bytes:
    import io
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _svg_pdf(source: Path, destination: Path, folder: Path) -> None:
    import base64
    import re
    text = source.read_text(encoding='utf-8')
    images = []
    for index, match in enumerate(re.finditer(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)', text)):
        raw = base64.b64decode(re.sub(r'\s+', '', match.group(2)))
        image_path = folder / f'embedded-{index}.png'
        image_path.write_bytes(raw)
        images.append(image_path)
    try:
        import cairosvg
        cairosvg.svg2pdf(url=str(source), write_to=str(destination), unsafe=False)
    except Exception as error:
        if not images:
            raise RuntimeError('SVG 转 PDF 需要 CairoSVG；没有内嵌图可单独抽出。' + str(error)) from error
        _image_pdf(images[0], destination)
        (folder / 'svg-convert.txt').write_text('cairo-unavailable; extracted embedded image only\n', encoding='utf-8')


def _office_image_pdf(source: Path, destination: Path, folder: Path, prefix: str) -> None:
    with zipfile.ZipFile(source) as package:
        names = [name for name in package.namelist() if name.startswith(prefix) and not name.endswith('/')]
        if not names:
            raise RuntimeError('文档里没有可抽出的图片')
        blob = package.read(names[0])
    image = folder / 'office-image.bin'
    image.write_bytes(blob)
    _image_pdf(image, destination)
