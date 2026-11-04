"""Measured labels shared by scene boxes and automatic placement."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .common import FigureError
from .editorial import PAD_X, PAD_Y, display_content, wrap_text

if TYPE_CHECKING:
    from .fonts import FontRegistry


def layout_label(registry: FontRegistry, content: str, size: float, *, role: str = 'label',
                 wrap_chars: int | None = None, wrap_width_pt: float | None = None) -> str:
    """Wrap semantic words before measuring; width uses design points at 8 pt."""
    display = display_content(content, role)
    if wrap_width_pt is not None:
        if wrap_chars is not None:
            raise FigureError('label_wrap_conflict', '字符限宽与实测限宽不能同时指定')
        if isinstance(wrap_width_pt, bool) or not math.isfinite(wrap_width_pt) or wrap_width_pt <= 0:
            raise FigureError('label_wrap_width', '实测限宽须为正的有限点数')
        from .chinese_wrap import wrap_measured
        return wrap_measured(display, wrap_width_pt * size / 8,
                             lambda text: registry.measure(text, size, role=role)['width'])
    return wrap_text(display, wrap_chars) if wrap_chars is not None else display


def ellipse_size(ink_width: float, ink_height: float, *, padx: float = PAD_X,
                 pady: float = PAD_Y) -> tuple[float, float]:
    """Contain the padded ink rectangle analytically, without iterative widening."""
    values = (ink_width, ink_height, padx, pady)
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise FigureError('ellipse_measurement', '椭圆须使用非负有限墨迹尺寸与留白')
    return math.sqrt(2) * (ink_width + 2 * padx), math.sqrt(2) * (ink_height + 2 * pady)
