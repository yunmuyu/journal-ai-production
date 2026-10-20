from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import catalog
from .core import FlowError, load_config
from .probing import probe
from .publishing import accept, publish, review
from .rendering import render
from .routing import route


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="离线期刊图件流程；状态与交付分离，不启用工作台")
    ap.add_argument("--config", required=True, type=Path, help="含 delivery_root/state_root/font_profile/cache_root/workbench_enabled=false 的 JSON")
    commands = ap.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="只读扫描现有编辑/作者目录，更新外置哈希索引")
    scan = commands.add_parser("probe", help="只读预检 manifest，并逐文件密封证据")
    scan.add_argument("manifest", type=Path, help="含 source_root 与 files[{id,path}] 的 JSON")
    routing = commands.add_parser("route", help="按 Agent 审阅记录做预检路由，并实时复核 manifest 源文件")
    routing.add_argument("probe_id")
    routing.add_argument("--review", required=True, type=Path)
    routing.add_argument("--manifest", required=True, type=Path)
    build = commands.add_parser("render", help="核对预检与已确认约束，渲染候选并审计实际 PDF")
    build.add_argument("spec", type=Path)
    build.add_argument("--constraints", required=True, type=Path)
    build.add_argument("--probe-id", required=True)
    inspect = commands.add_parser("review", help="保存 Agent 内部复核记录；不会标为人工终检")
    inspect.add_argument("candidate_id")
    inspect.add_argument("--record", required=True, type=Path,
        help="必须绑定候选/输出/源/约束哈希、作者路径/图号及内容与视觉具体证据")
    delivery = commands.add_parser("publish", help="向已存在作者目录原子发布平铺 PDF；异哈希默认拒绝")
    delivery.add_argument("candidate_id")
    delivery.add_argument("--author-rel", required=True)
    delivery.add_argument("--figure-number", required=True)
    delivery.add_argument("--expected-target-sha", help="仅替换时给出当前目标 PDF 的准确 SHA-256；旧版外置归档")
    delivery.add_argument("--author", help="显式目标文件作者；必须与已确认约束和审阅记录完全一致")
    delivery.add_argument("--target-basename", help="显式平铺PDF文件名；须绑定约束及审阅，不得含目录")
    acceptance = commands.add_parser("accept", help="显式登记人工终检文件及哈希，此后普通发布不可替换")
    acceptance.add_argument("--author-rel", required=True)
    acceptance.add_argument("--figure-number", required=True)
    acceptance.add_argument("--expected-sha", required=True)
    acceptance.add_argument("--reviewer", required=True)
    acceptance.add_argument("--evidence", required=True)
    status = commands.add_parser("status", help="显示候选与内部复核、交付状态")
    status.add_argument("candidate_id", nargs="?")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = load_config(args.config)
        match args.command:
            case "catalog":
                result = catalog(config)
            case "probe":
                result = probe(config, args.manifest)
            case "route":
                result = route(config, args.probe_id, args.review, args.manifest)
            case "render":
                result = render(config, args.spec, args.constraints, args.probe_id)
            case "review":
                result = review(config, args.candidate_id, args.record)
            case "publish":
                result = publish(config, args.candidate_id, args.author_rel,
                    args.figure_number, args.expected_target_sha,
                    author=args.author, target_basename=args.target_basename)
            case "accept":
                result = accept(config, args.author_rel, args.figure_number,
                    args.expected_sha, args.reviewer, args.evidence)
            case "status":
                root = config.state_root
                if args.candidate_id:
                    cid = args.candidate_id
                    if not cid or not all(c in "0123456789abcdef" for c in cid):
                        raise FlowError("candidate_id", "候选 ID 无效")
                    publication = root / "publications" / f"{cid}.json"
                    accepted = False
                    if publication.exists():
                        details = json.loads(publication.read_text(encoding="utf-8"))
                        marker = root / "accepted" / details["author_rel"] / (Path(details["target"]).name + ".json")
                        accepted = marker.exists()
                    result = {"candidate_id": cid,
                        "candidate": (root / "candidates" / cid / "candidate.json").exists(),
                        "agent_review": (root / "reviews" / f"{cid}.json").exists(),
                        "publication": publication.exists(),
                        "protected": accepted}
                else:
                    result = {"catalog": (root / "catalog-cache.json").exists(),
                        "probe_count": len(list((root / "probes").glob("*/seal.json"))),
                        "candidate_count": len(list((root / "candidates").glob("*/candidate.json"))),
                        "review_count": len(list((root / "reviews").glob("*.json"))),
                        "publication_count": len(list((root / "publications").glob("*.json"))),
                        "protected_file_count": len(list((root / "accepted").rglob("*.json")))}
            case _:
                raise FlowError("command", "未知命令")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FlowError, OSError, KeyError, TypeError) as exc:
        code = exc.code if isinstance(exc, FlowError) else type(exc).__name__
        print(json.dumps({"status": "blocked", "code": code, "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
