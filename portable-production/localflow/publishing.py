from __future__ import annotations

import math
import os
import shutil
import tempfile
import time
import unicodedata
from pathlib import Path

from .core import Config, FlowError, author_dir, hash_file, hash_json, json_file, safe_child, write_json, writer_lock
from .rendering import check_candidate
from .target_identity import TargetIdentity
from .pdf_compat import audit_pdf_compatibility


_ARTIFACT_SUFFIXES = {".pdf", ".jpg", ".jpeg"}


def _filename_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def target_for_artifact(folder: Path, figure_number: str, *, output_format: str = "pdf",
    author: str | None = None, target_basename: str | None = None) -> Path:
    """Apply the existing safe figure identity to PDF or a native JPEG filename.

    JPG is canonical; an explicitly bound .jpeg name is also supported. Format
    never comes from a directory scan or a renderer's arbitrary output basename.
    """
    if output_format not in ("pdf", "jpg"):
        raise FlowError("artifact_format", "仅支持 PDF 或原生 JPG 交付")
    if output_format == "pdf":
        return TargetIdentity(author, target_basename).target(folder, figure_number)
    if target_basename is None:
        name = str(Path(TargetIdentity(author).basename(folder.name, figure_number)).with_suffix(".jpg"))
    else:
        if not isinstance(target_basename, str) or Path(target_basename).suffix not in (".jpg", ".jpeg"):
            raise FlowError("target_identity", "原生 JPG 显式目标文件名必须以 .jpg 或 .jpeg 结尾")
        pdf_name = target_basename.rsplit(".", 1)[0] + ".pdf"
        TargetIdentity(author, pdf_name).basename(folder.name, figure_number)
        name = target_basename
    safe_child(folder, name, existing=False)
    # Preserve requested spelling after containment/link checks: Windows resolve
    # canonicalizes an existing differently-cased filename and hides collisions.
    return folder.resolve() / name


def artifact_format(candidate: dict, artifact: Path) -> str:
    """Discover the declared delivery format, preserving legacy PDF candidates."""
    value = candidate.get("output_format", "pdf")
    allowed = {"pdf": {".pdf"}, "jpg": {".jpg", ".jpeg"}}
    if value not in allowed or artifact.suffix.lower() not in allowed[value]:
        raise FlowError("artifact_format", "候选声明格式与实际文件扩展名不一致")
    return value


def audit_jpg_compatibility(path: Path, report: dict | None = None) -> dict:
    """Read real JPEG bytes, not the extension or receipt's success flags.

    Source reconstruction is performed by check_raster_candidate. This final
    copy/acceptance check verifies the native grayscale image and physical size.
    It does not claim content, visual, publication or print acceptance.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as image:
            image.load()
            if image.format != "JPEG" or image.mode != "L" or getattr(image, "n_frames", 1) != 1:
                raise FlowError("jpg_audit", "实际 JPG 必须是单帧灰度 JPEG，不按文件扩展名判断")
            exif = image.getexif()
            if exif.get(274, 1) != 1 or exif.get(296) != 2 or image.info.get("icc_profile"):
                raise FlowError("jpg_audit", "JPG 方向、色彩配置或英寸分辨率元数据不符合保留画布路线")
            x_ppi, y_ppi = float(exif[282]), float(exif[283])
            if not all(math.isfinite(v) and v > 0 for v in (x_ppi, y_ppi)) or not math.isclose(x_ppi, y_ppi, rel_tol=1e-8):
                raise FlowError("jpg_audit", "JPG 双轴分辨率必须有限、为正且相同")
            width_mm = image.width * 25.4 / x_ppi
            if report is not None:
                expected = report.get("source_dimensions")
                expected_width = report.get("width_mm")
                if expected != list(image.size) or isinstance(expected_width, bool) or not isinstance(expected_width, (int, float)) or not math.isfinite(expected_width) or expected_width <= 0:
                    raise FlowError("jpg_audit", "JPG 实际像素尺寸或报告栏宽无效")
                if not math.isclose(width_mm, expected_width, rel_tol=1e-8):
                    raise FlowError("jpg_audit", "JPG 实际物理栏宽与报告不一致")
            return {"passed": True, "format": "JPEG", "mode": "L", "dimensions": list(image.size),
                "width_mm": width_mm, "effective_ppi": x_ppi, "acceptance": "not_recorded"}
    except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise FlowError("jpg_audit", "无法安全核验实际 JPG 字节或分辨率元数据") from exc


def _audit_artifact(path: Path, output_format: str, report: dict | None = None) -> None:
    if output_format == "jpg":
        audit_jpg_compatibility(path, report)
    else:
        audit_pdf_compatibility(path)


def _editorial_gate(config: Config, candidate: dict, report: dict, output_format: str) -> None:
    # Imported lazily so loading/inspecting the CLI does not evaluate contracts.
    from .editorial_gate import check_editorial_gate
    decision = check_editorial_gate(config, candidate, report, output_format)
    if output_format == "pdf":
        # Rendering is also a preview API. Publication must consume the actual
        # measured policy evidence rather than accept a final 6–8pt range alone.
        from journal_pdf.rules_registry import _font_policy_evidence
        spec = json_file(config.state_root / "candidates" / candidate["candidate_id"] / "spec.json")
        if decision["route"] == "plot_reletter":
            _check_chart_semantics(spec, report)
        evidence = report.get("layout", {}).get("layout_evidence", {})
        default_start, explicit_exception = _font_policy_evidence(spec, evidence)
        if not (default_start or explicit_exception):
            raise FlowError("publication_font_policy", "PDF候选缺少实测8pt起排或绑定当前来源及回复的制作例外；只能保留预览，不能发布")


def _check_chart_semantics(spec: dict, report: dict) -> None:
    """A recorded plot route must use chart rules, not a scene of generic labels.

    This checks dedicated renderer evidence, not the truth of the source's class.
    Ordinary preview scenes remain valid outside production plot publication.
    """
    if spec.get("kind") != "chart" or report.get("kind") != "chart":
        raise FlowError("publication_chart_semantics", "图表换字须通过chart专用语义规则；普通scene标签不能替代轴题、刻度和图例审计")
    texts = report.get("layout", {}).get("texts", [])
    titles = [row for row in texts if row.get("role") == "axis-title"]
    audit = report.get("pdf_audit", {}).get("axis_unit_notation", {})
    checks = audit.get("checks", [])
    if (len(titles) != 2 or {row.get("id") for row in titles} != {"xtitle", "ytitle"}
        or audit.get("ok") is not True or len(checks) != 2
        or {row.get("id") for row in checks} != {"xtitle", "ytitle"}
        or any(row.get("actual_pdf_contains_expected") is not True
               or row.get("scene_matches_rule") is not True
               or row.get("status") == "semantic_review_needed" for row in checks)):
        raise FlowError("publication_chart_semantics", "图表须有两轴专用角色及非空的实际PDF轴题审计；空检查或未解决语义不能发布")


def _validate_review(config: Config, candidate: dict, report: dict, record: dict,
    output_format: str) -> None:
    expected = {"candidate_id": candidate["candidate_id"], "output_sha256": candidate["output_sha256"],
        "constraints_sha256": candidate["constraints_sha256"],
        "source_hashes": {row["path"]: row["sha256"] for row in report["source_bindings"]}}
    for key, value in expected.items():
        if record.get(key) != value:
            raise FlowError("review_binding", f"审阅记录绑定不匹配：{key}")
    if not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip():
        raise FlowError("review_evidence", "审阅人不能为空")
    folder = author_dir(config.delivery_root, record.get("author_rel", ""))
    identity = TargetIdentity(record.get("author"), record.get("target_basename"))
    target_for_artifact(folder, record.get("figure_number", ""), output_format=output_format, **identity.fields())
    candidate_folder = config.state_root / "candidates" / candidate["candidate_id"]
    spec = json_file(candidate_folder / "spec.json")
    # Batch membership is not candidate identity: figure 1 must never be reviewed
    # or published as figure 2 merely because both are expected in the same job.
    for key in ("author_rel", "figure_number"):
        if record.get(key) != spec.get(key) or (key in report and report[key] != spec.get(key)):
            raise FlowError("review_target_binding", f"审阅目标与当前候选图件身份不一致：{key}")
    spec_identity = TargetIdentity(spec.get("author"), spec.get("target_basename"))
    spec_target = target_for_artifact(folder, spec["figure_number"], output_format=output_format, **spec_identity.fields())
    review_target = target_for_artifact(folder, record["figure_number"], output_format=output_format, **identity.fields())
    if spec_target != review_target:
        raise FlowError("review_target_binding", "审阅显式文件身份与当前候选制作说明不一致")
    constraints = json_file(candidate_folder / "constraints.json")
    expected_output = {"author_rel": record["author_rel"], "figure_number": record["figure_number"], **identity.fields()}
    if expected_output not in constraints["confirmed"]["expected_outputs"]:
        raise FlowError("constraint_target", "审阅目标及显式文件身份未在已确认输出清单中绑定")
    for key in ("content", "visual"):
        item = record.get(key)
        if not isinstance(item, dict) or item.get("conclusion") != "approved":
            raise FlowError("review_evidence", f"{key} 须有明确 approved 结论")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(v, str) and len(v.strip()) >= 12 for v in evidence):
            raise FlowError("review_evidence", f"{key} 须给出具体核对证据")


def review(config: Config, candidate_id: str, record_path: Path) -> dict:
    candidate, report, artifact = check_candidate(config, candidate_id)
    output_format = artifact_format(candidate, artifact)
    _editorial_gate(config, candidate, report, output_format)
    record = json_file(record_path)
    _validate_review(config, candidate, report, record, output_format)
    stored = safe_child(config.state_root, f"reviews/{candidate_id}.json", existing=False)
    with writer_lock(config.state_root):
        if stored.exists():
            previous = json_file(stored)
            if previous.get("record") != record or previous.get("record_sha256") != hash_json(record):
                raise FlowError("review_exists", "已有不同审阅记录；请生成新候选")
            return {"candidate_id": candidate_id, "review_sha256": previous["record_sha256"], "cached": True}
        write_json(stored, {"schema_version": 1, "record": record,
            "record_sha256": hash_json(record), "reviewed_at": time.time(),
            "acceptance": "not_recorded"})
    return {"candidate_id": candidate_id, "review_sha256": hash_json(record),
        "status": "agent-reviewed", "acceptance": "not_recorded"}


def _check_collisions(folder: Path, target: Path) -> None:
    for item in folder.iterdir():
        if _filename_key(item.stem) != _filename_key(target.stem) or item.suffix.casefold() not in _ARTIFACT_SUFFIXES:
            continue
        if item.name == target.name:
            if item.is_symlink() or not item.is_file():
                raise FlowError("unsafe_target", "交付目标必须为普通文件，不能是符号链接或目录")
            continue
        if item.suffix.casefold() != target.suffix.casefold():
            raise FlowError("format_conflict", "同一作者图号已有 PDF/JPG/JPEG 成品；需单独审核迁移")
        raise FlowError("filename_collision", "交付目标存在大小写不同的同名文件；禁止跨平台碰撞")


def _accepted_marker(config: Config, author_rel: str, target: Path) -> Path:
    folder = safe_child(config.state_root, f"accepted/{author_rel}", existing=False)
    path = folder / f"{target.name}.json"
    safe_child(config.state_root, f"accepted/{author_rel}/{target.name}.json", existing=False)
    if folder.exists():
        for marker in folder.iterdir():
            named = Path(marker.stem)
            if marker.suffix == ".json" and _filename_key(named.stem) == _filename_key(target.stem) and named.suffix.casefold() in _ARTIFACT_SUFFIXES and marker.name != path.name:
                raise FlowError("accepted_target", "同一图号已有不同文件名或格式的人工终检记录；不得迁移覆盖")
    return path


def _check_source_target(config: Config, candidate: dict, target: Path) -> None:
    from .probing import check_snapshot
    seal = check_snapshot(config, candidate["probe_id"])
    source_root = Path(seal["source_root"])
    for rel in seal["sources"]:
        source = safe_child(source_root, rel)
        if target.resolve() == source.resolve() or (target.exists() and target.samefile(source)):
            raise FlowError("source_protected", "发布目标是本候选绑定的原始素材，禁止覆盖")


def _archive_target(config: Config, author_rel: str, target: Path, current: str) -> None:
    archive = safe_child(config.state_root, f"archive/{author_rel}/{target.name}/{current}{target.suffix}", existing=False)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        if archive.is_symlink() or hash_file(archive) != current:
            raise FlowError("archive_collision", "外置归档已有同名异内容文件")
        return
    fd, name = tempfile.mkstemp(prefix=".archive-", suffix=target.suffix, dir=archive.parent)
    try:
        with os.fdopen(fd, "wb") as output, target.open("rb") as source:
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        if hash_file(Path(name)) != current:
            raise FlowError("archive_failed", "外置归档哈希核对失败")
        os.replace(name, archive)
    finally:
        Path(name).unlink(missing_ok=True)


def _record_publication(config: Config, candidate_id: str, author_rel: str, figure_number: str,
    target: Path, candidate: dict, reviewed: dict, output_format: str, *, check_only: bool = False) -> None:
    path = safe_child(config.state_root, f"publications/{candidate_id}.json", existing=False)
    publication = {"candidate_id": candidate_id, "author_rel": author_rel,
        "figure_number": figure_number, "target": str(target), "output_format": output_format,
        "sha256": candidate["output_sha256"], "review_sha256": reviewed["record_sha256"],
        "acceptance": "not_recorded"}
    if path.exists():
        existing = json_file(path)
        if all(existing.get(key) == value for key, value in publication.items() if key != "output_format"):
            return
        raise FlowError("publication_changed", "已有发布记录与当前候选、目标或审阅不一致")
    if not check_only:
        write_json(path, {**publication, "published_at": time.time()})


def publish(config: Config, candidate_id: str, author_rel: str, figure_number: str,
    expected_target_sha: str | None = None, *, target_basename: str | None = None,
    author: str | None = None) -> dict:
    began = time.perf_counter()
    candidate, report, artifact = check_candidate(config, candidate_id)
    output_format = artifact_format(candidate, artifact)
    _editorial_gate(config, candidate, report, output_format)
    review_path = safe_child(config.state_root, f"reviews/{candidate_id}.json")
    reviewed = json_file(review_path)
    record = reviewed["record"]
    if reviewed.get("record_sha256") != hash_json(record):
        raise FlowError("review_changed", "审阅记录或候选绑定已变化")
    _validate_review(config, candidate, report, record, output_format)
    if record.get("author_rel") != author_rel or record.get("figure_number") != figure_number:
        raise FlowError("review_target", "发布目标与审阅记录绑定不一致")
    folder = author_dir(config.delivery_root, author_rel)
    if report.get("author") != folder.name:
        raise FlowError("author_mismatch", "制作说明作者与交付目录作者不一致")
    identity = TargetIdentity(author, target_basename)
    target = target_for_artifact(folder, figure_number, output_format=output_format, **identity.fields())
    if identity.fields() != TargetIdentity(record.get("author"), record.get("target_basename")).fields():
        raise FlowError("review_target", "显式发布文件身份与审阅记录不一致")
    _check_source_target(config, candidate, target)
    with writer_lock(config.state_root):
        _check_collisions(folder, target)
        _record_publication(config, candidate_id, author_rel, figure_number, target, candidate, reviewed,
            output_format, check_only=True)
        accepted = _accepted_marker(config, author_rel, target)
        if accepted.exists():
            locked = json_file(accepted)
            if target.exists() and hash_file(target) == candidate["output_sha256"] == locked["sha256"]:
                _audit_artifact(target, output_format, report)
                return {"status": "already-accepted", "target": str(target), "sha256": locked["sha256"]}
            raise FlowError("accepted_target", "目标已登记人工终检；不允许普通发布替换")
        existed = target.exists()
        current = hash_file(target) if existed else None
        if existed:
            if current == candidate["output_sha256"]:
                _audit_artifact(target, output_format, report)
                _record_publication(config, candidate_id, author_rel, figure_number, target, candidate, reviewed, output_format)
                return {"status": "already-published", "target": str(target),
                    "sha256": current, "acceptance": "not_recorded"}
            if expected_target_sha is None or current != expected_target_sha:
                raise FlowError("target_changed", "目标已有不同内容；替换需提供当前目标的准确 SHA-256")
            _archive_target(config, author_rel, target, current)
        elif expected_target_sha is not None:
            raise FlowError("target_missing", "已给 expected-target-sha，但目标不存在")
        fd, temp_name = tempfile.mkstemp(prefix=".publish-", suffix=target.suffix, dir=folder)
        try:
            with os.fdopen(fd, "wb") as output, artifact.open("rb") as source:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            temp = Path(temp_name)
            if hash_file(temp) != candidate["output_sha256"]:
                raise FlowError("copy_failed", "发布副本哈希核对失败")
            _audit_artifact(temp, output_format, report)
            # Revalidate bindings after staging, not merely before a long copy.
            fresh, fresh_report, fresh_artifact = check_candidate(config, candidate_id)
            if fresh != candidate or fresh_report != report or fresh_artifact != artifact or json_file(review_path) != reviewed:
                raise FlowError("candidate_changed", "发布暂存期间候选或审阅绑定变化")
            _editorial_gate(config, fresh, fresh_report, output_format)
            _check_source_target(config, candidate, target)
            _check_collisions(folder, target)
            if target.exists() != existed or (existed and hash_file(target) != current):
                raise FlowError("target_changed", "写入前目标存在状态或内容再次变化")
            if _accepted_marker(config, author_rel, target).exists():
                raise FlowError("accepted_target", "写入前目标新增人工终检记录")
            os.replace(temp, target)
        finally:
            Path(temp_name).unlink(missing_ok=True)
        _record_publication(config, candidate_id, author_rel, figure_number, target, candidate, reviewed, output_format)
    return {"status": "published-candidate", "target": str(target), "output_format": output_format,
        "sha256": candidate["output_sha256"], "acceptance": "not_recorded",
        "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)}


def _accept_target(folder: Path, figure_number: str, output_format: str | None,
    author: str | None, target_basename: str | None) -> tuple[Path, str]:
    if output_format is not None:
        return target_for_artifact(folder, figure_number, output_format=output_format,
            author=author, target_basename=target_basename), output_format
    if target_basename is not None:
        suffix = Path(target_basename).suffix
        output_format = "jpg" if suffix in (".jpg", ".jpeg") else "pdf"
        return target_for_artifact(folder, figure_number, output_format=output_format,
            author=author, target_basename=target_basename), output_format
    base = target_for_artifact(folder, figure_number, author=author)
    matches = [path for path in folder.iterdir() if _filename_key(path.stem) == _filename_key(base.stem)
        and path.suffix.casefold() in _ARTIFACT_SUFFIXES]
    if len(matches) > 1:
        raise FlowError("format_conflict", "同图号存在多个 PDF/JPG/JPEG 文件，不能自动选择终检目标")
    if not matches:
        return base, "pdf"
    target = matches[0]
    fmt = "pdf" if target.suffix == ".pdf" else "jpg"
    checked = target_for_artifact(folder, figure_number, output_format=fmt, author=author, target_basename=target.name)
    return checked, fmt


def accept(config: Config, author_rel: str, figure_number: str, expected_sha: str,
    reviewer: str, evidence: str, *, output_format: str | None = None,
    author: str | None = None, target_basename: str | None = None) -> dict:
    folder = author_dir(config.delivery_root, author_rel)
    if not reviewer.strip() or len(evidence.strip()) < 12:
        raise FlowError("acceptance_evidence", "人工终检须记录审阅人及具体核对证据")
    with writer_lock(config.state_root):
        target, output_format = _accept_target(folder, figure_number, output_format, author, target_basename)
        _check_collisions(folder, target)
        if not target.is_file() or target.is_symlink() or hash_file(target) != expected_sha:
            raise FlowError("acceptance_target", "人工终检登记的目标哈希与实际文件不一致")
        _audit_artifact(target, output_format)
        path = _accepted_marker(config, author_rel, target)
        if path.exists():
            previous = json_file(path)
            if previous["sha256"] != expected_sha:
                raise FlowError("accepted_target", "已有不同人工终检记录")
            return {"status": "already-accepted", "target": str(target), "sha256": expected_sha}
        if hash_file(target) != expected_sha:
            raise FlowError("acceptance_target", "终检核验期间目标变化")
        write_json(path, {"target": str(target), "sha256": expected_sha, "output_format": output_format,
            "reviewer": reviewer, "evidence": evidence, "accepted_at": time.time()})
    return {"status": "accepted", "target": str(target), "sha256": expected_sha}
