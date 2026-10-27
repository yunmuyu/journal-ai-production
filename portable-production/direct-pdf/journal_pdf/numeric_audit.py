from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Final, TypeAlias

import pymupdf


NumericLabel: TypeAlias = tuple[str, tuple[float, float, float, float]]
BBOX_PROTECTION_PT: Final = 0.5


def _normalized_label_text(text: str) -> str:
    return " ".join(text.split())


def missing_numeric_labels(
    page: pymupdf.Page, labels: Sequence[NumericLabel]
) -> dict[str, int]:
    """Return declared numeric labels absent from their expected PDF regions."""
    crop = page.cropbox_position
    missing: Counter[str] = Counter()
    for text, bbox in labels:
        region = pymupdf.Rect(
            bbox[0] - crop.x - BBOX_PROTECTION_PT,
            bbox[1] - crop.y - BBOX_PROTECTION_PT,
            bbox[2] - crop.x + BBOX_PROTECTION_PT,
            bbox[3] - crop.y + BBOX_PROTECTION_PT,
        )
        words = page.get_text("words", clip=region)
        ordered = sorted(words, key=lambda word: (word[1], word[0]))
        actual = _normalized_label_text(" ".join(word[4] for word in ordered))
        if actual != _normalized_label_text(text):
            missing[text] += 1
    return dict(missing)
