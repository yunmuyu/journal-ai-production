"""Conservative parallel SVG font-family preprocessing; not a renderer or acceptance authority.

Color remains with normalize_svg_color.py; final size/strokes/ink remain native responsibilities.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import multiprocessing
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "jfw-headless-font-family-v1"
SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ALLOWED = {"svg", "g", "defs", "clipPath", "path", "rect", "line", "polyline", "polygon", "circle", "ellipse", "text", "title", "desc", "use"}
MAX_BYTES = 20_000_000
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def properties(style: str) -> list[tuple[str, str]]:
    result = []
    for pair in style.split(";"):
        if not pair.strip():
            continue
        if ":" not in pair:
            raise ValueError("Malformed inline style")
        key, value = (part.strip() for part in pair.split(":", 1))
        if key in {"font", "direction", "unicode-bidi", "writing-mode"} or "!important" in value.lower():
            raise ValueError("Complex text CSS requires native route")
        if key in [old for old, _ in result]:
            raise ValueError("Duplicate style declaration")
        result.append((key, value))
    return result

def geometry(root: ET.Element) -> str:
    result = []
    for element in root.iter():
        attributes = {}
        for key, value in element.attrib.items():
            if key == "font-family":
                continue
            if key == "style":
                attributes[key] = [(k, v) for k, v in properties(value) if k != "font-family"]
            else:
                attributes[key] = value
        result.append(["#comment" if element.tag is ET.Comment else element.tag, attributes, element.text, element.tail])
    return sha(canonical(result))

def transform(data: bytes, font_map: dict[str, str]) -> tuple[bytes, dict]:
    if len(data) > MAX_BYTES:
        raise ValueError("SVG exceeds preprocessing size limit")
    text = data.decode("utf-8-sig")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)|<\?xml-stylesheet", text, re.I):
        raise ValueError("External XML declarations unsupported")
    if not isinstance(font_map, dict) or not font_map or any(
        not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
        or any(char in v for char in ";{}<>\n\r") for k, v in font_map.items()
    ):
        raise ValueError("Explicit safe font-family mapping required")
    root = ET.fromstring(text, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    if root.tag != f"{{{SVG}}}svg":
        raise ValueError("Namespaced SVG root required")
    nodes = list(root.iter())
    if len(nodes) > 100_000:
        raise ValueError("SVG exceeds node limit")
    ids = [e.get("id") for e in nodes if e.get("id")]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate SVG object id")
    for element in nodes:
        if element.tag is ET.Comment:
            continue
        tag = element.tag.removeprefix(f"{{{SVG}}}")
        if not element.tag.startswith(f"{{{SVG}}}") or tag not in ALLOWED:
            raise ValueError(f"Unsupported SVG element: {tag}")
        for key, value in element.attrib.items():
            local = key.split("}")[-1]
            if local.lower().startswith("on") or local in {"textLength", "lengthAdjust", "font", "direction", "unicode-bidi", "writing-mode"}:
                raise ValueError("Event handler or complex text attribute unsupported")
            if local == "href" and (not value.startswith("#") or value[1:] not in ids):
                raise ValueError("External or unresolved SVG reference")
            for target in re.findall(r"url\((.*?)\)", value, re.I):
                if not target.startswith("#") or target[1:] not in ids:
                    raise ValueError("External or unresolved SVG paint reference")
            if local == "style":
                properties(value)
    if not any(e.tag == f"{{{SVG}}}text" for e in nodes):
        raise ValueError("No editable SVG text; use existing outlined-source adapter")
    before = geometry(root)
    changes = 0
    for element in nodes:
        family = element.get("font-family")
        if family in font_map and font_map[family] != family:
            element.set("font-family", font_map[family]); changes += 1
        if "style" in element.attrib:
            pairs = properties(element.attrib["style"])
            updated = [(k, font_map.get(v, v) if k == "font-family" else v) for k, v in pairs]
            if updated != pairs:
                element.set("style", ";".join(f"{k}:{v}" for k, v in updated)); changes += 1
    after = geometry(root)
    if before != after:
        raise ValueError("Non-font SVG structure changed")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), {
        "changedFamilies": changes, "structureHash": after, "nonFontStructurePreserved": True,
        "requiresInkRemeasurement": changes > 0, "requiresNativeReview": True,
        "fontSizeChanged": False, "finalStrokeAuditRequired": True,
    }

def prepare(job: dict, destination: str) -> dict:
    source = Path(job["source"]).resolve()
    if source.suffix.lower() != ".svg" or not source.is_file():
        raise ValueError("Existing SVG source required")
    data = source.read_bytes()
    if not re.fullmatch(r"[a-f0-9]{64}", job.get("sourceHash", "")) or sha(data) != job["sourceHash"]:
        raise ValueError("SVG source hash mismatch")
    tool_hash = sha(Path(__file__).read_bytes())
    key = sha(canonical({"version": VERSION, "toolHash": tool_hash, "sourceHash": job["sourceHash"], "fontFamilyMap": job.get("fontFamilyMap")}))
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cache = root / key
    output, audit = transform(data, job.get("fontFamilyMap"))
    if source.read_bytes() != data:
        raise ValueError("SVG source changed during preprocessing")
    if cache.exists():
        report = json.loads((cache / "prepared.json").read_text("utf-8"))
        if report.get("key") != key or report.get("outputHash") != sha(output) or sha((cache / "prepared.svg").read_bytes()) != sha(output) or report.get("productionAccepted") is not False:
            raise ValueError("Cached SVG changed; preserving it for review")
        return {**report, "id": job["id"], "output": str(cache / "prepared.svg"), "cached": True}
    report = {"id": job["id"], "version": VERSION, "key": key, "toolHash": tool_hash,
              "sourceHash": job["sourceHash"], "outputHash": sha(output), "audit": audit,
              "status": "prepared-for-native-review", "productionAccepted": False}
    stage = Path(tempfile.mkdtemp(prefix=".svg-stage-", dir=root))
    (stage / "prepared.svg").write_bytes(output)
    (stage / "prepared.json").write_bytes(canonical(report))
    try:
        stage.rename(cache)
    except OSError:
        if not cache.exists():
            raise
        existing = json.loads((cache / "prepared.json").read_text("utf-8"))
        if existing.get("key") != key or sha((cache / "prepared.svg").read_bytes()) != report["outputHash"]:
            raise ValueError("Concurrent SVG cache mismatch")
    return {**report, "output": str(cache / "prepared.svg"), "cached": False}

def worker(pair):
    job, destination = pair
    try:
        return prepare(job, destination)
    except Exception as error:
        return {"id": job.get("id"), "status": "blocked", "reason": str(error), "productionAccepted": False}

def prepare_batch(jobs: list[dict], destination: str, workers: int = 2) -> list[dict]:
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError("workers must be an integer between 1 and 8")
    ids = [job.get("id") for job in jobs]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Unique nonempty job ids required")
    if workers == 1:
        return [worker((job, destination)) for job in jobs]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        return list(pool.map(worker, ((job, destination) for job in jobs)))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    jobs = json.loads(args.manifest.read_text("utf-8-sig"))
    for job in jobs:
        job["source"] = str((args.manifest.resolve().parent / job["source"]).resolve())
    result = prepare_batch(jobs, str(args.destination), args.workers)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2 if any(item["status"] == "blocked" for item in result) else 0)
