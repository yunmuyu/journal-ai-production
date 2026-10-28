"""Typed public report structures for the optional figure inspection tools."""
from typing import TypedDict


class FingerprintReport(TypedDict):
    file: str
    page_mm: list[float]
    n_frames: int
    n_bars: int
    n_groups: int
    bars_per_group: list[int]
    bars_even: bool
    group_axis: str
    n_series: int
    legend_texts: list[str]
    has_x_title: bool
    has_y_title: bool
    n_ticks_x: int
    n_ticks_y: int
    body_pt: float


class GuardArguments(TypedDict):
    out: str | None
    src: str | None
    column: int | None
    mode: str
    font_levels: int | None
    allow_bitmap: int
    spacing_json: str | None
    json: str | None


class SpacingItem(TypedDict):
    role: str
    desc: str
    n: int
    measured_pt: float
    em: float
    target_pt: float | None
    mode: str
    range_pt: list[float]
    verdict: str
    note: str
    where: str
    origin: str | None
    origin_ref: str


class SpacingReport(TypedDict):
    figure: str
    pdf: str
    pdf_sha256: str
    size_pt: float
    n_frames: int
    rules_version: int | None
    items: list[SpacingItem]
    n_fail: int
    n_warn: int
    n_info: int
