import fitz
import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import render_one


def spec():
    return {'version':1,'id':'mask','author':'synthetic','kind':'scene','synthetic':True,
            'width_pt':130,'height_pt':70,'policy':{'column':'single'},'nodes':[],
            'paths':[{'id':'plot','points':[[5,30],[125,30]],'semantic_role':'data-annotation'},
                     {'id':'frame','points':[[40,20],[100,20],[100,50],[40,50],[40,20]],'semantic_role':'decorative'},
                     {'id':'key','points':[[45,40],[60,40]],'semantic_role':'decorative'}],
            'texts':[{'id':'label','text':'Legend','x':80,'y':40}],
            'legend_backgrounds':[{'frame_id':'frame','foreground_path_ids':['frame','key'],
                                   'foreground_text_ids':['label'],'foreground_node_ids':[]}]}


def test_legend_opaque_background_hides_underlying_plot_but_preserves_foreground(tmp_path,reg):
    root=tmp_path/'src';root.mkdir();assets=Assets()
    try:result=render_one(spec(),reg,assets,root,tmp_path/'out')
    finally:assets.close()
    with fitz.open(tmp_path/'out'/result['output_pdf']) as doc:
        page=doc[0];offset=page.cropbox_position;pix=page.get_pixmap(matrix=fitz.Matrix(4,4),alpha=False)
        def pixel(x,y):return pix.pixel(round((x-offset.x)*4),round((y-offset.y)*4))[:3]
        assert pixel(50,30)==(255,255,255)
        assert min(pixel(20,30))<40
        assert min(pixel(50,40))<40
        assert 'Legend' in page.get_text()


def test_nonrectangular_frame_rejected_before_white_background(tmp_path,reg):
    root=tmp_path/'src';root.mkdir();data=spec()
    data['paths'][1]['points']=[[40,20],[100,20],[90,50],[40,50],[40,20]]
    assets=Assets()
    try:
        with pytest.raises(FigureError):render_one(data,reg,assets,root,tmp_path/'out')
    finally:assets.close()


def test_white_background_rejects_legend_text_outside_frame(tmp_path,reg):
    root=tmp_path/'src';root.mkdir();data=spec();data['texts'][0]['x']=101
    assets=Assets()
    try:
        with pytest.raises(FigureError,match='文字越过白底框'):render_one(data,reg,assets,root,tmp_path/'out')
    finally:assets.close()
