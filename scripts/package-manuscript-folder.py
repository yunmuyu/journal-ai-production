"""Package a local source folder for the existing archive intake; never modify it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile


def package(folder: Path, output: Path) -> dict:
    root = folder.resolve(strict=True)
    output = output.resolve()
    if not root.is_dir() or output == root or root in output.parents:
        raise ValueError('output must be outside the source folder')
    members = []
    total = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        parent = Path(parent)
        if any((parent / name).is_symlink() or getattr(os.path, 'isjunction', lambda _: False)(parent / name) for name in dirs + files):
            raise ValueError('source contains a symbolic link; inspect it before intake')
        dirs[:] = sorted(name for name in dirs if name not in ('交付', '__MACOSX'))
        for name in sorted(files):
            if name.startswith('~$'):
                continue
            source = parent / name
            relative = source.relative_to(root).as_posix()
            before = source.stat()
            total += before.st_size
            if total > 512 * 1024 * 1024:
                raise ValueError('source exceeds archive intake size limit')
            data = source.read_bytes()
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('source changed while packaging: ' + relative)
            members.append((relative, data, hashlib.sha256(data).hexdigest()))
    if not any(name.lower().endswith(('.doc', '.docx')) for name, _, _ in members):
        raise ValueError('no manuscript Word file found')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as raw, zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data, _ in sorted(members):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return {'generatedArchive': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'sourceFolder': str(root), 'members': [{'path': n, 'sha256': h} for n, _, h in members]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    print(json.dumps(package(args.folder, args.archive), ensure_ascii=False))
