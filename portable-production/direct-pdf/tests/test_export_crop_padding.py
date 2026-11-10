import hashlib
import pymupdf as fitz
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import render_one


def render_sample(reg,tmp_path,name,padding='absent'):
    spec={'id':name,'author':'test','synthetic':True,'kind':'scene','width_pt':100,'height_pt':100,'policy':{'design_font_size_pt':8},'texts':[{'id':'word','text':'Export','x':50,'y':50}]}
    if padding!='absent':spec['policy']['export_crop_padding_pt']=padding
    source=tmp_path/'source';source.mkdir(exist_ok=True);assets=Assets()
    try:result=render_one(spec,reg,assets,source,tmp_path/'out')
    finally:assets.close()
    with fitz.open(tmp_path/'out'/result['output_pdf']) as doc:
        page=doc[0];dimensions=list(page.rect);crop=list(page.cropbox)
        pixels=hashlib.sha256(page.get_pixmap(dpi=300).samples).hexdigest()
    return result,dimensions,crop,pixels


def test_explicit_export_crop_padding_changes_only_the_crop_margin(reg,tmp_path):
    original,size,crop,_=render_sample(reg,tmp_path,'default')
    result,padded,padded_crop,_=render_sample(reg,tmp_path,'padded',4)
    assert result['layout']['layout_evidence']['export_crop']['protection_pt']==4
    assert padded[2]-size[2]==pytest.approx(4,abs=.25)
    assert padded[3]-size[3]==pytest.approx(4,abs=.25)
    assert result['export_padding_audit']['pages'][0]['measured_margins_pt']==pytest.approx([4]*4,abs=.25)
    assert result['layout']['texts']==original['layout']['texts']
    assert result['layout']['layout_evidence']['export_crop']['rescaled'] is False


def test_absent_setting_uses_two_point_export_behavior(reg,tmp_path):
    original,size,crop,pixels=render_sample(reg,tmp_path,'absent')
    explicit,other_size,other_crop,other_pixels=render_sample(reg,tmp_path,'explicit',2)
    assert original['layout']['layout_evidence']['export_crop']==explicit['layout']['layout_evidence']['export_crop']
    assert size==other_size and crop==other_crop and pixels==other_pixels


def test_quarter_point_crop_cannot_publish_text_without_actual_safe_margins(reg,tmp_path):
    with pytest.raises(FigureError) as error:
        render_sample(reg,tmp_path,'unsafe',.25)
    assert error.value.code=='text_export_margin'


@pytest.mark.parametrize('value',[-.01,12.01,float('inf'),float('-inf'),float('nan'),True,False,'4',None,[],{}])
def test_invalid_export_padding_is_rejected_before_outputs_or_scene_construction(tmp_path,value):
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
