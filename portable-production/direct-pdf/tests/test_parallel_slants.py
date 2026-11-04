from types import SimpleNamespace
import pytest
from journal_pdf.parallel_slants import audit_parallel_slants,parse_parallel_slants


def test_repeated_branch_slopes_are_compared_without_requiring_identical_lengths():
    paths=[{'id':'a','points':[[0,0],[6,44]],'arrow':True},
           {'id':'b','points':[[30,0],[30+6*38/44,38]],'arrow':True}]
    scene=SimpleNamespace(paths=paths,parallel_slant_checks=parse_parallel_slants([{'path_ids':['a','b']}]))
    result=audit_parallel_slants(scene)
    assert not result['notes'] and not result['issues']
    assert result['checks'][0]['spread_degrees']==pytest.approx(0,abs=1e-6)
    paths[1]['points'][1][0]+=4
    assert audit_parallel_slants(scene)['notes'][0]['code']=='parallel_slant_review'


def test_parallel_slants_reject_missing_or_unverifiable_path():
    scene=SimpleNamespace(paths=[{'id':'a','points':[[0,0],[1,5]],'arrow':True}],
                          parallel_slant_checks=parse_parallel_slants([{'path_ids':['a','missing']}]))
    assert audit_parallel_slants(scene)['issues'][0]['code']=='parallel_slant_path_invalid'
