"""Load the repository rule file without a circular import into editorial.py."""
from __future__ import annotations

import sys
from pathlib import Path

_portable = Path(__file__).resolve().parents[2]
if str(_portable) not in sys.path:
    sys.path.insert(0, str(_portable))

from production_rules.load import load_rules
from production_rules.margin import margin_tolerance_pt
from production_rules.width import column_tiers, is_simple_chart
from production_rules.names import validate_figure_stem, figure_stem, FigureNameError

__all__ = [
    'load_rules', 'margin_tolerance_pt', 'column_tiers', 'is_simple_chart',
    'validate_figure_stem', 'figure_stem', 'FigureNameError',
]
