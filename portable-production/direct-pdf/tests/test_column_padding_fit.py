import pymupdf as fitz
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import render_one


def test_padding_is_included_in_fitted_single_column(reg, tmp_path):
    spec={'id':'wide','author':'test','synthetic':True,'kind':'scene','width_pt':226,'height_pt':50,
          'policy':{'column':'single','design_font_size_pt':8},
          'texts':[{'id':'a','text':'A','x':4,'y':25},{'id':'b','text':'B','x':222,'y':25}]}
    source=tmp_path/'source';source.mkdir();assets=Assets()
    try:result=render_one(spec,reg,assets,source,tmp_path/'out')
    finally:assets.close()
    with fitz.open(tmp_path/'out'/result['output_pdf']) as doc:
        assert doc[0].rect.width <= 80*72/25.4 + .01
    assert 6 <= result['layout']['texts'][0]['font_size_pt'] < 8


def test_minimum_font_size_is_not_bypassed(reg, tmp_path):
    spec={'id':'minimum','author':'test','synthetic':True,'kind':'scene','width_pt':226,'height_pt':50,
          'policy':{'column':'single','design_font_size_pt':6},
          'texts':[{'id':'a','text':'A','x':4,'y':25},{'id':'b','text':'B','x':222,'y':25}]}
    source=tmp_path/'source';source.mkdir();assets=Assets()
    try:
        with pytest.raises(FigureError) as error:render_one(spec,reg,assets,source,tmp_path/'out')
        assert error.value.code == 'layout_reflow_required'
    finally:assets.close()
