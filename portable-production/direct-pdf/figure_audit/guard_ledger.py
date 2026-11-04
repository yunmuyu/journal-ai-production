"""Spacing ledger and topology observations."""
from __future__ import annotations
import json, math
from pathlib import Path
from .guard_core import R

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
        if isinstance(old, bool) or not isinstance(old, (int, float)) or not math.isfinite(old):
            bad.append(f"{role} 缺少有效测量值")
        elif abs(float(old) - hit["measured_pt"]) > 0.3:
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
