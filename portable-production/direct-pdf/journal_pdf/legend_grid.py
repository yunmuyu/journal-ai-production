"""Pack original legend entries in reading order using measured ink widths."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

from .common import FigureError


@dataclass(frozen=True, slots=True)
class LegendGrid:
    columns: int
    rows: int
    width: float
    offsets: tuple[float, ...]


def pack_legend_columns(widths: Sequence[float], available: float, *, gap: float) -> LegendGrid:
    if not widths or not all(math.isfinite(v) and v >= 0 for v in widths):
        raise FigureError('legend_grid_width', '图例须提供非负有限实测宽度')
    if not math.isfinite(available) or available <= 0 or not math.isfinite(gap) or gap < 0:
        raise FigureError('legend_grid_capacity', '图例可用宽度和列距无效')
    for columns in range(len(widths), 0, -1):
        column_widths = [max(widths[col::columns]) for col in range(columns)]
        total = sum(column_widths) + gap * (columns - 1)
        if total <= available or columns == 1:
            offsets = tuple(sum(column_widths[:col]) + gap * col for col in range(columns))
            return LegendGrid(columns, math.ceil(len(widths) / columns), total, offsets)
    raise FigureError('legend_grid_capacity', '无法排布原图例')
