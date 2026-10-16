from __future__ import annotations

import sys
import time
from pathlib import Path

from .core import Config, FlowError, hash_json, json_file, safe_child, write_json, writer_lock
from .probing import check_snapshot


def route(config: Config, probe_id: str, review_path: Path, manifest_path: Path) -> dict:
    seal = check_snapshot(config, probe_id)
    review = json_file(review_path)
    manifest = json_file(manifest_path)
    source = Path(manifest.get("source_root", "")).resolve()
    if source != Path(seal["source_root"]):
        raise FlowError("route_manifest", "当前 manifest 的源目录与预检快照不同")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != len(seal["sources"]):
        raise FlowError("route_manifest", "当前 manifest 文件集合与预检快照不同")
    bound: dict[str, str] = {}
    identity: dict[str, str] = {}
    live_rows: list[dict[str, str]] = []
    for row in rows:
        rel = row["path"]
        path = safe_child(source, rel)
        bound[rel] = seal["sources"].get(rel, "")
        identity[row["id"]] = rel
        live_rows.append({"id": row["id"], "path": str(path)})
    if bound != seal["sources"] or identity != seal["identity"]:
        raise FlowError("route_manifest", "当前 manifest 文件集合与预检快照不同")
    release = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(release / "preflight"))
    from journal_preflight.routing import apply_review
    probe_result = json_file(config.state_root / "probes" / probe_id / "evidence" / "probe.json")
    result = apply_review(probe_result, review, {"files": live_rows})
    route_id = hash_json({"probe_id": probe_id, "review": review, "manifest": manifest})
    target = config.state_root / "routes" / f"{route_id}.json"
    with writer_lock(config.state_root):
        if target.exists():
            return {"route_id": route_id, "figures": len(result["figures"]), "cached": True}
        write_json(target, {"route_id": route_id, "probe_id": probe_id,
            "generated_at": time.time(), "result": result, "ready_for_publication": False})
    return {"route_id": route_id, "figures": len(result["figures"]), "cached": False,
        "ready_for_publication": False}
