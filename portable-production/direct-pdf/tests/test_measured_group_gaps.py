from copy import deepcopy
import pytest
from journal_pdf.layouts import primitive
from journal_pdf.scene import audit_scene
from journal_pdf.common import FigureError


def six_boxes():
    return {'width_pt':120, 'height_pt':220,
            'nodes':[{'id':str(i),'text':text} for i,text in enumerate(['微服务','API接口','统一认证','业务处理','数据访问','服务治理'])],
            'measured_groups':[{'id':'column','axis':'column','nodes':[str(i) for i in range(6)],'origin':[9,10],
                                'gap_pts':[8.503937007874015,8.503937007874015,3.5,3.5,3.5]}]}


def test_column_uses_measured_equal_width_and_individual_gaps(reg):
    # Given: six genuinely measured labels and mixed arrow/frame clearances.
    spec=six_boxes()
    # When: the public primitive compiler places the measured column.
    scene=primitive(spec,reg,8)
    # Then: width comes from the real maximum ink, while every requested gap is exact.
    rects=[n['rect'] for n in scene.nodes]
    assert [rects[i+1][1]-rects[i][3] for i in range(5)] == pytest.approx(spec['measured_groups'][0]['gap_pts'])
    expected=max(reg.measure(n['text'],8)['width'] for n in spec['nodes'])+9
    assert [r[2]-r[0] for r in rects] == pytest.approx([expected]*6)
    assert not audit_scene(scene)


@pytest.mark.parametrize('value', [[1], [1,2,3,4,float('nan')], [1,2,3,4,float('inf')], [1,2,3,4,-1], [1,2,3,4,True], None, '9'])
def test_invalid_gap_list_is_rejected(reg,value):
    # Given: an invalid new boundary field.
    spec=six_boxes();spec['measured_groups'][0]['gap_pts']=value
    # When / Then: invalid metadata cannot silently fall back to a constant gap.
    with pytest.raises(FigureError) as error:primitive(spec,reg,8)
    assert error.value.code=='measured_group_gaps'


def test_explicit_scalar_and_list_are_mutually_exclusive(reg):
    # Given: two competing definitions of the same gaps.
    spec=six_boxes();spec['measured_groups'][0]['gap_pt']=9
    # When / Then: the caller must select one unambiguous public representation.
    with pytest.raises(FigureError) as error:primitive(spec,reg,8)
    assert error.value.code=='measured_group_gaps'


def test_single_member_accepts_empty_gap_list(reg):
    # Given: the nonnegative boundary includes zero, and one node has no adjacent gap.
    spec=six_boxes();spec['nodes']=spec['nodes'][:1]
    spec['measured_groups'][0]['nodes']=['0'];spec['measured_groups'][0]['gap_pts']=[]
    # When: the singleton is compiled.
    scene=primitive(spec,reg,8)
    # Then: its measured rectangle remains valid.
    assert len(scene.nodes)==1 and not audit_scene(scene)


def test_zero_gap_is_a_valid_nonnegative_value(reg):
    # Given: two measured nodes request the lower numeric boundary.
    spec=six_boxes();spec['nodes']=spec['nodes'][:2]
    spec['measured_groups'][0]['nodes']=['0','1'];spec['measured_groups'][0]['gap_pts']=[0]
    # When: their boundary configuration is parsed and applied.
    scene=primitive(spec,reg,8)
    # Then: zero is retained exactly; existing downstream audits still own geometry policy.
    assert scene.nodes[1]['rect'][1] == scene.nodes[0]['rect'][3]
