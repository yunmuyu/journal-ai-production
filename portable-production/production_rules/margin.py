"""Export-margin tolerance. The 0.25pt target must not accept a missing pad."""
from .load import load_rules


def margin_tolerance_pt(padding: float) -> float:
    rules = load_rules()['normative']
    tight = float(rules['margin_measure_tolerance_pt'])
    if padding <= 0.5:
        return tight
    return max(tight, float(rules['legacy_large_pad_tolerance_pt']))
