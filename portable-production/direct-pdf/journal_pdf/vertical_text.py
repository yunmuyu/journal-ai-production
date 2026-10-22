from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .common import FigureError

if TYPE_CHECKING:
    from .fonts import FontRegistry


def measure_vertical(registry: FontRegistry, text: str, size: float) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise FigureError('vertical_text', '竖排需要非空文字')
    tokens = re.findall(r'[A-Za-z0-9_./+-]+|[^\s]', text)
    pieces = []
    for token in tokens:
        measured = registry.measure(token, size, role='literal')
        turn = 270 if re.fullmatch(r'[A-Za-z0-9_./+-]+', token) else 0
        x0, y0, x1, y1 = measured['ink']
        ink = [-y1, x0, -y0, x1] if turn else [x0, y0, x1, y1]
        advance = max(size, ink[3]-ink[1])
        pieces.append((measured, turn, ink, advance))
    width = max(p[2][2]-p[2][0] for p in pieces)
    glyphs = []
    cursor = 0.
    for measured, turn, ink, advance in pieces:
        dx = width/2-(ink[0]+ink[2])/2
        dy = cursor+(advance-(ink[3]-ink[1]))/2-ink[1]
        for original in measured['glyphs']:
            glyph = dict(original)
            x, y = original['x'], original['y']
            b = original['ink']
            glyph['x'], glyph['y'] = (dx-y, dy+x) if turn else (dx+x, dy+y)
            glyph['ink'] = ([dx-b[3], dy+b[0], dx-b[1], dy+b[2]] if turn
                            else [dx+b[0], dy+b[1], dx+b[2], dy+b[3]])
            glyph['rotation'] = turn
            glyph['line'] = len(glyphs)
            glyphs.append(glyph)
        cursor += advance
    boxes = [g['ink'] for g in glyphs if not g['ch'].isspace()]
    bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]
    return {'text': text, 'glyphs': glyphs, 'ink': bbox,
            'width': bbox[2]-bbox[0], 'height': bbox[3]-bbox[1], 'size': size}
