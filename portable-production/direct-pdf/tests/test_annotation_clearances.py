from types import SimpleNamespace
import pytest
from journal_pdf.common import FigureError
from journal_pdf.annotation_clearances import parse_annotation_clearances,audit_annotation_clearances


def text(identifier,box):
    return {'id':identifier,'position':{'bbox':box,'offset':[0,0],'rotation':0},
            'measurement':{'glyphs':[{'ch':'x','ink':box}],'ink':box}}


def frame(identifier,rect):
    x0,y0,x1,y1=rect
    return {'id':identifier,'points':[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]],'width':.5,'arrow':False}


def scene(texts,paths,checks,size=8):
    return SimpleNamespace(texts=texts,paths=paths,annotation_clearance_checks=parse_annotation_clearances(checks),size=size)


def test_data_labels_close_but_nonoverlapping_require_review_not_failure():
    checks=[{'kind':'labels','first_id':'a','second_id':'b'}]
    s=scene([text('a',[10,10,20,15]),text('b',[22,10,30,15])],[],checks)
    result=audit_annotation_clearances(s)
    assert not result['issues'] and result['checks'][0]['gap_pt']==pytest.approx(2)
    assert result['notes'][0]['code']=='annotation_spacing_review'
    s.texts[1]=text('b',[19,10,30,15])
    assert audit_annotation_clearances(s)['issues'][0]['code']=='annotation_text_overlap'


def test_label_to_legend_and_plot_bounds_use_distinct_references():
    checks=[{'kind':'legend_frame','first_id':'a','second_id':'legend'},
            {'kind':'plot_frame','first_id':'b','second_id':'plot'}]
    s=scene([text('a',[34,15,38,20]),text('b',[11,11,20,16])],
            [frame('legend',[40,10,60,30]),frame('plot',[10,10,80,50])],checks)
    result=audit_annotation_clearances(s)
    assert [x['gap_pt'] for x in result['checks']]==pytest.approx([1.75,.75])
    assert [x['target_pt'] for x in result['checks']]==[3,1]
    assert len(result['notes'])==2 and not result['issues']


def test_unverified_frame_and_missing_reason_are_rejected():
    check={'kind':'plot_frame','first_id':'a','second_id':'plot'}
    with pytest.raises(FigureError):parse_annotation_clearances([{**check,'target_pt':0}])
    s=scene([text('a',[11,11,20,16])],[{'id':'plot','points':[[0,0],[1,1]],'width':.5}],[check])
    assert audit_annotation_clearances(s)['issues'][0]['code']=='annotation_clearance_unverified'
    with pytest.raises(FigureError):parse_annotation_clearances([{**check,'kind':[]}])


def test_frame_collision_remains_a_hard_failure():
    check={'kind':'plot_frame','first_id':'a','second_id':'plot','target_pt':0,'reason':'空间紧张'}
    s=scene([text('a',[9,11,20,16])],[frame('plot',[10,10,80,50])],[check])
    assert audit_annotation_clearances(s)['issues'][0]['code']=='annotation_frame_overlap'


def test_overlapping_bounding_boxes_do_not_invent_glyph_collision():
    first=text('a',[0,0,10,10]);first['measurement']['glyphs'][0]['ink']=[0,0,2,2]
    second=text('b',[5,0,15,10]);second['measurement']['glyphs'][0]['ink']=[13,0,15,2]
    s=scene([first,second],[],[{'kind':'labels','first_id':'a','second_id':'b'}])
    result=audit_annotation_clearances(s)
    assert not result['issues'] and result['notes'][0]['code']=='annotation_spacing_review'


def test_label_bbox_overlap_with_legend_is_not_automatically_glyph_overlap():
    item=text('a',[34,15,41,20]);item['measurement']['glyphs'][0]['ink']=[34,15,38,20]
    s=scene([item],[frame('legend',[40,10,60,30])],[{'kind':'legend_frame','first_id':'a','second_id':'legend'}])
    result=audit_annotation_clearances(s)
    assert not result['issues'] and result['notes'][0]['code']=='annotation_spacing_review'


def test_scene_spec_exposes_short_but_clear_label_for_review(reg):
    from journal_pdf.layouts import primitive
    from journal_pdf.scene import audit_scene
    spec={'width_pt':80,'height_pt':80,'texts':[{'id':'a','text':'1','x':10,'y':20},
          {'id':'b','text':'2','x':16,'y':20}],
          'annotation_clearance_checks':[{'kind':'labels','first_id':'a','second_id':'b'}]}
    scene=primitive(spec,reg,8);issues=audit_scene(scene)
    assert not any(i['code']=='annotation_text_overlap' for i in issues)
    assert scene.layout_evidence['annotation_clearance_checks'][0]['target_pt']==2.5


def test_tick_labels_use_two_pt_glyph_geometry_as_flexible_reference():
    check={'kind':'ticks','first_id':'a','second_id':'b'}
    s=scene([text('a',[0,0,4,4]),text('b',[5,0,9,4])],[],[check])
    result=audit_annotation_clearances(s)
    assert not result['issues'] and result['checks'][0]['gap_pt']==pytest.approx(1.)
    assert result['checks'][0]['target_pt']==2 and result['notes'][0]['code']=='annotation_spacing_review'
    s.texts[1]=text('b',[6,0,10,4])
    assert not audit_annotation_clearances(s)['notes']
    s.texts[1]=text('b',[5.95,0,9.95,4])
    assert not audit_annotation_clearances(s)['notes']


def test_tick_label_spacing_does_not_use_overlapping_whole_label_boxes():
    first=text('a',[0,0,10,10]);first['measurement']['glyphs'][0]['ink']=[0,0,2,2]
    second=text('b',[5,0,15,10]);second['measurement']['glyphs'][0]['ink']=[13,0,15,2]
    result=audit_annotation_clearances(scene([first,second],[],[{'kind':'ticks','first_id':'a','second_id':'b'}]))
    assert result['checks'][0]['gap_pt']==pytest.approx(11.)
    assert not result['issues'] and not result['notes']
