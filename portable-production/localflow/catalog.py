from __future__ import annotations

import time
import re
from pathlib import Path

from .core import Config, author_dir, hash_file, json_file, write_json, writer_lock


def catalog(config: Config) -> dict:
    root = config.delivery_root
    began = time.perf_counter()
    cache_file = config.state_root / "catalog-cache.json"
    old = json_file(cache_file).get("files", {}) if cache_file.exists() else {}
    rows: dict[str, dict] = {}
    authors: list[str] = []
    deliveries: list[str] = []
    reused = 0
    hashed = 0
    for editor in sorted(root.iterdir()):
        if not editor.is_dir() or editor.is_symlink():
            continue
        for folder in sorted(editor.iterdir()):
            if not folder.is_dir() or folder.is_symlink():
                continue
            targets = sorted(folder.iterdir()) if folder.name == "0没做完" else [folder]
            for author in targets:
                if not author.is_dir() or author.is_symlink():
                    continue
                rel_author = author.relative_to(root).as_posix()
                author_dir(root, rel_author)
                if rel_author not in authors:
                    authors.append(rel_author)
                for file in sorted(author.rglob("*")):
                    if not file.is_file() or file.is_symlink() or any(parent.is_symlink() for parent in file.parents if parent != root):
                        continue
                    rel = file.relative_to(root).as_posix()
                    st = file.stat()
                    stamp = [st.st_size, st.st_mtime_ns, st.st_ctime_ns]
                    cached = old.get(rel)
                    if isinstance(cached, dict) and cached.get("stat") == stamp:
                        digest = cached["sha256"]
                        reused += 1
                    else:
                        digest = hash_file(file)
                        hashed += 1
                    rows[rel] = {"sha256": digest, "stat": stamp, "author_rel": rel_author}
                    if file.parent == author and re.fullmatch(re.escape(author.name) + r"-图[0-9]+(?:\.[0-9]+)*\.(?:pdf|jpg|jpeg)", file.name, re.IGNORECASE):
                        deliveries.append(rel)
    output = {"schema_version": 1, "root": str(root), "authors": sorted(authors),
        "existing_deliveries": sorted(deliveries),
        "files": rows, "reused_hashes": reused, "hashed_files": hashed,
        "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)}
    with writer_lock(config.state_root):
        write_json(cache_file, output)
    return {"authors": len(authors), "files": len(rows), "existing_deliveries": len(deliveries), "reused_hashes": reused,
        "hashed_files": hashed, "elapsed_ms": output["elapsed_ms"], "index": str(cache_file)}
