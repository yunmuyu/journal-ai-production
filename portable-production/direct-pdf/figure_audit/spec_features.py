"""Advisory label and legend extraction."""
from __future__ import annotations
from .spec_core import Axes, Span, spans, filled_rects
from .spec_axes import _NUMONLY, _is_title_text

def category_labels(page, frame: Axes, sp: list["Span"] | None = None) -> list["Span"]:
    """横轴下方的类目名（非数字标签），取最靠轴的那一行。

    图6 的「上下文精确率／上下文召回率／回答准确率」就是这一类。
    必须与轴标题区分：轴标题更靠下、且居中；类目名紧贴轴。
    """
    sp = spans(page) if sp is None else sp
    if not frame.x_axis_y:
        return []
    size = (frame.ticks_x or sp or [None])[0]
    size = size.size if size else 8.0
    cand = [s for s in sp
            if not s.vertical
            and not _NUMONLY.match(s.text)
            and _is_title_text(s.text)
            and s is not frame.title_x
            and s.box[1] >= frame.x_axis_y - 0.3 * size
            and s.box[1] <= frame.x_axis_y + 1.9 * size]
    if not cand:
        return []
    top = min(s.box[1] for s in cand)
    row = [s for s in cand if s.box[1] - top < 0.6 * size]
    return row


def value_labels(page, frame: Axes, sp: list["Span"] | None = None) -> list[tuple["Span", tuple]]:
    """数值标签 + 它所标注的对象（柱顶/绘图区内的点）。

    只认「数字文本，x 中心落在某个填充矩形内，且位于矩形上方 0—3 em」。
    """
    sp = spans(page) if sp is None else sp
    rects = [r for r in filled_rects(page) if r[2] - r[0] >= 2 and r[3] - r[1] >= 2]
    out = []
    for s in sp:
        if s.vertical or not _NUMONLY.match(s.text):
            continue
        for r in rects:
            if r[0] - 1 <= s.cx <= r[2] + 1 and 0 <= r[1] - s.box[3] <= 3.0 * s.size:
                out.append((s, r))
                break
    return out


def legend_items(page, sp: list[Span], axes: Axes) -> list[tuple]:
    """图例：一条短线段/小色块 + 紧跟右侧的文字。

    返回 [((x0,x1,y0,y1), 文字 Span)]。只认"线样右缘 → 文字左缘 ≤ 1 个字号"的配对，
    避免把正文里的下划线当图例。
    """
    out = []
    # 样例必须是**单个 path** 的小水平线样或小色块。
    # 不能按线段取：雷达圆环被拆成几百条 2.1 pt 短线，逐线段取会把圆环当图例。
    pa = page.rect.width * page.rect.height
    cands = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.width * r.height > 0.85 * pa:
            continue
        if not (d.get("fill") or d.get("color")):
            continue
        if 2.0 <= max(r.width, r.height) <= 40.0 and min(r.width, r.height) <= 12.0:
            cands.append((r.x0, r.x1, r.y0, r.y1))

    for s in sp:
        if s.vertical:
            continue
        best = None
        for gx0, gx1, gy0, gy1 in cands:
            gap = s.box[0] - gx1
            if -0.5 <= gap <= 1.2 * s.size and gy0 - 1.0 <= s.cy <= gy1 + 1.0:
                if best is None or gap < best[0]:
                    best = (gap, gx0, gx1, gy0, gy1)
        if best is None:
            continue
        # 图例文字常被拆成多段（「通用」+「RAG」相接，间隙 0），向右吸附同行后续段
        text, right = s.text, s.box[2]
        for t in sorted(sp, key=lambda x: x.box[0]):
            if t is s or t.vertical or abs(t.cy - s.cy) > 0.4 * s.size:
                continue
            if -0.5 <= t.box[0] - right <= 0.35 * s.size:
                text += t.text
                right = t.box[2]
        # bbox 必须跟着吸附后的右缘一起扩，否则合并段的宽度是假的（图例挖不干净）
        out.append(((best[1], best[2], best[3], best[4]), Span(
            text=text, size=s.size, bbox=(s.bbox[0], s.bbox[1], right, s.bbox[3]),
            origin=s.origin, vertical=False, font=s.font)))
    # 去重（同一行可能被多个样例匹配）
    seen, uniq = set(), []
    for g, s in out:
        key = (round(g[1], 1), round(s.cy, 1))
        if key in seen:
            continue
        seen.add(key)
        uniq.append((g, s))
    return uniq
