from __future__ import annotations

import pymupdf

from journal_pdf.assets import Assets
from journal_pdf.numeric_audit import missing_numeric_labels
from journal_pdf.render import render_one


def _horizontal_tick_page() -> pymupdf.Page:
    doc = pymupdf.open()
    page = doc.new_page(width=220, height=30)
    for index in range(15):
        page.insert_text((5 + index * 14, 20), str(index + 1), fontsize=8)
    return page


def test_horizontal_multidigit_labels_are_found_when_pdf_merges_the_line() -> None:
    # Given
    page = _horizontal_tick_page()
    words = {
        word[4]: tuple(word[:4])
        for word in page.get_text("words")
        if word[4].isdigit()
    }
    labels = [(str(number), words[str(number)]) for number in range(1, 16)]
    assert page.get_text().splitlines()[-1].split() == [
        str(number) for number in range(10, 16)
    ]

    # When
    missing = missing_numeric_labels(page, labels)

    # Then
    assert missing == {}


def test_numeric_label_from_another_axis_region_does_not_mask_a_missing_tick() -> None:
    # Given
    page = _horizontal_tick_page()
    first_word = next(
        word for word in page.get_text("words") if word[4] == "1"
    )
    first_bbox = (first_word[0], first_word[1], first_word[2], first_word[3])

    # When
    missing = missing_numeric_labels(
        page,
        [("1", first_bbox), ("16", first_bbox)],
    )

    # Then
    assert missing == {"16": 1}


def test_missing_grouping_space_in_numeric_label_is_not_masked() -> None:
    # Given
    doc = pymupdf.open()
    page = doc.new_page(width=80, height=30)
    page.insert_text((5, 20), "0.073162", fontsize=8)
    word = next(word for word in page.get_text("words") if word[4] == "0.073162")

    # When
    missing = missing_numeric_labels(
        page,
        [("0.073 162", (word[0], word[1], word[2], word[3]))],
    )

    # Then
    assert missing == {"0.073 162": 1}


def test_rendered_horizontal_axis_ticks_pass_real_pdf_audit(tmp_path, reg) -> None:
    # Given
    source_root = tmp_path / "source"
    source_root.mkdir()
    spec = {
        "version": 1,
        "id": "horizontal-density-audit",
        "author": "Synthetic",
        "kind": "scene",
        "synthetic": True,
        "policy": {"column": "single", "design_font_size_pt": 8},
        "sources": [],
        "width_pt": 250,
        "height_pt": 30,
        "nodes": [],
        "assets": [],
        "texts": [
            {
                "id": f"xtick{index}",
                "text": str(index + 1),
                "x": 12 + index * 15,
                "y": 18,
                "role": "axis-tick",
            }
            for index in range(15)
        ],
    }
    assets = Assets()
    try:
        # When
        result = render_one(spec, reg, assets, source_root, tmp_path / "output")
    finally:
        assets.close()

    # Then
    assert result["pdf_audit"]["numeric_grouping_in_actual_pdf"] is True
    assert result["pdf_audit"]["numeric_missing"] == {}
