"""fingerprint —— 版式拓扑指纹：源图 vs 重画稿，机器比对"结构有没有被改"。

## 解决什么

redraw（凭版式重画）的图，几何本来就变，S6 等比校验用不上，
只剩「数值守恒 + 文字覆盖」。但版式拓扑——几张子图、几组柱、每组几根、
图例几项、有没有轴标题——一直是人眼看。

图6 曾被拆成三行叠排，被用户否掉：「我选错了，不能拆成这样，这是完全错误的」。
当时这个问题只写在 registry 的备注里，没有任何机器校验。

现在把拓扑抽成指纹，源图与成稿逐项比：

    n_frames      坐标区数量（拆成三行 → 3，原图 → 1）
    group_axis    组是横排还是竖排（拆行会从 row 变 column）
    n_groups      组数（3 组）
    bars_per_group 每组柱数（[4,4,4] → 众数 4）
    n_series      图例条目数（4）
    has_x_title / has_y_title
    n_ticks_x / n_ticks_y

用法：
    fingerprint.bat 源图.pdf 成稿.pdf
    from fingerprint import fp, compare
"""

from __future__ import annotations
from .types import FingerprintReport
from .errors import AuditInputError

import argparse
import json
import statistics
import sys
from pathlib import Path

import fitz

from . import spec_lib as L


def detect_bars(page, frame: L.Axes | None) -> list[tuple[float, float, float, float]]:
    """填充矩形柱。要求：尺寸像柱、底边贴在同一基线上（竖柱）。

    不要求 items 全是 're'：很多绘图软件把柱画成闭合多边形。
    """
    pa = page.rect.width * page.rect.height
    base_y = frame.x_axis_y if frame and frame.x_axis_y else None
    out = []
    for d in page.get_drawings():
        if not d.get("fill"):
            continue
        raw = d["rect"]
        if raw.width * raw.height > 0.5 * pa:
            continue
        # 源图的柱常常溢出到页外（图6源柱底画到 y=1132、页高才 394），
        # 先与页框求交再判尺寸，否则宽高比失真会被当成异常元素滤掉。
        r = raw & page.rect
        if r.is_empty or not (1.5 <= r.width <= 60 and 4 <= r.height):
            continue
        # 竖柱判据是「跨过基线」而不是「底边贴基线」：
        # 溢出的柱底在页外，用贴边判会全部漏掉，源图柱数被数成 0。
        if base_y is not None and not (r.y0 < base_y - 1.5 and r.y1 >= base_y - 1.5):
            continue
        y1 = min(r.y1, base_y) if base_y is not None else r.y1
        out.append((r.x0, r.y0, r.x1, y1))
    return out


def _group_by_labels(bars, cats) -> list[list[tuple]]:
    """按类目名把柱分到各组（类目名 cx 即组中心）。"""
    if not cats or not bars:
        return []
    xs = sorted(s.cx for s in cats)
    if len(xs) >= 2:
        step = statistics.median([xs[i + 1] - xs[i] for i in range(len(xs) - 1)])
    else:
        step = (max(b[2] for b in bars) - min(b[0] for b in bars)) or 1
    groups = [[] for _ in xs]
    for b in bars:
        cx = (b[0] + b[2]) / 2
        i = min(range(len(xs)), key=lambda k: abs(cx - xs[k]))
        if abs(cx - xs[i]) <= 0.55 * step:
            groups[i].append(b)
    return [g for g in groups if g]


def _group_by_gaps(bars) -> list[list[tuple]]:
    """退路：按柱间空隙切组（空隙明显大于中位空隙处断开）。"""
    if len(bars) < 2:
        return [bars] if bars else []
    bars = sorted(bars, key=lambda b: b[0])
    gaps = [bars[i + 1][0] - bars[i][2] for i in range(len(bars) - 1)]
    med = statistics.median(gaps) if gaps else 0
    thr = max(med * 2.2, 3.0)
    groups, cur = [], [bars[0]]
    for i, g in enumerate(gaps):
        if g > thr:
            groups.append(cur)
            cur = [bars[i + 1]]
        else:
            cur.append(bars[i + 1])
    groups.append(cur)
    return groups


def fp(path: str | Path) -> FingerprintReport:
    doc = fitz.open(str(path))
    if len(doc) != 1:
        doc.close()
        raise AuditInputError("指纹只接受单页 PDF")
    page = doc[0]
    sp = L.spans(page)
    frames = L.detect_frames(page, sp)
    main = max(frames, key=lambda f: (f.plot[2] - f.plot[0]) * (f.plot[3] - f.plot[1])) if frames else None

    bars = detect_bars(page, main)
    cats = L.category_labels(page, main, sp) if main else []
    groups = _group_by_labels(bars, cats) or _group_by_gaps(bars)

    per_group = [len(g) for g in groups]
    # 组是横排还是竖排：看各组中心的 x 是否递变、y 是否几乎相同
    axis = "none"
    if len(groups) >= 2:
        cx = [statistics.mean([(b[0] + b[2]) / 2 for b in g]) for g in groups]
        cy = [statistics.mean([(b[1] + b[3]) / 2 for b in g]) for g in groups]
        spread_x = max(cx) - min(cx)
        spread_y = max(cy) - min(cy)
        axis = "row" if spread_x >= spread_y else "column"
    elif groups:
        axis = "single"

    items = L.legend_items(page, sp, main) if main else L.legend_items(page, sp, L.Axes())
    result = {
        "file": Path(str(path)).name,
        "page_mm": [round(page.rect.width * L.MM, 2), round(page.rect.height * L.MM, 2)],
        "n_frames": len(frames),
        "n_bars": len(bars),
        "n_groups": len(groups),
        "bars_per_group": per_group,
        "bars_even": len(set(per_group)) <= 1,
        "group_axis": axis,
        "n_series": len(items),
        "legend_texts": [s.text for g, s in items][:8],
        "has_x_title": bool(main and main.title_x),
        "has_y_title": bool(main and main.title_y),
        "n_ticks_x": len(main.ticks_x) if main else 0,
        "n_ticks_y": len(main.ticks_y) if main else 0,
        "body_pt": round(L.body_size(sp), 2),
    }
    doc.close()
    return result


# 硬判据：只比**几何拓扑**，必须一致。
#
# 为什么不比文字类字段（n_series / has_x_title）：
# 源图的中文常是转曲轮廓（无 ToUnicode），文字提不出来，成稿是真文字。
# 拿"源图提不到"去比"成稿提到了"，必然误报——这不是版式被改，是提取能力差异。
# 系列数也不必单列：bars_per_group 已经隐含（每组 4 根柱 = 4 个系列）。
STRICT = {
    "n_frames": "坐标区（子图）数量",
    "n_groups": "分组数",
    "bars_per_group": "每组柱数",
    "group_axis": "组排布方向（横排/竖排）",
    "n_bars": "柱总数",
}

# 软指标：只记录，供人看，不判 FAIL
SOFT = {
    "n_series": "图例条目数（源图中文转曲时不可靠）",
    "has_x_title": "有无横轴标题（同上）",
    "has_y_title": "有无纵轴标题（同上）",
}


def compare(src: dict, out: dict, allow: set[str] | None = None) -> list[dict]:
    allow = allow or set()
    rows = []
    for k, desc in STRICT.items():
        if k in allow:
            continue
        a, b = src.get(k), out.get(k)
        rows.append({"field": k, "desc": desc, "src": a, "out": b, "ok": a == b})
    for k, desc in SOFT.items():
        a, b = src.get(k), out.get(k)
        rows.append({"field": k, "desc": desc, "src": a, "out": b,
                     "ok": a == b, "soft": True})
    return rows


def report(rows: list[dict], src: dict, out: dict) -> str:
    bad = [r for r in rows if not r["ok"] and not r.get("soft")]
    L_ = [f"\n版式指纹  {src['file']}  →  {out['file']}"]
    L_.append(f"  {'源':<26s} {'源图':<22s} {'成稿':<22s}")
    for r in rows:
        mark = "√" if r["ok"] else ("·" if r.get("soft") else "×")
        L_.append(f"  {mark} {r['desc']:<22s} {str(r['src']):<22s} {str(r['out']):<22s}")
    L_.append("")
    if bad:
        L_.append(f"  → 检测结果有 {len(bad)} 处差异，须核对源图与识别结果：")
        for r in bad:
            L_.append(f"     · {r['desc']}：源 {r['src']} → 稿 {r['out']}")
    else:
        L_.append("  → 检测结果一致，不能证明版式完整或未改动")
    return "\n".join(L_)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="版式拓扑指纹比对（源图 vs 重画稿）")
    ap.add_argument("src")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--allow", default="", help="允许改动的字段，逗号分隔，如 n_frames")
    ap.add_argument("--json", help="把两份指纹写到该 JSON")
    ap.add_argument("--save", help="只生成成稿指纹（用于 guard 读取）")
    a = ap.parse_args(argv)

    inputs = {Path(value).resolve() for value in (a.src, a.out) if value}
    for destination in (a.json, a.save):
        if destination and Path(destination).resolve() in inputs:
            raise AuditInputError("报告不能覆盖输入 PDF")

    allow = {x.strip() for x in a.allow.split(",") if x.strip()}

    if not a.out:
        f = fp(a.src)
        print(json.dumps(f, ensure_ascii=False, indent=1))
        return 0

    fs, fo = fp(a.src), fp(a.out)
    rows = compare(fs, fo, allow)
    print(report(rows, fs, fo))
    if a.json:
        Path(a.json).write_text(json.dumps({"src": fs, "out": fo, "rows": rows},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
    if a.save:
        Path(a.save).write_text(json.dumps(fo, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if all(r["ok"] or r.get("soft") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
