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
    result,padded,padded_crop,_=render_sample(reg,tmp_path,'padded',7.6)
    assert result['layout']['layout_evidence']['export_crop']['protection_pt']==7.6
    assert padded[2]-size[2]==pytest.approx(7.2,abs=.0001)
    assert padded[3]-size[3]==pytest.approx(7.2,abs=.0001)
    assert padded_crop==pytest.approx([crop[0],crop[1],crop[2]+7.2,crop[3]+7.2],abs=.0001)
    before,after=original['layout']['texts'][0],result['layout']['texts'][0]
    assert after['text']==before['text'] and after['font_size_pt']==before['font_size_pt']==8
    assert after['ink_bounds']==pytest.approx([v+3.6 for v in before['ink_bounds']])
    assert result['layout']['layout_evidence']['export_crop']['rescaled'] is False


def test_absent_setting_uses_safe_four_point_export_behavior(reg,tmp_path):
    original,size,crop,pixels=render_sample(reg,tmp_path,'absent')
    explicit,other_size,other_crop,other_pixels=render_sample(reg,tmp_path,'explicit',4)
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
