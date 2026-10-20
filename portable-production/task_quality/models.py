"""Strict JSON contract boundary; no optional runtime dependency."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

JSON: TypeAlias = str | int | float | bool | None | list['JSON'] | dict[str, 'JSON']


class GateError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f'{code}: {detail}')


def fields(raw: JSON, required: str) -> dict[str, JSON]:
    match raw:
        case dict():
            if set(raw) == set(required.split()):
                return raw
        case _:
            pass
    raise GateError('invalid_schema', f'Expected exactly: {required}')


def text(raw: JSON) -> str:
    if type(raw) is not str or not raw.strip():
        raise GateError('invalid_schema', 'Expected nonempty string')
    return raw


def texts(raw: JSON) -> tuple[str, ...]:
    if type(raw) is not list:
        raise GateError('invalid_schema', 'Expected string array')
    values = tuple(text(item) for item in raw)
    if not values or len(set(values)) != len(values):
        raise GateError('invalid_schema', 'Expected nonempty distinct strings')
    return values


def array(raw: JSON) -> list[JSON]:
    if type(raw) is not list:
        raise GateError('invalid_schema', 'Expected array')
    return raw


def number(raw: JSON) -> float:
    if type(raw) not in (int, float) or not math.isfinite(raw) or raw <= 0:
        raise GateError('invalid_schema', 'Expected finite positive number')
    return float(raw)


@dataclass(frozen=True, slots=True)
class FileRef:
    path: Path
    sha256: str

    @classmethod
    def parse(cls, raw: JSON) -> FileRef:
        row = fields(raw, 'path sha256')
        digest = text(row['sha256'])
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise GateError('invalid_schema', 'Expected lowercase SHA256')
        return cls(Path(text(row['path'])).resolve(), digest)


@dataclass(frozen=True, slots=True)
class History:
    evidence: FileRef
    conclusion: str
    reusable: bool
    revision_authorization: str

    @classmethod
    def parse(cls, raw: JSON) -> History:
        row = fields(raw, 'evidence conclusion reusable revision_authorization')
        if row['conclusion'] not in ('reuse', 'new') or type(row['reusable']) is not bool:
            raise GateError('invalid_schema', 'History must be checked with reuse/new conclusion')
        if type(row['revision_authorization']) is not str:
            raise GateError('invalid_schema', 'Revision authorization must be a string')
        return cls(FileRef.parse(row['evidence']), text(row['conclusion']),
                   row['reusable'], row['revision_authorization'])


@dataclass(frozen=True, slots=True)
class Runtime:
    python: FileRef
    code_root: Path
    code: tuple[FileRef, ...]
    font_profile: FileRef

    @classmethod
    def parse(cls, raw: JSON) -> Runtime:
        row = fields(raw, 'python code_root code font_profile')
        code = tuple(FileRef.parse(item) for item in array(row['code']))
        if not code:
            raise GateError('invalid_schema', 'Runtime code manifest cannot be empty')
        return cls(FileRef.parse(row['python']), Path(text(row['code_root'])).resolve(),
                   code, FileRef.parse(row['font_profile']))


@dataclass(frozen=True, slots=True)
class Output:
    id: str
    path: str
    delivery_target: Path
    format: str
    width_mm: float
    pixels: tuple[int, ...]
    dpi: float
    stroke_pt: float | None

    @classmethod
    def parse(cls, raw: JSON) -> Output:
        row = fields(raw, 'id path delivery_target format width_mm pixels dpi stroke_pt')
        pixels = array(row['pixels'])
        if any(type(value) is not int or value <= 0 for value in pixels):
            raise GateError('invalid_schema', 'Pixels must be positive integers')
        kind = text(row['format'])
        if kind not in ('pdf', 'jpg') or len(pixels) not in (0, 2):
            raise GateError('invalid_schema', 'Output must be PDF/JPG with 0/2 pixel values')
        if kind == 'jpg' and (len(pixels) != 2 or row['stroke_pt'] is not None):
            raise GateError('invalid_schema', 'JPG requires pixels and cannot measure vector stroke')
        stroke = None if row['stroke_pt'] is None else number(row['stroke_pt'])
        identity = text(row['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]+', identity) or Path(text(row['path'])).suffix.lower() != '.' + kind:
            raise GateError('invalid_schema', 'Output ID must be a safe slug; extension must match format')
        return cls(identity, text(row['path']), Path(text(row['delivery_target'])).resolve(), kind, number(row['width_mm']),
                   tuple(pixels), number(row['dpi']), stroke)


@dataclass(frozen=True, slots=True)
class Contract:
    id: str
    producer: str
    route: str
    source: FileRef
    source_inputs: tuple[FileRef, ...]
    history: History
    frozen_manifest: FileRef
    workspace: Path
    author_roots: tuple[Path, ...]
    runtime: Runtime
    outputs: tuple[Output, ...]
    mechanical: tuple[str, ...]
    manual_review: tuple[str, ...]
    allowed_changes: tuple[str, ...]
    immutable_content: tuple[str, ...]
    failure_policy: dict[str, JSON]

    @classmethod
    def parse(cls, raw: JSON) -> Contract:
        row = fields(raw, 'id producer route source source_inputs history frozen_manifest workspace author_roots '
                     'runtime outputs mechanical manual_review allowed_changes immutable_content failure_policy')
        source_inputs = tuple(FileRef.parse(item) for item in array(row['source_inputs']))
        if not source_inputs:
            raise GateError('invalid_schema', 'All source inputs must be registered')
        policy = fields(row['failure_policy'], 'max_attempts repair time_budget_seconds cost_budget')
        if type(policy['max_attempts']) is not int or not 1 <= policy['max_attempts'] <= 3 or policy['repair'] != 'local-only':
            raise GateError('invalid_schema', 'Failure policy: 1-3 attempts, local-only repair')
        for budget in ('time_budget_seconds', 'cost_budget'):
            if policy[budget] is not None:
                number(policy[budget])
        outputs = tuple(Output.parse(item) for item in array(row['outputs']))
        if not outputs or len({item.id for item in outputs}) != len(outputs):
            raise GateError('invalid_schema', 'Output IDs must be nonempty and unique')
        route = text(row['route'])
        if route == 'data-redraw':
            raise GateError('data_redraw_forbidden', 'Source-preserving charts are supported; data redraw is not')
        if route not in ('diagram', 'circuit', 'source-preserving-chart', 'raster'):
            raise GateError('invalid_schema', 'Unsupported professional route')
        mechanical = texts(row['mechanical'])
        if not set(mechanical).issubset({'dimensions', 'coverage', 'pixels', 'dpi', 'stroke', 'artifact_set', 'preview_hashes'}):
            raise GateError('unsupported_check', 'Unknown mechanical semantics must remain manual')
        manual = texts(row['manual_review'])
        minimum = {'source_content', 'visual', 'runtime_provenance'}
        if route in ('diagram', 'circuit'):
            minimum.update(('topology', 'label_ownership'))
        if not minimum.issubset(manual):
            raise GateError('invalid_schema', 'Missing route-required manual review items')
        return cls(text(row['id']), text(row['producer']), route, FileRef.parse(row['source']), source_inputs,
                   History.parse(row['history']), FileRef.parse(row['frozen_manifest']),
                   Path(text(row['workspace'])).resolve(),
                   tuple(Path(item).resolve() for item in texts(row['author_roots'])),
                   Runtime.parse(row['runtime']), outputs, texts(row['mechanical']),
                   texts(row['manual_review']), tuple(text(item) for item in array(row['allowed_changes'])), texts(row['immutable_content']), policy)
