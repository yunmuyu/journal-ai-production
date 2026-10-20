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
    assert padded[2]-size[2]==pytest.approx(7.5,abs=.0001)
    assert padded[3]-size[3]==pytest.approx(7.5,abs=.0001)
    assert padded_crop==pytest.approx([crop[0]-3.75,crop[1]-3.75,crop[2]+3.75,crop[3]+3.75],abs=.0001)
    assert result['layout']['texts']==original['layout']['texts']
    assert result['layout']['layout_evidence']['export_crop']['rescaled'] is False


def test_absent_setting_retains_existing_quarter_point_export_behavior(reg,tmp_path):
    original,size,crop,pixels=render_sample(reg,tmp_path,'absent')
    explicit,other_size,other_crop,other_pixels=render_sample(reg,tmp_path,'explicit',.25)
    assert original['layout']['layout_evidence']['export_crop']==explicit['layout']['layout_evidence']['export_crop']
    assert size==other_size and crop==other_crop and pixels==other_pixels


@pytest.mark.parametrize('value',[-.01,12.01,float('inf'),float('-inf'),float('nan'),True,False,'4',None,[],{}])
def test_invalid_export_padding_is_rejected_before_outputs_or_scene_construction(tmp_path,value):
    spec={'policy':{'export_crop_padding_pt':value}}
    with pytest.raises(FigureError) as error:render_one(spec,None,None,tmp_path/'source',tmp_path/'output')
    assert error.value.code=='export_crop_padding_invalid'
    assert not (tmp_path/'output').exists()
