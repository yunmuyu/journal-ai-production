"""Experimental PDF figure inspection CLI; results require human review."""
from __future__ import annotations
import json, sys
from pathlib import Path
import fitz
from .types import GuardArguments
from .errors import AuditInputError
from .guard_core import R, spans_of, ink_bbox, group3, num_segments, is_grouped, numbers_of
from .guard_checks import c_page, c_font_policy, c_font_uniform, c_group3, c_numbers_conserved, c_text_cover, c_margin, c_stroke, c_bitmap, c_fonts_embedded
from .guard_trace import shape_sig, shape_dist, c_trace
from .guard_ledger import c_spacing_ledger, c_fingerprint

def run(out: Path, src: Path | None, column, mode, font_levels, allow_bitmap, spacing_json):
    doc = fitz.open(out)
    if len(doc) != 1:
        doc.close()
        raise AuditInputError("审计只接受单页 PDF；请逐页提供文件")
    page = doc[0]
    src_doc = fitz.open(src) if src else None
    if src_doc is not None and len(src_doc) != 1:
        src_doc.close(); doc.close()
        raise AuditInputError("源图只接受单页 PDF")
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


HELP = """Usage: python -m figure_audit.guard --out FILE [--src FILE] [--column 80|110|159] [--mode trace|redraw] [--allow-bitmap N] [--json REPORT]
--allow-bitmap N sets the maximum image count; it does not verify image content or source fidelity.
Results are incomplete pending source and visual review. Exit 1: flagged; 3: no flags but incomplete; 2: invalid input.
"""


def parse_argv(argv: list[str]) -> GuardArguments:
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
            raise AuditInputError("报告路径不能覆盖输入 PDF")
        Path(a["json"]).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    icon = {"FAIL": "×", "WARN": "!", "PASS": "√", "SKIP": "·"}
    print(f"\n{Path(a['out']).name}  →  {rep['status']}  (FAIL {rep['n_fail']} / WARN {rep['n_warn']})")
    for i in rep["issues"]:
        print(f"  {icon.get(i['level'], '?')} {i['code']:4s} {i['msg']}")
    return 1 if rep["n_fail"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
