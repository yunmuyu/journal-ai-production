"""Confirmed editorial rule: unary U+002D, binary subtraction U+2212.

Classify the complete semantic text before measuring it, including styled runs.
Ordinary label hyphens are not interpreted as mathematical subtraction.
"""
from __future__ import annotations

import re
from typing import Final

_PREFIX: Final = frozenset('([{,;:=+−-*/×·÷^_<>≤≥≠|±∓～~〜')
_OPERAND_START: Final = frozenset('([{√∛±∓−-+')
_EXPONENT: Final = re.compile(r'(?:^|[^A-Za-z0-9_.])(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)[eE]$')


def normalize_mathematical_signs(text: str, *, mathematical: bool = False) -> str:
    result = list(text)
    line_start = 0
    for index, char in enumerate(text):
        if char == '\n':
            line_start = index + 1
        if char not in '-−':
            continue
        left = text[line_start:index].rstrip()
        right = text[index + 1:].lstrip()
        if not right or not (right[0].isalnum() or right[0] in _OPERAND_START):
            continue
        exponent = bool(_EXPONENT.search(left)) and right[0].isdigit()
        unary = not left or left[-1] in _PREFIX or exponent
        if unary:
            result[index] = '-'
        elif mathematical:
            result[index] = '−'
    return ''.join(result)
