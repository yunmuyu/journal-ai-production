"""Bind explicit body/script roles to text actually present in the candidate PDF."""
from __future__ import annotations

from pathlib import Path

import fitz

from .models import JSON, GateError, array, fields


def pdf_spans(path: Path) -> list[dict[str, JSON]]:
    """No OCR: bitmap glyph heights are never interpreted as font sizes."""
    spans: list[dict[str, JSON]] = []
    with fitz.open(path) as document:
        for page in document:
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        if span['text'].strip():
                            spans.append(dict(index=len(spans), text=span['text'],
                                size_pt=float(span['size']), bbox=[float(v) for v in span['bbox']]))
    return spans


def audit_typography(path: Path, identity: str, supplied: JSON) -> tuple[dict[str, JSON], list[JSON]]:
    """Undeclared small spans remain pending; only bound body text has a hard 6 pt floor."""
    spans = pdf_spans(path)
    roles = None
    if supplied is not None:
        if type(supplied) is not dict:
            raise GateError('invalid_schema', 'text_roles must map output IDs to actual span roles')
        if identity in supplied:
            roles = [fields(row, 'index text size_pt bbox role') for row in array(supplied[identity])]
    if roles is not None:
        if len(roles) != len(spans):
            raise GateError('text_role_binding_mismatch', identity)
        for actual, declared in zip(spans, roles):
            if any(declared[key] != value for key, value in actual.items()):
                raise GateError('text_role_binding_mismatch', f'{identity}: span {actual["index"]}')
            if declared['role'] not in ('body', 'subscript', 'superscript'):
                raise GateError('invalid_schema', 'Text role must be body/subscript/superscript')
            if declared['role'] == 'body' and actual['size_pt'] < 6 - .01:
                raise GateError('body_font_below_minimum', f'{identity}: span {actual["index"]}')
    small = [row for row in spans if row['size_pt'] < 6 - .01]
    pending: list[JSON] = ['typography'] if not spans or small and roles is None else []
    return dict(spans=spans, roles=roles, small_spans=small,
        scope='Actual editable PDF text only; script roles require independent semantic review; no bitmap OCR'), pending
