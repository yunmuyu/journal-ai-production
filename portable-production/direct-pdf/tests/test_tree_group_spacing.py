"""Separate sibling groups by twice the normal visible box gap."""
import pytest
from journal_pdf.layouts import tree


@pytest.mark.parametrize('size',[6,8])
def test_group_separation_is_twice_sibling_clearance(reg,size):
    # Given groups with different leaf counts and measured text boxes.
    spec={'root':'Root','branches':[{'text':'First','children':['One','Two','Three']},
                                    {'text':'Second','children':['Four','Five']}]}
    # When the common hierarchy template places the boxes.
    scene=tree(spec,reg,size)
    nodes={node['id']:node for node in scene.nodes}
    def clear_gap(first,second):
        a,b=nodes[first],nodes[second]
        return b['rect'][1]-a['rect'][3]-(a['width']+b['width'])/2
    # Then group whitespace is twice the unchanged within-group whitespace.
    normal=clear_gap('leaf0-0','leaf0-1')
    assert normal==pytest.approx(2.5*size/8)
    assert clear_gap('leaf0-2','leaf1-0')==pytest.approx(2*normal)
    assert len(nodes)==8
