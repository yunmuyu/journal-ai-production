from pathlib import Path

import pymupdf as fitz
import pytest

from journal_pdf.common import FigureError
from journal_pdf.source_stream_text import prepare_stream_body


def fixture(path: Path):
    with fitz.open() as doc:
        page=doc.new_page(width=120,height=80)
        page.draw_line((10,20),(110,65),width=.73)
        page.insert_text((20,30),'R1',fontsize=8)
        span=page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        page.clean_contents()
        stream=page.get_contents()[0]
        raw=doc.xref_stream(stream).replace(b'BT/',b'\nBT\n/').replace(b' ET ',b'\nET\n')
        doc.update_stream(stream,raw)
        doc.save(path)
    return [{'source_text':'R1','source_bbox':list(span['bbox']),'target_text_id':'r1'}]


def test_stream_body_keeps_original_vector_paint_and_registered_text_is_removed(tmp_path):
    source=tmp_path/'source.pdf';rows=fixture(source)
    result=prepare_stream_body(source,0,[0,0,120,80],rows)
    with fitz.open(stream=result.data,filetype='pdf') as doc:
        assert len(doc[0].get_drawings())==1
        assert not doc[0].get_texttrace()
        assert not doc[0].get_fonts(full=True)


def test_stream_body_refuses_unregistered_text_or_partial_page(tmp_path):
    source=tmp_path/'source.pdf';rows=fixture(source)
    with pytest.raises(FigureError):prepare_stream_body(source,0,[0,0,120,80],[])
    with pytest.raises(FigureError):prepare_stream_body(source,0,[0,0,100,80],rows)


def test_stream_body_preserves_color_state_inside_text_block(tmp_path):
    source=tmp_path/'state.pdf'
    rows=fixture(source)
    with fitz.open(source) as doc:
        xref=doc[0].get_contents()[0]
        raw=doc.xref_stream(xref).replace(b'BT\n',b'BT\n0.3 g\n',1)
        doc.update_stream(xref,raw)
        data=doc.tobytes()
    source.write_bytes(data)
    result=prepare_stream_body(source,0,[0,0,120,80],rows)
    with fitz.open(stream=result.data,filetype='pdf') as doc:
        assert not doc[0].get_texttrace()
        assert len(doc[0].get_drawings())==1
