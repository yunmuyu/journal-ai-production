"""Conservative evidence for proportional sizing of a single-page PDF."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Final, Literal, TypedDict

import fitz

from .errors import AuditInputError

WIDTHS_MM: Final = (80, 160)


class TextSize(TypedDict):
    size_pt: float
    characters: int


class Estimate(TypedDict):
    width_mm: int
    scale: float
    dominant_text_pt: float | None


class PrescanReport(TypedDict):
    status: Literal["INCOMPLETE"]
    source_sha256: str
    page_width_pt: float
    page_height_pt: float
    text_sizes: list[TextSize]
    proportional_estimates: list[Estimate]
    limitations: list[str]


def _digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def inspect_pdf(path: Path) -> PrescanReport:
    """Measure source-page evidence, without deciding suitability or acceptance."""
    try:
        before = _digest(path)
        with fitz.open(str(path)) as document:
            if not document.is_pdf or document.needs_pass or len(document) != 1:
                raise AuditInputError("需要未加密的单页 PDF")
            page = document[0]
            width, height = page.rect.width, page.rect.height
            if width <= 0 or height <= 0:
                raise AuditInputError("页面尺寸无效")
            counts: Counter[float] = Counter()
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        count = sum(not char.isspace() for char in span["text"])
                        if count:
                            counts[round(float(span["size"]), 2)] += count
        if _digest(path) != before:
            raise AuditInputError("读取期间源文件发生变化")
    except (OSError, fitz.FileDataError, fitz.EmptyFileError) as exc:
        raise AuditInputError(f"无法读取 PDF: {exc}") from exc
    sizes: list[TextSize] = [
        {"size_pt": size, "characters": count}
        for size, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    dominant = sizes[0]["size_pt"] if sizes else None
    estimates: list[Estimate] = []
    for target in WIDTHS_MM:
        scale = min(1.0, target * 72 / 25.4 / width)
        estimates.append({"width_mm": target, "scale": scale,
                          "dominant_text_pt": dominant * scale if dominant is not None else None})
    return {
        "status": "INCOMPLETE", "source_sha256": before,
        "page_width_pt": width, "page_height_pt": height,
        "text_sizes": sizes, "proportional_estimates": estimates,
        "limitations": [
            "仅按整页等比缩小估算，未考虑裁边、换字、折行或重绘。",
            "只统计可提取文字，不代表位图、轮廓字或全部文字的字号。",
            "结果不是单栏可行性、规范合格或视觉验收结论，须人工核对。",
        ],
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--json", type=Path, help="写入尚不存在的报告文件")
    args = parser.parse_args()
    try:
        report = inspect_pdf(args.source)
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.json is not None:
            with args.json.open("x", encoding="utf-8") as output:
                output.write(payload)
        print(payload, end="")
    except (AuditInputError, OSError) as exc:
        print(f"预检失败: {exc}", file=sys.stderr)
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
