# -*- coding: utf-8 -*-
"""图稿守门器 guard.py —— 对单张已成稿 PDF 做不依赖引擎的独立复核。

设计原则（2026-10-28 教训）：
  1. **不信任引擎自报**。引擎的 pdf_audit 只有 6 条判据，且部分规则按 kind 分支
     （如 numeric-groups-of-three 只对 kind=='chart' 生效），走别的通道就静默不触发。
     本工具直接读 PDF 成品，规则不看 kind、不看 spec、不看报告。
  2. **每条判据都对应一次真实翻车**（见 CHECKS 里各函数的 docstring）。
  3. **有源图就比源图**。只自成稿内部自洽，很容易"错得一致"。

用法：
    python guard.py --out 成稿.pdf [--src 源.pdf] [--column 80] [--mode trace|redraw]
                    [--font-levels 1] [--json report.json]

退出码：0 = 无 FAIL（可有 WARN）；1 = 有 FAIL；2 = 工具自身出错。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import fitz
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "缺 PyMuPDF。请用运行时 python 跑（见 _tools/README.md）：\n"
        "  Install PyMuPDF in the selected environment.\n"
    )
    raise SystemExit(2)

MM = 25.4 / 72.0


# ---------------------------------------------------------------- 基础设施

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

def c_page(r: R, page, column: int | None):
    """S1 页面尺寸。翻车：两张图按 159mm 通栏出，实际都该 80mm 单栏。

    判级：**超栏 = FAIL**（放不进版）；**未满栏 = WARN**（只需说明理由，不算错）。
    这么分是因为"等比缩放后只有 71.3 mm"是合法结果，硬拉满反而破坏等比。
    """
    w_mm = page.rect.width * MM
    h_mm = page.rect.height * MM
    r.facts["page_mm"] = [round(w_mm, 3), round(h_mm, 3)]
    if column is None:
        r.skip("S1", f"未指定栏目，实测 {w_mm:.2f}×{h_mm:.2f} mm")
        return
    if w_mm > column + 0.02:
        r.fail("S1", f"页宽 {w_mm:.2f} mm 超出 {column} mm 栏目（+{w_mm - column:.2f}）")
    elif abs(w_mm - column) > 1.5:
        r.warn("S1", f"未满栏 {w_mm:.2f}×{h_mm:.2f} mm（差 {column - w_mm:.2f} mm）")
    else:
        r.ok("S1", f"{w_mm:.2f}×{h_mm:.2f} mm")


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


def _one_path_pts(d) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for it in d["items"]:
        k = it[0]
        if k == "l":
            if not pts:
                pts.append(tuple(it[1]))
            elif math.dist(pts[-1], tuple(it[1])) > 1e-9:
                pts.append(tuple(it[1]))
            pts.append(tuple(it[2]))
        elif k == "c":
            for p in (it[1], it[2], it[3], it[4]):
                pts.append(tuple(p))
        elif k == "re":
            r = it[1]
            pts += [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
        elif k == "qu":
            q = it[1]
            pts += [tuple(q.ul), tuple(q.ur), tuple(q.lr), tuple(q.ll)]
    return pts


def shape_sig(pts: list[tuple[float, float]], n: int = 32):
    """形状签名：按弧长重采样 n 点 → 减质心 → 除 RMS。

    与平移、缩放、起点无关；比较时再按循环移位对齐，于是也与旋转起点无关。
    这才是判断「图形有没有被改」的正确描述子——bbox 会被文字包围盒污染，
    点对点比对又因为源图文字是转曲轮廓而根本对不上。
    """
    P: list[tuple[float, float]] = []
    for p in pts:
        if not P or math.dist(p, P[-1]) > 1e-9:
            P.append(p)
    if len(P) < 3:
        return None
    if math.dist(P[0], P[-1]) > 1e-6:
        P.append(P[0])
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + math.dist(P[i - 1], P[i]))
    L = acc[-1]
    if L <= 1e-9:
        return None
    out = []
    j = 0
    for k in range(n):
        t = L * k / n
        while j < len(acc) - 2 and acc[j + 1] < t:
            j += 1
        seg = acc[j + 1] - acc[j]
        r = 0.0 if seg <= 0 else (t - acc[j]) / seg
        out.append((P[j][0] + (P[j + 1][0] - P[j][0]) * r,
                    P[j][1] + (P[j + 1][1] - P[j][1]) * r))
    cx = sum(p[0] for p in out) / n
    cy = sum(p[1] for p in out) / n
    q = [(p[0] - cx, p[1] - cy) for p in out]
    rms = math.sqrt(sum(x * x + y * y for x, y in q) / n)
    if rms <= 1e-9:
        return None
    return [(x / rms, y / rms) for x, y in q]


def shape_dist(a, b) -> float:
    n = len(a)
    best = float("inf")
    for s in range(n):
        d = sum((a[i][0] - b[(i + s) % n][0]) ** 2 + (a[i][1] - b[(i + s) % n][1]) ** 2
                for i in range(n)) / n
        if d < best:
            best = d
    return math.sqrt(best)


def c_trace(r: R, page, src_page, mode: str, tol: float):
    """S6 几何忠实度（trace 模式）= 每条 path 的形状必须能在源图里找到同形对应。

    翻车：为了让图满栏，重算了雷达半径和角度 → 用户「你动了原图的矢量图数据！！！
    这是不行的，必须和原图等比例缩小一模一样！！！」

    为什么不用 bbox 比：源图文字是**转曲轮廓**（path 里有字形），成稿是真文字，
    两者的墨迹包围盒天然不等，比值假阳性/假阴性都出过。
    为什么不用点对点：源 115 条 path vs 成稿 17 条，数量都对不上。

    所以只比**形状**：弧长重采样 32 点、去质心、除 RMS，再循环移位取最小 L2。
    纯等比缩放形状不变（距离≈0）；改半径/改角度/重排顶点，形状立刻变形。**反向不要求**
    （源里的字形轮廓不需要在成稿出现，因为被原生文字替代了）。
    """
    if src_page is None:
        r.skip("S6", "无源图，无法比较路径")
        return
    if mode != "trace":
        r.skip("S6", f"mode={mode}（凭版式重画），数值和文字检查不能证明几何忠实")
        return

    src_sigs = []
    for d in src_page.get_drawings():
        sig = shape_sig(_one_path_pts(d))
        if sig:
            src_sigs.append((sig, d["rect"]))
    if not src_sigs:
        r.skip("S6", "源图无 path")
        return

    unmatched = []
    dists = []
    for d in page.get_drawings():
        sig = shape_sig(_one_path_pts(d))
        if not sig:
            continue
        best = min(shape_dist(sig, bs) for bs, _ in src_sigs)
        dists.append(best)
        if best > tol:
            rr = d["rect"]
            unmatched.append({
                "bbox": [round(rr.x0, 1), round(rr.y0, 1), round(rr.x1, 1), round(rr.y1, 1)],
                "dist": round(best, 4),
            })

    r.facts["shape_match"] = {
        "checked": len(dists),
        "max_dist": round(max(dists), 4) if dists else None,
        "unmatched": unmatched,
    }
    if not dists:
        r.skip("S6", "成稿未检测到可比较的矢量路径")
        return
    if unmatched:
        r.fail(
            "S6",
            f"{len(unmatched)}/{len(dists)} 条 path 在源图里找不到同形对应（上限 {tol}），"
            f"几何被改动：{unmatched[:4]}",
        )
    else:
        r.warn("S6", f"{len(dists)} 条成稿路径匹配源路径签名，不能证明源内容完整或相对位置正确；最大距离 {max(dists):.4f}")


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


def c_spacing_ledger(r: R, out_pdf: Path, path: Path | None):
    """S12 间距台账 —— 规则判定 + 台账对账（双保险）。

    翻车经过：图例到绘图区、轴题到轴的距离全靠 magic number，被追问
    「图例和图的距离是多少，纵横轴固定名称距离呢？？？」答不出依据。

    现在判三件事：
      a) **独立重算**：不读台账，直接用 spacing 模块从 PDF 量 12 个角色，
         按 spacing_rules.json 判（target 型给中位+区间，bound 型只判不粘连）；
      b) **台账对账**：台账里的数字必须和重算值差 <0.3 pt，否则就是台账造假/过期；
      c) **来源可溯**：每条必须有 origin / origin_ref，且 size_pt 与成品一致。
    """
    from . import spacing as SP

    sp_ = SP.Spacing()
    led = sp_.measure(out_pdf)
    r.facts["spacing"] = {i["role"]: i["measured_pt"] for i in led["items"]}
    r.facts["spacing_verdict"] = {i["role"]: i["verdict"] for i in led["items"]}

    if not led["items"]:
        r.skip("S12", "本图无可测间距角色（无坐标轴、无图例、无类目标签）")
    else:
        fails = [i for i in led["items"] if i["verdict"] == "FAIL"]
        if fails:
            r.fail("S12", "；".join(f"{i['role']}：{i['note']}" for i in fails))
        else:
            r.warn("S12", f"{len(led['items'])} 项间距为经验观测，需人工复核"
                        f"（{led['n_warn']} 项偏离目标、{led['n_info']} 项仅记录）")

    if path is None:
        r.skip("S12b", "未提供外观台账；可运行 spacing 模块生成（本判据已独立重算，台账用于留痕）")
        return
    if not Path(path).exists():
        r.fail("S12b", f"台账文件不存在：{path}")
        return

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items_raw = data.get("items", []) if isinstance(data, dict) else []
    if not items_raw:
        r.fail("S12b", "台账为空或无 items")
        return

    bad = []
    # 台账是不是这张图的
    if isinstance(data, dict):
        if data.get("size_pt") and abs(float(data["size_pt"]) - led["size_pt"]) > 0.05:
            bad.append(f"字号不符（台账 {data['size_pt']} vs 成品 {led['size_pt']}）")
        if data.get("pdf_sha256") != led["pdf_sha256"]:
            bad.append("台账未绑定当前 PDF 哈希")

    # 逐条：有来源 + 与重算一致
    recalc = {i["role"]: i for i in led["items"]}
    roles = [it.get("role") for it in items_raw]
    if len(roles) != len(set(roles)) or set(roles) != set(recalc):
        bad.append("台账角色集合与当前测量不一致")
    for it in items_raw:
        role = it.get("role") or it.get("name") or "?"
        if not it.get("origin") and not it.get("origin_ref"):
            bad.append(f"{role} 缺 origin/来源")
        hit = recalc.get(role)
        if hit is None:
            bad.append(f"{role} 无法重算")
            continue
        old = it.get("measured_pt")
        if old is not None and abs(float(old) - hit["measured_pt"]) > 0.3:
            bad.append(f"{role} 台账 {float(old):.2f} pt ≠ 重算 {hit['measured_pt']:.2f} pt")

    if bad:
        r.fail("S12b", "台账与成品不符：" + "；".join(bad[:6]))
    else:
        r.ok("S12b", f"{len(items_raw)} 条台账逐条可溯，且与重算值一致（±0.3 pt）")


def c_fingerprint(r: R, out_pdf: Path, src: Path | None, mode: str):
    """S14 版式拓扑指纹 —— redraw 专用。

    翻车经过：图6 被拆成三行叠排，用户「我选错了，不能拆成这样，这是完全错误的」。
    当时这条约束只写在 registry 的备注里，机器不校验。redraw 的图几何本来就变，
    S6 等比用不上，于是"版式有没有被改"完全靠人看。

    现在比几何拓扑：子图数、分组数、每组柱数、组排布方向、柱总数。
    """
    if mode != "redraw":
        r.skip("S14", f"mode={mode}；版式指纹只在 redraw 时判")
        return
    if not src:
        r.skip("S14", "无源图，无法比对拓扑")
        return

    from . import fingerprint as FP

    fs, fo = FP.fp(src), FP.fp(out_pdf)

    rows = FP.compare(fs, fo)
    hard = [x for x in rows if not x.get("soft")]
    bad = [x for x in hard if not x["ok"]]
    r.facts["fingerprint"] = {x["field"]: [x["src"], x["out"]] for x in hard}
    if bad:
        r.fail("S14", "版式拓扑被改：" + "；".join(
            f"{x['desc']} 源 {x['src']} → 稿 {x['out']}" for x in bad))
    else:
        r.warn("S14", f"{len(hard)} 项识别结果一致，需核对检测是否完整（子图 {fo['n_frames']}、"
                    f"{fo['n_groups']} 组×{fo['bars_per_group']}、{fo['group_axis']}）")


# ---------------------------------------------------------------- 主流程

def run(out: Path, src: Path | None, column, mode, font_levels, allow_bitmap, spacing_json):
    doc = fitz.open(out)
    if len(doc) != 1:
        doc.close()
        raise ValueError("审计只接受单页 PDF；请逐页提供文件")
    page = doc[0]
    src_doc = fitz.open(src) if src else None
    if src_doc is not None and len(src_doc) != 1:
        src_doc.close(); doc.close()
        raise ValueError("源图只接受单页 PDF")
    src_page = src_doc[0] if src_doc else None
    r = R(out, src)

    spans = spans_of(page)
    src_spans = spans_of(src_page) if src_page else None

    c_page(r, page, column)
    c_font_policy(r, spans)
    c_font_uniform(r, spans, font_levels)
    c_group3(r, spans)
    c_numbers_conserved(r, spans, src_spans)
    c_text_cover(r, spans, src_spans)
    c_trace(r, page, src_page, mode, tol=0.06)
    c_margin(r, page)
    c_stroke(r, page)
    c_bitmap(r, page, allow_bitmap)
    c_fonts_embedded(r, page)
    c_spacing_ledger(r, out, Path(spacing_json) if spacing_json else None)
    c_fingerprint(r, out, src, mode)

    doc.close()
    if src_doc is not None: src_doc.close()
    return {
        "out": str(out),
        "src": str(src) if src else None,
        "mode": mode,
        "column_mm": column,
        "n_fail": r.n_fail,
        "n_warn": sum(1 for i in r.issues if i["level"] == "WARN"),
        "status": "FAIL" if r.n_fail else "INCOMPLETE",
        "issues": r.issues,
        "facts": r.facts,
    }


HELP = """Usage: python -m figure_audit.guard --out FILE [--src FILE] [--column 80|110|159] [--mode trace|redraw] [--json REPORT]
Results are incomplete pending source and visual review. Exit 1: flagged; 3: no flags but incomplete; 2: invalid input.
"""


def parse_argv(argv: list[str]) -> dict:
    a = {"out": None, "src": None, "column": None, "mode": "trace",
         "font_levels": None, "allow_bitmap": 0, "spacing_json": None, "json": None}
    ints = {"column", "font_levels", "allow_bitmap"}
    pos: list[str] = []
    given: set[str] = set()
    i = 0
    while i < len(argv):
        k = argv[i]
        if k in ("-h", "--help"):
            print(HELP)
            raise SystemExit(0)
        if k.startswith("--"):
            name = k[2:].replace("-", "_")
            if name not in a:
                raise SystemExit(f"未知参数 {k}\n{HELP}")
            if i + 1 >= len(argv):
                raise SystemExit(f"参数 {k} 缺值\n{HELP}")
            a[name] = int(argv[i + 1]) if name in ints else argv[i + 1]
            given.add(name)
            i += 2
        else:
            pos.append(k)
            i += 1
    # 位置参数只在没被 --xxx 显式给过时才填（mode 有默认值 trace，不能拿 None 判断）
    for j, key in enumerate(["out", "src", "column", "mode"]):
        if j < len(pos) and key not in given:
            a[key] = int(pos[j]) if key == "column" else pos[j]
    if a["out"] is None:
        print(HELP)
        raise SystemExit(2)
    if a["column"] is not None and a["column"] not in (80, 110, 159):
        raise SystemExit(f"栏宽只能是 80/110/159，给的是 {a['column']}")
    if a["mode"] not in ("trace", "redraw"):
        raise SystemExit(f"模式只能是 trace/redraw，给的是 {a['mode']}")
    return a


def main(argv=None):
    try:
        a = parse_argv(list(sys.argv[1:] if argv is None else argv))
    except SystemExit as e:
        if isinstance(e.code, int): return e.code
        print(e.code, file=sys.stderr)
        return 2

    rep = run(Path(a["out"]), Path(a["src"]) if a["src"] else None, a["column"],
              a["mode"], a["font_levels"], a["allow_bitmap"], a["spacing_json"])

    if a["json"]:
        if Path(a["json"]).resolve() in {Path(a["out"]).resolve(), Path(a["src"]).resolve() if a["src"] else None, Path(a["spacing_json"]).resolve() if a["spacing_json"] else None}:
            raise ValueError("报告路径不能覆盖输入 PDF")
        Path(a["json"]).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    icon = {"FAIL": "×", "WARN": "!", "PASS": "√", "SKIP": "·"}
    print(f"\n{Path(a['out']).name}  →  {rep['status']}  (FAIL {rep['n_fail']} / WARN {rep['n_warn']})")
    for i in rep["issues"]:
        print(f"  {icon.get(i['level'], '?')} {i['code']:4s} {i['msg']}")
    return 1 if rep["n_fail"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
