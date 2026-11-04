import pytest
from journal_pdf.scene import Scene,audit_scene


@pytest.mark.parametrize(('points','collision'),[
    ([[10,20],[35,20]],True),
    ([[10,10],[35,10]],False),
    ([[29.5,15],[29.5,25]],True),
    ([[29.4,15],[29.4,25]],False),
])
def test_bound_data_line_cannot_touch_legend_frame(reg,points,collision):
    scene=Scene(reg,8).finish(100,60)
    scene.line('frame',[[30,15],[60,15],[60,30],[30,30],[30,15]],semantic_role='decorative')
    scene.line('curve',points,semantic_role='decorative')
    scene.legend_data_checks=[{'frame_id':'frame','data_path_ids':['curve']}]
    issues=audit_scene(scene)
    assert any(x['code']=='legend_data_collision' for x in issues) is collision


def test_missing_declared_data_path_is_not_silently_accepted(reg):
    scene=Scene(reg,8).finish(100,60)
    scene.line('frame',[[30,15],[60,15],[60,30],[30,30],[30,15]],semantic_role='decorative')
    scene.legend_data_checks=[{'frame_id':'frame','data_path_ids':['missing']}]
    assert any(x['code']=='legend_data_path_missing' for x in audit_scene(scene))
def test_nearby_but_separate_curve_is_reported_for_review():
    from journal_pdf.legend_collision import segment_box_distance
    assert segment_box_distance([2,8.7],[8,8.7],[0,10,10,20]) == pytest.approx(1.3)
    assert segment_box_distance([-1,8],[12,21],[0,10,10,20]) == 0


def test_nearby_curve_requires_review_but_is_not_called_a_collision(reg):
    scene=Scene(reg,8).finish(100,60)
    scene.line('frame',[[30,15],[60,15],[60,30],[30,30],[30,15]],semantic_role='decorative')
    scene.line('data',[[35,13.7],[55,13.7]],semantic_role='decorative')
    scene.legend_data_checks=[{'frame_id':'frame','data_path_ids':['data']}]
    issues=audit_scene(scene)
    assert not any(x['code']=='legend_data_collision' for x in issues)
    assert any(x['code']=='legend_data_clearance_review' for x in scene.notes)
