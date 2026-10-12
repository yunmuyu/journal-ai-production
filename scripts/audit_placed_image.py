"""Prove an opaque final image draw survives author aggregation unchanged."""
import copy
import json
import sys
from pathlib import Path
from PIL import ImageChops
from pypdf import PdfReader


def plain(value):
    value = value.get_object() if hasattr(value, 'get_object') else value
    if hasattr(value, 'get_data'):
        return value.get_data()
    if isinstance(value, list):
        return [plain(x) for x in value]
    return value


def audit(summary, source, placement):
    source_page = PdfReader(source).pages[0]
    reader = PdfReader(summary)
    page = reader.pages[placement['page'] - 1]
    if page.rotation or list(page.cropbox) != list(page.mediabox):
        return {'ok': False, 'reason': 'Rotated or cropped summary page'}
    resources = page['/Resources']
    objects = resources.get('/XObject', {})
    if len(objects) != 1 or len(page.images) != 1 or len(source_page.images) != 1:
        return {'ok': False, 'reason': 'Expected one direct image on the selected page'}
    name, ref = next(iter(objects.items()))
    obj = ref.get_object()
    if obj.get('/Subtype') != '/Image' or '/SMask' in obj or '/Mask' in obj or obj.get('/ImageMask'):
        return {'ok': False, 'reason': 'Masked or indirect image'}
    source_obj = next(iter(source_page['/Resources']['/XObject'].values())).get_object()
    for key in ['/ColorSpace', '/Decode', '/Interpolate', '/Intent']:
        if plain(obj.get(key)) != plain(source_obj.get(key)):
            return {'ok': False, 'reason': 'Image color or interpolation changed: '+key}
    config = reader.trailer['/Root'].get('/OCProperties', {}).get('/D', {})
    if config.get('/BaseState', '/ON') != '/ON' or config.get('/OFF'):
        return {'ok': False, 'reason': 'Optional content not fully visible'}
    state = {'matrix': [1., 0., 0., 1., 0., 0.], 'clipped': False, 'opaque': True}
    stack, found, draw = [], False, None
    painting = {b'Do', b'S', b's', b'f', b'F', b'f*', b'B', b'B*', b'b', b'b*', b'Tj', b'TJ', b"'", b'"', b'sh', b'BI'}
    for values, op in page.get_contents().operations:
        if found and op in painting:
            return {'ok': False, 'reason': 'Painting follows the selected image'}
        if op == b'q':
            stack.append(copy.deepcopy(state))
        elif op == b'Q':
            if not stack:
                return {'ok': False, 'reason': 'Unbalanced graphics state'}
            state = stack.pop()
        elif op == b'cm':
            a,b,c,d,e,f = map(float, values)
            A,B,C,D,E,F = state['matrix']
            state['matrix'] = [a*A+b*C,a*B+b*D,c*A+d*C,c*B+d*D,e*A+f*C+E,e*B+f*D+F]
        elif op in {b'W', b'W*'}:
            state['clipped'] = True
        elif op == b'gs':
            gs = resources['/ExtGState'][values[0]]
            if any(float(gs.get(key, 1)) != 1 for key in ['/ca','/CA']) or gs.get('/SMask','/None') != '/None' or gs.get('/BM','/Normal') != '/Normal' or any(key in gs for key in ['/TR','/TR2']):
                state['opaque'] = False
        elif op == b'Do':
            if values[0] != name or state['clipped'] or not state['opaque']:
                return {'ok': False, 'reason': 'Image has clipping, transparency or unknown placement'}
            found = True
            draw = state['matrix']
    if not found or stack:
        return {'ok': False, 'reason': 'Missing draw or unbalanced state'}
    a,b,c,d,x,y = draw
    left, top, right, bottom = placement['bounds']
    origin, board_top, _, board_bottom = placement['artboardRect']
    media_left, media_bottom = map(float, page.mediabox.lower_left)
    expected = [left-origin+media_left, bottom-board_bottom+media_bottom, right-origin+media_left, top-board_bottom+media_bottom]
    if a <= 0 or d <= 0 or abs(b)>1e-6 or abs(c)>1e-6 or any(abs(u-v)>.01 for u,v in zip([x,y,x+a,y+d],expected)):
        return {'ok': False, 'reason': 'Image position or dimensions differ'}
    actual = page.images[0].image.convert('RGB')
    original = source_page.images[0].image.convert('RGB')
    if actual.size != original.size or ImageChops.difference(actual,original).getbbox() is not None:
        return {'ok': False, 'reason': 'Embedded pixels changed'}
    return {'ok': True, 'method': 'identical_image_pixels_color_and_unclipped_opaque_final_draw', 'pixels': list(actual.size), 'page': placement['page'], 'bounds': expected, 'requiresVisualReadabilityReview': True}


if __name__ == '__main__':
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
    result = audit(request['pdf'],request['source'],request['placement'])
    print(json.dumps(result,ensure_ascii=False))
    sys.exit(0 if result['ok'] else 2)
