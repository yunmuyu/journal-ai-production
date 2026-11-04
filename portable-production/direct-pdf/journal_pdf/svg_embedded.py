"""Bounded, opt-in decoding of raster data URIs. Never fetch external resources."""
import base64
import io
import re
from PIL import Image
from .common import FigureError

MAX_BYTES = 16 * 1024 * 1024
MAX_PIXELS = 40_000_000

def embedded_image(value):
    match = re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)', value)
    if not match or len(match[2]) > MAX_BYTES * 4 // 3 + 4096:
        raise FigureError('svg_embedded_image', '仅接受有大小上限的内嵌PNG/JPEG')
    try:
        raw = base64.b64decode(re.sub(r'\s+', '', match[2]), validate=True)
        if len(raw) > MAX_BYTES:
            raise ValueError('encoded image too large')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != {'png':'PNG','jpeg':'JPEG'}[match[1]] or image.width * image.height > MAX_PIXELS:
                raise ValueError('image format or pixel limit')
            image.verify()
        return raw
    except Exception as error:
        raise FigureError('svg_embedded_image', '内嵌图格式、内容或尺寸校验失败') from error

def gray_data_uri(value):
    raw = embedded_image(value)
    with Image.open(io.BytesIO(raw)) as source:
        rgba = source.convert('RGBA')
        gray = rgba.convert('L')
        result = Image.merge('RGBA', (gray, gray, gray, rgba.getchannel('A')))
        output = io.BytesIO()
        result.save(output, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
