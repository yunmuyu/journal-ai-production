from __future__ import annotations
import hashlib, json, os, tempfile, math
from pathlib import Path
from typing import Any

PT_PER_MM = 72 / 25.4

class FigureError(ValueError):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code, self.details = code, details
    def as_dict(self):
        return {"code": self.code, "message": str(self), **self.details}


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def atomic_json(path: str | Path, data: Any) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def digest_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def digest_json(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def resolve_source(root: Path, value: str) -> Path:
    root = root.resolve()
    p = Path(value)
    if not p.is_absolute(): p = root / p
    p = p.resolve()
    if p != root and root not in p.parents:
        raise FigureError("source_outside_root", "素材路径必须位于显式指定的素材根目录内", path=str(p))
    if not p.is_file(): raise FigureError("source_missing", "素材文件不存在", path=str(p))
    return p


def finite(values, positive=False):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               and (not positive or v > 0) for v in values)


def safe_name(value: str) -> str:
    if not isinstance(value,str) or not value or value.endswith((' ','.')) or any(c in value for c in '\\/:*?"<>|') or value in (".", ".."):
        raise FigureError("unsafe_id", "图件 ID 不能包含路径分隔符或非法文件名字符", id=value)
    stem=value.split('.')[0].upper()
    reserved={'CON','PRN','AUX','NUL',*('COM'+str(i) for i in range(1,10)),*('LPT'+str(i) for i in range(1,10))}
    if stem in reserved or any(ord(c)<32 for c in value):
        raise FigureError('unsafe_id','图件ID含Windows保留名称或控制字符',id=value)
    return value


def intersects(a, b, gap=0):
    return a[0] < b[2] + gap and a[2] + gap > b[0] and a[1] < b[3] + gap and a[3] + gap > b[1]


def contains(outer, inner, tol=0):
    return inner[0] >= outer[0]-tol and inner[1] >= outer[1]-tol and inner[2] <= outer[2]+tol and inner[3] <= outer[3]+tol


def segment_hits(a, b, rect, pad=0):
    lo, hi = 0., 1.
    for k in (0, 1):
        mn, mx = rect[k]-pad, rect[k+2]+pad
        delta = b[k]-a[k]
        if abs(delta) < 1e-10:
            if a[k] <= mn+1e-7 or a[k] >= mx-1e-7: return False
        else:
            s, t = (mn-a[k])/delta, (mx-a[k])/delta
            lo, hi = max(lo, min(s,t)), min(hi,max(s,t))
            if lo >= hi-1e-7: return False
    return hi > 1e-7 and lo < 1-1e-7


def validate_output_isolation(source_root: Path, output_root: Path) -> None:
    """Check before ANY mkdir/write, including failure reports and GUI startup."""
    source = source_root.resolve()
    output = output_root.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise FigureError("output_source_overlap", "候选输出与只读素材目录必须相互隔离")
