"""Generate horizontal bands and content-bound regions before drawing."""
from collections.abc import Sequence
import math
from .common import FigureError
from .editorial import ARROW_LENGTH


def horizontal_band(widths: Sequence[float], *, origin: float,
                    minimum_gap: float = 6, arrow_channels: bool = False) -> list[float]:
    if not widths or any(not math.isfinite(w) or w <= 0 for w in widths):
        raise FigureError('region_band_width','横向布局须提供真实测量宽度')
    if not math.isfinite(origin) or not math.isfinite(minimum_gap) or minimum_gap < 3:
        raise FigureError('region_band_gap','横向净距必须为有限值且不小于3pt')
    # Both strokes consume half a point outside the declared region bounds.
    gap=max(minimum_gap,ARROW_LENGTH if arrow_channels else 0)+.5
    starts=[];cursor=origin
    for width in widths:
        starts.append(cursor);cursor+=width+gap
    return starts


def content_region(rectangles: Sequence[Sequence[float]], *, padding: float = 6,
                   title_height: float = 0) -> list[float]:
    if not rectangles or not math.isfinite(padding) or padding < 3 or not math.isfinite(title_height) or title_height<0:
        raise FigureError('region_members','区域须有明确内容、留白及标题高度')
    if any(len(r)!=4 or any(not math.isfinite(v) for v in r) or r[2]<=r[0] or r[3]<=r[1] for r in rectangles):
        raise FigureError('region_members','区域成员边界无效')
    inset=padding+.25
    return [min(r[0] for r in rectangles)-inset,
            min(r[1] for r in rectangles)-inset-title_height,
            max(r[2] for r in rectangles)+inset,
            max(r[3] for r in rectangles)+inset]


def align_region_bottoms(regions: Sequence[list[float]]) -> None:
    if not regions:raise FigureError('region_alignment','缺少需要对齐的区域')
    bottom=max(r[3] for r in regions)
    for rect in regions:rect[3]=bottom
