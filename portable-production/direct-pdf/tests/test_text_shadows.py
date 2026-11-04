import copy
import sys
from pathlib import Path

import pymupdf as fitz
import pytest

from journal_pdf.source_text_shadows import discover_text_shadows, remove_confirmed_text_shadows
from journal_pdf.common import FigureError


def fixture(tmp_path):
    source = tmp_path / 'source.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=120, height=80)
        page.insert_text((20, 40), 'ABC', fontsize=12)
        page.draw_rect((22, 32, 25, 38), color=None, fill=(.8, .8, .8))
        page.draw_rect((80, 32, 90, 45), color=None, fill=(.8, .8, .8))
        page.draw_line((10, 60), (100, 60))
        span = page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        doc.save(source)
    rows = [{'source_text': 'ABC', 'source_bbox': list(span['bbox']), 'target_text_id': 'a'}]
    return source, rows


def test_nearby_gray_shape_is_only_a_proposal_and_never_auto_deleted(tmp_path):
    source, rows = fixture(tmp_path)
    proposal = discover_text_shadows(source, 0, rows)
    assert proposal['status'] == 'needs-semantic-binding'
    assert len(proposal['candidates']) == 1
    with pytest.raises(FigureError):
        remove_confirmed_text_shadows(source, 0, rows, proposal, None)
    with fitz.open(source) as doc:
        assert len(doc[0].get_drawings()) == 3


def test_explicit_selection_uses_existing_remover_and_preserves_other_objects(tmp_path):
    source, rows = fixture(tmp_path)
    proposal = discover_text_shadows(source, 0, rows)
    confirmation = {'proposal_sha256': proposal['proposal_sha256'], 'candidate_ids': [proposal['candidates'][0]['id']], 'basis': 'Reviewed glyph ownership'}
    data, receipt = remove_confirmed_text_shadows(source, 0, rows, proposal, confirmation)
    with fitz.open(stream=data, filetype='pdf') as doc:
        assert len(doc[0].get_drawings()) == 2
        assert doc[0].get_text().strip() == 'ABC'
    assert receipt['removed_path_count'] == 1
    assert receipt['status'] == 'source-prepared-not-candidate'


@pytest.mark.parametrize('mutation', ['source', 'binding', 'proposal', 'unknown', 'duplicate'])
def test_stale_or_invalid_confirmation_is_rejected(tmp_path, mutation):
    source, rows = fixture(tmp_path)
    proposal = discover_text_shadows(source, 0, rows)
    confirmation = {'proposal_sha256': proposal['proposal_sha256'], 'candidate_ids': [proposal['candidates'][0]['id']], 'basis': 'Reviewed'}
    if mutation == 'source':
        source.write_bytes(source.read_bytes() + b'\n% changed')
    elif mutation == 'binding':
        rows[0]['target_text_id'] = 'other'
    elif mutation == 'proposal':
        proposal = copy.deepcopy(proposal)
        proposal['candidates'][0]['registration']['source_text'] = 'wrong'
    elif mutation == 'unknown':
        confirmation['candidate_ids'] = ['unknown']
    else:
        confirmation['candidate_ids'] *= 2
    with pytest.raises(FigureError):
        remove_confirmed_text_shadows(source, 0, rows, proposal, confirmation)
