"""Deterministic figure routing. Ambiguous screenshots stay raster and are logged."""
from __future__ import annotations

from pathlib import Path

from .load import load_rules

_RASTER_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.tif', '.tiff', '.bmp'}
_STANDALONE = ('standalone-chart', '单图统计', '单独统计图')
_PAGE = ('webpage', '网页', '浏览器', 'citespace', '知识图谱', 'photo', '照片', '截图')


def route_source(name: str, hint: str | None = None) -> dict:
    """Return route, whether to redraw, and the reason that was logged."""
    text = f'{hint or ""} {Path(name).name}'.lower()
    if any(token in text for token in _STANDALONE):
        return {
            'route': 'screenshot-chart',
            'redraw': True,
            'reason': '单独一张统计图、且只有截图：裁出图区，文字改成矢量。网页整页截图不走这条。',
        }
    if any(token in text for token in _PAGE):
        return {
            'route': 'raster-only',
            'redraw': False,
            'reason': '网页、照片、CiteSpace 或未标明的截图只做灰度和栏宽内缩小，不重绘。',
        }
    suffix = Path(name).suffix.lower()
    if suffix in _RASTER_EXT:
        return {
            'route': 'raster-only',
            'redraw': False,
            'reason': '位图没有标明为单独统计图，不猜测重绘。',
        }
    if suffix == '.svg':
        return {'route': 'vector-diagram', 'redraw': True, 'reason': 'SVG 按矢量图处理。'}
    if suffix == '.pdf':
        return {'route': 'vector-diagram', 'redraw': False, 'reason': 'PDF 先原样接入，是否重绘另看任务记录。'}
    if suffix in {'.emf', '.wmf', '.docx', '.xlsx', '.xls'}:
        return {'route': 'vector-diagram', 'redraw': False, 'reason': '先转成 PDF，再按内容分类。'}
    return {'route': 'unknown', 'redraw': False, 'reason': '扩展名不在已知来源里。'}


def route_dense_chart(point_count: int, line_count: int, approved: bool = False, rules=None) -> dict:
    """A crowded chart becomes a bitmap plot plus vector text only after approval."""
    rules = rules or load_rules()
    normative = rules['normative']
    dense = point_count >= int(normative['dense_chart_point_threshold']) or line_count >= int(normative['dense_chart_line_threshold'])
    if not dense:
        return {'route': 'vector-chart', 'redraw': True, 'reason': '点数和线数都在矢量范围内。'}
    if approved is True:
        return {
            'route': 'bitmap-plot-vector-text',
            'redraw': True,
            'reason': '主人已批准：图面用位图，文字保持矢量。重绘的框和线用 0.5pt。',
        }
    return {
        'route': 'needs-owner-approval',
        'redraw': False,
        'approval_field': 'bitmap_plot_vector_text',
        'reason': '点或线过多。未在任务记录里批准 bitmap_plot_vector_text 之前，不改成位图图面。',
    }
