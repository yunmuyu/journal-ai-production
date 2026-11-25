import hashlib
import pymupdf as fitz
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.journal_rules import load_rules
from journal_pdf.render import render_one


def render_sample(reg,tmp_path,name):
    spec={'id':name,'author':'test','synthetic':True,'kind':'scene','width_pt':100,'height_pt':100,'policy':{'design_font_size_pt':8},'texts':[{'id':'word','text':'Export','x':50,'y':50}]}
    source=tmp_path/'source';source.mkdir(exist_ok=True);assets=Assets()
    try:result=render_one(spec,reg,assets,source,tmp_path/'out'/name)
    finally:assets.close()
    with fitz.open(tmp_path/'out'/name/result['output_pdf']) as doc:
        page=doc[0]
        pixels=hashlib.sha256(page.get_pixmap(dpi=300).samples).hexdigest()
    return result,pixels


def test_pdf_margin_comes_only_from_the_rule_file(reg,tmp_path):
    margin=float(load_rules()['normative']['margin_pt'])
    result,_=render_sample(reg,tmp_path,'rule')
    assert result['layout']['layout_evidence']['export_crop']['protection_pt']==margin
    assert result['export_padding_audit']['pages'][0]['measured_margins_pt']==pytest.approx([margin]*4,abs=.065)
    assert min(result['export_padding_audit']['pages'][0]['measured_margins_pt'])>0.05


@pytest.mark.parametrize('value',[0,4,12,-.01,12.01,float('inf'),float('nan'),True,False,'4',None,[],{}])
def test_any_other_export_padding_is_rejected(tmp_path,value):
    spec={'policy':{'export_crop_padding_pt':value}}
    with pytest.raises(FigureError) as error:render_one(spec,None,None,tmp_path/'source',tmp_path/'output')
    assert error.value.code=='export_crop_padding_invalid'
    assert not (tmp_path/'output').exists()


def test_final_saved_width_is_rechecked_after_padding(reg, tmp_path, monkeypatch):
    import journal_pdf.export_padding as padding_module
    original = padding_module.normalize_pdf_padding
    def expanded(source, destination, padding):
        receipt = original(source, destination, padding)
        with fitz.open(destination) as doc:
            page = doc[0]; height = page.rect.height
            page.set_mediabox(fitz.Rect(0, 0, 500, height))
            page.set_cropbox(fitz.Rect(0, 0, 500, height))
            doc.saveIncr()
        return receipt
    monkeypatch.setattr(padding_module, 'normalize_pdf_padding', expanded)
    with pytest.raises(FigureError) as error:
        render_sample(reg, tmp_path, 'final-width')
    assert error.value.code == 'export_column_width'
    assert not list((tmp_path/'out').rglob('final-width.pdf'))
