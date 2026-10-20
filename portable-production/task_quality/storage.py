"""Evidence hashing, immutable records, and isolated workspace ownership."""
from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from typing import Iterator
from pathlib import Path

from localflow.core import hash_file, safe_child, writer_lock, FlowError
from .models import JSON, Contract, FileRef, GateError, array, fields, text


def read(path: Path) -> JSON:
    def reject_constant(value: str) -> None:
        raise GateError('invalid_json', f'Nonfinite JSON value: {value}')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise GateError('invalid_json', f'Duplicate field: {key}')
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'),
                          parse_constant=reject_constant, object_pairs_hook=unique)
    except (OSError, ValueError) as exc:
        raise GateError('invalid_json', str(path)) from exc


def encoded(value: JSON) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def ref(path: Path) -> dict[str, JSON]:
    return dict(path=str(path.resolve()), sha256=hash_file(path))


def checked(item: FileRef) -> dict[str, JSON]:
    if not item.path.is_file() or hash_file(item.path) != item.sha256:
        raise GateError('hash_mismatch', str(item.path))
    return dict(path=str(item.path), sha256=item.sha256)


def child(root: Path, name: str) -> Path:
    try:
        return safe_child(root, name, existing=False)
    except FlowError as exc:
        raise GateError('unsafe_path', str(exc)) from exc


def state(contract: Contract) -> Path:
    return child(contract.workspace, '.task-quality')


def exclusive(path: Path, value: JSON) -> None:
    data = encoded(value)
    try:
        with path.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o444)
    except FileExistsError:
        if path.read_bytes() != data:
            raise GateError('sealed_record_conflict', str(path)) from None


def frozen_refs(path: Path) -> tuple[FileRef, ...]:
    raw = read(path)
    refs = []
    for item in array(raw):
        if type(item) is not dict or not {'path', 'sha256'}.issubset(item):
            raise GateError('invalid_schema', 'Unsupported frozen manifest item')
        refs.append(FileRef.parse(dict(path=item['path'], sha256=item['sha256'])))
    return tuple(refs)


def inputs(contract: Contract) -> list[JSON]:
    refs = [contract.source, *contract.source_inputs, contract.history.evidence, contract.frozen_manifest,
            contract.runtime.python, contract.runtime.font_profile, *contract.runtime.code]
    refs.extend(FileRef(path, hash_file(path)) for path in sorted(Path(__file__).parent.glob('*.py')))
    tool_core = Path(__file__).parents[1] / 'localflow' / 'core.py'
    refs.append(FileRef(tool_core, hash_file(tool_core)))
    refs.append(FileRef(Path(sys.executable).resolve(), hash_file(Path(sys.executable))))
    rows: list[JSON] = [checked(item) for item in refs]
    rows.extend(checked(item) for item in frozen_refs(contract.frozen_manifest.path))
    return rows


def prepare(contract: Contract, raw: JSON) -> dict[str, JSON]:
    workspace = contract.workspace
    roots = contract.author_roots
    protected = [contract.source.path, *[item.path for item in contract.source_inputs], contract.history.evidence.path, contract.frozen_manifest.path,
                 contract.runtime.python.path, contract.runtime.font_profile.path, *[r.path for r in contract.runtime.code]]
    protected += [item.path for item in frozen_refs(contract.frozen_manifest.path)]
    if any(workspace == root or workspace.is_relative_to(root) or root.is_relative_to(workspace) for root in roots):
        raise GateError('author_directory_overlap', str(workspace))
    if any(path.is_relative_to(workspace) or workspace == path for path in protected):
        raise GateError('input_workspace_overlap', str(workspace))
    if contract.runtime.python.path != Path(sys.executable).resolve():
        raise GateError('runtime_mismatch', 'Contract Python must identify the running interpreter')
    if any(not item.path.is_relative_to(contract.runtime.code_root) for item in contract.runtime.code):
        raise GateError('runtime_mismatch', 'Runtime code must be inside code_root')
    destinations = [child(workspace, item.path) for item in contract.outputs]
    targets = [item.delivery_target for item in contract.outputs]
    frozen_paths = {item.path for item in frozen_refs(contract.frozen_manifest.path)}
    if len(set(targets)) != len(targets):
        raise GateError('duplicate_output', 'Delivery targets must be unique')
    for target in targets:
        if not any(target != root and target.is_relative_to(root) for root in roots) or target in destinations:
            raise GateError('unsafe_delivery_target', str(target))
        if target in frozen_paths:
            raise GateError('frozen_target', 'Use the existing formal revision workflow: ' + str(target))
    if len(set(destinations)) != len(destinations) or any(path.is_relative_to(state(contract)) for path in destinations):
        raise GateError('duplicate_output', 'Output paths must be distinct and outside gate state')
    if contract.history.reusable and contract.history.conclusion == 'new' and not contract.history.revision_authorization.strip():
        raise GateError('history_reuse_required', 'Reusable output requires concrete revision authorization for new work')
    if contract.history.conclusion == 'reuse':
        raise GateError('history_reuse_required', 'Reuse existing output via localflow; do not create a new candidate')
    history = fields(read(contract.history.evidence.path), 'checked conclusion reusable observation')
    text(history['observation'])
    if history['checked'] is not True or history['conclusion'] != contract.history.conclusion or history['reusable'] != contract.history.reusable:
        raise GateError('history_unchecked', 'History evidence must confirm checked conclusion and reusable status')
    rows = inputs(contract)
    for parent in workspace.parents:
        if (parent / '.task-quality-owner.json').exists():
            raise GateError('workspace_conflict', str(parent))
    if workspace.exists() and any(workspace.rglob('.task-quality-owner.json')):
        if not (workspace / '.task-quality-owner.json').exists():
            raise GateError('workspace_conflict', str(workspace))
    workspace.mkdir(parents=True, exist_ok=True)
    marker = workspace / '.task-quality-owner.json'
    owner: dict[str, JSON] = dict(id=contract.id, contract=raw)
    try:
        exclusive(marker, owner)
    except GateError as exc:
        raise GateError('workspace_conflict', str(workspace)) from exc
    state(contract).mkdir(exist_ok=True)
    envelope: dict[str, JSON] = dict(schema_version=1, contract=raw, inputs=rows, targets=target_states(contract),
        limitation='Audit declarations are not cryptographic identity or proof of visual truth')
    exclusive(state(contract) / 'envelope.json', envelope)
    return envelope


def verify_refs(raw: JSON) -> None:
    for item in array(raw):
        checked(FileRef.parse(item))


@contextmanager
def task_lock(contract: Contract) -> Iterator[None]:
    try:
        with writer_lock(contract.workspace):
            yield
    except FlowError as exc:
        raise GateError(exc.code, str(exc)) from exc


def target_states(contract: Contract) -> list[JSON]:
    rows: list[JSON] = []
    for item in contract.outputs:
        path = item.delivery_target
        if path.exists() and not path.is_file():
            raise GateError('unsafe_delivery_target', str(path))
        rows.append(dict(path=str(path), exists=path.exists(), sha256=hash_file(path) if path.exists() else None))
    return rows
