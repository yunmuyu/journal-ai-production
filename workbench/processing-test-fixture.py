"""Synthetic real-render fixtures for the JavaScript publication boundary tests."""
import json
import sys
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw
from journal_pdf.assets import Assets
from journal_pdf.common import digest_file
from journal_pdf.fonts import FontRegistry
from journal_pdf.render import render_one


root, operation, profile = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
source_root = root / 'source'
source_root.mkdir(parents=True, exist_ok=True)
spec = {'version': 1, 'id': 'proof', 'author': 'fixture', 'kind': 'scene',
        'width_pt': 210, 'height_pt': 150,
        'policy': {'column': 'single', 'design_font_size_pt': 8, 'export_crop_padding_pt': 4}}
if operation == 'vector-reletter':
    source = source_root / 'original.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=180, height=120)
        page.draw_line((10, 80), (170, 80), width=.5)
        page.insert_text((20, 30), 'R1', fontsize=9)
        span = page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        doc.save(source)
    spec['assets'] = [{'id': 'body', 'path': str(source), 'source_kind': 'pdf', 'source_vector_body': True,
                       'clip': [0, 0, 180, 120], 'target': [5, 5, 185, 125],
                       'text_replacements': [{'source_text': 'R1', 'source_bbox': list(span['bbox']), 'target_text_id': 'label'}]}]
    spec['texts'] = [{'id': 'label', 'text': 'R1', 'x': 30, 'y': 30}]
else:
    source = source_root / 'original.png'
    image = Image.new('RGB', (600, 400), 'white')
    draw = ImageDraw.Draw(image)
    draw.line([(30, 20), (30, 350), (560, 350)], fill='black', width=2)
    draw.line([(30, 300), (170, 240), (560, 300)], fill='black', width=2)
    draw.text((350, 45), 'R1', fill='black')
    draw.line((290, 50, 330, 50), fill='black', width=2)
    image.save(source)
    if operation == 'raster-reletter':
        spec['assets'] = [{'id': 'body', 'path': str(source), 'source_kind': 'raster',
                           'clip': [0, 0, 600, 400], 'target': [5, 5, 205, 5+400/3],
                           'masks': [[345, 40, 380, 65]], 'approved_empty_regions': [[340, 35, 390, 70]],
                           'text_replacements': [{'source_text': 'R1', 'source_bbox': [345, 40, 380, 65], 'target_text_id': 'label'}]}]
        spec['texts'] = [{'id': 'label', 'text': 'R1', 'x': 126, 'y': 22}]
    else:
        spec.update({'kind': 'chart', 'source_kind': 'raster', 'source': str(source),
                     'plot_clip': [28, 18, 564, 354], 'axis_frame_source': [30, 20, 560, 350],
                     'plot_width_pt': 180, 'tick_length_source_units': 0,
                     'masks': [[280, 35, 390, 70]], 'approved_empty_regions': [[270, 30, 540, 190]],
                     'legend_safe_region': [270, 30, 540, 190], 'legend_placement': 'source-region',
                     'legend_frame': False, 'x_title': 't(s)', 'y_title': 'U(V)',
                     'x_ticks': [{'text': '0', 'position': 30}, {'text': '1', 'position': 560}],
                     'y_ticks': [{'text': '0', 'position': 350}, {'text': '1', 'position': 20}],
                     'series': [{'id': 's', 'label': 'R1', 'swatch_clip': [290, 49, 331, 53]}]})
spec['sources'] = [{'path': str(source), 'sha256': digest_file(source)}]
assets = Assets()
reg = FontRegistry(profile, root / 'font-cache')
try:
    report = render_one(spec, reg, assets, source_root, root / 'output')
    print(json.dumps({'source': spec['sources'][0], 'report': report}, ensure_ascii=False))
finally:
    assets.close()
    reg.close()
