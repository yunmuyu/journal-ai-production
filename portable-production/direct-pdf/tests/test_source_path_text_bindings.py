import pymupdf as fitz
import pytest
from journal_pdf.common import FigureError
from journal_pdf.source_path_text_coverage import path_fingerprint, validate_nontext_paths


def source_and_bindings(tmp_path, *, glyph=False):
    source=tmp_path/'source.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_line((10,60),(90,60),width=.5)
        if glyph:page.draw_rect((30,30,31,35),color=None,fill=(0,))
        doc.save(source)
    with fitz.open(source) as doc:
        bindings=[{'index':i,'sha256':path_fingerprint(row),'role':'axis',
                   'basis':'Explicit synthetic axis object, not a font outline'}
                  for i,row in enumerate(doc[0].get_drawings())]
    return source,bindings


def test_complete_source_stroke_bindings_are_verified(tmp_path):
    source,bindings=source_and_bindings(tmp_path)
    receipt=validate_nontext_paths(source,0,[0,0,100,80],bindings)
    assert receipt['status']=='all-retained-paths-bound' and receipt['source_path_count']==1


@pytest.mark.parametrize('change',['missing','duplicate','hash','basis','filled-glyph'])
def test_unverified_or_incomplete_bindings_cannot_approve_source_text(tmp_path,change):
    source,bindings=source_and_bindings(tmp_path,glyph=change=='filled-glyph')
    match change:
        case 'missing':bindings=[]
        case 'duplicate':bindings*=2
        case 'hash':bindings[0]['sha256']='0'*64
        case 'basis':bindings[0]['basis']=''
    with pytest.raises(FigureError) as error:
        validate_nontext_paths(source,0,[0,0,100,80],bindings)
    assert error.value.code=='source_path_text_binding'
