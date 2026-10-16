from __future__ import annotations

import sys
import time
from pathlib import Path

from .core import Config, FlowError, hash_file, hash_json, json_file, safe_child, write_json, writer_lock


def files_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hash_file(p) for p in sorted(root.rglob("*")) if p.is_file()}


def code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parents[1] / "preflight" / "journal_preflight"
    return {p.name: hash_file(p) for p in sorted(package.glob("*.py"))}


def check_snapshot(config: Config, probe_id: str) -> dict:
    if not probe_id or not all(c in "0123456789abcdef" for c in probe_id):
        raise FlowError("probe_id", "预检 ID 无效")
    folder = config.state_root / "probes" / probe_id
    seal = json_file(folder / "seal.json")
    if seal["code_hashes"] != code_hashes():
        raise FlowError("preflight_changed", "预检源码已变化，旧快照不能复用")
    source = Path(seal["source_root"])
    for rel, digest in seal["sources"].items():
        if hash_file(safe_child(source, rel)) != digest:
            raise FlowError("source_changed", f"预检后源文件已变化：{rel}")
    if files_hashes(folder / "evidence") != seal["evidence_hashes"]:
        raise FlowError("evidence_changed", "预检证据文件缺失或哈希变化")
    if hash_file(folder / "evidence" / "probe.json") != seal["probe_sha256"]:
        raise FlowError("evidence_changed", "预检报告已变化")
    return seal


def probe(config: Config, manifest_path: Path) -> dict:
    began = time.perf_counter()
    manifest = json_file(manifest_path)
    source = Path(manifest["source_root"]).resolve()
    if not source.is_dir() or source == config.state_root or source in config.state_root.parents or config.state_root in source.parents or source == config.cache_root or source in config.cache_root.parents or config.cache_root in source.parents:
        raise FlowError("source_root", "源目录不存在或与状态/缓存写入目录重叠")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise FlowError("manifest", "manifest.files 必须是非空数组")
    bindings: dict[str, str] = {}
    scan_files: list[dict[str, str]] = []
    identity: dict[str, str] = {}
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("path"), str):
            raise FlowError("manifest", "每个文件必须给出 id 与相对 path")
        rel = Path(row["path"]).as_posix()
        if row["id"] in ids or rel in bindings:
            raise FlowError("manifest", "文件 ID 或路径重复")
        ids.add(row["id"])
        identity[row["id"]] = rel
        file = safe_child(source, rel)
        if not file.is_file() or file.is_symlink():
            raise FlowError("manifest", f"源路径不是普通文件：{rel}")
        bindings[rel] = hash_file(file)
        scan_files.append({"id": row["id"], "path": str(file)})
    release = Path(__file__).resolve().parents[1]
    source_code_hashes = code_hashes()
    probe_id = hash_json({"source_root": str(source), "sources": bindings,
        "identity": identity, "code": source_code_hashes})
    folder = config.state_root / "probes" / probe_id
    if folder.exists():
        check_snapshot(config, probe_id)
        return {"probe_id": probe_id, "cached": True, "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)}
    with writer_lock(config.state_root):
        if folder.exists():
            check_snapshot(config, probe_id)
            return {"probe_id": probe_id, "cached": True}
        sys.path.insert(0, str(release / "preflight"))
        from journal_preflight.probe import scan
        evidence = folder / "evidence"
        result = scan({"files": scan_files}, evidence)
        for rel, digest in bindings.items():
            if hash_file(safe_child(source, rel)) != digest:
                raise FlowError("source_changed", f"预检时源文件变化：{rel}")
        seal = {"probe_id": probe_id, "source_root": str(source), "sources": bindings,
            "code_hashes": source_code_hashes, "identity": identity,
            "evidence_hashes": files_hashes(evidence),
            "probe_sha256": hash_file(evidence / "probe.json"), "asset_count": result["asset_count"]}
        write_json(folder / "seal.json", seal)
    return {"probe_id": probe_id, "cached": False, "assets": result["asset_count"],
        "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)}
