from types import SimpleNamespace
import pymupdf as fitz
import pytest
from journal_pdf.common import FigureError
from journal_pdf.icon_ink_spacing import parse_icon_ink_checks,audit_icon_ink_checks


def vector_asset():
    doc=fitz.open();page=doc.new_page(width=20,height=20)
    page.draw_rect(fitz.Rect(4,4,16,16),color=None,fill=(0,0,0))
    return SimpleNamespace(kind='pdf',doc=doc,rect=[0,0,20,20],key='test-icon',
                           audit={'mode':'source-bound-vector-icon'})


def scene(asset,checks):
    return SimpleNamespace(size=8,assets=[{'id':'icon','asset':asset,'rect':[10,10,30,30]}],
        texts=[{'id':'label','position':{'bbox':[29,14,36,26]}}],
        nodes=[{'id':'frame','kind':'rectangle','rect':[9.25,9.25,40,31],'width':.5}],
        icon_ink_checks=parse_icon_ink_checks(checks),_icon_ink_cache={})


def test_vector_ink_uses_painted_pixels_not_crop_edges():
    a=vector_asset()
    try:
        checks=[{'kind':'icon_text','asset_id':'icon','text_id':'label','side':'right'},
                {'kind':'icon_frame','asset_id':'icon','frame_id':'frame','side':'left'}]
        result=audit_icon_ink_checks(scene(a,checks))
        assert not result['issues'] and not result['notes']
        assert result['checks'][0]['gap_pt']==pytest.approx(3,abs=.1)
        assert result['checks'][1]['gap_pt']==pytest.approx(4.5,abs=.1)
        assert result['checks'][0]['ink_bbox_pt'][2]==pytest.approx(26,abs=.1)
    finally:a.doc.close()


def test_unsupported_raster_is_reviewed_not_claimed_measured():
    a=SimpleNamespace(kind='raster',audit={'mode':'raster'},key='test-raster')
    result=audit_icon_ink_checks(scene(a,[{'kind':'icon_text','asset_id':'icon','text_id':'label','side':'right'}]))
    assert not result['checks'] and result['notes'][0]['code']=='icon_ink_unverified'


def test_too_close_is_reviewed_and_reason_is_recorded():
    a=vector_asset()
    try:
        checks=[{'kind':'icon_text','asset_id':'icon','text_id':'label','side':'right','target_pt':2,'reason':'内容较密'}]
        s=scene(a,checks);s.texts[0]['position']['bbox']=[27,14,34,26]
        result=audit_icon_ink_checks(s)
        assert result['checks'][0]['reason']=='内容较密'
        assert result['notes'][0]['code']=='icon_ink_spacing_review'
        with pytest.raises(FigureError):parse_icon_ink_checks([{**checks[0],'reason':''}])
    finally:a.doc.close()


def test_icon_text_group_center_uses_union_of_visible_ink_and_text():
    from journal_pdf.icon_ink_spacing import audit_icon_group_centers
    a=vector_asset()
    try:
        s=scene(a,[])
        s.texts[0]['position']['bbox']=[14,29,26,35]
        s.nodes[0]['rect']=[9,9,31,45]
        s.icon_group_centers=[{'asset_id':'icon','text_id':'label','frame_id':'frame','axis':'vertical'}]
        result=audit_icon_group_centers(s)
        assert result['checks'][0]['first_margin_pt']==pytest.approx(4.75,abs=.1)
        assert result['checks'][0]['second_margin_pt']==pytest.approx(9.75,abs=.1)
        assert result['notes'][0]['code']=='icon_group_center_review'
        s.texts[0]['position']['bbox']=[14,34,26,40]
        assert not audit_icon_group_centers(s)['notes']
    finally:a.doc.close()


@pytest.mark.parametrize('side,expected_side', [('left','right'),('top','bottom')])
def test_stage_grid_places_padded_vector_icon_by_ink(reg,tmp_path,side,expected_side):
    from journal_pdf.assets import Assets
    from journal_pdf.stage_grid import stage_grid
    from journal_pdf.scene import audit_scene
    with fitz.open() as doc:
        page=doc.new_page(width=20,height=20)
        page.draw_rect(fitz.Rect(4,4,16,16),color=None,fill=(0,0,0))
        doc.save(tmp_path/'icon.pdf')
    spec={'columns':[{'id':'a','blocks':[{'id':'item','kind':'node','text':'数据',
           'icon':{'path':'icon.pdf','source_kind':'pdf','clip':[0,0,20,20],'width_pt':20,'side':side}}]}],
          'edges':[]}
    assets=Assets()
    try:
        instance=stage_grid(spec,reg,8,assets,tmp_path)
        audit_scene(instance)
        rows=instance.layout_evidence['icon_ink_checks']
        assert any(r['kind']=='icon_text' and r['side']==expected_side and r['gap_pt']==pytest.approx(3,abs=.15) for r in rows)
        assert all(r['gap_pt']>=r['target_pt']-.15 for r in rows if r['kind']=='icon_frame')
        center=instance.layout_evidence['icon_group_centers'][0]
        assert center['first_margin_pt']==pytest.approx(center['second_margin_pt'],abs=.3)
    finally:assets.close()
