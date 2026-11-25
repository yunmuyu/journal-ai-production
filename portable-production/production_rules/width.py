"""Column tiers. Explicit single stays locked unless the rule file says otherwise."""
from .load import load_rules


def is_simple_chart(spec, kind, rules=None) -> bool:
    rules = rules or load_rules()
    policy = spec.get('policy') or {}
    if policy.get('simple_chart') is True:
        return True
    if policy.get('simple_chart') is False:
        return False
    if kind != 'chart':
        return False
    if spec.get('panels'):
        return False
    series = spec.get('series') or []
    return len(series) <= int(rules['normative']['simple_chart_max_series'])


def column_tiers(mode: str, spec, kind, rules=None) -> list[float]:
    """Smallest tier first. Explicit single does not jump to double while the flag is false."""
    rules = rules or load_rules()
    normative = rules['normative']
    single = float(normative['single_column_mm'])
    double = float(normative['double_column_mm'])
    simple = float(normative['simple_chart_mm'])
    if mode == 'double':
        return [double]
    tiers = []
    # Simple charts start at 60mm even when the column is explicitly single.
    # Single still does not jump to the two-column tier.
    if is_simple_chart(spec, kind, rules):
        tiers.append(simple)
    tiers.append(single)
    if mode == 'auto' or normative.get('explicit_single_advances'):
        tiers.append(double)
    # de-duplicate while keeping order
    seen = []
    for value in tiers:
        if value not in seen:
            seen.append(value)
    return seen
