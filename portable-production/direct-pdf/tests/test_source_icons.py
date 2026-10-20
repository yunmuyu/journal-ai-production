from pathlib import Path

import pymupdf as fitz
import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.source_icons import audit_icon_paths


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / 'source.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=120)
        page.draw_rect(fitz.Rect(20, 20, 45, 55), width=.75)
        page.draw_line((25, 30), (40, 30), width=.24)
        page.insert_text((100, 100), 'outside')
        doc.save(path)
    return path


def placed(source: Path, count: int = 1) -> tuple[Assets, fitz.Document, list]:
    assets = Assets()
    icon = assets.source_icon(source, 0, [18, 18, 48, 58])
    doc = fitz.open()
    page = doc.new_page(width=160, height=120)
    rows = []
    for index in range(count):
        target = [10 + index * 50, 10, 40 + index * 50, 50]
        assets.place(page, icon, target)
        rows.append({'asset': icon, 'rect': target, 'id': str(index)})
    page.draw_rect(fitz.Rect(5, 70, 100, 100), width=.5)
    return assets, doc, rows


def test_source_paths_keep_width_and_new_paths_still_require_half_point(source: Path):
    assets, doc, rows = placed(source)
    try:
        result = audit_icon_paths(doc[0], rows)
        assert result['matched_path_count'] == 2
        assert result['stroke_violations'] == []
        doc[0].draw_line((15, 15), (25, 15), width=.75)
        result = audit_icon_paths(doc[0], rows)
        assert len(result['stroke_violations']) == 1
    finally:
        doc.close()
        assets.close()


@pytest.mark.parametrize('mutation', ['delete', 'width', 'duplicate'])
def test_source_path_instance_mutations_rejected(source: Path, mutation: str):
    assets, doc, rows = placed(source)
    try:
        page = doc[0]
        if mutation == 'duplicate':
            rows = rows + rows
        else:
            page.add_redact_annot(fitz.Rect(0, 0, 50, 60), fill=False)
            page.apply_redactions(graphics=2, text=0, images=0)
            if mutation == 'width':
                page.draw_rect(fitz.Rect(12, 12, 37, 47), width=.5)
        with pytest.raises(FigureError) as error:
            audit_icon_paths(page, rows)
        assert error.value.code == 'source_icon_path_changed'
    finally:
        doc.close()
        assets.close()


def test_two_placements_consumed_individually(source: Path):
    assets, doc, rows = placed(source, 2)
    try:
        assert audit_icon_paths(doc[0], rows)['matched_path_count'] == 4
    finally:
        doc.close()
        assets.close()


def test_full_page_with_text_rejected(source: Path):
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            assets.source_icon(source, 0, [0, 0, 200, 120])
        assert error.value.code == 'source_icon_contains_text'
    finally:
        assets.close()


@pytest.mark.parametrize('field', ['source', 'clip'])
def test_wrong_source_or_clip_binding_rejected(source: Path, field: str):
    assets, doc, rows = placed(source)
    try:
        icon = rows[0]['asset']
        if field == 'source':
            icon.source_hash = '0' * 64
        else:
            icon.audit['source_clip'] = [0, 0, 200, 120]
        with pytest.raises(FigureError):
            audit_icon_paths(doc[0], rows)
    finally:
        doc.close()
        assets.close()



def test_nonzero_cropbox_and_multiple_saved_placements(source: Path):
    assets, doc, rows = placed(source, 2)
    try:
        doc[0].set_cropbox(fitz.Rect(3, 4, 150, 110))
        with fitz.open(stream=doc.tobytes(garbage=4), filetype='pdf') as saved:
            result = audit_icon_paths(saved[0], rows)
            assert result['matched_path_count'] == 4
            assert not result['stroke_violations']
    finally:
        doc.close()
        assets.close()


def test_explicit_native_reletter_preserves_paths_and_requires_exact_span(source: Path):
    assets = Assets()
    try:
        with fitz.open(source) as doc:
            span = doc[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        replacement = {'source_text': 'outside', 'source_bbox': list(span['bbox']), 'target_text_id': 'replacement'}
        icon = assets.source_icon(source, 0, [0, 0, 200, 120], text_replacements=[replacement])
        assert icon.audit['preparation_mode'] == 'source-vector-reletter'
        assert not icon.doc[0].get_text()
        assert not icon.doc[0].get_fonts()
        assert all(row['nontext_exact'] for row in icon.audit['pixels'])
        assert all(not row['exact'] for row in icon.audit['pixels'])
        replacement['source_text'] = 'wrong'
        with pytest.raises(FigureError):
            assets.source_icon(source, 0, [0, 0, 200, 120], text_replacements=[replacement])
    finally:
        assets.close()


def test_omitted_second_source_span_rejected(tmp_path: Path):
    source = tmp_path / 'words.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=120)
        page.insert_text((20, 30), 'one')
        page.insert_text((20, 70), 'two')
        span = page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        doc.save(source)
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            assets.source_icon(source, 0, [0, 0, 200, 120], text_replacements=[{'source_text':'one','source_bbox':list(span['bbox']),'target_text_id':'one'}])
        assert error.value.code == 'source_icon_contains_text'
    finally:
        assets.close()


@pytest.mark.parametrize('points', [[(15, 15), (25, 15)], [(15, 15), (15, 25)]])
def test_new_axis_aligned_bad_stroke_is_never_exempt_inside_icon(source: Path, points):
    assets, doc, rows = placed(source)
    try:
        doc[0].draw_line(points[0], points[1], width=.75)
        assert len(audit_icon_paths(doc[0], rows)['stroke_violations']) == 1
    finally:
        doc.close()
        assets.close()


@pytest.mark.parametrize('mutation', ['missing', 'wrong-text', 'bbox-outside', 'extra-registration', 'unavailable-selection'])
def test_reletter_mapping_and_registration_rejected(source: Path, reg, mutation: str):
    from journal_pdf.render import compile_figure
    with fitz.open(source) as doc:
        span = doc[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
    replacement = {'source_text':'outside','source_bbox':list(span['bbox']),'target_text_id':'replacement'}
    item = {'id':'icon','path':source.name,'source_kind':'pdf','source_icon':True,'page':0,'clip':[0,0,200,120],
            'target':[1,1,201,121],'text_replacements':[replacement]}
    texts = [{'id':'replacement','text':'outside','x':110,'y':140}]
    if mutation == 'missing':
        texts = []
    elif mutation == 'wrong-text':
        texts[0]['text'] = 'wrong'
    elif mutation == 'bbox-outside':
        replacement['source_bbox'] = [-1, 0, 200, 120]
    elif mutation == 'extra-registration':
        item['text_replacements'].append(dict(replacement, target_text_id='duplicate'))
    else:
        item['source_path_indices'] = [0]
    spec = {'id':'mapping','kind':'scene','width_pt':210,'height_pt':160,'assets':[item],'texts':texts}
    assets = Assets()
    try:
        with pytest.raises(FigureError):
            compile_figure(spec, reg, assets, source.parent)
    finally:
        assets.close()
