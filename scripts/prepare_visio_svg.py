#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# ─── How to run ───
# 1. Install uv if needed.
# 2. Run: uv run scripts/prepare_visio_svg.py INPUT.svg OUTPUT.svg REPORT.json
# 3. The output and report paths must not exist.
# ──────────────────
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict

SVG: Final = "http://www.w3.org/2000/svg"
XLINK: Final = "http://www.w3.org/1999/xlink"
VISIO: Final = "http://schemas.microsoft.com/visio/2003/SVGExtensions/"
MARKERS: Final = ("marker-start", "marker-mid", "marker-end")
STYLE_KEYS: Final = ("display", "visibility", "opacity", "stroke", "stroke-opacity")
CSS_RULE: Final = re.compile(r"\s*\.([A-Za-z_][\w-]*)\s*\{([^{}]*)\}")
DOCTYPE: Final = re.compile(rb"<!DOCTYPE\s+[^>]*>", re.IGNORECASE)
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)
ET.register_namespace("v", VISIO)


class Prepared(TypedDict):
    sourceId: str | None
    sourcePath: str
    bodyId: str


class Risk(TypedDict):
    code: str
    path: str
    detail: str


@dataclass(frozen=True, slots=True)
class UnsupportedSvg(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


def declarations(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in value.split(";"):
        if not part.strip():
            continue
        if ":" not in part:
            raise UnsupportedSvg(f"Malformed CSS declaration: {part[:80]}")
        key, raw = part.split(":", 1)
        result[key.strip().lower()] = raw.strip()
    return result


def stylesheet(root: ET.Element) -> tuple[dict[str, dict[str, str]], list[Risk]]:
    classes: dict[str, dict[str, str]] = {}
    risks: list[Risk] = []
    for style in root.iter(f"{{{SVG}}}style"):
        source = re.sub(r"/\*.*?\*/", "", "".join(style.itertext()), flags=re.DOTALL)
        position = 0
        for rule in CSS_RULE.finditer(source):
            if source[position:rule.start()].strip():
                risks.append({"code": "unsupported-css", "path": "style", "detail": source[position:rule.start()].strip()[:120]})
            position = rule.end()
            selector = rule.group(1)
            try:
                classes.setdefault(selector, {}).update(declarations(rule.group(2)))
            except UnsupportedSvg as error:
                risks.append({"code": "unsupported-css", "path": f".{selector}", "detail": str(error)})
        if source[position:].strip():
            risks.append({"code": "unsupported-css", "path": "style", "detail": source[position:].strip()[:120]})
    return classes, risks


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def properties(node: ET.Element, classes: dict[str, dict[str, str]]) -> dict[str, str]:
    result = {local(key): value for key, value in node.attrib.items() if local(key) in (*MARKERS, *STYLE_KEYS)}
    for name in node.get("class", "").split():
        result.update(classes.get(name, {}))
    result.update(declarations(node.get("style", "")))
    return result


def hidden(node: ET.Element, parents: dict[ET.Element, ET.Element], classes: dict[str, dict[str, str]]) -> bool:
    cursor: ET.Element | None = node
    while cursor is not None:
        prop = properties(cursor, classes)
        if prop.get("display") == "none" or prop.get("visibility") == "hidden" or prop.get("opacity") in {"0", "0.0"}:
            return True
        cursor = parents.get(cursor)
    return False


def location(node: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    parts: list[str] = []
    cursor: ET.Element | None = node
    while cursor is not None:
        parent = parents.get(cursor)
        label = local(cursor.tag)
        if parent is not None:
            label += f"[{list(parent).index(cursor) + 1}]"
        parts.append(label)
        cursor = parent
    return "/".join(reversed(parts))


def in_definition(node: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    cursor: ET.Element | None = node
    while cursor is not None:
        if local(cursor.tag) in {"defs", "marker", "symbol", "clipPath", "mask"}:
            return True
        cursor = parents.get(cursor)
    return False


def compatibility_risks(root: ET.Element) -> list[Risk]:
    risks: list[Risk] = []
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        tag = local(node.tag)
        if tag in {"linearGradient", "radialGradient", "pattern", "filter", "mask"}:
            risks.append({"code": "unsupported-structure", "path": tag,
                          "detail": node.get("id", "unnamed")})
        for key, value in node.attrib.items():
            if local(key) in {"filter", "mask"} and value not in {"none", ""}:
                risks.append({"code": "unsupported-effect", "path": tag,
                              "detail": f"{local(key)}={value[:80]}"})
    return risks


def prepare(source: Path, output: Path, report_path: Path) -> None:
    paths = (source.resolve(), output.resolve(), report_path.resolve())
    if len(set(paths)) != 3 or output.exists() or report_path.exists():
        raise UnsupportedSvg("Input, output and report must be distinct; output and report must be new")
    raw = source.read_bytes()
    if b"<!ENTITY" in raw.upper() or re.search(rb"<!DOCTYPE[^>]*\[", raw, re.IGNORECASE):
        raise UnsupportedSvg("Internal DTD/entities are unsupported; source was not expanded")
    safe = DOCTYPE.sub(b"", raw)
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    root = ET.fromstring(safe, parser=parser)
    if root.tag != f"{{{SVG}}}svg":
        raise UnsupportedSvg("Input root is not SVG")
    classes, css_risks = stylesheet(root)
    risks = [*css_risks, *compatibility_risks(root)]
    parents = {child: parent for parent in root.iter() for child in parent}
    existing_ids = {node.get("id") for node in root.iter() if node.get("id")}
    prepared: list[Prepared] = []
    skipped_hidden: list[str] = []
    for node in list(root.iter(f"{{{SVG}}}path")):
        if in_definition(node, parents):
            continue
        place = location(node, parents)
        own = properties(node, classes)
        own_marker = any(own.get(key, "").startswith("url(#") for key in MARKERS)
        if css_risks:
            continue
        if not own_marker:
            if any(properties(ancestor, classes).get(key, "").startswith("url(#")
                   for key in MARKERS for ancestor in ancestors(node, parents)):
                risks.append({"code": "inherited-marker", "path": place, "detail": "Marker declared on ancestor"})
            continue
        if node.get("data-visio-line-body") in existing_ids:
            continue
        unknown_classes = [name for name in node.get("class", "").split() if name not in classes]
        if unknown_classes:
            risks.append({"code": "unknown-class", "path": place, "detail": ",".join(unknown_classes)})
            continue
        if "stroke" not in own:
            risks.append({"code": "inherited-stroke", "path": place, "detail": "Stroke is not local to path"})
            continue
        opacity = [(key, properties(part, classes)[key]) for part in [node, *ancestors(node, parents)]
                   for key in ("opacity", "stroke-opacity") if key in properties(part, classes)]
        if any(value not in {"0", "0.0", "1", "1.0"} for _, value in opacity):
            risks.append({"code": "partial-opacity", "path": place, "detail": str(opacity)})
            continue
        if hidden(node, parents, classes) or own.get("stroke") == "none" or own.get("stroke-opacity") in {"0", "0.0"}:
            skipped_hidden.append(place)
            continue
        if not node.get("d"):
            risks.append({"code": "missing-path-data", "path": place, "detail": "Marker path lacks d"})
            continue
        parent = parents[node]
        body = ET.fromstring(ET.tostring(node, encoding="unicode"))
        candidate = f"{node.get('id') or 'path'}-line-body"
        suffix = 2
        while candidate in existing_ids:
            candidate = f"{node.get('id') or 'path'}-line-body-{suffix}"
            suffix += 1
        existing_ids.add(candidate)
        body.set("id", candidate)
        node.set("data-visio-line-body", candidate)
        base = node.get("style", "").rstrip("; ")
        body.set("style", f"{base};" if base else "")
        body.set("style", body.get("style", "") + "fill:none;marker-start:none;marker-mid:none;marker-end:none")
        parent.insert(list(parent).index(node), body)
        prepared.append({"sourceId": node.get("id"), "sourcePath": place, "bodyId": candidate})
    output.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    result = {"source": str(paths[0]), "sourceHash": hashlib.sha256(raw).hexdigest(),
              "output": str(paths[1]), "outputHash": hashlib.sha256(output.read_bytes()).hexdigest(),
              "prepared": prepared, "skippedHidden": skipped_hidden, "risks": risks,
              "productionCompatibility": "needs_review" if risks else "candidate",
              "scope": "Simple class/inline SVG marker paths; no text, image or gradient rewriting"}
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def ancestors(node: ET.Element, parents: dict[ET.Element, ET.Element]) -> list[ET.Element]:
    result: list[ET.Element] = []
    cursor = parents.get(node)
    while cursor is not None:
        result.append(cursor)
        cursor = parents.get(cursor)
    return result


def main() -> int:
    cli = argparse.ArgumentParser(description="Prepare Visio SVG marker path line bodies")
    cli.add_argument("input", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("report", type=Path)
    args = cli.parse_args()
    try:
        prepare(args.input, args.output, args.report)
    except (UnsupportedSvg, ET.ParseError, OSError) as error:
        print(f"Visio SVG preparation failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
