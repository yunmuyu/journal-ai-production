"""Font-free native JPEG candidates with source-bound, independently checked pixels.

The raster engine's receipt is evidence, not authority: every candidate check
reconstructs the engine's lossless PNG and quality-95 JPEG from the sealed source.
Neither this module nor a successful mechanical check grants review/acceptance.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import sys
import time
import unicodedata
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath

from .core import (Config, FlowError, author_dir, engine_directory, hash_file,
                   hash_json, safe_child, write_json, writer_lock)
from .probing import check_snapshot
from .target_identity import TargetIdentity

_METHOD = "full-canvas-grayscale"
_JPG = "raster/grayscale.jpg"
_PNG = "raster/grayscale.png"
_RECEIPT = "raster/audit.json"
_REPORT = "raster/report.json"
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _raster():
    engine = str(engine_directory())
    if engine not in sys.path:
        sys.path.insert(0, engine)
    from journal_pdf import raster_preprocess
    return raster_preprocess


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise FlowError(code, message)


def _text(value: object) -> bool:
    return (isinstance(value, str) and bool(value.strip())
            and not any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value))


def _sha(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _no_links(path: Path) -> None:
    # Do not resolve first: resolving would hide a symlink in the supplied path.
    path = Path(os.path.abspath(path))
    for item in (*reversed(path.parents), path):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise FlowError("unsafe_path", f"路径包含符号链接或联接点：{path}")


def _relative(value: object) -> str:
    _require(_text(value), "unsafe_path", "相对路径必须是非空且不含控制字符的字符串")
    assert isinstance(value, str)
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    _require(not posix.is_absolute() and not windows.drive and not windows.root
             and posix.as_posix() == value and "\\" not in value,
             "unsafe_path", f"不是规范的安全相对路径：{value}")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    for part in value.split("/"):
        _require(part not in {"", ".", ".."} and not part.endswith((".", " "))
                 and not any(c in part for c in ':*?"<>|')
                 and part.split(".")[0].upper() not in reserved,
                 "unsafe_path", f"路径含不安全文件名：{value}")
    return value


def _file(root: Path, relative: str) -> Path:
    _no_links(root)
    result = safe_child(root, _relative(relative))
    _require(result.is_file(), "missing_path", f"路径不是普通文件：{relative}")
    return result


def _bytes(path: Path) -> bytes:
    _no_links(path)
    _require(path.is_file(), "missing_path", f"文件不存在或不是普通文件：{path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FlowError("missing_path", f"无法读取文件：{path}") from exc


def _document(path: Path) -> tuple[dict, str]:
    data = _bytes(path)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"non-finite number: {value}")

    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique,
                           parse_constant=invalid_constant)
        if not isinstance(value, dict):
            raise ValueError("expected object")
        # Also rejects overflow to Infinity (e.g. 1e999) and lone surrogates.
        hash_json(value)
    except (ValueError, UnicodeError, TypeError, OverflowError, RecursionError) as exc:
        raise FlowError("invalid_json", f"JSON须为无重复字段、无非有限数值的对象：{path}") from exc
    return value, _digest(data)


def _snapshot(config: Config, probe_id: str) -> dict:
    _require(_sha(probe_id), "probe_id", "预检 ID 无效")
    _no_links(config.state_root)
    folder = safe_child(config.state_root, f"probes/{probe_id}")
    seal, _ = _document(folder / "seal.json")
    _require(seal.get("probe_id") == probe_id and isinstance(seal.get("source_root"), str)
             and Path(seal["source_root"]).is_absolute()
             and isinstance(seal.get("sources"), dict) and bool(seal["sources"])
             and isinstance(seal.get("identity"), dict)
             and isinstance(seal.get("code_hashes"), dict)
             and isinstance(seal.get("evidence_hashes"), dict)
             and _sha(seal.get("probe_sha256")), "source_identity", "预检来源封印字段缺失或无效")
    source = Path(seal["source_root"])
    _no_links(source)
    for rel, digest in seal["sources"].items():
        _relative(rel)
        _require(_sha(digest), "source_identity", "预检来源哈希无效")
        _file(source, rel)
    _require(all(_text(key) and _text(rel) and rel in seal["sources"] for key, rel in seal["identity"].items()),
             "source_identity", "预检文件身份与来源不一致")
    identity_hash = hash_json({"source_root": seal["source_root"], "sources": seal["sources"],
                              "identity": seal["identity"], "code": seal["code_hashes"]})
    _require(identity_hash == probe_id, "source_identity", "预检来源封印与预检 ID 不一致")
    evidence = safe_child(folder, "evidence")
    for path in evidence.rglob("*"):
        _no_links(path)
    for rel, digest in seal["evidence_hashes"].items():
        _relative(rel)
        _require(_sha(digest), "evidence_changed", "预检证据哈希无效")
    try:
        checked = check_snapshot(config, probe_id)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise FlowError("source_identity", "无法核对预检来源封印") from exc
    _require(checked == seal, "source_changed", "核对期间预检封印发生变化")
    return seal


def _author_relative(value: object) -> str:
    relative = _relative(value)
    parts = PurePosixPath(relative).parts
    _require(len(parts) in (2, 3) and (len(parts) == 2 or parts[1] == "0没做完"),
             "author_path", "作者目录须为编辑/作者或编辑/0没做完/作者")
    return relative


def _target_identity(output: dict) -> str:
    author = output.get("author")
    if author is not None:
        _require(_text(author), "target_identity", "显式目标作者无效")
    basename = output.get("target_basename")
    if basename is not None:
        _relative(basename)
        _require("/" not in basename and Path(basename).suffix in {".jpg", ".jpeg"},
                 "target_identity", "原生位图目标须为匹配图号的 .jpg 或 .jpeg 文件名")
        basename = str(Path(basename).with_suffix(".pdf"))
    number = output.get("figure_number")
    _require(isinstance(number, str), "figure_number", "图号必须是字符串")
    name = TargetIdentity(author, basename).basename(Path(output["author_rel"]).name, number)
    return str(Path(name).with_suffix(".jpg"))


def _width(value: object) -> float:
    try:
        valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                 and math.isfinite(value) and value > 0)
    except OverflowError:
        valid = False
    _require(valid, "raster_width", "栏宽必须为有限正数毫米")
    return float(value)


def _inputs(config: Config, spec: dict, constraints: dict, seal: dict) -> tuple[str, float]:
    confirmed, suggested = constraints.get("confirmed"), constraints.get("suggested", {})
    _require(isinstance(confirmed, dict) and isinstance(suggested, dict),
             "constraints", "约束须包含 confirmed 对象")
    for field in ("split", "processing_method", "column", "backend", "output_format"):
        fixed = confirmed.get(field)
        _require(_text(fixed), "constraints", f"缺少已确认约束：{field}")
        _require(suggested.get(field) is None or suggested[field] == fixed,
                 "constraint_conflict", f"{field} 建议与已确认值冲突")
    _require(confirmed["backend"] == "raster-preprocess" and confirmed["output_format"] == "jpg",
             "constraint_conflict", "原生位图须明确 raster-preprocess 后端及 jpg 输出")
    _require(confirmed["processing_method"] == spec.get("processing_method") == _METHOD,
             "constraint_conflict", "只支持已确认的 full-canvas-grayscale 加工方式")
    policy = spec.get("policy")
    _require(isinstance(policy, dict) and policy.get("column") == confirmed["column"] == "single",
             "constraint_conflict", "此路线只支持已确认的 single 单栏")
    width = _width(policy.get("width_mm", _raster().DEFAULT_WIDTH_MM))
    _require(width == _raster().DEFAULT_WIDTH_MM or "width_mm" in confirmed,
             "constraint_conflict", "非默认物理栏宽必须有 confirmed.width_mm 明确匹配，不能仅由制作说明覆盖")
    if "width_mm" in confirmed:
        _require(_width(confirmed["width_mm"]) == width, "constraint_conflict", "制作说明栏宽与已确认毫米值冲突")
    if suggested.get("width_mm") is not None:
        _require(_width(suggested["width_mm"]) == width, "constraint_conflict", "建议栏宽与实际毫米值冲突")
    for field, value in (("backend", "raster-preprocess"), ("output_format", "jpg")):
        _require(field not in spec or spec[field] == value, "constraint_conflict", f"制作说明 {field} 冲突")
    _require(spec.get("synthetic", False) is False, "synthetic", "合成测试说明不能生成可发布候选")
    rel = _author_relative(spec.get("author_rel"))
    _no_links(config.delivery_root)
    author = author_dir(config.delivery_root, rel)
    _require(_text(spec.get("author")) and spec["author"] == author.name,
             "author_mismatch", "制作说明作者与已确认目标作者不一致")
    number = spec.get("figure_number")
    _require(isinstance(number, str), "figure_number", "图号必须是字符串")
    TargetIdentity().basename(author.name, number)
    outputs = confirmed.get("expected_outputs")
    _require(confirmed["split"] in {"single", "multi"} and isinstance(outputs, list) and bool(outputs),
             "constraints", "须明确 split 和非空 expected_outputs")
    pairs = set()
    for output in outputs:
        _require(isinstance(output, dict), "constraints", "每项 expected_outputs 必须是对象")
        output_rel = _author_relative(output.get("author_rel"))
        _target_identity(output)
        pair = (unicodedata.normalize("NFC", output_rel).casefold(), output["figure_number"])
        _require(pair not in pairs, "constraints", "expected_outputs 重复")
        pairs.add(pair)
    _require((confirmed["split"] == "single") == (len(outputs) == 1),
             "constraints", "split 与 expected_outputs 数量不一致")
    _require(any(row["author_rel"] == rel and row["figure_number"] == number for row in outputs),
             "constraint_conflict", "制作说明交付目标未在已确认输出清单中")
    if "target_basename" in spec:
        selected = next(row for row in outputs if row["author_rel"] == rel and row["figure_number"] == number)
        _require(spec["target_basename"] == selected.get("target_basename"),
                 "constraint_conflict", "制作说明显式文件身份与已确认目标不一致")
    bindings = spec.get("sources")
    _require(isinstance(bindings, list) and bool(bindings), "source_identity", "真实图件必须绑定源文件")
    seen = set()
    for row in bindings:
        _require(isinstance(row, dict) and _sha(row.get("sha256")) and _text(row.get("role")),
                 "source_identity", "每项来源须有 path、SHA-256 和非空 role")
        path = _relative(row.get("path"))
        key = unicodedata.normalize("NFC", path).casefold()
        _require(key not in seen, "source_identity", "来源路径重复或跨平台身份歧义")
        seen.add(key)
        _require(seal["sources"].get(path) == row["sha256"],
                 "source_identity", "制作说明来源与当前预检快照不一致")
        _require(hash_file(_file(Path(seal["source_root"]), path)) == row["sha256"],
                 "source_changed", f"候选来源变化：{path}")
    selected = spec.get("source_path", bindings[0]["path"] if len(bindings) == 1 else None)
    _require(selected is not None, "source_identity", "多个来源须明确指定 source_path")
    selected = _relative(selected)
    _require(selected in {row["path"] for row in bindings}, "source_identity", "source_path 必须明确绑定 sources 中的一个来源")
    return selected, width


def _engine_signature() -> str:
    raster = _raster()
    from journal_pdf import common
    return hash_json({"raster_preprocess.py": hash_file(Path(raster.__file__)),
                      "common.py": hash_file(Path(common.__file__)),
                      "pillow": raster.pillow_version, "pymupdf": raster.fitz.VersionBind})


def _audit(render_root: Path, spec: dict, seal: dict, source_path: str, width: float,
           receipt: dict) -> dict[str, str]:
    """Verify saved bytes, including deterministic source-to-JPEG conversion."""
    raster = _raster()
    from journal_pdf.common import FigureError
    from PIL import Image
    source = _file(Path(seal["source_root"]), source_path)
    data = _bytes(source)
    _require(_digest(data) == seal["sources"][source_path], "source_changed", "读取的原始位图已变化")
    try:
        gray, facts = raster._load_gray(data)
        ppi = gray.width * 25.4 / width
        expected_png = raster._png(gray)
        expected_jpg, jpg_audit = raster._jpeg(gray, ppi)
        png_path, jpg_path = _file(render_root, _PNG), _file(render_root, _JPG)
        png, jpg = _bytes(png_path), _bytes(jpg_path)
        with Image.open(io.BytesIO(png)) as actual:
            actual.load()
            _require(actual.format == "PNG" and actual.mode == gray.mode and actual.size == gray.size
                     and actual.tobytes() == gray.tobytes(), "raster_audit", "无损PNG不等于完整灰度原图")
        with Image.open(io.BytesIO(jpg)) as actual:
            actual.load()
            exif = actual.getexif()
            xppi, yppi = float(exif.get(282, 0)), float(exif.get(283, 0))
            _require(actual.format == "JPEG" and actual.mode == "L" and actual.size == gray.size
                     and exif.get(296) == 2 and exif.get(274, 1) == 1
                     and all(math.isfinite(v) and v > 0 and math.isclose(v, ppi, rel_tol=1e-8) for v in (xppi, yppi))
                     and math.isclose(actual.width * 25.4 / xppi, width, rel_tol=1e-8),
                     "raster_audit", "实际JPEG的灰度、像素尺寸或EXIF物理栏宽无效")
        _require(png == expected_png and jpg == expected_jpg, "raster_audit", "实际输出不是绑定来源的确定性完整画布转换")
    except FigureError as exc:
        raise FlowError(exc.code, f"位图审计阻断：{exc}") from exc
    except (OSError, ValueError, TypeError, OverflowError, ZeroDivisionError, KeyError) as exc:
        raise FlowError("raster_audit", "无法独立核对实际位图字节及物理尺寸") from exc
    expected_outputs = {
        "png": {"path": _PNG, "sha256": _digest(expected_png), "mode": gray.mode,
                "lossy": False, "exact_grayscale_pixels_preserved": True,
                "alpha_pixels_preserved": True if gray.mode == "LA" else None},
        "jpeg": {"path": _JPG, "sha256": _digest(expected_jpg), **jpg_audit},
    }
    expected = {
        "version": 1, "id": "raster", "mode": _METHOD, "status": "candidate-rendered",
        "mechanical_checks_passed": True, "ready_for_publication": False, "publication_accepted": False,
        "source_identity_review": "not-performed", "content_review": "not-performed",
        "visual_review": "not-performed", "print_acceptance": "not-performed",
        "source_path": str(Path(source_path)), "source_sha256": _digest(data), "source_unchanged": True,
        **facts, "pillow_version": raster.pillow_version, "pymupdf_version": raster.fitz.VersionBind,
        "source_icc_applied": False, "source_metadata_copied": False,
        "full_canvas_preserved": True, "aspect_ratio_preserved": True, "crop": False,
        "background_removal": False, "resampled": False, "sharpening": False,
        "contrast_adjustment": False, "alpha_composited": False, "exif_orientation_applied": False,
        "font_substitution": False, "width_mm": width, "height_mm": width * gray.height / gray.width,
        "effective_ppi": ppi, "width_user_confirmed": None,
        "width_basis": "caller-supplied" if "width_mm" in spec["policy"] else "repository-default-single-column",
        "outputs": expected_outputs, "receipt": _RECEIPT,
    }
    for key, value in expected.items():
        _require(key in receipt and hash_json({"v": receipt[key]}) == hash_json({"v": value}),
                 "raster_audit", f"原生位图回执与实际来源/输出不一致：{key}")
    return {_PNG: _digest(png), _JPG: _digest(jpg)}


def check_raster_candidate(config: Config, candidate_id: str) -> tuple[dict, dict, Path]:
    _require(isinstance(candidate_id, str) and re.fullmatch(r"[0-9a-f]{32}", candidate_id) is not None,
             "candidate_id", "候选 ID 无效")
    _no_links(config.state_root)
    folder = safe_child(config.state_root, f"candidates/{candidate_id}")
    candidate, candidate_file_sha = _document(folder / "candidate.json")
    _require(candidate.get("candidate_id") == candidate_id and candidate.get("output_format") == "jpg"
             and candidate.get("backend") == "raster-preprocess" and candidate.get("status") == "candidate-rendered"
             and candidate.get("output_jpg") == _JPG, "candidate_changed", "原生JPG候选登记身份无效")
    for key in ("output_sha256", "report_sha256", "spec_sha256", "constraints_sha256", "constraints_file_sha256"):
        _require(_sha(candidate.get(key)), "candidate_changed", f"候选登记缺少有效哈希：{key}")
    spec, spec_file_sha = _document(folder / "spec.json")
    constraints, constraints_file_sha = _document(folder / "constraints.json")
    _require(hash_json(spec) == candidate["spec_sha256"], "candidate_changed", "制作说明已变化")
    _require(hash_json(constraints) == candidate["constraints_sha256"], "candidate_changed", "已确认约束已变化")
    original_path = candidate.get("constraints_path")
    _require(isinstance(original_path, str) and Path(original_path).is_absolute(),
             "candidate_changed", "原始已确认约束路径无效")
    original, original_file_sha = _document(Path(original_path))
    _require(original_file_sha == candidate["constraints_file_sha256"] and hash_json(original) == hash_json(constraints),
             "constraints_changed", "原始已确认约束文件已变化")
    seal = _snapshot(config, candidate.get("probe_id"))
    source_path, width = _inputs(config, spec, constraints, seal)
    render_root = safe_child(folder, "render")
    report_path, receipt_path = _file(render_root, _REPORT), _file(render_root, _RECEIPT)
    report, report_file_sha = _document(report_path)
    receipt, receipt_file_sha = _document(receipt_path)
    _require(report_file_sha == candidate["report_sha256"], "candidate_changed", "引擎报告已变化")
    _require(candidate.get("native_receipt") == _RECEIPT and candidate.get("native_receipt_sha256") == receipt_file_sha,
             "candidate_changed", "候选登记与原生回执绑定不一致")
    expected_report = {
        "candidate_id": candidate_id, "backend": "raster-preprocess", "output_format": "jpg",
        "status": "candidate-rendered", "mechanical_checks_passed": True,
        "ready_for_publication": False, "publication_accepted": False,
        "source_identity_review": "not-performed", "content_review": "not-performed",
        "visual_review": "not-performed", "print_acceptance": "not-performed",
        "author": spec["author"], "author_rel": spec["author_rel"], "figure_number": spec["figure_number"],
        "processing_method": _METHOD, "source_bindings": spec["sources"], "source_path": source_path,
        "source_sha256": seal["sources"][source_path], "spec_hash": candidate["spec_sha256"],
        "constraints_sha256": candidate["constraints_sha256"], "probe_id": candidate["probe_id"],
        "output_jpg": _JPG, "output_sha256": candidate["output_sha256"],
        "native_receipt": _RECEIPT, "native_receipt_sha256": receipt_file_sha, "raster_audit": receipt,
        "width_mm": width, "source_dimensions": receipt.get("source_dimensions"),
        "effective_ppi": receipt.get("effective_ppi"), "engine_signature": _engine_signature(),
    }
    for key, value in expected_report.items():
        _require(key in report and hash_json({"v": report[key]}) == hash_json({"v": value}),
                 "candidate_changed", f"候选报告绑定不一致：{key}")
    image_hashes = _audit(render_root, spec, seal, source_path, width, receipt)
    _require(image_hashes[_JPG] == candidate["output_sha256"], "candidate_changed", "候选登记与JPEG哈希不一致")
    # Recheck every saved input after decoding/reconstruction to catch changes
    # during this check as well as changes made since candidate creation.
    snapshots = {folder / "candidate.json": candidate_file_sha, folder / "spec.json": spec_file_sha,
                 folder / "constraints.json": constraints_file_sha, Path(original_path): original_file_sha,
                 report_path: report_file_sha, receipt_path: receipt_file_sha,
                 **{render_root / rel: digest for rel, digest in image_hashes.items()}}
    for path, digest in snapshots.items():
        _require(_digest(_bytes(path)) == digest, "candidate_changed", "核对期间候选文件发生变化")
    _require(_snapshot(config, candidate["probe_id"]) == seal, "source_changed", "核对期间预检来源发生变化")
    return candidate, report, _file(render_root, _JPG)


def render_raster(config: Config, spec_path: Path, constraints_path: Path, probe_id: str) -> dict:
    began = time.perf_counter()
    spec_path, constraints_path = Path(spec_path), Path(constraints_path)
    spec, spec_initial_sha = _document(spec_path)
    constraints, constraints_initial_sha = _document(constraints_path)
    seal = _snapshot(config, probe_id)
    source_path, width = _inputs(config, spec, constraints, seal)
    _no_links(config.state_root)
    state, delivery, source = (p.resolve() for p in (config.state_root, config.delivery_root, Path(seal["source_root"])))
    for other in (delivery, source):
        _require(state != other and state not in other.parents and other not in state.parents,
                 "state_delivery_overlap", "候选状态目录须与交付和来源目录相互隔离")
    candidate_id = uuid.uuid4().hex
    folder = safe_child(config.state_root, f"candidates/{candidate_id}", existing=False)
    raster = _raster()
    from journal_pdf.common import FigureError
    with writer_lock(config.state_root):
        folder.mkdir(parents=True)
        render_root = folder / "render"
        try:
            receipt = raster.preprocess_raster(source_path, render_root, source_root=source,
                                               figure_id="raster", width_mm=spec["policy"].get("width_mm"),
                                               write_jpeg=True, write_pdf=False)
        except FigureError as exc:
            raise FlowError(exc.code, f"位图引擎阻断：{exc}") from exc
        receipt_path = _file(render_root, _RECEIPT)
        saved_receipt, receipt_sha = _document(receipt_path)
        _require(saved_receipt == receipt, "raster_audit", "保存的原生回执与引擎返回不一致")
        image_hashes = _audit(render_root, spec, seal, source_path, width, saved_receipt)
        report = {
            "schema_version": 1, "candidate_id": candidate_id, "backend": "raster-preprocess", "output_format": "jpg",
            "status": "candidate-rendered", "mechanical_checks_passed": True,
            "ready_for_publication": False, "publication_accepted": False,
            "source_identity_review": "not-performed", "content_review": "not-performed",
            "visual_review": "not-performed", "print_acceptance": "not-performed",
            "author": spec["author"], "author_rel": spec["author_rel"], "figure_number": spec["figure_number"],
            "processing_method": _METHOD, "source_bindings": spec["sources"], "source_path": source_path,
            "source_sha256": seal["sources"][source_path], "spec_hash": hash_json(spec),
            "constraints_sha256": hash_json(constraints), "probe_id": probe_id,
            "output_jpg": _JPG, "output_sha256": image_hashes[_JPG],
            "native_receipt": _RECEIPT, "native_receipt_sha256": receipt_sha, "raster_audit": receipt,
            "width_mm": width, "source_dimensions": receipt["source_dimensions"],
            "effective_ppi": receipt["effective_ppi"], "engine_signature": _engine_signature(),
        }
        _require(_digest(_bytes(constraints_path)) == constraints_initial_sha,
                 "constraints_changed", "渲染期间原始已确认约束文件变化")
        _require(_digest(_bytes(spec_path)) == spec_initial_sha, "candidate_changed", "渲染期间原始制作说明文件变化")
        _require(_snapshot(config, probe_id) == seal, "source_changed", "渲染期间预检来源变化")
        write_json(folder / "spec.json", spec)
        write_json(folder / "constraints.json", constraints)
        write_json(render_root / _REPORT, report)
        log_path = folder / "render.log"
        log_path.write_text("", encoding="utf-8")
        candidate = {
            "candidate_id": candidate_id, "probe_id": probe_id, "backend": "raster-preprocess",
            "output_format": "jpg", "output_jpg": _JPG, "output_sha256": image_hashes[_JPG],
            "report_sha256": hash_file(render_root / _REPORT), "spec_sha256": hash_json(spec),
            "constraints_sha256": hash_json(constraints), "status": "candidate-rendered",
            "constraints_path": str(constraints_path.resolve()), "constraints_file_sha256": constraints_initial_sha,
            "native_receipt": _RECEIPT, "native_receipt_sha256": receipt_sha,
            "render_log": str(log_path), "warning_count": 0,
            "render_ms": round((time.perf_counter() - began) * 1000, 3),
        }
        write_json(folder / "candidate.json", candidate)
        check_raster_candidate(config, candidate_id)
    return {"candidate_id": candidate_id, "jpg": str(render_root / _JPG), "output_format": "jpg",
            "sha256": image_hashes[_JPG], "render_ms": candidate["render_ms"], "audit": "passed",
            "status": "candidate-rendered", "render_log": str(log_path), "warning_count": 0,
            "acceptance": "not_recorded"}
