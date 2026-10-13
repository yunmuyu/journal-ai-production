"""Measure the visible ink in an exported preview without altering image content."""
import json
import sys
from PIL import Image

with Image.open(sys.argv[1]) as image:
    mask = image.convert('L').point(lambda value: 255 if value < 245 else 0)
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError('Cannot trim a blank figure')
    print(json.dumps({'pixels':list(bounds),'size':list(image.size)}))
