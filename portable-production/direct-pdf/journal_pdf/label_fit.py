"""Category-label fitting: wrap first, tilt only when wrapping cannot help.

编辑口径（2026-10-27 由 A10 孙豪图3 的复核确立）：
  1. 能单行横排就单行横排；
  2. 单行放不下时先按分隔符拆行（西文在 `-`、`/`、空格处断，中文在字间断），
     仍横排——因为横排的阅读成本最低；
  3. 拆行也放不下才倾斜，且取能让宽度落回可用宽度的最小角度；
  4. 任何一步都不缩字号；缩字属于版面决策，由调用方显式改 policy。

本模块只做决策与实测记账，不画字、不改字号。
"""
from __future__ import annotations

import math

from .common import FigureError

# 西文可断分隔符：断在符号之后，符号随前一段，避免行首出现连字符。
WESTERN_BREAK_AFTER = "-－–—/／· 　"
# 中文断行禁则：这些字符不能出现在行首，断点落在它们之前会让断点后一行以它们开头。
CJK_NO_LINE_START = "，。、；：？！）〕］｝〉》」』】”’%‰"
CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(low <= code <= high for low, high in CJK_RANGES)


def _western_cuts(text: str) -> list[int]:
    """断点位置，从靠后往前的顺序返回：先保住前段的完整语义。"""
    cuts = [index + 1 for index, ch in enumerate(text[:-1]) if ch in WESTERN_BREAK_AFTER]
    return sorted(set(cuts), reverse=True)


def _cjk_cuts(text: str) -> list[int]:
    """汉字字间断点，按离中线的距离由近到远返回：先求均衡。"""
    middle = len(text) / 2
    cuts = []
    for index, ch in enumerate(text[:-1]):
        nxt = text[index + 1]
        if _is_cjk(ch) and _is_cjk(nxt) and nxt not in CJK_NO_LINE_START:
            cuts.append(index + 1)
    return sorted(set(cuts), key=lambda cut: (abs(cut - middle), -cut))


def _rotated_width(measured: dict, angle: float) -> float:
    """旋转后的水平投影宽度；用于判断倾斜能否落回可用宽度。"""
    if not angle:
        return measured["width"]
    radians = math.radians(angle)
    return abs(measured["width"] * math.cos(radians)) + abs(measured["height"] * math.sin(radians))


def plan(text: str, *, width_pt: float, measure, size: float,
         max_lines: int = 2, allow_angles=(0.0,)):
    """给出一个标签在 width_pt 内的排版方案。

    返回 {'lines', 'angle', 'reason', 'width_pt', 'height_pt'}；
    放不下时抛 label_does_not_fit，交回调用方改版面，不静默缩字。
    """
    if not isinstance(text, str) or not text.strip():
        raise FigureError("label_fit_text", "标签排版须给出非空文本")
    if isinstance(width_pt, bool) or not isinstance(width_pt, (int, float)) \
            or not math.isfinite(width_pt) or width_pt <= 0:
        raise FigureError("label_fit_width", "标签可用宽度须为有限正数", width_pt=width_pt)
    if not isinstance(max_lines, int) or max_lines < 1:
        raise FigureError("label_fit_max_lines", "标签最多行数须为不小于1的整数", max_lines=max_lines)
    angles = []
    for angle in allow_angles:
        if isinstance(angle, bool) or not isinstance(angle, (int, float)) \
                or not math.isfinite(angle) or not -90 <= angle <= 90:
            raise FigureError("label_fit_angle", "标签候选角度须在-90到90度之间", angle=angle)
        angles.append(float(angle))

    tolerance = 1e-6

    def record(lines, angle, reason):
        measured = measure("\n".join(lines), size)
        return {"lines": lines, "angle": angle, "reason": reason,
                "width_pt": measured["width"], "height_pt": measured["height"],
                "availability_pt": width_pt}

    single = measure(text, size)
    if single["width"] <= width_pt + tolerance:
        return record([text], 0.0, "single-line-horizontal-fits")

    if max_lines >= 2:
        for cut in _western_cuts(text):
            head, tail = text[:cut], text[cut:]
            if not tail.strip():
                continue
            if max(measure(head, size)["width"], measure(tail, size)["width"]) <= width_pt + tolerance:
                return record([head, tail], 0.0, "wrapped-two-lines-horizontal-fits")
        for cut in _cjk_cuts(text):
            head, tail = text[:cut], text[cut:]
            if max(measure(head, size)["width"], measure(tail, size)["width"]) <= width_pt + tolerance:
                return record([head, tail], 0.0, "wrapped-two-lines-horizontal-fits")

    for angle in sorted(a for a in angles if a):
        if _rotated_width(single, angle) <= width_pt + tolerance:
            measured = measure(text, size)
            return {"lines": [text], "angle": angle, "reason": f"tilted-{angle:g}-degrees-fits",
                    "width_pt": measured["width"], "height_pt": measured["height"],
                    "availability_pt": width_pt}

    raise FigureError("label_does_not_fit",
                      "标签在给可用宽度内既拆不开也倾不下，须调版面而不是缩字",
                      text=text, width_pt=width_pt, measured_width_pt=round(single["width"], 3),
                      max_lines=max_lines, allow_angles=angles)
