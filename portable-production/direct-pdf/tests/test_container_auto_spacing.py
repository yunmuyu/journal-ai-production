import pytest
from journal_pdf.scene import Scene,audit_scene


def test_unbound_container_child_spacing_is_reported_without_confusing_nested_content(reg):
    scene=Scene(reg).finish(140,130)
    scene.shape('outer',[10,10,100,110],container=True)
    scene.shape('heading',[20,14,90,30])
    scene.shape('nested',[20,35,90,100],container=True)
    scene.shape('deep',[25,40,85,95])
    audit_scene(scene)
    rows=[row for row in scene.layout_evidence['automatic_container_spacing'] if row['container']=='outer']
    assert {(r['side'],r['child']) for r in rows}=={('top','heading'),('bottom','nested')}
    assert next(r for r in rows if r['side']=='top')['gap_pt']==pytest.approx(3.5)
    assert any(n['code']=='container_spacing_review' and n['id']=='outer' for n in scene.notes)


def test_matching_container_margins_do_not_create_review_note(reg):
    scene=Scene(reg).finish(120,100)
    scene.shape('outer',[10,10,100,90],container=True)
    scene.shape('one',[20,13.5,90,86.5])
    audit_scene(scene)
    assert not any(n['code']=='container_spacing_review' and n['id']=='outer' for n in scene.notes)


def test_container_title_is_not_misidentified_as_empty_top_margin(reg):
    scene=Scene(reg).finish(120,100)
    scene.shape('outer',[10,10,100,90],container=True)
    scene.shape('child',[20,35,90,86.5])
    scene.text('title','标题',55,20,owner='outer')
    audit_scene(scene)
    assert not any(n['code']=='container_spacing_review' and n['id']=='outer' and n['side']=='top' for n in scene.notes)


def test_container_exception_is_valid_only_for_the_recorded_measured_gap(reg):
    scene=Scene(reg).finish(120,100)
    scene.shape('outer',[10,10,100,90],container=True)
    scene.shape('one',[20,16,90,86.5])
    scene.container_spacing_exceptions=[{'container':'outer','child':'one','side':'top','gap_pt':5.5,'reason':'已有明确排版确认'}]
    audit_scene(scene)
    assert not any(n['code']=='container_spacing_review' and n['id']=='outer' and n['side']=='top' for n in scene.notes)
    row=next(x for x in scene.layout_evidence['automatic_container_spacing'] if x['container']=='outer' and x['side']=='top')
    assert row['exception_reason']=='已有明确排版确认'
    scene.nodes[1]['rect'][1]+=1
    audit_scene(scene)
    assert any(n['code']=='container_spacing_review' and n['id']=='outer' and n['side']=='top' for n in scene.notes)
    scene.nodes[1]['rect'][1]-=1
    audit_scene(scene)
    assert not any(n['code']=='container_spacing_review' and n['id']=='outer' and n['side']=='top' for n in scene.notes)


def test_exception_cannot_silently_match_wrong_or_missing_child(reg):
    scene=Scene(reg).finish(120,100);scene.shape('outer',[10,10,100,90],container=True)
    scene.container_spacing_exceptions=[{'container':'outer','child':'missing','side':'top','gap_pt':5.5,'reason':'明确例外'}]
    audit_scene(scene)
    assert any(n['code']=='container_exception_unverified' for n in scene.notes)
