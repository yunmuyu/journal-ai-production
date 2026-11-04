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
from dataclasses import dataclass

import fitz

MM = 25.4 / 72.0          # pt → mm
PT = 1 / MM               # mm → pt

UP = 0.88                 # baseline → 字形顶
DOWN = 0.12               # baseline → 字形底（降部）

# 轴类图形（柱/线/散点）的判定门槛：主轴至少这么长才算"有轴"
AXIS_MIN_PT = 60.0


# ------------------------------------------------------------------ 文本

@dataclass(frozen=True, slots=True)
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

@dataclass(frozen=True, slots=True)
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

class Axes:
    """Mutable accumulator for one detected coordinate frame."""
    __slots__ = ('x_axis_y', 'y_axis_x', 'plot', 'ticks_x', 'ticks_y', 'title_x', 'title_y')

    def __init__(self, x_axis_y=0.0, y_axis_x=0.0, plot=(0, 0, 0, 0),
                 ticks_x=None, ticks_y=None, title_x=None, title_y=None):
        self.x_axis_y = x_axis_y
        self.y_axis_x = y_axis_x
        self.plot = plot
        self.ticks_x = [] if ticks_x is None else ticks_x
        self.ticks_y = [] if ticks_y is None else ticks_y
        self.title_x = title_x
        self.title_y = title_y

    @property
    def found(self) -> bool:
        return self.x_axis_y > 0 or self.y_axis_x > 0


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
