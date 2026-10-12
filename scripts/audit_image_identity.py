"""Verify one unmasked, opaque, full-page PDF image against its prepared pixels."""
import json
import sys
from PIL import Image, ImageChops
from pypdf import PdfReader


def audit(pdf_path, image_path):
    reader = PdfReader(pdf_path)
    if len(reader.pages) != 1:
        return {'ok': False, 'reason': 'Expected one page'}
    page = reader.pages[0]
    if page.rotation or list(page.cropbox) != list(page.mediabox):
        return {'ok': False, 'reason': 'Rotated or cropped page'}
    resources = page['/Resources']
    objects = resources.get('/XObject', {})
    if len(objects) != 1 or len(page.images) != 1:
        return {'ok': False, 'reason': 'Expected one direct image'}
    name, obj_ref = next(iter(objects.items()))
    obj = obj_ref.get_object()
    if obj.get('/Subtype') != '/Image' or '/SMask' in obj or '/Mask' in obj or obj.get('/ImageMask'):
        return {'ok': False, 'reason': 'Image masks or form objects are outside this proof'}
    config = reader.trailer['/Root'].get('/OCProperties', {}).get('/D', {})
    if config.get('/BaseState', '/ON') != '/ON' or config.get('/OFF'):
        return {'ok': False, 'reason': 'Optional-content visibility is not fully on'}
    operations = page.get_contents().operations
    allowed = {b'BDC', b'EMC', b'q', b'Q', b'gs', b'ri', b'cm', b'Do'}
    if any(operator not in allowed for _, operator in operations):
        return {'ok': False, 'reason': 'Extra painting, clipping or unsupported operators'}
    matrices = [(i, values) for i, (values, op) in enumerate(operations) if op == b'cm']
    draws = [(i, values) for i, (values, op) in enumerate(operations) if op == b'Do']
    if len(matrices) != 1 or len(draws) != 1 or matrices[0][0] >= draws[0][0] or draws[0][1][0] != name:
        return {'ok': False, 'reason': 'Image transform is not a single direct placement'}
    if any(op in {b'q', b'Q'} for _, op in operations[matrices[0][0] + 1:draws[0][0]]):
        return {'ok': False, 'reason': 'Transform scope changed before drawing'}
    for values, operator in operations:
        if operator == b'gs':
            state = resources['/ExtGState'][values[0]]
            if float(state.get('/ca', 1)) != 1 or float(state.get('/CA', 1)) != 1 or state.get('/SMask', '/None') != '/None' or state.get('/BM', '/Normal') != '/Normal' or any(k in state for k in ['/TR', '/TR2']):
                return {'ok': False, 'reason': 'Image is transparent or color-modified'}
    a, b, c, d, x, y = map(float, matrices[0][1])
    box = list(map(float, page.mediabox))
    if a <= 0 or d <= 0 or abs(b) > 1e-6 or abs(c) > 1e-6 or any(abs(u-v) > .01 for u, v in zip([x, y, x+a, y+d], box)):
        return {'ok': False, 'reason': 'Image does not cover the page exactly'}
    with Image.open(image_path) as source:
        if 'A' in source.getbands() and source.getchannel('A').getextrema() != (255, 255):
            return {'ok': False, 'reason': 'Prepared source has transparency'}
        expected = source.convert('RGB')
    actual = page.images[0].image.convert('RGB')
    match = expected.size == actual.size and ImageChops.difference(expected, actual).getbbox() is None
    if not match:
        return {'ok': False, 'reason': 'Embedded pixels differ from prepared source'}
    if abs((a/d)/(expected.width/expected.height)-1) > 1e-5:
        return {'ok': False, 'reason': 'Image aspect ratio changed'}
    return {'ok': True, 'method': 'exact_rgb_pixels_and_full_page_opaque_transform', 'pixels': list(expected.size), 'widthMm': a*25.4/72, 'heightMm': d*25.4/72, 'requiresVisualReadabilityReview': True}


if __name__ == '__main__':
    result = audit(*sys.argv[1:3])
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result['ok'] else 2)
