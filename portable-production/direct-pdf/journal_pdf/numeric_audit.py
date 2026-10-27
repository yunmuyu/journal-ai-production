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
    expected = Counter(_normalized_label_text(text) for text, _ in labels)
    actual: Counter[str] = Counter()
    for _, bbox in labels:
        region = pymupdf.Rect(
            bbox[0] - crop.x - BBOX_PROTECTION_PT,
            bbox[1] - crop.y - BBOX_PROTECTION_PT,
            bbox[2] - crop.x + BBOX_PROTECTION_PT,
            bbox[3] - crop.y + BBOX_PROTECTION_PT,
        )
        words = page.get_text("words", clip=region)
        ordered = sorted(words, key=lambda word: (word[1], word[0]))
        actual[_normalized_label_text(" ".join(word[4] for word in ordered))] += 1

    missing_normalized = expected - actual
    missing: Counter[str] = Counter()
    for text, _ in labels:
        normalized = _normalized_label_text(text)
        if missing_normalized[normalized] > 0:
            missing[text] += 1
            missing_normalized[normalized] -= 1
    return dict(missing)
