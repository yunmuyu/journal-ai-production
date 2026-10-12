"""Render the PDF itself and detect image loss relative to the native preview."""
from pathlib import Path
import json
import sys
from PIL import Image, ImageChops, ImageFilter
from pypdf import PdfReader
import pypdfium2 as pdfium

def native_grid(rendered: Image.Image, expected_size: tuple[int, int]) -> Image.Image:
    """Keep 300-dpi pixels intact when page-edge rounding differs by at most two pixels."""
    if all(abs(actual - expected) <= 2 for actual, expected in zip(rendered.size, expected_size, strict=True)):
        aligned = Image.new('L', expected_size, 255)
        aligned.paste(rendered, (0, 0))
        return aligned
    return rendered.resize(expected_size)

def audit(pdf_path: str, native_path: str, preview_path: str) -> dict[str, int | float | bool | str]:
    reader = PdfReader(pdf_path)
    invisible = 0
    images = reader.pages[0].images
    for image in images:
        alpha = image.image.getchannel('A') if 'A' in image.image.getbands() else None
        if alpha is not None and alpha.getextrema()[1] == 0:
            invisible += 1
    pdf = pdfium.PdfDocument(pdf_path)
    page = pdf[0]
    rendered = page.render(scale=300 / 72).to_pil().convert('RGB')
    rendered.save(preview_path)
    with Image.open(native_path) as native:
        expected = native.convert('L')
    actual = native_grid(rendered.convert('L'), expected.size)
    expected_ink = expected.point(lambda value: 255 if value < 160 else 0)
    actual_ink = actual.point(lambda value: 255 if value < 160 else 0)
    covered = ImageChops.multiply(expected_ink, actual_ink.filter(ImageFilter.MaxFilter(5)))
    total = sum(expected_ink.histogram()[1:])
    matched = sum(covered.histogram()[1:])
    recall = matched / total if total else 1.0
    page.close()
    pdf.close()
    return {'ok': invisible == 0 and recall >= 0.94, 'invisibleImages': invisible,
            'nativeInkRecall': recall, 'pdfPreview': preview_path, 'imageCount': len(images)}

if __name__ == '__main__':
    result = audit(*sys.argv[1:4])
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result['ok'] else 2)
