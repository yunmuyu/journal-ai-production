"""Publication file names: 作者-图1 and 作者-图1.1, never 1.A or 1a."""
from __future__ import annotations

import re

_STEM = re.compile(r'^(.+)-图([0-9]+(?:\.[0-9]+)?)$')
_NUMBER = re.compile(r'^[1-9][0-9]*(?:\.[1-9][0-9]*)?$')


class FigureNameError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def validate_figure_stem(stem: str) -> dict:
    if not isinstance(stem, str) or not stem.strip():
        raise FigureNameError('figure_name', '图件文件名不能为空')
    if re.search(r'[A-Za-z]', stem.split('-图')[-1] if '-图' in stem else stem):
        # Letters after 图 are the subfigure form the owner rejected (1A / 1a / 1.A).
        tail = stem.split('-图', 1)[-1]
        if re.search(r'[A-Za-z]', tail):
            raise FigureNameError('figure_name', '子图号只用 1.1、1.2，不用 1.A 或 1a')
    match = _STEM.fullmatch(stem.strip())
    if not match or not _NUMBER.fullmatch(match.group(2)):
        raise FigureNameError('figure_name', '文件名须为作者-图N 或 作者-图N.N，例如张三-图1.2')
    return {'author': match.group(1), 'number': match.group(2)}


def figure_stem(author: str, number: str) -> str:
    stem = f'{author}-图{number}'
    validate_figure_stem(stem)
    return stem
