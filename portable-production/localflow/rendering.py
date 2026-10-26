from __future__ import annotations

import sys
import time
import uuid
import logging
from contextlib import contextmanager, redirect_stderr
from typing import Iterator
from pathlib import Path

from .core import Config, FlowError, engine_directory, hash_file, hash_json, json_file, safe_child, write_json, writer_lock
from .probing import check_snapshot
from .target_identity import TargetIdentity
from .pdf_compat import audit_pdf_compatibility


@contextmanager
def font_warning_log(path: Path, mode: str) -> Iterator[None]:
    logger = logging.getLogger("fontTools")
    previous_propagate = logger.propagate
    with path.open(mode, encoding="utf-8") as stream, redirect_stderr(stream):
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        logger.propagate = False
        try:
            yield
        finally:
            logger.removeHandler(handler)
            logger.propagate = previous_propagate


def check_constraints(spec: dict, constraints: dict) -> None:
    confirmed = constraints.get("confirmed")
    suggested = constraints.get("suggested", {})
    if not isinstance(confirmed, dict) or not isinstance(suggested, dict):
        raise FlowError("constraints", "约束须包含 confirmed 对象")
    for field in ("split", "processing_method", "column"):
        fixed = confirmed.get(field)
        proposed = suggested.get(field)
        if not isinstance(fixed, str) or not fixed:
            raise FlowError("constraints", f"缺少已确认约束：{field}")
        if proposed is not None and proposed != fixed:
            raise FlowError("constraint_conflict", f"{field} 建议与已确认值冲突")
    if confirmed["split"] not in ("single", "multi"):
        raise FlowError("constraints", "split 必须为 single 或 multi")
    outputs = confirmed.get("expected_outputs")
    if not isinstance(outputs, list) or not outputs:
        raise FlowError("constraints", "须明确 expected_outputs")
    from .core import author_dir, figure_name
    pairs: set[tuple[str, str]] = set()
    for output in outputs:
        if not isinstance(output, dict) or not isinstance(output.get("author_rel"), str) or not isinstance(output.get("figure_number"), str):
            raise FlowError("constraints", "每项 expected_outputs 须含 author_rel 和 figure_number")
        pair = (output["author_rel"], output["figure_number"])
        TargetIdentity(output.get("author"), output.get("target_basename")).basename(Path(pair[0]).name, pair[1])
        if pair in pairs:
            raise FlowError("constraints", "expected_outputs 重复")
        pairs.add(pair)
    if (confirmed["split"] == "single") != (len(pairs) == 1):
        raise FlowError("constraints", "split 与 expected_outputs 数量不一致")
    if (spec.get("author_rel"), spec.get("figure_number")) not in pairs:
        raise FlowError("constraint_conflict", "制作说明交付目标未在已确认输出清单中")
    if spec.get("processing_method") != confirmed["processing_method"]:
        raise FlowError("constraint_conflict", "制作说明加工方式与已确认值冲突")
    if spec.get("policy", {}).get("column") != confirmed["column"]:
        raise FlowError("constraint_conflict", "制作说明栏宽与已确认栏宽冲突")
    if confirmed.get("backend") != "direct-pdf":
        raise FlowError("constraint_conflict", "当前引擎仅支持 direct-pdf 后端")


def check_report(report: dict, pdf: Path) -> None:
    if (any(a.get("mode") in ("source-vector-body", "source-mixed-body") for a in report.get("assets", []))
            or report.get("typography_coverage", {}).get("status") == "unverified"):
        raise FlowError("source_text_coverage", "源图路径或像素中的文字覆盖尚未验证；原生文字检查不能证明全图文字合格")
    if report.get("status") != "candidate-rendered" or report.get("mechanical_checks_passed") is not True:
        raise FlowError("render_audit", "引擎没有生成机械检查通过的候选")
    if report.get("pdf_sha256") != hash_file(pdf):
        raise FlowError("render_audit", "候选 PDF 与引擎报告哈希不一致")
    audit = report.get("pdf_audit")
    if not isinstance(audit, dict) or audit.get("page_count") != 1:
        raise FlowError("render_audit", "实际 PDF 页数审计缺失")
    for key in ("text_multiset_exact", "all_fonts_embedded", "neutral_rgb_300dpi",
        "numeric_grouping_in_actual_pdf", "editable_text_pure_black", "effective_path_strokes_05pt"):
        if audit.get(key) is not True:
            if (key == "editable_text_pure_black" and audit.get("editable_text_declared_black_white_exact") is True
                    and any(a.get("mode") == "registered-native-pdf-text" for a in report.get("assets", []))):
                continue
            raise FlowError("render_audit", f"实际 PDF 审计未通过：{key}")
    if audit.get("axis_unit_notation", {}).get("ok") is not True:
        raise FlowError("render_audit", "实际 PDF 轴单位审计未通过")
    if audit.get("editable_text_rotation_exact", True) is not True:
        raise FlowError("render_audit", "实际 PDF 文字旋转角核对未通过")
    if audit.get("font_descriptors", {}).get("passed") is not True:
        raise FlowError("render_audit", "引擎报告缺少字体描述完整性审计")
    audit_pdf_compatibility(pdf)
    if audit.get("font_profile_is_preview") is not False or report.get("font", {}).get("purpose") != "production":
        raise FlowError("preview_font", "预览字体不能进入发布候选")


def check_candidate(config: Config, candidate_id: str) -> tuple[dict, dict, Path]:
    if not candidate_id or not all(c in "0123456789abcdef" for c in candidate_id):
        raise FlowError("candidate_id", "候选 ID 无效")
    folder = config.state_root / "candidates" / candidate_id
    candidate = json_file(folder / "candidate.json")
    if candidate.get("output_format") == "jpg":
        from .raster_candidates import check_raster_candidate
        return check_raster_candidate(config, candidate_id)
    if candidate.get("output_format", "pdf") != "pdf":
        raise FlowError("artifact_format", "不支持的候选输出格式")
    report_path = safe_child(folder / "render", candidate["output_pdf"])
    engine_report_path = safe_child(folder / "render", str(Path(candidate["output_pdf"]).parent / "report.json"))
    report = json_file(engine_report_path)
    if hash_file(engine_report_path) != candidate["report_sha256"]:
        raise FlowError("candidate_changed", "引擎报告已变化")
    check_report(report, report_path)
    if report["pdf_sha256"] != candidate["output_sha256"]:
        raise FlowError("candidate_changed", "候选登记与 PDF 哈希不一致")
    saved_spec = json_file(folder / "spec.json")
    if hash_json(saved_spec) != candidate["spec_sha256"] or report.get("spec_hash") != candidate["spec_sha256"]:
        raise FlowError("candidate_changed", "制作说明已变化")
    saved_constraints = json_file(folder / "constraints.json")
    if hash_json(saved_constraints) != candidate["constraints_sha256"]:
        raise FlowError("candidate_changed", "已确认约束已变化")
    check_constraints(saved_spec, saved_constraints)
    if hash_file(Path(candidate["constraints_path"])) != candidate["constraints_file_sha256"]:
        raise FlowError("constraints_changed", "原始已确认约束文件已变化")
    if hash_file(config.font_profile) != candidate["font_profile_sha256"]:
        raise FlowError("font_changed", "字体方案文件已变化")
    sys.path.insert(0, str(engine_directory()))
    from journal_pdf.editorial import engine_signature
    from journal_pdf.fonts import FontRegistry
    if engine_signature() != report["engine_signature"]:
        raise FlowError("engine_changed", "渲染引擎源码已变化")
    with font_warning_log(folder / "render.log", "a"):
        registry = FontRegistry(config.font_profile, config.cache_root)
        try:
            if registry.fingerprint != report["font"]["fingerprint"]:
                raise FlowError("font_changed", "实际字体指纹已变化")
        finally:
            registry.close()
    seal = check_snapshot(config, candidate["probe_id"])
    source = Path(seal["source_root"])
    for binding in report["source_bindings"]:
        rel = binding["path"]
        if hash_file(safe_child(source, rel)) != binding["sha256"] or seal["sources"].get(rel) != binding["sha256"]:
            raise FlowError("source_changed", f"候选来源变化：{rel}")
    if {(row["path"], row["sha256"]) for row in report["source_bindings"]} != {(row["path"], row["sha256"]) for row in saved_spec["sources"]}:
        raise FlowError("source_identity", "引擎报告的来源绑定与制作说明不一致")
    return candidate, report, report_path


def render(config: Config, spec_path: Path, constraints_path: Path, probe_id: str) -> dict:
    began = time.perf_counter()
    seal = check_snapshot(config, probe_id)
    spec = json_file(spec_path)
    constraints = json_file(constraints_path)
    constraints_initial_sha = hash_file(constraints_path)
    check_constraints(spec, constraints)
    from .core import author_dir
    author = author_dir(config.delivery_root, spec["author_rel"])
    if spec.get("author") != author.name:
        raise FlowError("author_mismatch", "制作说明作者与已确认目标作者不一致")
    if spec.get("synthetic") is True:
        raise FlowError("synthetic", "合成测试说明不能生成可发布候选")
    bindings = spec.get("sources")
    if not isinstance(bindings, list) or not bindings:
        raise FlowError("source_identity", "真实图件必须绑定源文件")
    for row in bindings:
        if not isinstance(row, dict) or seal["sources"].get(row.get("path")) != row.get("sha256"):
            raise FlowError("source_identity", "制作说明来源与当前预检快照不一致")
    candidate_id = uuid.uuid4().hex
    folder = config.state_root / "candidates" / candidate_id
    with writer_lock(config.state_root):
        folder.mkdir(parents=True)
        log_path = folder / "render.log"
        sys.path.insert(0, str(engine_directory()))
        from journal_pdf.assets import Assets
        from journal_pdf.common import FigureError
        from journal_pdf.fonts import FontRegistry
        from journal_pdf.render import render_one
        with font_warning_log(log_path, "w"):
            try:
                registry = FontRegistry(config.font_profile, config.cache_root)
                assets = Assets()
                try:
                    report = render_one(spec, registry, assets, Path(seal["source_root"]), folder / "render")
                finally:
                    assets.close()
                    registry.close()
            except FigureError as exc:
                raise FlowError(exc.code, f"引擎阻断：{exc}；日志：{log_path}") from exc
        pdf = folder / "render" / report["output_pdf"]
        check_report(report, pdf)
        if hash_file(constraints_path) != constraints_initial_sha:
            raise FlowError("constraints_changed", "渲染期间原始已确认约束文件变化")
        write_json(folder / "spec.json", spec)
        write_json(folder / "constraints.json", constraints)
        report_path = folder / "render" / Path(report["output_pdf"]).parent / "report.json"
        candidate = {"candidate_id": candidate_id, "probe_id": probe_id,
            "output_pdf": report["output_pdf"], "output_sha256": report["pdf_sha256"],
            "report_sha256": hash_file(report_path), "spec_sha256": hash_json(spec),
            "constraints_sha256": hash_json(constraints), "status": "candidate-rendered",
            "constraints_path": str(constraints_path.resolve()),
            "constraints_file_sha256": constraints_initial_sha,
            "font_profile_sha256": hash_file(config.font_profile),
            "render_log": str(log_path),
            "warning_count": len([line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]),
            "render_ms": round((time.perf_counter() - began) * 1000, 3)}
        write_json(folder / "candidate.json", candidate)
    return {"candidate_id": candidate_id, "pdf": str(pdf), "sha256": report["pdf_sha256"],
        "render_ms": candidate["render_ms"], "audit": "passed", "status": "candidate-rendered",
        "render_log": str(log_path), "warning_count": candidate["warning_count"]}
