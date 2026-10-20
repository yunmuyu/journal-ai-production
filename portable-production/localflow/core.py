from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class FlowError(Exception):

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


def engine_directory(release: Path | None = None) -> Path:
    release = release or Path(__file__).resolve().parents[1]
    candidates = [release / name for name in ("direct-pdf", "engine")
                  if (release / name / "journal_pdf" / "__init__.py").is_file()]
    if len(candidates) != 1:
        raise FlowError("engine_layout", "应有且仅有一套引擎：direct-pdf 或 engine")
    return candidates[0]


@dataclass(frozen=True, slots=True)
class Config:
    delivery_root: Path
    state_root: Path
    font_profile: Path
    cache_root: Path


def json_file(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise FlowError("invalid_json", f"无法读取 JSON：{path}") from exc
    if not isinstance(value, dict):
        raise FlowError("invalid_json", f"JSON 顶层必须是对象：{path}")
    return value


def load_config(path: Path) -> Config:
    raw = json_file(path)
    if raw.get("workbench_enabled") is not False:
        raise FlowError("workbench_disabled", "workbench_enabled 必须明确为 false")
    try:
        config = Config(*(Path(raw[key]).resolve() for key in (
            "delivery_root", "state_root", "font_profile", "cache_root")))
    except (KeyError, TypeError) as exc:
        raise FlowError("invalid_config", "配置缺少四个必需路径") from exc
    if config.delivery_root == config.state_root or config.delivery_root in config.state_root.parents or config.state_root in config.delivery_root.parents:
        raise FlowError("state_delivery_overlap", "状态目录与交付目录必须隔离")
    if config.cache_root == config.delivery_root or config.delivery_root in config.cache_root.parents:
        raise FlowError("cache_delivery_overlap", "缓存目录不能位于交付目录内")
    return config


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_json(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def safe_child(root: Path, relative: str, *, existing: bool = True) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or not relative or any(part in (".", "..") for part in candidate.parts):
        raise FlowError("unsafe_path", f"不是安全相对路径：{relative}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved_root not in resolved.parents:
        raise FlowError("unsafe_path", f"路径越过根目录：{relative}")
    current = resolved_root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise FlowError("unsafe_path", f"路径包含符号链接或联接点：{relative}")
    if existing and not resolved.exists():
        raise FlowError("missing_path", f"路径不存在：{relative}")
    return resolved


def author_dir(root: Path, relative: str) -> Path:
    folder = safe_child(root, relative)
    if not folder.is_dir() or len(Path(relative).parts) not in (2, 3):
        raise FlowError("author_path", "作者目录须已存在，格式为编辑/作者或编辑/0没做完/作者")
    parts = Path(relative).parts
    if len(parts) == 3 and parts[1] != "0没做完":
        raise FlowError("author_path", "三层作者目录第二层只能是 0没做完")
    return folder


def figure_name(author: str, number: str) -> str:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", number):
        raise FlowError("figure_number", "图号只能是数字与小数点，如 4.1")
    if any(char in author for char in '\\/:*?"<>|') or not author:
        raise FlowError("author_name", "作者目录名不安全")
    return f"{author}-图{number}.pdf"


@contextmanager
def writer_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".writer.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise FlowError("writer_busy", f"本地写入锁已占用：{lock}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(f"pid={os.getpid()} time={time.time()}\n")
        yield
    finally:
        lock.unlink(missing_ok=True)
