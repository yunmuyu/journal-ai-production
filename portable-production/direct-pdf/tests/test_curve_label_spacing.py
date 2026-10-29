from types import SimpleNamespace
import pymupdf as fitz
import pytest
from journal_pdf.common import FigureError
from journal_pdf.curve_label_spacing import audit_curve_label_checks,parse_curve_label_checks


def test_source_curve_distance_and_close_curve_review():
    doc=fitz.open();page=doc.new_page(width=100,height=100)
    shape=page.new_shape();shape.draw_polyline([(10,50),(50,50),(90,50)])
    shape.finish(color=(0,0,0),width=1,dashes='[4 2] 0');shape.commit()
    asset=SimpleNamespace(kind='pdf',doc=doc,rect=[0,0,100,100],audit={'mode':'source-svg-group','clipped_viewport':False})
    scene=SimpleNamespace(size=8,texts=[{'id':'t','position':{'bbox':[30,40,40,48]}}],paths=[],
        assets=[{'id':'curve','asset':asset,'rect':[0,0,100,100]}],
        curve_label_checks=parse_curve_label_checks([{'text_id':'t','asset_id':'curve'}]))
    try:
        result=audit_curve_label_checks(scene)
        assert result['checks'][0]['gap_pt']==pytest.approx(1.5)
        assert not result['notes']
        scene.texts[0]['position']['bbox']=[30,40,40,49.5]
        result=audit_curve_label_checks(scene)
        assert result['notes'][0]['code']=='data_curve_spacing_review'
        assert not result['issues']
        asset.audit['clipped_viewport']=True
        result=audit_curve_label_checks(scene)
        assert not result['checks'] and result['notes'][0]['code']=='data_curve_unverified'
    finally:doc.close()


def test_manual_exception_requires_a_reason():
    with pytest.raises(FigureError):parse_curve_label_checks([{'text_id':'t','path_id':'p','target_pt':.5}])
    assert parse_curve_label_checks([{'text_id':'t','path_id':'p','target_pt':.5,'reason':'数据密集'}])[0]['target_pt']==.5
