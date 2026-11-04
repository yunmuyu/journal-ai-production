from pathlib import Path

import pytest

from localflow.core import FlowError
from localflow.rendering import check_report


@pytest.mark.parametrize('mode', ['source-vector-body', 'source-mixed-body'])
def test_legacy_mechanical_pass_cannot_certify_source_body_text(mode):
    report = {'status': 'candidate-rendered', 'mechanical_checks_passed': True,
              'assets': [{'id': 'body', 'mode': mode}]}
    with pytest.raises(FlowError) as error:
        check_report(report, Path('unused.pdf'))
    assert error.value.code == 'source_text_coverage'


def test_explicit_unverified_coverage_is_not_a_render_failure():
    report = {'status': 'candidate-unverified-source-text', 'mechanical_checks_passed': True,
              'typography_coverage': {'status': 'unverified'}}
    with pytest.raises(FlowError) as error:
        check_report(report, Path('unused.pdf'))
    assert error.value.code == 'source_text_coverage'
