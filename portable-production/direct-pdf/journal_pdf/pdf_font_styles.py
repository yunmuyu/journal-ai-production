"""Match editable scene glyphs to actual PDF fonts at their baseline positions.

No variable inference. The caller separately proves embedded-font descriptors;
this audit binds those actual PostScript identities to each declared glyph face.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import re
from typing import Final, NotRequired, TypedDict

from .text_geometry import rotate_point

POSITION_TOLERANCE_PT: Final = .1
_SUBSET_PREFIX: Final = re.compile(r'^[A-Z]{6}\+')


class Glyph(TypedDict):
    ch: str
    face: str
    size: float
    x: float
    y: float
    rotation: NotRequired[float]


class Measurement(TypedDict):
    glyphs: list[Glyph]


class Position(TypedDict):
    offset: Sequence[float]
    rotation: float


class TextItem(TypedDict):
    id: str
    measurement: Measurement
    position: Position


class Trace(TypedDict):
    font: str
    size: float
    dir: Sequence[float]
    chars: Sequence[tuple[int, int, Sequence[float], Sequence[float]]]


class StyleIssue(TypedDict):
    code: str
    text_id: str
    character: str
    expected_font: str
    actual_fonts: list[str]
    expected_origin: tuple[float, float]


class StyleAudit(TypedDict):
    ok: bool
    checked_scene_characters: int
    position_tolerance_pt: float
    issues: list[StyleIssue]
    scope: str


@dataclass(frozen=True, slots=True)
class ActualGlyph:
    character: str
    font: str
    size: float
    angle: float
    x: float
    y: float


def _font_name(name: str) -> str:
    return _SUBSET_PREFIX.sub('', name)


def audit_pdf_font_styles(
    texts: Sequence[TextItem], traces: Sequence[Trace],
    postscript_names: Mapping[str, str], crop_offset: Sequence[float] = (0., 0.),
) -> StyleAudit:
    """Require one actual glyph with the declared font at every scene baseline."""
    actual = []
    for trace in traces:
        angle = math.degrees(math.atan2(-trace['dir'][1], trace['dir'][0])) % 360
        for codepoint, _gid, origin, _bbox in trace['chars']:
            if not chr(codepoint).isspace():
                actual.append(ActualGlyph(chr(codepoint), _font_name(trace['font']),
                                          trace['size'], angle, origin[0], origin[1]))
    used: set[int] = set()
    issues: list[StyleIssue] = []
    checked = 0
    for item in texts:
        position = item['position']
        for glyph in item['measurement']['glyphs']:
            if glyph['ch'].isspace():
                continue
            checked += 1
            rx, ry = rotate_point(glyph['x'], glyph['y'], position['rotation'])
            x = position['offset'][0] + rx - crop_offset[0]
            y = position['offset'][1] + ry - crop_offset[1]
            angle = (position['rotation'] + glyph.get('rotation', 0.)) % 360
            expected = postscript_names.get(glyph['face'], '')
            candidates = [index for index, found in enumerate(actual)
                          if index not in used and found.character == glyph['ch']
                          and math.hypot(found.x-x, found.y-y) <= POSITION_TOLERANCE_PT
                          and abs(found.size-glyph['size']) < .01
                          and abs((found.angle-angle+180) % 360-180) < .01]
            if len(candidates) != 1 or not expected:
                code = 'actual_font_glyph_match_unproven'
            elif actual[candidates[0]].font != _font_name(expected):
                code = 'actual_font_face_mismatch'
            else:
                used.add(candidates[0])
                continue
            issues.append({'code': code, 'text_id': item['id'], 'character': glyph['ch'],
                           'expected_font': expected,
                           'actual_fonts': [actual[index].font for index in candidates],
                           'expected_origin': (x, y)})
    return {'ok': not issues, 'checked_scene_characters': checked,
            'position_tolerance_pt': POSITION_TOLERANCE_PT, 'issues': issues,
            'scope': 'Editable scene glyphs only; character, baseline, size, rotation and configured PostScript face. '
                     'Unknown or ambiguous matches fail; imported text and semantic variable classification are outside scope.'}
