import pytest
from PIL import Image
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError,digest_file
from journal_pdf.render import render_one
from journal_pdf.scene import Scene,audit_scene
from journal_pdf.fonts import position_text


@pytest.mark.parametrize(('gap','valid'),[(4,True),(3,False),(7,False)])
def test_declared_image_row_requires_four_point_clearance(reg,gap,valid):
    scene=Scene(reg,8).finish(100,50)
    scene.embed('left',None,[5,5,25,25])
    scene.embed('right',None,[25+gap,5,45+gap,25])
    scene.image_row_gap_checks=[{'asset_ids':['left','right']}]
    issues=audit_scene(scene)
    assert (not any(x['code']=='image_row_gap_mismatch' for x in issues)) is valid
    assert scene.layout_evidence['image_row_gap_checks'][0]['gap_pt']==pytest.approx(gap)


@pytest.mark.parametrize(('gap','valid'),[(4,True),(6,False)])
def test_image_row_default_in_rendered_figure(tmp_path,reg,gap,valid):
    root=tmp_path/'src';root.mkdir();path=root/'image.png'
    Image.new('RGB',(30,30),'black').save(path)
    data={'id':'row','author':'synthetic','kind':'scene','width_pt':90,'height_pt':50,
          'policy':{'column':'single'},'sources':[{'path':path.name,'sha256':digest_file(path)}],
          'assets':[{'id':'left','path':path.name,'source_kind':'raster','clip':[0,0,30,30],'target':[5,5,25,25]},
                    {'id':'right','path':path.name,'source_kind':'raster','clip':[0,0,30,30],'target':[25+gap,5,45+gap,25]}],
          'image_row_gap_checks':[{'asset_ids':['left','right']}]}
    assets=Assets()
    try:
        if valid:
            result=render_one(data,reg,assets,root,tmp_path/'out')
            assert result['layout']['layout_evidence']['image_row_gap_checks'][0]['gap_pt']==pytest.approx(4)
        else:
            with pytest.raises(FigureError,match='布局未通过实际几何检查'):
                render_one(data,reg,assets,root,tmp_path/'out')
    finally:assets.close()


@pytest.mark.parametrize(('gap','valid'),[(6,True),(9,False)])
def test_image_label_gap_uses_text_ink(reg,gap,valid):
    scene=Scene(reg,8).finish(100,80)
    scene.embed('image',None,[20,25,60,55])
    probe=position_text(reg.measure('Title',8),40,15,'center',0)['bbox']
    scene.text('title','Title',40,15+25-gap-probe[3])
    probe=position_text(reg.measure('Caption',8),40,65,'center',0)['bbox']
    scene.text('caption','Caption',40,65+55+gap-probe[1])
    scene.image_label_gap_checks=[{'asset_id':'image','title_id':'title','caption_id':'caption'}]
    issues=audit_scene(scene)
    assert (not any(x['code']=='image_label_gap_mismatch' for x in issues)) is valid


def test_vertical_grid_rule_is_checked_in_the_rendered_pdf(tmp_path,reg):
    root=tmp_path/'src';root.mkdir();path=root/'image.png';Image.new('RGB',(30,30),'black').save(path)
    data={'id':'grid','author':'synthetic','kind':'scene','width_pt':60,'height_pt':60,
          'policy':{'column':'single'},'sources':[{'path':path.name,'sha256':digest_file(path)}],
          'assets':[{'id':'a','path':path.name,'source_kind':'raster','clip':[0,0,30,30],'target':[5,5,25,25]},
                    {'id':'b','path':path.name,'source_kind':'raster','clip':[0,0,30,30],'target':[5,29,25,49]}],
          'confirmed_spacing_checks':[{'rule':'image_grid_vertical','first_id':'a','second_id':'b'}]}
    assets=Assets()
    try:
        result=render_one(data,reg,assets,root,tmp_path/'out')
        assert result['layout']['layout_evidence']['confirmed_spacing_checks'][0]['actual_pt']==pytest.approx(4)
        data['assets'][1]['target'][1]+=1;data['assets'][1]['target'][3]+=1
        with pytest.raises(FigureError,match='布局未通过实际几何检查'):
            render_one(data,reg,assets,root,tmp_path/'other')
    finally:assets.close()
