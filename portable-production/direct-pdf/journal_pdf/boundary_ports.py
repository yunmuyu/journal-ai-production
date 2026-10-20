from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, assert_never
from collections.abc import Mapping

from .common import FigureError

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type Side = Literal['left', 'right', 'top', 'bottom']
type TargetKind = Literal['node', 'asset', 'path', 'text', 'group', 'page']


@dataclass(frozen=True, slots=True)
class BoundaryPort:
    target_kind: TargetKind
    target_id: str
    side: Side
    fraction: float
    offset_pt: float = 0.

    def point(self, rect: tuple[float, float, float, float], offset_scale: float=1.) -> tuple[float, float]:
        x, y, right, bottom = rect
        offset=self.offset_pt*offset_scale
        match self.side:
            case 'left':
                return x - offset, y + (bottom - y) * self.fraction
            case 'right':
                return right + offset, y + (bottom - y) * self.fraction
            case 'top':
                return x + (right - x) * self.fraction, y - offset
            case 'bottom':
                return x + (right - x) * self.fraction, bottom + offset
            case unreachable:
                assert_never(unreachable)


def parse_boundary_port(value: JsonValue) -> BoundaryPort:
    offset: JsonValue = 0.
    inset: JsonValue = 0.
    match value:
        case {'page': 'external', 'side': side, 'fraction': fraction, 'inset_pt': inset} if len(value) == 4:
            kind: TargetKind = 'page'
            target = 'external'
        case {'node': str(target), 'side': side, 'fraction': fraction} if len(value) == 3:
            kind = 'node'
        case {'asset': str(target), 'side': side, 'fraction': fraction} if len(value) == 3:
            kind = 'asset'
        case {'path': str(target), 'side': side, 'fraction': fraction} if len(value) == 3:
            kind = 'path'
        case {'group': str(target), 'side': side, 'fraction': fraction} if len(value) == 3:
            kind = 'group'
        case {'text': str(target), 'side': side, 'fraction': fraction, 'offset_pt': offset} if len(value) == 4:
            kind = 'text'
        case {'text': str(target), 'side': side, 'fraction': fraction} if len(value) == 3:
            kind = 'text'
        case _:
            raise FigureError('arrow_endpoint_declaration_invalid', '端口需明确一个真实目标、side和fraction')
    if kind == 'page' and (isinstance(inset,bool) or not isinstance(inset,(int,float)) or not math.isfinite(inset) or not 0<=inset<=1):
        raise FigureError('arrow_endpoint_page_inset_invalid','页面开放端口inset_pt必须为0到1之间的有限数值')
    match side:
        case 'left' | 'right' | 'top' | 'bottom':
            parsed_side: Side = side
        case _:
            raise FigureError('arrow_endpoint_side_invalid', '端口side必须是四边之一')
    match offset:
        case bool():
            raise FigureError('arrow_endpoint_offset_invalid','文字端口offset_pt必须是有限非负数值')
        case int() | float():
            if not math.isfinite(offset) or offset < 0:
                raise FigureError('arrow_endpoint_offset_invalid','文字端口offset_pt必须是有限非负数值')
        case _:
            raise FigureError('arrow_endpoint_offset_invalid','文字端口offset_pt必须是有限非负数值')
    match fraction:
        case bool():
            raise FigureError('arrow_endpoint_fraction_invalid', 'fraction必须是0到1之间的有限数值')
        case int() | float():
            if not math.isfinite(fraction) or not 0 <= fraction <= 1:
                raise FigureError('arrow_endpoint_fraction_invalid', 'fraction必须是0到1之间的有限数值')
            return BoundaryPort(kind, target, parsed_side, float(fraction), -float(inset) if kind=='page' else float(offset))
        case _:
            raise FigureError('arrow_endpoint_fraction_invalid', 'fraction必须是0到1之间的有限数值')


def rectangular_path_bounds(points: list[list[float]]) -> tuple[float, float, float, float] | None:
    if len(points) != 5 or points[0] != points[-1]:
        return None
    xs = sorted({point[0] for point in points})
    ys = sorted({point[1] for point in points})
    if len(xs) != 2 or len(ys) != 2:
        return None
    if {tuple(point) for point in points[:4]} != {(x, y) for x in xs for y in ys}:
        return None
    if any(a[0] != b[0] and a[1] != b[1] for a, b in zip(points, points[1:])):
        return None
    return xs[0], ys[0], xs[1], ys[1]


@dataclass(frozen=True, slots=True)
class BoundaryGeometry:
    nodes: Mapping[str, tuple[float, float, float, float]]
    assets: Mapping[str, tuple[float, float, float, float]]
    paths: Mapping[str, tuple[float, float, float, float] | None]
    texts: Mapping[str, tuple[float, float, float, float]] = field(default_factory=dict)
    groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    page: tuple[float,float,float,float] | None = None
    page_inset_scale: float = 1.

    def matches(self, value: JsonValue, point: tuple[float, float], adjacent: tuple[float,float] | None=None) -> bool:
        declared = parse_boundary_port(value)
        match declared.target_kind:
            case 'page':
                rect = self.page
                if rect is None or adjacent is None or not (rect[0]<=point[0]<=rect[2] and rect[1]<=point[1]<=rect[3]):return False
                normals={'left':(-1.,0.),'right':(1.,0.),'top':(0.,-1.),'bottom':(0.,1.)}
                nx,ny=normals[declared.side]
                if (point[0]-adjacent[0])*nx+(point[1]-adjacent[1])*ny<=0:return False
            case 'node':
                rect = self.nodes.get(declared.target_id)
            case 'asset':
                rect = self.assets.get(declared.target_id)
            case 'path':
                rect = self.paths.get(declared.target_id)
            case 'text':
                rect = self.texts.get(declared.target_id)
            case 'group':
                members = self.groups.get(declared.target_id, ())
                rects = [self.nodes[node] for node in members if node in self.nodes]
                rect = (min(r[0] for r in rects), min(r[1] for r in rects),
                        max(r[2] for r in rects), max(r[3] for r in rects)) if rects and len(rects) == len(members) else None
            case unreachable:
                assert_never(unreachable)
        return rect is not None and math.dist(point, declared.point(rect,self.page_inset_scale if declared.target_kind=='page' else 1.)) <= .15
