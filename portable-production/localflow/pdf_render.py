"""Isolated PDF render gate; decoding success is not visual approval.

CLI: python portable-production/localflow/pdf_render.py <candidate.pdf>
Uses the existing PyMuPDF dependency; emits JSON and exits nonzero on failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import pymupdf as fitz


@dataclass(frozen=True, slots=True)
class RenderCheck:
    passed: bool
    page_count: int
    rendered_pages: int
    error: str = ""
    diagnostic_kind: Literal["", "pdf_structure", "pdf_decoder"] = ""


def _render_worker(path: Path) -> RenderCheck:
    """Render all pages in a fresh process so MuPDF diagnostics cannot leak."""
    fitz.TOOLS.mupdf_display_errors(False)
    fitz.TOOLS.mupdf_display_warnings(False)
    fitz.TOOLS.reset_mupdf_warnings()
    count = 0
    rendered = 0
    try:
        with fitz.open(path) as doc:
            count = len(doc)
            if not count or doc.is_encrypted:
                return RenderCheck(False, count, rendered, "empty or encrypted PDF")
            for page in doc:
                scale = min(1.0, 1024 / max(page.rect.width, page.rect.height, 1))
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                if pix.width < 1 or pix.height < 1:
                    return RenderCheck(False, count, rendered, "empty raster")
                rendered += 1
                diagnostics = fitz.TOOLS.mupdf_warnings()
                if diagnostics:
                    # Classify only the reproduced outline diagnostic. Mixed or
                    # unknown warnings remain decoder failures, never approvals.
                    structure_only = all(line == "Bad or missing last pointer in outline tree, repairing"
                                         for line in diagnostics.splitlines())
                    return RenderCheck(False, count, rendered, diagnostics,
                                       "pdf_structure" if structure_only else "pdf_decoder")
    except (OSError, RuntimeError, ValueError) as exc:
        return RenderCheck(False, count, rendered, str(exc))
    return RenderCheck(True, count, rendered)


def audit_pdf_render(path: Path) -> RenderCheck:
    """Require a complete render without decoder warnings, in isolation."""
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker", str(path.resolve())],
            capture_output=True, text=True, encoding="utf-8", timeout=180, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RenderCheck(False, 0, 0, str(exc))
    try:
        report = RenderCheck(**json.loads(result.stdout))
    except (ValueError, TypeError) as exc:
        return RenderCheck(False, 0, 0, f"invalid render report: {exc}")
    if result.returncode != 0 or result.stderr.strip():
        return RenderCheck(False, report.page_count, report.rendered_pages,
                           report.error or result.stderr or "render process failed",
                           report.diagnostic_kind if not result.stderr.strip() else "")
    if not report.passed or report.page_count < 1 or report.rendered_pages != report.page_count:
        return RenderCheck(False, report.page_count, report.rendered_pages,
                           report.error or "incomplete render", report.diagnostic_kind)
    return report


if __name__ == "__main__":
    worker = len(sys.argv) == 3 and sys.argv[1] == "--worker"
    if len(sys.argv) != 2 and not worker:
        print(json.dumps(asdict(RenderCheck(False, 0, 0, "expected one PDF path"))))
        raise SystemExit(2)
    check = _render_worker(Path(sys.argv[2])) if worker else audit_pdf_render(Path(sys.argv[1]))
    print(json.dumps(asdict(check), ensure_ascii=True))
    raise SystemExit(0 if check.passed else 1)
