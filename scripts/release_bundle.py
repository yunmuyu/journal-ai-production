"""Build a reproducible public portable bundle; verify an extracted bundle.

Uses only the Python standard library. Configuration, fonts and production
artifacts remain external. Git-tracked inputs and sealed hashes are required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_bytes(root: Path, name: str) -> bytes:
    relative = PurePosixPath(name)
    if (not name or "\\" in name or relative.is_absolute()
            or ":" in name or ".." in relative.parts
            or relative.as_posix() != name):
        raise ValueError(f"Unsafe bundle path: {name}")
    target = root.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Bundle path escapes root: {name}")
    if any(part.is_symlink() for part in [target, *target.parents]):
        raise ValueError(f"Bundle symlink forbidden: {name}")
    return target.read_bytes()


def verify(root: Path) -> dict:
    manifest = json.loads((root / "BUNDLE-MANIFEST.json").read_text(encoding="utf-8"))
    names = set()
    for item in manifest["files"]:
        name = item["path"]
        if name in names:
            raise ValueError(f"Duplicate bundle path: {name}")
        names.add(name)
        data = file_bytes(root, name)
        if len(data) != item["bytes"] or digest(data) != item["sha256"]:
            raise ValueError(f"Bundle hash mismatch: {name}")
    return {"release": manifest["release"], "verified_files": len(names)}


def build(root: Path, output: Path) -> dict:
    release = json.loads((root / "RELEASE.json").read_text(encoding="utf-8"))
    identity = release["id"]
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}-[a-z0-9-]+", identity):
        raise ValueError("Invalid release identity")
    tracked = set(subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z"]).decode("utf-8").split("\0"))
    payload = {}
    for item in release["portableFiles"]:
        name = "portable-production/" + item["path"]
        data = file_bytes(root, name)
        if digest(data) != item["sha256"] or len(data) != item["bytes"]:
            raise ValueError(f"Release hash mismatch: {name}")
        payload[name] = data
    for name in ("README.md", "CHANGELOG.md", "RELEASE.json",
                 "docs/RELEASE-GUIDE.md", "scripts/release_bundle.py",
                 f"release-notes/{identity}.md"):
        payload[name] = file_bytes(root, name)
    for name in payload:
        if name not in tracked:
            raise ValueError(f"Untracked bundle input: {name}")
        if (name.endswith((".local.json", ".ttf", ".otf", ".ttc", ".pdf",
                           ".docx", ".ai", ".pyc"))
                or any(part.startswith(".") for part in PurePosixPath(name).parts)):
            raise ValueError(f"Private or generated bundle input: {name}")
    manifest = {"schemaVersion": 1, "release": identity, "files": [
        {"path": name, "bytes": len(data), "sha256": digest(data)}
        for name, data in sorted(payload.items())]}
    payload["BUNDLE-MANIFEST.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # Fixed timestamp, order and permissions make the same inputs reproducible.
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            entry = zipfile.ZipInfo(f"journal-ai-production-{identity}/{name}",
                                    date_time=(2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    checksum = digest(output.read_bytes())
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{checksum}  {output.name}\n", encoding="utf-8")
    return {"release": identity, "files": len(manifest["files"]),
            "bytes": output.stat().st_size, "sha256": checksum}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "build" and args.output is None:
        parser.error("build requires --output (must not already exist)")
    result = build(args.root, args.output) if args.command == "build" else verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
