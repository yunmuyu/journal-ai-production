"""Deterministic figure routing. Ambiguous screenshots stay raster and are logged."""
from __future__ import annotations

from pathlib import Path

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
