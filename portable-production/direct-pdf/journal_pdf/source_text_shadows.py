"""Propose text-shadow ownership, then reuse the registered-paint remover.

Proximity and gray fill are discovery signals, never deletion authorization.
Semantic confirmation is supplied by the plan author, not a new user approval.
"""
from dataclasses import asdict
from pathlib import Path

import pymupdf as fitz
from pypdf import PdfReader
from pypdf.generic import ContentStream

from journal_pdf.common import FigureError, digest_file, digest_json
from journal_pdf.source_icon_text import validate_replacements
from journal_pdf.source_icons import path_record
from journal_pdf.source_registered_paints import remove_registered_paints


def discover_text_shadows(source: Path, page_no: int, replacements: list) -> dict:
    """Return source-bound candidates; ambiguous ownership remains unresolved."""
    source = Path(source)
    source_hash = digest_file(source)
    reader = PdfReader(source)
    with fitz.open(source) as doc:
        if type(page_no) is not int or not 0 <= page_no < len(doc):
            raise FigureError('text_shadow_page', '必须指定真实源页')
        page = doc[page_no]
        rows = validate_replacements(page, page.rect, replacements, allow_target_text=True, allow_grouped=True)
        result = {'version': 1, 'source_sha256': source_hash, 'source_page': page_no,
                  'binding_sha256': digest_json(rows), 'candidates': [], 'unresolved': []}
        if page.get_xobjects():
            result.update(status='unsupported-structure', reason='Form内部paint尚无可靠索引映射')
        else:
            operations = ContentStream(reader.pages[page_no].get_contents(), reader).operations
            counts = {b'S': 1, b's': 1, b'f': 1, b'F': 1, b'f*': 1, b'B': 2, b'B*': 2, b'b': 2, b'b*': 2}
            if any(op == b'sh' for _, op in operations):
                raise FigureError('text_shadow_shading', '直接shading不能可靠映射paint')
            events = [i for i, event in enumerate(page.get_bboxlog()) if event[0] in ('fill-path', 'stroke-path', 'fill-shade')]
            cursor = 0
            mapping = {}
            for position, (_, op) in enumerate(operations):
                count = counts.get(op, 0)
                for sequence in events[cursor:cursor + count]:
                    mapping[sequence] = (position, op, count)
                cursor += count
            if cursor != len(events):
                raise FigureError('text_shadow_mapping', '绘制序列映射不完整')
            for index, drawing in enumerate(page.get_drawings()):
                fill = drawing.get('fill')
                if drawing['type'] != 'f' or not fill or max(fill)-min(fill) > .02 or not .45 < fill[0] < .98:
                    continue
                owners = []
                for row in rows:
                    box = fitz.Rect(row['source_bbox'])
                    before, after = min(2, box.height*.125), min(4, box.height*.25)
                    if (box + (-before, -before, after, after)).contains(drawing['rect']):
                        owners.append(row)
                if not owners:
                    continue
                position, op, count = mapping[drawing['seqno']]
                if count != 1 or op not in (b'f', b'F', b'f*'):
                    continue
                path_hash = digest_json(asdict(path_record(drawing)))
                candidate_id = digest_json([source_hash, page_no, index, path_hash, position])
                evidence = {'source_bbox': list(drawing['rect']), 'fill': list(fill),
                            'owner_candidates': [r['target_text_id'] for r in owners],
                            'reason': '邻近原生文字的灰色独立填充；尚未证明为字形阴影'}
                if len(owners) != 1:
                    result['unresolved'].append({'id': candidate_id, **evidence})
                    continue
                owner = owners[0]
                registration = {'source_sha256': source_hash, 'source_page': page_no,
                    'source_path_index': index, 'source_path_sha256': path_hash,
                    'source_paint_operation_index': position, 'source_text': owner['source_text'],
                    'target_text_id': 'shadow-' + candidate_id[:24]}
                result['candidates'].append({'id': candidate_id, 'owner_target_text_id': owner['target_text_id'],
                    'registration': registration, **evidence})
            result['status'] = 'needs-semantic-binding' if result['candidates'] or result['unresolved'] else 'no-candidates-not-proof-of-absence'
    result['proposal_sha256'] = digest_json(result)
    return result


def remove_confirmed_text_shadows(source: Path, page_no: int, replacements: list,
                                  proposal: dict, confirmation: dict) -> tuple[bytes, dict]:
    """Revalidate the proposal and remove only explicitly confirmed independent paints."""
    current = discover_text_shadows(source, page_no, replacements)
    if proposal != current:
        raise FigureError('text_shadow_stale', '来源、文字绑定或候选发生变化，不能沿用旧确认')
    if not isinstance(confirmation, dict) or set(confirmation) != {'proposal_sha256', 'candidate_ids', 'basis'}:
        raise FigureError('text_shadow_confirmation', '需要制作方案确认具体候选和字形对应依据')
    ids = confirmation['candidate_ids']
    candidates = {r['id']: r for r in current['candidates']}
    if (confirmation['proposal_sha256'] != current['proposal_sha256'] or
        not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids) or
        len(set(ids)) != len(ids) or any(i not in candidates for i in ids) or
        not isinstance(confirmation['basis'], str) or not confirmation['basis'].strip()):
        raise FigureError('text_shadow_confirmation', '阴影确认过期、重复、缺失或引用不明确')
    registrations = [candidates[i]['registration'] for i in ids]
    data, bound, _, removed = remove_registered_paints(Path(source), page_no, outline_rows=registrations)
    with fitz.open(source) as before, fitz.open(stream=data, filetype='pdf') as after:
        if before[page_no].get_text('dict') != after[0].get_text('dict'):
            raise FigureError('text_shadow_native_changed', '准备阶段不得改变原生文字')
    return data, {'status': 'source-prepared-not-candidate', 'source_sha256': current['source_sha256'],
                  'proposal_sha256': current['proposal_sha256'], 'confirmation': confirmation,
                  'removed_path_count': len(removed), 'bindings': bound,
                  'owner_targets': {i: candidates[i]['owner_target_text_id'] for i in ids},
                  'remaining_candidates': [i for i in candidates if i not in ids],
                  'unresolved': current['unresolved'], 'native_text_unchanged': True,
                  'nonselected_paths_verified_by_existing_remover': True}
