import fitz
import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import render_one
from journal_pdf.fonts import position_text
from journal_pdf.scene import Scene,audit_scene


def spec(reg):
    bbox=position_text(reg.measure('Legend',8),80,40,'center',0)['bbox']
    right=bbox[2]+4.75;top=bbox[1]-2.95;bottom=bbox[3]+2.95
    return {'version':1,'id':'mask','author':'synthetic','kind':'scene','synthetic':True,
            'width_pt':130,'height_pt':70,'policy':{'column':'single'},'nodes':[],
            'paths':[{'id':'plot','points':[[5,top+1],[125,top+1]],'semantic_role':'data-annotation'},
                     {'id':'frame','points':[[40.25,top],[right,top],[right,bottom],[40.25,bottom],[40.25,top]],'semantic_role':'decorative'},
                     {'id':'key','points':[[45,40],[60,40]],'semantic_role':'decorative'}],
            'texts':[{'id':'label','text':'Legend','x':80,'y':40}],
            'legend_backgrounds':[{'frame_id':'frame','foreground_path_ids':['frame','key'],
                                   'foreground_text_ids':['label'],'foreground_node_ids':[]}]}


def test_legend_opaque_background_hides_underlying_plot_but_preserves_foreground(tmp_path,reg):
    root=tmp_path/'src';root.mkdir();assets=Assets()
    data=spec(reg);plot_y=data['paths'][0]['points'][0][1]
    try:result=render_one(data,reg,assets,root,tmp_path/'out')
    finally:assets.close()
    assert result['status']=='candidate-editorial-review'
    assert 'legend_data_overlap_unverified' in result['needs_review']
    measured=result['layout']['layout_evidence']['legend_clearance_measurements'][0]
    assert measured['right_pt']==pytest.approx(4.5) and measured['left_pt']==pytest.approx(4.5)
    assert measured['top_pt']==pytest.approx(2.7) and measured['bottom_pt']==pytest.approx(2.7)
    with fitz.open(tmp_path/'out'/result['output_pdf']) as doc:
        page=doc[0];offset=page.cropbox_position;pix=page.get_pixmap(matrix=fitz.Matrix(4,4),alpha=False)
        def pixel(x,y):return pix.pixel(round((x-offset.x)*4),round((y-offset.y)*4))[:3]
        assert pixel(50,plot_y)==(255,255,255)
        assert min(pixel(20,plot_y))<40
        assert min(min(pixel(50,y)) for y in (39.75,40,40.25))<40
        assert 'Legend' in page.get_text()


def test_nonrectangular_frame_rejected_before_white_background(tmp_path,reg):
    root=tmp_path/'src';root.mkdir();data=spec(reg)
    data['paths'][1]['points']=[[40,20],[100,20],[90,50],[40,50],[40,20]]
    assets=Assets()
    try:
        with pytest.raises(FigureError):render_one(data,reg,assets,root,tmp_path/'out')
    finally:assets.close()


def test_white_background_rejects_legend_text_outside_frame(tmp_path,reg):
    root=tmp_path/'src';root.mkdir();data=spec(reg);data['texts'][0]['x']=101
    assets=Assets()
    try:
        with pytest.raises(FigureError,match='文字越过白底框'):render_one(data,reg,assets,root,tmp_path/'out')
    finally:assets.close()


def test_unbound_legend_frame_requires_review(tmp_path,reg):
    root=tmp_path/'src';root.mkdir();data=spec(reg)
    data['paths'][1]['id']='legend-frame'
    data.pop('legend_backgrounds')
    assets=Assets()
    try:result=render_one(data,reg,assets,root,tmp_path/'out')
    finally:assets.close()
    assert result['status']=='candidate-editorial-review'
    assert 'legend_background_unverified' in result['needs_review']


@pytest.mark.parametrize('side',['left','right'])
def test_white_legend_rejects_excess_padding_without_opt_in(tmp_path,reg,side):
    root=tmp_path/'src';root.mkdir();data=spec(reg)
    frame=data['paths'][1]['points']
    indices=(0,3,4) if side=='left' else (1,2)
    for index in indices:frame[index][0]+=(-3 if side=='left' else 3)
    assets=Assets()
    try:
        with pytest.raises(FigureError,match='布局未通过实际几何检查'):
            render_one(data,reg,assets,root,tmp_path/'out')
    finally:assets.close()


@pytest.mark.parametrize('side',['top','bottom'])
def test_white_legend_rejects_vertical_padding_error(tmp_path,reg,side):
    root=tmp_path/'src';root.mkdir();data=spec(reg);frame=data['paths'][1]['points']
    indices=(0,1,4) if side=='top' else (2,3)
    for index in indices:frame[index][1]+=(-2 if side=='top' else 2)
    assets=Assets()
    try:
        with pytest.raises(FigureError,match='布局未通过实际几何检查'):
            render_one(data,reg,assets,root,tmp_path/'out')
    finally:assets.close()


@pytest.mark.parametrize(('gap','valid'),[(3,True),(4,False)])
def test_single_column_legend_checks_actual_row_ink(reg,gap,valid):
    scene=Scene(reg,8).finish(130,70)
    first=scene.text('a','Short',20,20,align='left')
    probe=position_text(reg.measure('Longer',8),20,40,'left',0)['bbox']
    y=40+(first['position']['bbox'][3]+gap-probe[1])
    second=scene.text('b','Longer',20,y,align='left')
    bounds=[15.25,first['position']['bbox'][1]-2.95,
            max(first['position']['bbox'][2],second['position']['bbox'][2])+4.75,
            second['position']['bbox'][3]+2.95]
    x0,y0,x1,y1=bounds
    scene.line('frame',[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]],semantic_role='decorative')
    scene.legend_backgrounds=[{'frame_id':'frame','rect':bounds,'foreground_path_ids':['frame'],
                               'foreground_text_ids':['a','b'],'foreground_node_ids':[]}]
    issues=audit_scene(scene)
    assert (not any(x['code']=='legend_row_gap_mismatch' for x in issues)) is valid
