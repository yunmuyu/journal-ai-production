"""spec_lib —— 图稿几何与文本的共用读取层。

三个遗留问题（间距台账 / 版式指纹 / 压栏可行性）本质是同一个内核：
**把 PDF 里的"看得见的盒子"算准**。以前每个工具各写一份，量出来的数互相打架。

## 视觉框约定（本文件唯一的硬约定）

`bbox` 含字体 ascent/descent：8 pt 字的 bbox 高 10.8 pt，可视字形只有 5.8 pt。
直接拿 bbox 相减量间距，比眼睛看到的少 2—3 pt —— 图5/图6 那两轮间距争议就是这么来的。

所以：
- **横向**用 bbox 的 x（数字/中文都没有横向伸部，准）
- **纵向**用 `origin`（基线）± 视觉高：
    上伸 0.88×size（中文全角顶 / 西文 ascent）
    下伸 0.12×size（降部）
  这对中文准，对纯数字保守 0.16 pt，但**源图与成稿同一算法**，比较时抵消。

## 旋转文字

`dir≈(0,-1)` 的竖排文字（y 轴标题）：基线是竖线 x=origin_x，字形向 −x 展开 cap 高。
实测算得"互相关值"视觉右缘 8.08，与 bbox.x1=8.0 吻合到 0.08 pt —— 中文竖排用 bbox 即可。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import fitz

MM = 25.4 / 72.0          # pt → mm
PT = 1 / MM               # mm → pt

UP = 0.88                 # baseline → 字形顶
DOWN = 0.12               # baseline → 字形底（降部）

# 轴类图形（柱/线/散点）的判定门槛：主轴至少这么长才算"有轴"
AXIS_MIN_PT = 60.0


# ------------------------------------------------------------------ 文本

@dataclass
class Span:
    text: str
    size: float
    bbox: tuple[float, float, float, float]
    origin: tuple[float, float]
    vertical: bool          # dir 接近 (0,±1)
    font: str = ""

    @property
    def box(self) -> tuple[float, float, float, float]:
        """视觉框：横 x 用 bbox，纵 y 用基线 ± 视觉高。"""
        x0, _, x1, _ = self.bbox
        if self.vertical:
            # 竖排：基线是竖线，字沿 −x 展开；bbox 的 x 本身就是视觉边界
            return self.bbox
        ox, oy = self.origin
        return (x0, oy - UP * self.size, x1, oy + DOWN * self.size)

    @property
    def cx(self) -> float:
        b = self.box
        return (b[0] + b[2]) / 2

    @property
    def cy(self) -> float:
        b = self.box
        return (b[1] + b[3]) / 2

    @property
    def w(self) -> float:
        b = self.box
        return b[2] - b[0]

    @property
    def h(self) -> float:
        b = self.box
        return b[3] - b[1]


def spans(page) -> list[Span]:
    out: list[Span] = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            d = line.get("dir", (1.0, 0.0))
            vertical = abs(d[1]) > 0.7
            for s in line["spans"]:
                if not s["text"].strip():
                    continue
                out.append(Span(
                    text=s["text"].strip(),
                    size=round(s["size"], 2),
                    bbox=tuple(float(v) for v in s["bbox"]),
                    origin=tuple(float(v) for v in s.get("origin", (s["bbox"][0], s["bbox"][3]))),
                    vertical=vertical,
                    font=s.get("font", ""),
                ))
    return out


def font_sizes(sp: list[Span]) -> dict[float, int]:
    """字号 → 字符数（不是 span 数：一个 8 pt 的 20 字标题不该压过 20 个数字）。"""
    from collections import Counter
    c: Counter = Counter()
    for s in sp:
        c[s.size] += len(s.text)
    return dict(c)


def body_size(sp: list[Span], default: float = 8.0) -> float:
    """正文字号 = 承载字符最多的那一档。"""
    fs = font_sizes(sp)
    return max(fs.items(), key=lambda kv: kv[1])[0] if fs else default


_CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]")


def text_width(text: str, size: float, cjk_ratio: float = 1.0) -> float:
    """估一行文字的宽度（pt）。中文按 1 em，西文按字宽表。

    用 PyMuPDF 内置字宽（helv）量西文/数字，中文按 cjk_ratio × size。
    误差 <3%，够做"放不放得下"的判断。
    """
    if not text:
        return 0.0
    w = 0.0
    for ch in text:
        if _CJK.match(ch):
            w += cjk_ratio * size
        else:
            w += fitz.get_text_length(ch, fontname="helv", fontsize=size)
    return w


def wrap_count(text: str, size: float, max_w: float) -> int:
    """把 text 塞进 max_w 需要几行（按字符贪心，中文可任意断行）。"""
    if max_w <= 0:
        return 999
    lines, cur = 1, 0.0
    for ch in text:
        cw = text_width(ch, size)
        if cur + cw > max_w and cur > 0:
            lines += 1
            cur = cw
        else:
            cur += cw
    return lines


# ------------------------------------------------------------------ 图形

@dataclass
class Seg:
    x0: float
    y0: float
    x1: float
    y1: float
    width: float = 0.0
    fill: tuple | None = None
    color: tuple | None = None
    rect: tuple[float, float, float, float] = (0, 0, 0, 0)

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def horizontal(self) -> bool:
        return abs(self.y1 - self.y0) < 0.4 and abs(self.x1 - self.x0) > 0.4

    @property
    def vertical(self) -> bool:
        return abs(self.x1 - self.x0) < 0.4 and abs(self.y1 - self.y0) > 0.4


def _on_page(r, page, ratio: float = 0.35) -> bool:
    """元素是否落在页框内（交集至少占自身 ratio）。

    源图常带伸到页外的裁剪路径（图6源有 y=1132 pt、页高才 394 pt 的框），
    不滤掉会把"柱底"算到页外去。
    """
    area = r.width * r.height
    if area <= 0:
        # 零面积 = 线段（坐标轴就是 width=0 的竖线）：& 运算会判成空，
        # 必须改用端点坐标判断，否则所有轴线都会被滤掉，y 轴识别整体失效。
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        return (page.rect.x0 - 2 <= cx <= page.rect.x1 + 2
                and page.rect.y0 - 2 <= cy <= page.rect.y1 + 2)
    inter = r & page.rect
    if inter.is_empty:
        return False
    return (inter.width * inter.height) >= ratio * area


def segments(page, min_len: float = 1.0) -> list[Seg]:
    """所有直线段（含矩形四边）。只取 'l' 与 're'，曲线留给圆形图不管。"""
    out: list[Seg] = []
    for d in page.get_drawings():
        if not _on_page(d["rect"], page):
            continue
        w = float(d.get("width") or 0)
        fill = tuple(d["fill"]) if d.get("fill") else None
        color = tuple(d["color"]) if d.get("color") else None
        r = d["rect"]
        rect = (r.x0, r.y0, r.x1, r.y1)
        for it in d["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                s = Seg(p.x, p.y, q.x, q.y, w, fill, color, rect)
                if s.length >= min_len:
                    out.append(s)
            elif it[0] == "re":
                rr = it[1]
                for a, b in (
                    ((rr.x0, rr.y0), (rr.x1, rr.y0)),
                    ((rr.x1, rr.y0), (rr.x1, rr.y1)),
                    ((rr.x1, rr.y1), (rr.x0, rr.y1)),
                    ((rr.x0, rr.y1), (rr.x0, rr.y0)),
                ):
                    s = Seg(a[0], a[1], b[0], b[1], w, fill, color, rect)
                    if s.length >= min_len:
                        out.append(s)
    return out


def filled_rects(page, min_w: float = 1.5, min_h: float = 1.5) -> list[tuple[float, float, float, float]]:
    """纯填充矩形（柱子、色块）。排除整页背景。"""
    pa = page.rect.width * page.rect.height
    out = []
    for d in page.get_drawings():
        if not d.get("fill"):
            continue
        r = d["rect"]
        if r.width * r.height > 0.85 * pa:
            continue
        if not _on_page(r, page):
            continue
        if r.width >= min_w and r.height >= min_h and all(it[0] == "re" for it in d["items"]):
            out.append((r.x0, r.y0, r.x1, r.y1))
    return out


# ------------------------------------------------------------------ 轴

@dataclass
class Axes:
    """一个坐标区（子图）。x_axis_y 是横轴所在 y，y_axis_x 是纵轴所在 x。"""
    x_axis_y: float = 0.0
    y_axis_x: float = 0.0
    plot: tuple[float, float, float, float] = (0, 0, 0, 0)
    ticks_x: list["Span"] = field(default_factory=list)
    ticks_y: list["Span"] = field(default_factory=list)
    title_x: "Span | None" = None
    title_y: "Span | None" = None

    @property
    def found(self) -> bool:
        return self.x_axis_y > 0 or self.y_axis_x > 0


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
    孙清洋-图9.1 三个子图叠排时会选中页框左边界。

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


def ink_bbox(page, skip_background: bool = True,
             exclude: tuple[float, float, float, float] | None = None
             ) -> tuple[float, float, float, float] | None:
    """墨迹外接框。exclude 给一个矩形，落在其中的元素不计（用于把图例挖掉）。"""
    pa = page.rect.width * page.rect.height

    def inside(x0, y0, x1, y1) -> bool:
        if not exclude:
            return False
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return exclude[0] - 1 <= cx <= exclude[2] + 1 and exclude[1] - 1 <= cy <= exclude[3] + 1

    xs, ys = [], []
    for d in page.get_drawings():
        r = d["rect"]
        if skip_background and r.width * r.height > 0.85 * pa:
            continue
        if inside(r.x0, r.y0, r.x1, r.y1):
            continue
        xs += [r.x0, r.x1]
        ys += [r.y0, r.y1]
    for s in spans(page):
        b = s.box
        if inside(*b):
            continue
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def has_bitmap(page) -> int:
    return len(page.get_images())


def is_3d_hint(page, axes: Axes) -> bool:
    """斜线多于直线的一半 → 3D 透视柱图，间距规则不适用。"""
    slanted = 0
    total = 0
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                total += 1
                p, q = it[1], it[2]
                if abs(p.y - q.y) > 0.5 and abs(p.x - q.x) > 0.5:
                    slanted += 1
    return total > 8 and slanted / total > 0.4
