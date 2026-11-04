"""Source-bound numeric annotations anchored to original PDF marker geometry."""
from __future__ import annotations

from dataclasses import dataclass

import pymupdf as fitz

from .assets import svg_root, element
from .common import FigureError, digest_file, resolve_source
from .editorial import LABEL_CLEARANCE, group_number
from .scene import Scene


@dataclass(frozen=True, slots=True)
class NumericAnnotation:
    id: str
    text: str
    marker_right: float
    marker_bottom: float


def source_annotations(spec, root) -> tuple[NumericAnnotation, ...]:
    rows = spec.get('source_annotations', [])
    if not isinstance(rows, list) or len(rows) > 200:
        raise FigureError('chart_annotation_binding', '标注须为不超过200项的源绑定列表')
    if not rows:
        return ()
    if spec.get('source_kind') != 'svg':
        raise FigureError('chart_annotation_source', '数值标注须绑定矢量SVG及其父PDF')
    svg = svg_root(resolve_source(root, spec['source']))
    output = []
    used = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'] or row.get('placement') != 'lower-right' or row.get('id') in used or any(type(row.get(k)) is not int or row[k] < 0 for k in ('source_span_index', 'source_marker_index')):
            raise FigureError('chart_annotation_binding', '数值标注须唯一并明确采用点的右下方')
        path = resolve_source(root, row['source_pdf'])
        if digest_file(path) != row['source_pdf_sha256'] or not any(s['path'] == row['source_pdf'] and s['sha256'] == row['source_pdf_sha256'] for s in spec['sources']):
            raise FigureError('chart_annotation_binding', '父PDF须纳入冻结来源且哈希一致')
        with fitz.open(path) as document:
            page = document[row.get('page', 0)]
            spans = [s for b in page.get_text('dict')['blocks'] if b['type'] == 0
                     for line in b['lines'] for s in line['spans'] if s['text'].strip()]
            drawings = page.get_drawings()
            if row['source_span_index'] >= len(spans) or row['source_marker_index'] >= len(drawings):
                raise FigureError('chart_annotation_binding', '源文字或圆点索引越界')
            span = spans[row['source_span_index']]
            drawing = drawings[row['source_marker_index']]
            rect = drawing['rect']
            if drawing['type'] not in ('f', 'fs') or len(drawing['items']) != 4 or any(item[0] != 'c' for item in drawing['items']) or abs(rect.width - rect.height) > .1 or rect.width <= 0:
                raise FigureError('chart_annotation_marker', '标注锚点须为原PDF明确的圆点路径')
            text = span['text'].strip()
            group_number(text)
            original = ''.join(element(svg, row['source_text_group']).itertext()).strip()
            if original != text or abs((span['bbox'][0] + span['bbox'][2] - rect.x0 - rect.x1) / 2) > rect.width:
                raise FigureError('chart_annotation_binding', 'SVG原标注或原PDF圆点对应关系不符')
            output.append(NumericAnnotation(row['id'], text, rect.x1, rect.y1))
            used.add(row['id'])
    return tuple(output)


def place_source_annotations(scene: Scene, rows: tuple[NumericAnnotation, ...], clip, scale: float, x: float, y: float) -> float:
    right = x
    for row in rows:
        text = group_number(row.text)
        measured = scene.registry.measure(text, scene.size, role='numeric-value')
        tx = x + (row.marker_right - clip[0]) * scale + LABEL_CLEARANCE + measured['width'] / 2
        ty = y + (row.marker_bottom - clip[1]) * scale + LABEL_CLEARANCE + measured['height'] / 2
        item = scene.text(row.id, row.text, tx, ty, role='numeric-value')
        right = max(right, item['position']['bbox'][2])
    return right
