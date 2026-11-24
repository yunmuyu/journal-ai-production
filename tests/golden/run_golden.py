"""Replay public synthetic cases. Real author cases stay in tests/golden/local/."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'portable-production'))
from production_rules.names import FigureNameError, validate_figure_stem
from production_rules.routing import route_source


def run_file(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding='utf-8'))
    problems = []
    for case in data['cases']:
        if 'stem' in case:
            try:
                validate_figure_stem(case['stem'])
                ok = True
            except FigureNameError:
                ok = False
            if ok != case['valid']:
                problems.append(case['stem'])
            continue
        actual = route_source(case['name'], case.get('hint'))
        if actual['route'] != case['route'] or actual['redraw'] != case['redraw']:
            problems.append(case['name'])
    return problems


def main() -> int:
    public = Path(__file__).resolve().parent / 'public' / 'cases.json'
    problems = run_file(public)
    local = Path(__file__).resolve().parent / 'local'
    config = local / 'cases.json'
    if config.is_file():
        problems.extend(run_file(config))
    if problems:
        print('golden mismatch: ' + ', '.join(problems))
        return 1
    print('golden ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
