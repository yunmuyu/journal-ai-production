"""Shared report and numeric extraction helpers."""
from __future__ import annotations
import math, re
from collections import Counter
from pathlib import Path
MM = 25.4 / 72.0

class R:
    """一份报告的收集器。"""

    def __init__(self, out: Path, src: Path | None):
        self.out = out
        self.src = src
        self.issues: list[dict] = []
        self.facts: dict = {}

    def add(self, code: str, level: str, msg: str, **extra):
        self.issues.append({"code": code, "level": level, "msg": msg, **extra})

    def ok(self, code: str, msg: str = ""):
        self.issues.append({"code": code, "level": "PASS", "msg": msg})

    def fail(self, code: str, msg: str, **extra):
        self.add(code, "FAIL", msg, **extra)

    def warn(self, code: str, msg: str, **extra):
        self.add(code, "WARN", msg, **extra)

    def skip(self, code: str, msg: str):
        self.add(code, "SKIP", msg)

    @property
    def n_fail(self) -> int:
        return sum(1 for i in self.issues if i["level"] == "FAIL")


# ---------------------------------------------------------------- 取数

def spans_of(page) -> list[dict]:
    out = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            for s in line["spans"]:
                if s["text"].strip():
                    out.append(s)
    return out


def ink_bbox(page) -> tuple[float, float, float, float] | None:
    """墨迹外接框。path 的 rect 先与页框求交——裁剪路径会伸到页外
    （图6源就有 y1=1132pt、页高 394pt 的裁剪框），不求交会把高度算成 3 倍。"""
    pr = page.rect
    xs: list[float] = []
    ys: list[float] = []
    for d in page.get_drawings():
        r = d["rect"] & pr
        if r.is_empty:
            continue
        xs += [r.x0, r.x1]
        ys += [r.y0, r.y1]
    for s in spans_of(page):
        x0, y0, x1, y1 = s["bbox"]
        xs += [x0, x1]
        ys += [y0, y1]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------- 数字规则


def _strip(s: str) -> str:
    return re.sub(r"[\s,]", "", s)


def group3(core: str) -> str:
    """把裸数字串按本刊体例加空格：整数从右每三位、小数从左每三位。"""
    if "." in core:
        ip, dp = core.split(".", 1)
    else:
        ip, dp = core, ""

    def chunk_right(s: str) -> str:
        out = []
        while len(s) > 3:
            out.insert(0, s[-3:])
            s = s[:-3]
        if s:
            out.insert(0, s)
        return " ".join(out)

    def chunk_left(s: str) -> str:
        return " ".join(s[i:i + 3] for i in range(0, len(s), 3))

    r = chunk_right(ip) if ip else "0"
    if dp:
        r += "." + chunk_left(dp)
    return r


def _split_chunk(ch: str) -> list[str]:
    """把一个只含「数字/点/空格」的块，拆成若干独立数值。

    判据只有一条：**整块拼起来如果正好是它自己三位一空的形式，那它就是分组数；
    否则这些空格是分隔符，不是分组符。**

    这一步很关键，否则 `5 10 15 20 25`（五个独立刻度标签）会被当成一个
    9 位数 510152025，误报「未按三位分组」——苏培育那 32 张坐标轴图就是这样被误伤的。
    """
    core = _strip(ch)
    if len(core.replace(".", "")) <= 3:
        return [ch]
    if ch == group3(core):
        return [ch]
    parts = ch.split()
    if len(parts) == 1:
        return [ch]
    out: list[str] = []
    for p in parts:
        out += _split_chunk(p)
    return out


def num_segments(text: str) -> list[str]:
    """切出「一个完整数值 + 其内嵌分组空格」的片段。"""
    out: list[str] = []
    for ch in re.split(r"[^\d.\s]+", text):
        ch = ch.strip()
        if not ch or not any(c.isdigit() for c in ch):
            continue
        out += _split_chunk(ch)
    return [s for s in out if s.strip(" .")]


def is_grouped(text: str) -> bool:
    """text 里每个数值是否都符合三位一空。"""
    for raw in num_segments(text):
        core = _strip(raw)
        if not core or core == ".":
            continue
        if len(core.replace(".", "")) <= 3:
            continue                            # 三段以内天然合规，无需空格
        if raw.strip() != group3(core):
            return False
    return True


def numbers_of(spans: list[dict]) -> Counter:
    """取页内全部数值（格式无关）。`0.918 1` 会还原成 0.9181，不会裂成 0.918 和 1。"""
    c: Counter = Counter()
    for s in spans:
        for raw in num_segments(s["text"]):
            c[round(float(_strip(raw)), 6)] += 1
    return c


# ---------------------------------------------------------------- 判据
