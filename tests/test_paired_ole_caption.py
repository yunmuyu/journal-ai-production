from pathlib import Path
from zipfile import ZipFile

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from legacy_caption import find_docx_caption_media


@pytest.mark.parametrize('style,crop,count,matched', [
    ('width:177pt;height:118pt', '', 2, True),
    ('position:absolute;width:177pt', '', 2, False),
    ('width:177pt', ' cropleft=".1"', 2, False),
    ('width:177pt', '', 3, False),
])
def test_paired_inline_ole_requires_unambiguous_source_order(tmp_path: Path, style, crop, count, matched):
    objects = ''.join(f'<w:r><w:object><v:shape style="{style}"><v:imagedata r:id="rId{i}"{crop}/></v:shape></w:object></w:r>' for i in range(count))
    document = f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p>{objects}</w:p><w:p><w:r><w:t>图2基极镇流电阻结构    图3射极镇流电阻结构</w:t></w:r></w:p></w:body></w:document>'
    rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="rId{i}" Target="media/image{i}.emf"/>' for i in range(count)) + '</Relationships>'
    source = tmp_path / 'source.docx'
    with ZipFile(source, 'w') as archive:
        archive.writestr('word/document.xml', document)
        archive.writestr('word/_rels/document.xml.rels', rels)
        for i in range(count):
            archive.writestr(f'word/media/image{i}.emf', bytes([i]))
    result = find_docx_caption_media(source)
    assert bool(result) == matched
    if matched:
        assert [(r['figure_no'], r['member']) for r in result] == [('2', 'word/media/image0.emf'), ('3', 'word/media/image1.emf')]
