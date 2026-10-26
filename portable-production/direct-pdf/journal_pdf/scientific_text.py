"""Explicit scientific notation for the public rich-text measurement pipeline.

These helpers consume known mathematical semantics; they do not infer exponents
from arbitrary source labels or change chart data. Base labels retain the normal
6–8 pt policy. A reduced mathematical script is not a reduced base label.
"""
from __future__ import annotations

import math

from .common import FigureError


def power_of_ten(
    exponent: int, base_size_pt: float = 8.0, exponent_scale: float = 0.7
) -> list[dict]:
    """Return upright ``10`` and a genuinely smaller, raised integer exponent.

    Pass the returned runs to ``Scene.text`` with ``role='axis-tick'`` and the
    same ``size=base_size_pt`` (or a scene with that size). The default is an
    8 pt base and a 5.6 pt exponent, raised 3.2 pt. The existing public font
    registry performs all measurement, embedding and drawing. Negative powers
    use ASCII U+002D for unary negative signs per the editorial contract.
    U+2212 is reserved for binary subtraction; scripts remain real raised text.

    This explicit mathematical script may be below 6 pt; it does not change
    the ordinary-text minimum or silently shrink an entire label to 6 pt.
    """
    if isinstance(exponent, bool) or not isinstance(exponent, int):
        raise FigureError('scientific_exponent_invalid', '十的幂指数必须为整数')
    if (
        isinstance(base_size_pt, bool)
        or not isinstance(base_size_pt, (int, float))
        or not math.isfinite(base_size_pt)
        or not 6 <= base_size_pt <= 8
    ):
        raise FigureError('font_size_out_of_policy', '底数字号必须在6—8pt之间')
    if (
        isinstance(exponent_scale, bool)
        or not isinstance(exponent_scale, (int, float))
        or not math.isfinite(exponent_scale)
        or not 0 < exponent_scale < 1
    ):
        raise FigureError('scientific_exponent_scale_invalid', '数学上标比例必须大于0且小于1')
    exponent_text = ('-' if exponent < 0 else '') + str(abs(exponent))
    return [
        {'text': '10', 'style': 'regular'},
        {
            'text': exponent_text,
            'style': 'regular',
            'scale': float(exponent_scale),
            'baseline_shift_pt': -0.4 * base_size_pt,
        },
    ]
