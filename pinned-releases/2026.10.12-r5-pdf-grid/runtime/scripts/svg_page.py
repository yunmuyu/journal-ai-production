import base64
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
source, output = map(Path, sys.argv[1:3])
data = source.read_bytes()
root = ET.fromstring(data)
if root.tag.split('}')[-1] != 'svg':
    raise ValueError('Input is not SVG')
for element in root.iter():
    for key, value in element.attrib.items():
        if key.split('}')[-1] == 'href' and not value.startswith(('#', 'data:')):
            raise ValueError('SVG external dependency requires a packaged local asset: ' + value)
view = [float(x) for x in root.get('viewBox', '').replace(',', ' ').split()]
def pixels(value, fallback):
    match = re.fullmatch(r'([0-9.]+)(px|pt|mm|cm|in)?', value.strip())
    if not match:
        if fallback is None:
            raise ValueError('SVG physical size/viewBox must be resolved')
        return fallback
    return float(match[1]) * {'px': 1, 'pt': 96/72, 'mm': 96/25.4, 'cm': 96/2.54, 'in': 96, None: 1}[match[2]]
w = pixels(root.get('width', ''), view[2] if len(view) == 4 else None)
h = pixels(root.get('height', ''), view[3] if len(view) == 4 else None)
if not 0 < w <= 20000 or not 0 < h <= 20000:
    raise ValueError('SVG dimensions outside supported range')
encoded = base64.b64encode(data).decode('ascii')
html = f'<!doctype html><meta charset="utf-8"><style>@page{{size:{w/96*25.4}mm {h/96*25.4}mm;margin:0}}html,body{{margin:0;padding:0;width:{w}px;height:{h}px}}img{{display:block;width:{w}px;height:{h}px}}</style><img src="data:image/svg+xml;base64,{encoded}">'
output.write_text(html, encoding='utf-8')
output.with_suffix('.json').write_text(json.dumps({'widthPx': w, 'heightPx': h, 'widthMm': w/96*25.4, 'heightMm': h/96*25.4}), encoding='utf-8')
