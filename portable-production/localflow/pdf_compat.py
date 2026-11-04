from __future__ import annotations

import math
import re
from dataclasses import asdict
from pathlib import Path

import pymupdf as fitz

from .core import FlowError
from .pdf_render import audit_pdf_render


def _descriptor_xref(doc: fitz.Document, font_xref: int, subtype: str) -> int:
    descendant = font_xref
    if subtype == "Type0":
        kind, value = doc.xref_get_key(font_xref, "DescendantFonts")
        if kind == "xref":
            target = int(value.split()[0])
            if doc.xref_get_key(target, "Subtype")[0] == "name":
                targets = [str(target)]
            else:
                targets = re.findall(r"(\d+)\s+\d+\s+R", doc.xref_object(target))
        else:
            targets = re.findall(r"(\d+)\s+\d+\s+R", value) if kind == "array" else []
        if len(targets) != 1:
            raise FlowError("pdf_font_descriptor", f"Type0 字体后代对象无效：xref={font_xref}")
        descendant = int(targets[0])
    kind, value = doc.xref_get_key(descendant, "FontDescriptor")
    if kind != "xref":
        raise FlowError("pdf_font_descriptor", f"字体描述对象缺失：xref={descendant}")
    return int(value.split()[0])


def audit_pdf_compatibility(path: Path) -> dict:
    render_check = audit_pdf_render(path)
    if not render_check.passed:
        if render_check.diagnostic_kind:
            label = "PDF 结构诊断未通过" if render_check.diagnostic_kind == "pdf_structure" else "PDF 渲染时的解码诊断未通过"
            raise FlowError(render_check.diagnostic_kind,
                            f"{label}（已渲染 {render_check.rendered_pages}/{render_check.page_count} 页）：{render_check.error}")
        raise FlowError("pdf_render", f"PDF 实际渲染失败：{render_check.error}")
    descriptors: dict[int, dict] = {}
    type3_fonts: set[int] = set()
    page_count = 0
    try:
        with fitz.open(path) as doc:
            page_count = len(doc)
            if page_count < 1:
                raise FlowError("pdf_compatibility", "PDF 没有页面")
            if doc.is_encrypted:
                raise FlowError("pdf_compatibility", "PDF 已加密")
            for page in doc:
                if page.rotation != 0:
                    raise FlowError("pdf_compatibility", "PDF 页面含旋转标记")
                if any(True for _ in (page.annots() or [])):
                    raise FlowError("pdf_compatibility", "PDF 页面含批注对象")
                if not page.get_texttrace():
                    continue
                for row in page.get_fonts(full=True):
                    font_xref, subtype = row[0], row[2]
                    if subtype == "Type3":
                        type3_fonts.add(font_xref)
                        continue
                    descriptor = _descriptor_xref(doc, font_xref, subtype)
                    if descriptor in descriptors:
                        continue
                    kind, value = doc.xref_get_key(descriptor, "CapHeight")
                    if kind not in {"int", "float"}:
                        raise FlowError(
                            "pdf_font_descriptor",
                            f"字体描述缺少有效 /CapHeight：xref={descriptor}",
                        )
                    cap_height = float(value)
                    if not math.isfinite(cap_height) or cap_height <= 0:
                        raise FlowError(
                            "pdf_font_descriptor",
                            f"字体描述 /CapHeight 无效：xref={descriptor}",
                        )
                    streams = sum(
                        doc.xref_get_key(descriptor, key)[0] == "xref"
                        for key in ("FontFile", "FontFile2", "FontFile3")
                    )
                    if streams != 1:
                        raise FlowError(
                            "pdf_font_embedding",
                            f"字体未完整嵌入：xref={descriptor}",
                        )
                    descriptors[descriptor] = {
                        "xref": descriptor,
                        "font_name": doc.xref_get_key(descriptor, "FontName")[1],
                        "cap_height": cap_height,
                    }
    except FlowError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise FlowError("pdf_compatibility", f"PDF 兼容性检查失败：{exc}") from exc
    return {
        "passed": True,
        "page_count": page_count,
        "font_descriptors": list(descriptors.values()),
        "type3_font_count": len(type3_fonts),
        "render_check": asdict(render_check),
    }


def audit_delivery_pdfs(root: Path) -> dict:
    files = sorted(root.rglob("*.pdf"))
    issues = []
    type3_files = 0
    for path in files:
        try:
            report = audit_pdf_compatibility(path)
            type3_files += int(report["type3_font_count"] > 0)
        except FlowError as exc:
            issues.append({
                "path": str(path.relative_to(root)),
                "code": exc.code,
                "detail": str(exc),
            })
    return {
        "status": "passed" if not issues else "blocked",
        "root": str(root),
        "pdf_count": len(files),
        "passed_count": len(files) - len(issues),
        "issue_count": len(issues),
        "type3_file_count": type3_files,
        "issues": issues,
    }
