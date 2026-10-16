from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

from .core import Config, FlowError, author_dir, figure_name, hash_file, hash_json, json_file, write_json, writer_lock
from .rendering import check_candidate


def review(config: Config, candidate_id: str, record_path: Path) -> dict:
    candidate, report, _pdf = check_candidate(config, candidate_id)
    record = json_file(record_path)
    expected = {"candidate_id": candidate_id, "output_sha256": candidate["output_sha256"],
        "constraints_sha256": candidate["constraints_sha256"],
        "source_hashes": {row["path"]: row["sha256"] for row in report["source_bindings"]}}
    for key, value in expected.items():
        if record.get(key) != value:
            raise FlowError("review_binding", f"审阅记录绑定不匹配：{key}")
    if not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip():
        raise FlowError("review_evidence", "审阅人不能为空")
    target = author_dir(config.delivery_root, record.get("author_rel", ""))
    figure_name(target.name, record.get("figure_number", ""))
    for key in ("content", "visual"):
        item = record.get(key)
        if not isinstance(item, dict) or item.get("conclusion") != "approved":
            raise FlowError("review_evidence", f"{key} 须有明确 approved 结论")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(v, str) and len(v.strip()) >= 12 for v in evidence):
            raise FlowError("review_evidence", f"{key} 须给出具体核对证据")
    stored = config.state_root / "reviews" / f"{candidate_id}.json"
    with writer_lock(config.state_root):
        if stored.exists():
            previous = json_file(stored)
            if previous.get("record") != record:
                raise FlowError("review_exists", "已有不同审阅记录；请生成新候选")
            return {"candidate_id": candidate_id, "review_sha256": previous["record_sha256"], "cached": True}
        write_json(stored, {"schema_version": 1, "record": record,
            "record_sha256": hash_json(record), "reviewed_at": time.time(),
            "acceptance": "not_recorded"})
    return {"candidate_id": candidate_id, "review_sha256": hash_json(record),
        "status": "agent-reviewed", "acceptance": "not_recorded"}


def publish(config: Config, candidate_id: str, author_rel: str, figure_number: str,
    expected_target_sha: str | None = None) -> dict:
    began = time.perf_counter()
    candidate, report, pdf = check_candidate(config, candidate_id)
    review_path = config.state_root / "reviews" / f"{candidate_id}.json"
    reviewed = json_file(review_path)
    record = reviewed["record"]
    if reviewed.get("record_sha256") != hash_json(record) or record.get("output_sha256") != candidate["output_sha256"]:
        raise FlowError("review_changed", "审阅记录或候选绑定已变化")
    if record.get("author_rel") != author_rel or record.get("figure_number") != figure_number:
        raise FlowError("review_target", "发布目标与审阅记录绑定不一致")
    folder = author_dir(config.delivery_root, author_rel)
    if report.get("author") != folder.name:
        raise FlowError("author_mismatch", "制作说明作者与交付目录作者不一致")
    target = folder / figure_name(folder.name, figure_number)
    from .probing import check_snapshot
    seal = check_snapshot(config, candidate["probe_id"])
    source_root = Path(seal["source_root"])
    if target.resolve() in {(source_root / rel).resolve() for rel in seal["sources"]}:
        raise FlowError("source_protected", "发布目标是本候选绑定的原始素材，禁止覆盖")
    constraints = json_file(config.state_root / "candidates" / candidate_id / "constraints.json")
    if {"author_rel": author_rel, "figure_number": figure_number} not in constraints["confirmed"]["expected_outputs"]:
        raise FlowError("constraint_target", "发布目标不在已确认输出清单中")
    if target.is_symlink():
        raise FlowError("unsafe_target", "目标 PDF 不能是符号链接")
    with writer_lock(config.state_root):
        sibling_stem = target.stem.casefold()
        if any(item.stem.casefold() == sibling_stem and item.suffix.casefold() in (".jpg", ".jpeg") for item in folder.iterdir()):
            raise FlowError("format_conflict", "同一作者图号已有 JPG/JPEG 成品；需单独审核迁移")
        accepted = config.state_root / "accepted" / author_rel / f"{target.name}.json"
        if accepted.exists():
            locked = json_file(accepted)
            if target.exists() and hash_file(target) == candidate["output_sha256"] == locked["sha256"]:
                return {"status": "already-accepted", "target": str(target), "sha256": locked["sha256"]}
            raise FlowError("accepted_target", "目标已登记人工终检；不允许普通发布替换")
        existed = target.exists()
        if existed:
            current = hash_file(target)
            if current == candidate["output_sha256"]:
                return {"status": "already-published", "target": str(target),
                    "sha256": current, "acceptance": "not_recorded"}
            if expected_target_sha is None or current != expected_target_sha:
                raise FlowError("target_changed", "目标已有不同内容；替换需提供当前目标的准确 SHA-256")
            archive = config.state_root / "archive" / author_rel / target.name / f"{current}.pdf"
            archive.parent.mkdir(parents=True, exist_ok=True)
            if archive.exists() and hash_file(archive) != current:
                raise FlowError("archive_collision", "外置归档已有同名异内容文件")
            if not archive.exists():
                shutil.copy2(target, archive)
                if hash_file(archive) != current:
                    raise FlowError("archive_failed", "外置归档哈希核对失败")
        elif expected_target_sha is not None:
            raise FlowError("target_missing", "已给 expected-target-sha，但目标不存在")
        fd, temp_name = tempfile.mkstemp(prefix=".publish-", suffix=".pdf", dir=folder)
        try:
            with os.fdopen(fd, "wb") as output, pdf.open("rb") as source:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            temp = Path(temp_name)
            if hash_file(temp) != candidate["output_sha256"]:
                raise FlowError("copy_failed", "发布副本哈希核对失败")
            if target.exists() != existed:
                raise FlowError("target_changed", "写入前目标存在状态变化")
            if existed and hash_file(target) != expected_target_sha:
                raise FlowError("target_changed", "写入前目标内容再次变化")
            os.replace(temp, target)
        finally:
            Path(temp_name).unlink(missing_ok=True)
        publication = {"candidate_id": candidate_id, "author_rel": author_rel,
            "figure_number": figure_number, "target": str(target),
            "sha256": candidate["output_sha256"], "review_sha256": reviewed["record_sha256"],
            "acceptance": "not_recorded", "published_at": time.time()}
        write_json(config.state_root / "publications" / f"{candidate_id}.json", publication)
    return {"status": "published-candidate", "target": str(target),
        "sha256": candidate["output_sha256"], "acceptance": "not_recorded",
        "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)}


def accept(config: Config, author_rel: str, figure_number: str, expected_sha: str,
    reviewer: str, evidence: str) -> dict:
    folder = author_dir(config.delivery_root, author_rel)
    target = folder / figure_name(folder.name, figure_number)
    if not reviewer.strip() or len(evidence.strip()) < 12:
        raise FlowError("acceptance_evidence", "人工终检须记录审阅人及具体核对证据")
    with writer_lock(config.state_root):
        if not target.is_file() or target.is_symlink() or hash_file(target) != expected_sha:
            raise FlowError("acceptance_target", "人工终检登记的目标哈希与实际文件不一致")
        path = config.state_root / "accepted" / author_rel / f"{target.name}.json"
        if path.exists():
            previous = json_file(path)
            if previous["sha256"] != expected_sha:
                raise FlowError("accepted_target", "已有不同人工终检记录")
            return {"status": "already-accepted", "target": str(target), "sha256": expected_sha}
        write_json(path, {"target": str(target), "sha256": expected_sha,
            "reviewer": reviewer, "evidence": evidence, "accepted_at": time.time()})
    return {"status": "accepted", "target": str(target), "sha256": expected_sha}
