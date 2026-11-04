import pytest
from journal_pdf.bound_branch_paths import prepare_bound_paths
from journal_pdf.common import FigureError
from journal_pdf.editorial import ARROW_LENGTH


def example():
    return {'paths':[{'id':'a','points':[[0,0],[30,0],[30,20]],'arrow':True,'auto_terminal':True,'endpoint_nodes':['source','a']},
                     {'id':'b','points':[[0,0],[50,0]],'arrow':True,'auto_terminal':True,'endpoint_nodes':['source','b']}],
            'shared_branch_groups':[{'id':'net','paths':['a','b'],'junction':[30,0]}]}


def test_shared_branch_expansion_preserves_ends_and_adds_exact_terminals():
    original=example();out=prepare_bound_paths(original,8)
    trunk=out['paths'][-1]
    assert trunk['points']==[[0,0],[30,0]] and trunk['arrow'] is False
    assert original['paths'][0]['points'][0]==[0,0]
    for p,end in zip(out['paths'][:2],[[30,20],[50,0]]):
        assert p['points'][0]==[30,0] and p['points'][-1]==end
        assert p['endpoint_nodes'][0] is None
        import math
        assert math.dist(*p['points'][-2:])==pytest.approx(ARROW_LENGTH)


@pytest.mark.parametrize('junction',[[31,0],[30,1],[0,0]])
def test_unproven_junction_is_rejected(junction):
    spec=example();spec['shared_branch_groups'][0]['junction']=junction
    with pytest.raises(FigureError):prepare_bound_paths(spec,8)


def test_insufficient_terminal_space_is_not_relaxed():
    s=example();s.pop('shared_branch_groups');s['paths'][0]['points']=[[0,0],[1,0]]
    with pytest.raises(FigureError):prepare_bound_paths(s,8)
