"""Detected axis and coordinate frame geometry."""
from __future__ import annotations
import math, re
from .spec_core import AXIS_MIN_PT, Axes, Span, spans, segments, filled_rects, ink_bbox

_NUMONLY = re.compile(r"^[\d\s.,%+\-]+$")
# 不可能是轴标题的文本：指数标注、孤立括号、纯符号
_NOT_TITLE = re.compile(r"^[（(）)\[\]【】,，。.、;；:：\-—_/·]+$|×\s*10")


def _is_title_text(t: str) -> bool:
    t = t.strip()
    if not t or len(t) > 24:
        return False
    if _NOT_TITLE.search(t):
        return False
    return bool(re.search(r"[A-Za-z\u4e00-\u9fff]", t))


def _cluster(vals: list[float], tol: float) -> list[list[int]]:
    """一维聚类：把相近的下标归到一组（值本身需排好序才稳）。"""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    groups: list[list[int]] = []
    cur: list[int] = []
    for i in order:
        if cur and vals[i] - vals[cur[-1]] > tol:
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    return groups


def _uniformity(vals: list[float]) -> float:
    """等距性 = 间距的标准差 / 均值。刻度序列通常 < 0.15。"""
    if len(vals) < 2:
        return 9.9
    d = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    m = sum(d) / len(d)
    if m <= 0:
        return 9.9
    sd = (sum((x - m) ** 2 for x in d) / len(d)) ** 0.5
    return sd / m


def detect_frames(page, sp: list["Span"] | None = None) -> list[Axes]:
    """按**刻度数字的等距序列**反推坐标区，一页可出多个（叠排子图）。

    为什么不用"最长横线"：网格线、页框线、分隔线都比轴长，
    图5 源图实测会被选成网格线 x=58.17（真轴 20.6），
    多子图叠排时会选中页框左边界。

    刻度序列是强特征：同基线一排、x 等距递增、纯数字。
    """
    sp = spans(page) if sp is None else sp
    segs = segments(page, min_len=8)
    hs = [s for s in segs if s.horizontal and s.length >= 0.5 * AXIS_MIN_PT]
    vs = [s for s in segs if s.vertical and s.length >= 0.5 * AXIS_MIN_PT]
    nums = [s for s in sp if not s.vertical and _NUMONLY.match(s.text) and len(s.text) <= 14]

    frames: list[Axes] = []
    used_rows: set[int] = set()

    # ---- 横轴刻度排：按基线聚类
    if nums:
        rows = _cluster([s.origin[1] for s in nums], 0.8)
        for g in rows:
            if len(g) < 3:
                continue
            cand = sorted((nums[i] for i in g), key=lambda s: s.cx)
            if _uniformity([s.cx for s in cand]) > 0.30:
                continue
            size = cand[0].size
            top = min(s.box[1] for s in cand)
            lo, hi = min(s.cx for s in cand), max(s.cx for s in cand)
            # 该排上方最近、且横向覆盖刻度范围的那条横线 = x 轴
            pick = None
            for h in hs:
                y = (h.y0 + h.y1) / 2
                hx0, hx1 = min(h.x0, h.x1), max(h.x0, h.x1)
                if not (-0.15 * size <= y - top <= 1.7 * size):
                    continue
                if (hx1 - hx0) < 0.6 * max(hi - lo, 1.0):   # 太短的线撑不起刻度排
                    continue
                if hx1 < lo - 2 or hx0 > hi + 2:            # 得横向覆盖刻度
                    continue
                if pick is None or y > pick[0]:
                    pick = (y, h)
            x_y = pick[0] if pick else 0.0
            h = pick[1] if pick else None
            frame = Axes(
                x_axis_y=round(x_y, 2),
                plot=(min(h.x0, h.x1) if h else lo, 0.0, max(h.x0, h.x1) if h else hi, x_y),
                ticks_x=cand,
            )
            # x 轴标题：刻度排下方、离轴 0.6—3 个字号的非数字横排文字
            # x 轴标题：紧贴刻度排下方、且大致居中于刻度范围（偏一侧的多半是类目名）
            mid = (max(s.cx for s in cand) + min(s.cx for s in cand)) / 2
            half = (max(s.cx for s in cand) - min(s.cx for s in cand)) / 2 + 1
            best = None
            for t in sp:
                if t.vertical or not _is_title_text(t.text):
                    continue
                gap = t.box[1] - cand[0].box[3]
                if not (-0.5 <= gap <= 3.0 * size):
                    continue
                if abs(t.cx - mid) > 0.45 * half + 0.5 * size:
                    continue
                if best is None or gap < best[0]:
                    best = (gap, t)
            frame.title_x = best[1] if best else None
            frames.append(frame)
            used_rows.update(g)

    # ---- 纵轴刻度列：按右缘（右对齐）聚类
    if nums:
        cols = _cluster([s.box[2] for s in nums], 0.8)
        for g in cols:
            if len(g) < 2:
                continue
            cand = sorted((nums[i] for i in g), key=lambda s: s.cy)
            if len(cand) >= 3 and _uniformity([s.cy for s in cand]) > 0.30:
                continue
            size = cand[0].size
            right = max(s.box[2] for s in cand)
            lo, hi = min(s.cy for s in cand), max(s.cy for s in cand)
            pick = None
            for v in vs:
                x = (v.x0 + v.x1) / 2
                if -0.15 * size <= x - right <= 1.7 * size and x > right:
                    if pick is None or x < pick[0]:
                        pick = (x, v)
            y_x = pick[0] if pick else 0.0
            # 归到最近的已有 frame（同一子图），否则新建
            tgt = None
            for f in frames:
                if f.ticks_x and abs(min(s.cy for s in f.ticks_x) - hi) < 3 * size:
                    tgt = f
                    break
            if tgt is None:
                tgt = Axes(plot=(0, lo, 0, hi))
                frames.append(tgt)
            tgt.ticks_y = cand
            tgt.y_axis_x = round(y_x, 2)
            p = list(tgt.plot)
            p[0] = y_x or p[0]
            # 绘图区上下界取**轴线**的两端，不是刻度序列的两端。
            # 截断轴（图6 源 y 从 0.70 起、柱底在轴底）用刻度范围会把底边算高 23 pt，
            # 导致柱底全部落不进容差，柱数被数成 0。
            if pick:
                ax = pick[1]
                ay0, ay1 = min(ax.y0, ax.y1), max(ax.y0, ax.y1)
            else:
                ay0, ay1 = lo, hi
            p[1] = ay0 if p[1] <= 0 else min(p[1], ay0)
            p[3] = ay1 if ay1 > ay0 else hi
            tgt.plot = tuple(p)
            # y 轴标题：竖排、在该列左侧
            # y 轴标题：竖排、在刻度列左侧、竖直方向大致居中
            midy = (lo + hi) / 2
            halfy = (hi - lo) / 2 + 1
            best = None
            for t in sp:
                if not t.vertical or not _is_title_text(t.text):
                    continue
                gap = min(s.box[0] for s in cand) - t.box[2]
                if not (-0.5 <= gap <= 4.0 * size):
                    continue
                if abs(t.cy - midy) > 0.55 * halfy + 0.6 * size:
                    continue
                if best is None or gap < best[0]:
                    best = (gap, t)
            if best:
                tgt.title_y = best[1]

    # ---- 兜底：分类轴（如分组柱状图）横轴下没有数字刻度，用柱底反推
    if frames:
        rects = filled_rects(page)
        ib = ink_bbox(page)
        for f in frames:
            if not f.x_axis_y and f.plot[3] > f.plot[1]:
                # 分类轴（柱状图横轴下没有数字刻度）：柱底 = 零刻度线 = 绘图区底边。
                # 优先用 Y 刻度下端（plot[3]），再用附近柱底众数校正。
                # 不能直接取"所有柱底众数"：图例框、标签底色也是填充矩形，
                # 源图曾因此把 x 轴算到 344.4（真柱底 320.9），柱全被容差筛掉。
                from collections import Counter
                cand = f.plot[3]
                near = [round(r[3], 1) for r in rects if abs(r[3] - cand) <= 5]
                if near:
                    cand = Counter(near).most_common(1)[0][0]
                f.x_axis_y = cand
            if f.plot[2] <= f.plot[0] and ib:
                f.plot = (f.plot[0], f.plot[1], ib[2], f.plot[3] or f.x_axis_y)
            if f.plot[3] <= f.plot[1] and f.x_axis_y:
                f.plot = (f.plot[0], min(f.plot[1], f.x_axis_y) if f.plot[1] else f.x_axis_y,
                          f.plot[2], f.x_axis_y)

    return [f for f in frames if f.found]


def detect_axes(page, sp: list["Span"] | None = None) -> Axes:
    """兼容接口：取面积最大的那个坐标区。多子图请用 detect_frames。"""
    fs = detect_frames(page, sp)
    if not fs:
        return Axes()
    return max(fs, key=lambda f: (f.plot[2] - f.plot[0]) * (f.plot[3] - f.plot[1]))
