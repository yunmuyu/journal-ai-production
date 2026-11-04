"""PDF page, text and drawing observations."""
from __future__ import annotations
from collections import Counter
from .guard_core import R, MM, ink_bbox, numbers_of, is_grouped, _strip

def c_page(r: R, page, column: int | None):
    """S1 页面尺寸。翻车：两张图按 159mm 通栏出，实际都该 80mm 单栏。

    栏宽是上限：超栏为 FAIL，未满栏本身不构成异常。
    """
    w_mm = page.rect.width * MM
    h_mm = page.rect.height * MM
    r.facts["page_mm"] = [round(w_mm, 3), round(h_mm, 3)]
    if column is None:
        r.skip("S1", f"未指定栏目，实测 {w_mm:.2f}×{h_mm:.2f} mm")
        return
    if w_mm > column + 0.02:
        r.fail("S1", f"页宽 {w_mm:.2f} mm 超出 {column} mm 栏目（+{w_mm - column:.2f}）")
    else:
        r.ok("S1", f"{w_mm:.2f}×{h_mm:.2f} mm（栏目上限 {column} mm）")


def c_font_policy(r: R, spans: list[dict]):
    """S2 字号 6—8pt。"""
    if not spans:
        r.skip("S2", "无文字")
        return
    sizes = sorted({round(s["size"], 3) for s in spans})
    r.facts["font_sizes"] = sizes
    bad = [s for s in sizes if s < 5.95 or s > 8.05]
    if bad:
        r.fail("S2", f"字号越界 {bad}（政策 6—8 pt）", sizes=sizes)
    else:
        r.ok("S2", f"全 {sizes} pt")


def c_font_uniform(r: R, spans: list[dict], max_levels: int):
    """S3 字号唯一性。翻车：环标 6.58 pt 与其余 8 pt 并存，被用户抓『0.70和其他的字号！』。

    等比缩放 + 源图多级字号（13/11/9 pt）→ 缩后必然分裂成三级；
    必须在设计期就把图整体用**一个**字号重设，而不是各级各缩一遍。
    """
    if not spans:
        r.skip("S3", "无文字")
        return
    sizes = sorted({round(s["size"] * 20) / 20 for s in spans})   # 0.05 pt 粒度
    if max_levels is None:
        r.warn("S3", f"检测到 {len(sizes)} 级字号；须结合图意核查")
        return
    if len(sizes) > max_levels:
        cnt = Counter(round(s["size"], 3) for s in spans)
        r.fail(
            "S3",
            f"出现 {len(sizes)} 级字号 {sizes}，上限 {max_levels}",
            detail={str(k): v for k, v in cnt.items()},
        )
    else:
        r.ok("S3", f"{len(sizes)} 级字号")


def c_group3(r: R, spans: list[dict]):
    """S4 三位一空。翻车：规则在引擎里只对 kind=='chart' 生效，流程图/雷达图静默漏检。

    本判据不看 kind，只要页里有数字就查。
    """
    if not spans:
        r.skip("S4", "无可提取文字，无法检查数值格式")
        return
    bad = []
    for s in spans:
        if not is_grouped(s["text"]):
            bad.append(s["text"])
    if bad:
        r.fail("S4", f"{len(bad)} 处数字未按三位一空分组", samples=bad[:8])
    else:
        r.ok("S4", f"扫过 {len(spans)} 个文字块")


def c_numbers_conserved(r: R, out_spans: list[dict], src_spans: list[dict] | None):
    """S5 数值守恒。翻车：改版式时手抄数值，错一位没人发现。

    源图所有可提取数值，成稿必须一个不多一个不少（按格式无关比较）。
    """
    if not src_spans:
        r.skip("S5", "无可提取的源文字")
        return
    a, b = numbers_of(src_spans), numbers_of(out_spans)
    if not a:
        r.skip("S5", "源文字中没有可提取数值")
        return
    if a == b:
        r.ok("S5", f"{sum(b.values())} 个数值与源图完全一致")
        return
    miss = a - b
    extra = b - a
    parts = []
    if miss:
        parts.append(f"缺 {dict(miss)}")
    if extra:
        parts.append(f"多 {dict(extra)}")
    r.fail("S5", "数值与源图不一致：" + "；".join(parts))


def c_text_cover(r: R, out_spans: list[dict], src_spans: list[dict] | None):
    """S13 文字覆盖。源图能提出来的字，成稿必须都在。"""
    if not src_spans:
        r.skip("S13", "无可提取的源文字")
        return
    a = Counter(_strip(s["text"]) for s in src_spans if s["text"].strip())
    b = Counter(_strip(s["text"]) for s in out_spans if s["text"].strip())
    miss = a - b
    if miss:
        r.fail("S13", f"成稿缺源图文字：{list(miss)[:8]}")
    else:
        r.ok("S13", f"覆盖源图 {len(a)} 条文字")


def c_margin(r: R, page):
    """S8 页内边距 / 出血。翻车：把页框直接设成墨迹外接框，四边贴边、右侧还差 0.26 pt 出界。"""
    b = ink_bbox(page)
    if not b:
        r.skip("S8", "墨迹为空")
        return
    w, h = page.rect.width, page.rect.height
    m = {"L": b[0], "T": b[1], "R": w - b[2], "B": h - b[3]}
    r.facts["margins_pt"] = {k: round(v, 3) for k, v in m.items()}
    out = {k: v for k, v in m.items() if v < 0}
    if out:
        r.fail("S8", "墨迹出界：" + "、".join(f"{k}{v:+.2f}pt" for k, v in out.items()))
        return
    tight = {k: v for k, v in m.items() if v < 2.0}
    if tight:
        r.warn("S8", "边距 < 2 pt：" + "、".join(f"{k}{v:.2f}" for k, v in tight.items()))
    else:
        r.ok("S8", "四边 " + " ".join(f"{k}{v:.2f}" for k, v in m.items()))


def c_stroke(r: R, page, target: float = 0.5):
    """S9 描边宽度。本刊统一 0.5 pt。

    分级：0.44—0.56 = PASS；0.30—0.44 / 0.56—0.70 = WARN（多为图标内部细节线，
    或 0.5 pt 经缩放后留下的残差）；更离谱才 FAIL。
    图3 的 0.556/0.645/0.461 就是图标细节线，不该按"错"处理。
    """
    ws = Counter()
    for d in page.get_drawings():
        w = d.get("width") or 0
        if w > 0:
            ws[round(w, 3)] += 1
    if not ws:
        r.skip("S9", "无描边 path")
        return
    fail = {k: v for k, v in ws.items() if abs(k - target) > 0.20}
    warn = {k: v for k, v in ws.items() if 0.06 < abs(k - target) <= 0.20}
    if fail:
        r.fail("S9", f"描边偏离 {target} pt 超过 0.2：{fail}")
    elif warn:
        r.warn("S9", f"描边微差（图标细节/缩放残差）：{warn}")
    else:
        r.ok("S9", f"{sum(ws.values())} 条描边全 {target} pt")


def c_bitmap(r: R, page, allow: int):
    """S10 位图。"""
    n = len(page.get_images(full=True))
    r.facts["bitmaps"] = n
    if n > allow:
        r.fail("S10", f"页内位图 {n} 个（上限 {allow}）")
    else:
        r.ok("S10", f"位图 {n} 个")


def c_fonts_embedded(r: R, page):
    """S11 字体全嵌。ext 为 'n/a' 表示未嵌入。"""
    fs = page.get_fonts(full=True)
    if not fs:
        r.skip("S11", "无可检查字体")
        return
    bad = [f[3] for f in fs if str(f[1]).lower() in ("n/a", "none", "")]
    r.facts["fonts"] = [f[3] for f in fs]
    if bad:
        r.fail("S11", f"未嵌入：{bad}")
    else:
        r.ok("S11", f"{len(fs)} 个字体全嵌")
