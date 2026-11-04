"""Experimental PDF spacing measurements; empirical values are advisory only."""

from __future__ import annotations
from .types import SpacingReport
from .errors import AuditInputError, UnknownSpacingRole

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

import fitz

from . import spec_lib as L
from .spec_lib import Axes

HERE = Path(__file__).resolve().parent
RULES = HERE / "spacing_rules.json"


def _is_vertical_bar_chart(page, frame) -> bool:
    """柱比宽高 → 竖柱图。取不到柱时返回 False（不测类目间距）。"""
    base = frame.x_axis_y
    ws, hs = [], []
    for r in L.filled_rects(page, 1.5, 3.0):
        if base and r[3] >= base - 2 and r[1] < base - 3:
            ws.append(r[2] - r[0])
            hs.append(base - r[1])
    if len(ws) < 2:
        # 取不到"贴 x 轴底"的柱：可能是横向柱图（柱贴的是 y 轴），也可能柱是描边而非填充。
        return False
    mw = statistics.median(ws)
    mh = statistics.median(hs)
    return mh >= mw


class Spacing:
    def __init__(self, rules: Path = RULES):
        self.rules = json.loads(rules.read_text(encoding="utf-8"))
        self.roles = self.rules["roles"]

    # ---------------------------------------------------------- 取值
    def get(self, role: str, size: float = 8.0) -> float | None:
        """该角色的目标间距（pt）= target_em × 字号。

        mode=bound 的角色语料分布极散（如"图例离绘图区多远"），
        本刊并无统一规范，只能给下限——这类角色没有 target，返回 None。
        """
        if role not in self.roles:
            raise UnknownSpacingRole(f"未定义的间距角色 {role}，可选：{', '.join(self.roles)}")
        t = self.roles[role].get("target_em")
        return None if t is None else round(t * size, 3)

    def min_gap(self, role: str, size: float = 8.0) -> float | None:
        """mode=bound 角色的下限（pt）。构建期用它当"至少留这么多"。"""
        r = self.roles[role]
        if r.get("mode") != "bound":
            return self.get(role, size)
        return round(r.get("min_em", 0.0) * size, 3)

    def range_pt(self, role: str, size: float = 8.0) -> tuple[float, float]:
        lo, hi = self.roles[role]["range_em"]
        return round(lo * size, 3), round(hi * size, 3)

    def judge(self, role: str, actual: float, size: float) -> tuple[str, str]:
        """Report an observation; the historical distribution is not a publication rule."""
        if role not in self.roles:
            raise UnknownSpacingRole(role)
        if size <= 0:
            raise AuditInputError("字号须大于零")
        return "INFO", f"{actual:.2f}pt = {actual / size:.2f}em（经验观察，须人工复核）"

    # ---------------------------------------------------------- 测量
    def measure(self, pdf: Path | str, figure: str = "", size: float | None = None) -> SpacingReport:
        """从成品 PDF 量全部可测角色，与规则比对。"""
        doc = fitz.open(str(pdf))
        if len(doc) != 1:
            doc.close()
            raise AuditInputError("间距观察只接受单页 PDF")
        page = doc[0]
        sp = L.spans(page)
        size = round(size or L.body_size(sp), 2)
        frames = L.detect_frames(page, sp)
        main = max(frames, key=lambda f: (f.plot[2] - f.plot[0]) * (f.plot[3] - f.plot[1])) if frames else None

        raw: dict[str, list[float]] = {}
        detail: dict[str, str] = {}

        def put(role: str, val: float, where: str):
            if val is None or val != val:
                return
            raw.setdefault(role, []).append(round(float(val), 3))
            detail.setdefault(role, where)

        for f in frames:
            # 刻度 → 轴（取绝对值；内侧风格记为负，这里统一用绝对值参与判定）
            if f.ticks_x and f.x_axis_y:
                d = [min(abs(s.box[1] - f.x_axis_y), abs(s.box[3] - f.x_axis_y)) for s in f.ticks_x]
                put("tick_to_axis", statistics.median(d), "横轴刻度近轴边 → x 轴线")
            if f.ticks_y and f.y_axis_x:
                d = [min(abs(s.box[0] - f.y_axis_x), abs(s.box[2] - f.y_axis_x)) for s in f.ticks_y]
                put("tick_to_axis", statistics.median(d), "纵轴刻度近轴边 → y 轴线")
            if f.title_x and f.x_axis_y:
                put("axis_title_x_to_axis", f.title_x.box[1] - f.x_axis_y, "x 轴标题顶 → x 轴线")
            if f.title_y and f.y_axis_x:
                put("axis_title_y_to_axis", f.y_axis_x - f.title_y.box[2], "y 轴标题右缘 → y 轴线")
            cats = L.category_labels(page, f, sp)
            # 只对**竖柱图**测类目间距：横向柱状图的类目在 y 轴左侧，
            if cats and f.x_axis_y and _is_vertical_bar_chart(page, f):
                put("category_to_axis", min(s.box[1] for s in cats) - f.x_axis_y, "类目名底 → x 轴线")
                if f.title_x:
                    put("category_to_axis_title",
                        f.title_x.box[1] - max(s.box[3] for s in cats), "类目名底 → x 轴标题顶")

        # 数值标签 → 柱顶
        if main:
            vl = L.value_labels(page, main, sp)
            if vl:
                put("value_label_to_element",
                    statistics.median([r[1] - s.box[3] for s, r in vl]), "数值标签底 → 柱顶")

        # 图例（无坐标区时也要测——图5 雷达图就属此类）
        items = L.legend_items(page, sp, main) if main else L.legend_items(page, sp, Axes())
        if True:
            if items:
                sw = [s.box[0] - g[1] for g, s in items if 0 <= s.box[0] - g[1] <= 2 * s.size]
                # 可靠性前置：流程图/框图里的"竖线 + 文字"会被误配成图例行，
                # 真图例的行距不会超过 4 em —— 超了整组图例判据都不采用（见下方 plausible）。
                # 行距：先按 0.6 em 聚类成行，否则同一行的字微小抖动会被当成两行
                raw_ys = sorted(s.cy for g, s in items)
                groups: list[list[float]] = []
                for y in raw_ys:
                    if groups and y - groups[-1][-1] <= 0.6 * size:
                        groups[-1].append(y)
                    else:
                        groups.append([y])
                ys = [statistics.median(gr) for gr in groups]
                plausible = all(
                    (ys[i + 1] - ys[i]) <= 4.0 * size for i in range(len(ys) - 1)
                ) if len(ys) >= 2 else True
                # 图例组整体可信才记这三项（swatch / 行距 / 到图距离），否则一律不判
                if sw and plausible:
                    put("legend_swatch_to_text", statistics.median(sw), "图例样例右缘 → 图例文字")
                if len(ys) >= 2 and plausible:
                    pitch = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
                    put("legend_row_pitch", statistics.median(pitch), "图例行距（基线到基线）")
                # 图例整体 bbox：样例几何 + 文字四边都要，漏掉 box[1] 会导致挖不干净
                xs = [g[0] for g, s in items] + [g[1] for g, s in items]
                ys2 = [g[2] for g, s in items] + [g[3] for g, s in items]
                for g, s in items:
                    b = s.box
                    xs += [b[0], b[2]]
                    ys2 += [b[1], b[3]]
                lb = (min(xs), min(ys2), max(xs), max(ys2))
                if main:
                    p = main.plot
                else:
                    # 无轴图：去掉图例后的墨迹就是"绘图区"
                    g = L.ink_bbox(page, exclude=lb) or lb
                    p = g
                inside = (lb[0] >= p[0] - 1 and lb[2] <= p[2] + 1 and lb[1] >= p[1] - 1 and lb[3] <= p[3] + 1)
                if not plausible:
                    pass          # 配对不可靠（流程图元素），不判图例到图的距离
                elif not inside:
                    role = "legend_to_plot" if main else "legend_to_graphic"
                    if lb[3] <= p[1]:
                        put(role, p[1] - lb[3], "图例底 → 绘图区顶" if main else "图例顶 → 图底")
                    elif lb[1] >= p[3]:
                        put(role, lb[1] - p[3], "图例顶 → 绘图区底" if main else "图例顶 → 图底")
                    else:
                        put(role, min(abs(lb[0] - p[2]), abs(p[0] - lb[2])), "图例与绘图区横向相邻")

        # 绘图区 → 画布
        if main:
            pw, ph = page.rect.width, page.rect.height
            p = main.plot
            ib = L.ink_bbox(page) or p
            put("plot_to_canvas", min(ib[0], ib[1], pw - ib[2], ph - ib[3]), "墨迹最近边 → 页边")

        # 子图间距
        if len(frames) >= 2:
            fs = sorted(frames, key=lambda f: f.plot[1])
            gaps = []
            for a, b in zip(fs, fs[1:]):
                a_bottom = a.title_x.box[3] if a.title_x else a.x_axis_y
                if a_bottom and b.plot[1]:
                    gaps.append(b.plot[1] - a_bottom)
            if gaps:
                put("subplot_gap", statistics.median(gaps), "上一子图轴标题底 → 下一子图绘图区顶")

        # ---------------------------------------------------------- 判定
        items = []
        for role, vals in raw.items():
            if role not in self.roles:
                continue
            v = round(statistics.median(vals), 2)
            level, msg = self.judge(role, v, size)
            rule = self.roles[role]
            tp = self.get(role, size)
            items.append({
                "role": role,
                "desc": rule["desc"],
                "n": len(vals),
                "measured_pt": v,
                "em": round(v / size, 3),
                "target_pt": tp,
                "mode": rule.get("mode", "target"),
                "range_pt": list(self.range_pt(role, size)),
                "verdict": level,
                "note": msg,
                "where": detail.get(role, ""),
                "origin": rule["origin"].get("kind"),
                "origin_ref": rule["origin"].get("why", ""),
            })
        items.sort(key=lambda x: ({"FAIL": 0, "WARN": 1, "OK": 2, "INFO": 3}[x["verdict"]], x["role"]))

        doc.close()
        return {
            "figure": figure or Path(str(pdf)).stem,
            "pdf": str(pdf),
            "pdf_sha256": hashlib.sha256(Path(pdf).read_bytes()).hexdigest(),
            "size_pt": size,
            "n_frames": len(frames),
            "rules_version": self.rules.get("version"),
            "items": items,
            "n_fail": sum(1 for i in items if i["verdict"] == "FAIL"),
            "n_warn": sum(1 for i in items if i["verdict"] == "WARN"),
            "n_info": sum(1 for i in items if i["verdict"] == "INFO"),
        }

    # ---------------------------------------------------------- 输出
    @staticmethod
    def dump(led: dict, out: Path | str) -> Path:
        p = Path(out)
        if p.resolve() == Path(led["pdf"]).resolve():
            raise AuditInputError("台账路径不能覆盖输入 PDF")
        p.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
        return p

    @staticmethod
    def report(led: dict) -> str:
        icon = {"FAIL": "×", "WARN": "!", "OK": "√", "INFO": "·"}
        L_ = [f"\n{led['figure']}  字号 {led['size_pt']} pt  子图 {led['n_frames']}"
              f"  →  FAIL {led['n_fail']} / WARN {led['n_warn']} / 仅记录 {led.get('n_info', 0)}"]
        if not led["items"]:
            L_.append("  （本图无可测间距角色：无坐标轴、无图例、无类目标签）")
        for i in led["items"]:
            L_.append(f"  {icon[i['verdict']]} {i['role']:24s} {i['note']:44s} [{i['origin']}] {i['where']}")
        return "\n".join(L_)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="间距台账：从成品 PDF 量间距并对规则表判定")
    ap.add_argument("pdf")
    ap.add_argument("--size", type=float, help="正文字号，默认按字符数最多的一档")
    ap.add_argument("--figure", default="", help="图号，写进台账")
    ap.add_argument("--out", help="台账输出路径（默认与 PDF 同目录 spacing.json）")
    a = ap.parse_args(argv)

    sp = Spacing()
    led = sp.measure(a.pdf, figure=a.figure, size=a.size)
    out = Path(a.out) if a.out else Path(a.pdf).with_name("spacing.json")
    sp.dump(led, out)
    print(sp.report(led))
    print(f"\n台账 → {out}")
    return 0 if led["n_fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
