"""Create source-bound replacement candidates for a native PDF page.

Run: python native-text-bindings.py SOURCE.pdf ENGINE_ROOT
Candidates require semantic and layout confirmation before production.
"""
import hashlib
import json
import sys
from pathlib import Path
from typing import TypedDict

import fitz


class Binding(TypedDict):
    source_text: str
    source_bbox: list[float]
    target_text_id: str
    source_occurrences: int


class Result(TypedDict):
    sourceSha256: str
    page: int
    replacements: list[Binding]
    validated: bool
    warning: str
    textShadowProposal: dict
    sourceCropBox: list[float]


def propose(source: Path, engine: Path) -> Result:
    sys.path.insert(0, str(engine))
    from journal_pdf.source_icon_text import validate_replacements
    from journal_pdf.source_text_shadows import discover_text_shadows
    from journal_pdf.common import FigureError

    with fitz.open(source) as document:
        if len(document) != 1:
            raise RuntimeError('single_page_required')
        page = document[0]
        if page.rotation:
            raise RuntimeError('unverified_page_transform')
        cropbox=list(page.cropbox)
        spans = [span for block in page.get_text('dict')['blocks'] if block['type'] == 0
                 for line in block['lines'] for span in line['spans'] if span['text'].strip()]
        if not spans:
            raise RuntimeError('no_native_text')
        groups: dict[str, tuple[dict, int]] = {}
        for span in spans:
            key = json.dumps(span, sort_keys=True, ensure_ascii=False)
            prior = groups.get(key)
            groups[key] = (span, (prior[1] if prior else 0) + 1)
        replacements: list[Binding] = []
        for index, (span, count) in enumerate(groups.values(), 1):
            replacements.append({'source_text': span['text'], 'source_bbox': list(span['bbox']),
                                 'target_text_id': f'label-{index:04}', 'source_occurrences': count})
        validate_replacements(page, page.rect, replacements, allow_target_text=True)
    try:
        shadows = discover_text_shadows(source, 0, replacements)
    except FigureError as error:
        shadows = {'status': 'unsupported-structure', 'reason': str(error)}
    return {'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'page': 0,
            'textShadowProposal': shadows,
            'sourceCropBox': cropbox,
            'replacements': replacements, 'validated': True,
            'warning': '仅验证源文字与重复层；文字语义、上下标、图形归属和最终排版未确认'}


if __name__ == '__main__':
    print(json.dumps(propose(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False))
