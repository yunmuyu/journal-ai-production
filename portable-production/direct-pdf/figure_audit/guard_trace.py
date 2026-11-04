"""Advisory path-shape matching."""
from __future__ import annotations
import math
from .guard_core import R

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
