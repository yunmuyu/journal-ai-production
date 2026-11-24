"""Replay public cases, and private pairs when JOURNAL_GOLDEN_DIR is set.

Private layout, matching the owner's box:

    $JOURNAL_GOLDEN_DIR/<issue>/<author>/source/
    $JOURNAL_GOLDEN_DIR/<issue>/<author>/final/

Optional index (not inside the cases tree):

    JOURNAL_GOLDEN_INDEX=/path/golden-index.json

Each index case is {"issue", "author", "source", "final"}. source is relative
to that author's source directory, final to final/. Missing env is not a failure.
"""
from __future__ import annotations

import json
import os
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


def check_private(root: Path, index: Path | None) -> list[str]:
    problems = []
    if not root.is_dir():
        return [f'JOURNAL_GOLDEN_DIR 不存在: {root}']
    authors = [author for issue in root.iterdir() if issue.is_dir() for author in issue.iterdir() if author.is_dir()]
    if not authors:
        problems.append(f'{root} 下没有 <期次>/<作者> 目录')
    for author in authors:
        if not (author / 'source').is_dir() or not (author / 'final').is_dir():
            problems.append(f'{author.relative_to(root)} 缺少 source/ 或 final/')
    if index is None:
        return problems
    if not index.is_file():
        return problems + [f'JOURNAL_GOLDEN_INDEX 不存在: {index}']
    data = json.loads(index.read_text(encoding='utf-8'))
    cases = data['cases'] if isinstance(data, dict) else data
    for case in cases:
        base = root / case['issue'] / case['author']
        for key, folder in (('source', 'source'), ('final', 'final')):
            relative = case.get(key)
            if not relative:
                problems.append(f'{case.get("issue")}/{case.get("author")} 缺少 {key}')
                continue
            if not (base / folder / relative).is_file():
                problems.append(str(base / folder / relative))
    return problems


def main() -> int:
    problems = run_file(Path(__file__).resolve().parent / 'public' / 'cases.json')
    private = os.environ.get('JOURNAL_GOLDEN_DIR')
    if private:
        index = os.environ.get('JOURNAL_GOLDEN_INDEX')
        problems.extend(check_private(Path(private), Path(index) if index else None))
    if problems:
        print('golden mismatch: ' + ', '.join(problems))
        return 1
    print('golden ok' + (' (含私有目录)' if private else ''))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
