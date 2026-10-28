# -*- coding: utf-8 -*-
"""guard.py 的自测：给每条判据造一个「应该被抓到」的故障样本。

为什么要有这个文件：
    2026-10-28 那次翻车的根子不是"少写了一条检查"，而是**检查本身没人检查**。
    引擎自报 issues=0，我就宣布可以交付，结果版式、间距、等比、字号唯一性
    四类问题全都没在判据覆盖范围内。所以守门器上线第一件事是自证：
    把每种错误人工制造一遍，确认它真的会被拦下来。

跑法：
    python -m figure_audit.selftest
"""
from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from . import guard

W80 = 80 / 25.4 * 72          # 226.77 pt


def new_doc(w=W80, h=200.0):
    doc = fitz.open()
    return doc, doc.new_page(width=w, height=h)


def poly(page, pts, width=0.5, color=(0, 0, 0), fill=None):
    page.draw_polyline(pts, color=color, width=width, fill=fill, closePath=True)


def text(page, x, y, s, size=7.98):
    page.insert_text((x, y), s, fontsize=size, fontname="helv", color=(0, 0, 0))


def run_case(name, out_doc, src_doc, expect: dict, **kw):
    """expect = {code: level}；只断言点名的 code，其余判据不参与。"""
    with tempfile.TemporaryDirectory() as td:
        op = Path(td) / "out.pdf"
        sp = Path(td) / "src.pdf"
        out_doc.save(op)
        if src_doc is not None:
            src_doc.save(sp)
        rep = guard.run(op, sp if src_doc is not None else None,
                        kw.get("column"), kw.get("mode", "trace"), 1, 0, None)
        got = {i["code"]: i["level"] for i in rep["issues"]}
        bad = []
        for code, want in expect.items():
            g = got.get(code, "MISSING")
            if g != want:
                bad.append(f"{code}: 期望 {want}，实得 {g}")
        msg = "；".join(bad)
        print(f"  {'√' if not bad else '×'} {name}" + (f"   ← {msg}" if bad else ""))
        return not bad


def main():
    ok = 0
    n = 0

    def case(*a, **k):
        nonlocal ok, n
        n += 1
        ok += 1 if run_case(*a, **k) else 0

    print("\n[guard 自测] 每条判据都要能抓到对应故障\n")

    # ---- S4 三位一空 ---------------------------------------------------
    d, p = new_doc()
    text(p, 40, 100, "0.9181")
    case("S4 抓到「0.9181」未分组", d, None, {"S4": "FAIL"}, column=80)
    d.close()

    d, p = new_doc()
    text(p, 40, 100, "0.918 1")
    case("S4 认可「0.918 1」", d, None, {"S4": "PASS"}, column=80)
    d.close()

    d, p = new_doc()
    text(p, 40, 100, "12 345.678 9")
    case("S4 认可整数+小数双分组", d, None, {"S4": "PASS"}, column=80)
    d.close()

    d, p = new_doc()
    text(p, 40, 100, "12345.6789")
    case("S4 抓到长整数未分组", d, None, {"S4": "FAIL"}, column=80)
    d.close()

    # ---- S3 字号唯一性 -------------------------------------------------
    d, p = new_doc()
    text(p, 20, 60, "0.70", 6.58)
    text(p, 20, 100, "语义边界", 8.0)
    case("S3 抓到 6.58 + 8.0 两级字号", d, None, {"S3": "FAIL"}, column=80)
    d.close()

    d, p = new_doc()
    text(p, 20, 60, "0.70", 7.98)
    text(p, 20, 100, "semantic", 7.98)
    case("S3 单字号通过", d, None, {"S3": "PASS"}, column=80)
    d.close()

    # ---- S2 字号政策 ---------------------------------------------------
    d, p = new_doc()
    text(p, 20, 100, "0.70", 13.0)
    case("S2 抓到 13 pt 超上限", d, None, {"S2": "FAIL"}, column=80)
    d.close()

    # ---- S1 页面 -------------------------------------------------------
    d, p = new_doc(w=159 / 25.4 * 72)
    text(p, 40, 100, "0.70")
    case("S1 抓到 159 mm 当 80 mm 栏用", d, None, {"S1": "FAIL"}, column=80)
    d.close()

    d, p = new_doc(w=71.3 / 25.4 * 72)
    text(p, 40, 100, "0.70")
    case("S1 未满栏正常通过", d, None, {"S1": "PASS"}, column=80)
    d.close()

    # ---- S5 数值守恒 / S13 文字覆盖 -------------------------------------
    ds, ps = new_doc()
    text(ps, 40, 100, "0.918 1")
    d, p = new_doc()
    text(p, 40, 100, "0.928 1")
    case("S5 抓到数值被改（0.9181→0.9281）", d, ds, {"S5": "FAIL"}, column=80)
    d.close()
    ds.close()

    ds, ps = new_doc()
    text(ps, 40, 100, "0.918 1")
    d, p = new_doc()
    text(p, 40, 100, "0.918 1")
    case("S5 同值通过", d, ds, {"S5": "PASS"}, column=80)
    d.close()
    ds.close()

    ds, ps = new_doc()
    text(ps, 40, 100, "0.918 1")
    text(ps, 40, 130, "语义边界")
    d, p = new_doc()
    text(p, 40, 100, "0.918 1")
    case("S13 抓到漏字「语义边界」", d, ds, {"S13": "FAIL"}, column=80)
    d.close()
    ds.close()

    # ---- S6 形状匹配 ---------------------------------------------------
    def penta(cx, cy, r, n=5, rot=0.0):
        return [(cx + r * math.cos(rot + 2 * math.pi * i / n),
                 cy + r * math.sin(rot + 2 * math.pi * i / n)) for i in range(n)]

    ds, ps = new_doc()
    poly(ps, penta(100, 100, 40))
    d, p = new_doc()
    poly(p, penta(100, 100, 20))
    case("S6 同形等比缩放只作为观察", d, ds, {"S6": "WARN"}, column=80)
    d.close()
    ds.close()

    ds, ps = new_doc()
    poly(ps, penta(100, 100, 40))
    d, p = new_doc()
    poly(p, penta(100, 100, 20, rot=0.35))          # 转了角度 = 动了数据
    case("S6 抓到顶点被旋转重排", d, ds, {"S6": "FAIL"}, column=80)
    d.close()
    ds.close()

    ds, ps = new_doc()
    poly(ps, penta(100, 100, 40))
    d, p = new_doc()
    poly(p, penta(100, 100, 20, n=4))               # 五边形变四边形
    case("S6 抓到边数被改（5→4）", d, ds, {"S6": "FAIL"}, column=80)
    d.close()
    ds.close()

    ds, ps = new_doc()
    poly(ps, penta(100, 100, 40))
    d, p = new_doc()
    poly(p, penta(100, 100, 20, rot=0.35))
    case("S6 redraw 模式不判几何（应 SKIP）", d, ds, {"S6": "SKIP"}, column=80, mode="redraw")
    d.close()
    ds.close()

    # ---- S8 页内边距 ---------------------------------------------------
    d, p = new_doc()
    poly(p, [(0.5, 60), (200, 60), (200, 120), (0.5, 120)])   # 左边贴边
    text(p, 40, 90, "0.70")
    case("S8 抓到左侧墨迹贴边 0.5 pt", d, None, {"S8": "WARN"}, column=80)
    d.close()

    # ---- S9 描边 -------------------------------------------------------
    d, p = new_doc()
    poly(p, [(40, 60), (180, 60), (180, 120), (40, 120)], width=1.0)
    text(p, 60, 90, "0.70")
    case("S9 抓到 1.0 pt 描边", d, None, {"S9": "FAIL"}, column=80)
    d.close()

    # ---- S10 位图 ------------------------------------------------------
    d, p = new_doc()
    text(p, 40, 100, "0.70")
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), 0)
    pix.set_rect(pix.irect, (255, 0, 0))
    p.insert_image(fitz.Rect(60, 120, 90, 150), pixmap=pix)
    case("S10 抓到页内位图", d, None, {"S10": "FAIL"}, column=80)
    d.close()

    print(f"\n结果：{ok} / {n} 通过\n")
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
