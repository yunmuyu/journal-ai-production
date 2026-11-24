"""Export-margin tolerance. The 0.25pt target must not accept a missing pad."""
from .load import load_rules


def margin_tolerance_pt(padding: float | None = None) -> float:
    """Measurement slack for the one PDF margin. It stays below that margin."""
    rules = load_rules()['normative']
    margin = float(rules['margin_pt'] if padding is None else padding)
    return min(float(rules['margin_measure_tolerance_pt']), margin * 0.6)
