"""Synthetic DOCX fixtures only; never include manuscript or cache bytes."""
import io
from zipfile import ZipFile

import pytest
from PIL import Image

from journal_preflight.probe import document_images, sha

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:v="urn:schemas-microsoft-com:vml" '
      'xmlns:o="urn:schemas-microsoft-com:office:office"')


def paragraph(content):
    return f'<w:p><w:r>{content}</w:r></w:p>'


def text(content):
    return f'<w:t>{content}</w:t>'


def drawing(rid='rImage'):
    return f'<w:drawing><a:blip r:embed="{rid}"/></w:drawing>'


def ole(prog_id='Visio.Drawing.15', extra=''):
    return ('<w:object><v:shape><v:imagedata r:id="rCache"/></v:shape>'
            f'<o:OLEObject ProgID="{prog_id}" r:id="rOle"/>{extra}</w:object>')


def make_package(tmp_path, body, extra_relationships=''):
    png = io.BytesIO()
    Image.new('RGB', (400, 300), 'white').save(png, format='PNG')
    docx = tmp_path / 'synthetic.docx'
    with ZipFile(docx, 'w') as z:
        z.writestr('word/document.xml', f'<w:document {NS}><w:body>{body}</w:body></w:document>')
        z.writestr('word/_rels/document.xml.rels',
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rImage" Target="media/image.png"/>'
                   '<Relationship Id="rCache" Target="media/cache.wmf"/>'
                   '<Relationship Id="rOle" Target="embeddings/object.bin"/>'
                   f'{extra_relationships}</Relationships>')
        z.writestr('word/media/image.png', png.getvalue())
        # Deliberately undecodable: probing evidence must not execute or decode OLE/cache payloads.
        z.writestr('word/media/cache.wmf', b'synthetic non-image cache')
        z.writestr('word/embeddings/object.bin', b'synthetic non-executable object')
    return docx


def probe(tmp_path, body, extra_relationships=''):
    source = make_package(tmp_path, body, extra_relationships)
    original_hash = sha(source.read_bytes())
    out = tmp_path / 'evidence'
    out.mkdir()
    result = document_images(source, out)
    assert sha(source.read_bytes()) == original_hash
    return result, out


def test_mixed_drawingml_ole_captions_cannot_silently_lose_five_figures(tmp_path):
    # Caption and object can share a paragraph, while equations occur in prose.
    body = paragraph(ole() + text('图1 Synthetic assembly'))
    for number in (2, 3, 4, 5, 6):
        body += paragraph(drawing() if number == 4 else ole())
        body += paragraph(text(f'图{number} Synthetic caption'))
        if number == 3:
            body += paragraph(text('图3展示了正文而非图题') + ole('Equation.DSMT4'))
    result, out = probe(tmp_path, body)
    assert [f['number'] for f in result['figures']] == ['4']
    assert result['figure_caption_count'] == 6
    assert result['mapped_figure_caption_count'] == 1
    assert [f['number'] for f in result['unmapped_figure_captions']] == ['1', '2', '3', '5', '6']
    assert set(result['warnings']) == {'unmapped_figure_caption_candidates',
                                      'ole_object_evidence_not_extracted',
                                      'vml_image_evidence_not_extracted'}
    assert not result['figure_inventory_verified']
    assert result['figure_extraction_status'] == 'incomplete'
    assert result['figure_caption_count_basis'] == 'caption_candidates_not_verified_inventory'
    evidence = result['unsupported_object_evidence']
    assert len(evidence) == 6
    assert sum(e['classification'] == 'equation_cache' for e in evidence) == 1
    for caption in result['unmapped_figure_captions']:
        assert not caption['figure_identity_verified']
        assert caption['nearby_unsupported_object_indexes']
        assert all(evidence[i]['classification'] != 'equation_cache'
                   for i in caption['nearby_unsupported_object_indexes'])
    assert [p.name for p in out.iterdir()] == ['image.png']


def test_standalone_vml_cache_is_evidence_not_a_figure(tmp_path):
    body = paragraph('<w:pict><v:shape><v:imagedata r:id="rImage"/></v:shape></w:pict>')
    body += paragraph(text('图2 Synthetic VML caption'))
    result, out = probe(tmp_path, body)
    assert result['figures'] == []
    assert result['figure_caption_count'] == 1
    assert result['unmapped_figure_captions'][0]['number'] == '2'
    assert result['unsupported_object_evidence'][0]['vml_images'] == [
        {'relationship_id': 'rImage', 'relationship_status': 'internal', 'target': 'media/image.png'}]
    assert list(out.iterdir()) == []


@pytest.mark.parametrize('prog_id', ['Equation.DSMT4', 'Equation.3', 'MathType.7'])
def test_equation_caches_are_never_promoted_to_figures(tmp_path, prog_id):
    result, out = probe(tmp_path, paragraph(ole(prog_id, drawing())))
    assert result['figures'] == []
    assert result['figure_caption_count'] == 0
    assert result['unmapped_figure_captions'] == []
    assert result['unsupported_object_evidence'][0]['classification'] == 'equation_cache'
    assert not result['unsupported_object_evidence'][0]['extracted_as_figure']
    assert list(out.iterdir()) == []


def test_legacy_object_prevents_stale_drawing_from_binding_to_its_caption(tmp_path):
    body = paragraph(drawing()) + paragraph(ole()) + paragraph(text('图5 Synthetic caption'))
    result, _ = probe(tmp_path, body)
    assert result['figures'] == []
    assert result['unmapped_figure_captions'][0]['number'] == '5'


def test_unbound_caption_without_any_image_has_a_warning(tmp_path):
    result, _ = probe(tmp_path, paragraph(text('图7 Synthetic missing image')))
    assert result['figure_caption_count'] == 1
    assert result['mapped_figure_caption_count'] == 0
    assert result['unmapped_figure_captions'][0]['nearby_unsupported_object_indexes'] == []
    assert result['warnings'] == ['unmapped_figure_caption_candidates']


def test_number_prefix_in_prose_does_not_consume_the_preceding_image(tmp_path):
    body = paragraph(drawing()) + paragraph(text('图9展示了其他信息'))
    body += paragraph(text('图4-1 Synthetic real caption'))
    result, _ = probe(tmp_path, body)
    assert result['figure_caption_count'] == 1
    assert [f['number'] for f in result['figures']] == ['4-1']
    assert result['unmapped_figure_captions'] == []
    assert result['warnings'] == []


def test_external_and_missing_cache_relationships_are_reported_not_read(tmp_path):
    body = paragraph('<w:pict><v:shape><v:imagedata r:id="external"/>'
                     '<v:imagedata o:relid="missing"/></v:shape></w:pict>')
    extra = '<Relationship Id="external" Target="https://example.invalid/cache.wmf" TargetMode="External"/>'
    result, out = probe(tmp_path, body, extra)
    images = result['unsupported_object_evidence'][0]['vml_images']
    assert [im['relationship_status'] for im in images] == ['external', 'missing']
    assert result['figures'] == []
    assert list(out.iterdir()) == []


def test_unsupported_object_in_table_is_still_inventoried_without_guessing_caption(tmp_path):
    body = '<w:tbl><w:tr><w:tc>' + paragraph(ole()) + '</w:tc></w:tr></w:tbl>'
    result, _ = probe(tmp_path, body)
    assert result['unsupported_object_evidence'][0]['paragraph_index'] is None
    assert 'ole_object_evidence_not_extracted' in result['warnings']
    assert result['figures'] == []
