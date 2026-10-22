from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from .common import FigureError
from .editorial import COMPACT_GAP, PAD_X, PAD_Y, display_content
from .fonts import FontRegistry
from .scene import Scene, port


class Branch(TypedDict):
    text: str
    children: NotRequired[list[str | Branch]]
    side: NotRequired[Literal['left', 'right']]
    wrap_chars: NotRequired[int]


class TreeSpec(TypedDict):
    root: str
    branches: list[Branch]
    root_vertical: NotRequired[bool]


@dataclass(frozen=True, slots=True)
class MeasuredNode:
    id: str
    text: str
    width: float
    height: float
    span: float
    children: tuple[MeasuredNode, ...]
    vertical: bool = False


def _label(text: str, wrap: int | None) -> str:
    if not isinstance(text, str) or not text.strip():
        raise FigureError('tree_text', '树节点须有非空原文')
    if wrap is not None:
        if isinstance(wrap, bool) or not isinstance(wrap, int) or not 1 <= wrap <= 20:
            raise FigureError('tree_wrap', '树节点中文换行宽度须为1—20的整数')
        if re.fullmatch(r'[\u3400-\u9fff]+', text):
            return '\n'.join(text[i:i+wrap] for i in range(0, len(text), wrap))
    return text


def bilateral_tree(spec: TreeSpec, reg: FontRegistry, size: float) -> Scene:
    scale = size / 8
    padding, gap, link_gap = PAD_X, COMPACT_GAP*scale, 2*COMPACT_GAP*scale
    widths: dict[tuple[str, int], float] = {}
    members: dict[tuple[str, int], list[str]] = {}
    parents: dict[str, str] = {}
    count = 0

    def measure(value: str | Branch, id: str, side: str, depth: int) -> MeasuredNode:
        nonlocal count
        count += 1
        if count > 80 or depth > 12:
            raise FigureError('tree_budget', '双侧树最多80节点、12层；不可压平层级')
        match value:
            case str(text):
                text = display_content(_label(text, None), 'label')
                children: list[str | Branch] = []
            case dict() if set(value) <= {'text', 'children', 'side', 'wrap_chars'}:
                if value.get('side', side) != side:
                    raise FigureError('tree_side', '子树不得中途改换左右归属', node=id)
                text = _label(display_content(_label(value.get('text', ''), None), 'label'), value.get('wrap_chars'))
                children = value.get('children', [])
                if not isinstance(children, list):
                    raise FigureError('tree_children', 'children须为保序数组', node=id)
            case _:
                raise FigureError('tree_node', '树节点只接受原文、children、side和wrap_chars', node=id)
        descendants = tuple(measure(v, f'{id}-{i}', side, depth+1) for i, v in enumerate(children))
        for child in descendants:
            parents[child.id] = id
        vertical = isinstance(value, dict) and value.get('wrap_chars') == 1 and all('㐀' <= c <= '鿿' for c in text if not c.isspace())
        m = reg.measure_vertical(text, size) if vertical else reg.measure(text, size, role='literal')
        width, height = m['width']+2*PAD_X*scale, m['height']+2*PAD_Y*scale
        key = side, depth
        widths[key] = max(widths.get(key, 0.), width)
        members.setdefault(key, []).append(id)
        span = max(height, sum(c.span for c in descendants)+gap*max(0, len(descendants)-1))
        return MeasuredNode(id, text, width, height, span, descendants, vertical)

    root_text = display_content(_label(spec.get('root', ''), None), 'label')
    vertical = spec.get('root_vertical', False)
    if not isinstance(vertical, bool):
        raise FigureError('tree_root_orientation', 'root_vertical须为布尔值')
    if vertical:
        root_text = '\n'.join(re.findall(r'[\u3400-\u9fff]|[^\u3400-\u9fff\n]+', root_text))
    raw = spec.get('branches')
    if not isinstance(raw, list) or not raw:
        raise FigureError('tree_branches', '双侧树须有非空branches数组')
    sides: dict[str, list[MeasuredNode]] = {'left': [], 'right': []}
    for i, value in enumerate(raw):
        if not isinstance(value, dict) or value.get('side') not in ('left', 'right'):
            raise FigureError('tree_side', '根分支须明确side:left/right，不猜原图归属')
        side = value['side']
        child = measure(value, f'b{i}', side, 1)
        parents[child.id] = 'root'
        sides[side].append(child)
    if count+1 > 80:
        raise FigureError('tree_budget', '双侧树最多80节点')
    m = reg.measure_vertical(root_text, size) if vertical else reg.measure(root_text, size, role='literal')
    root_w, root_h = m['width']+2*PAD_X*scale, m['height']+2*PAD_Y*scale
    side_heights = {side: sum(n.span for n in nodes)+gap*max(0, len(nodes)-1)
                    for side, nodes in sides.items()}
    height = max(root_h, *side_heights.values())
    extents = {side: sum(w+link_gap for (s, _), w in widths.items() if s == side)
               for side in sides}
    root_x = padding+extents['left']
    scene = Scene(reg, size)
    scene.template = 'bilateral-tree'
    root = scene.box('root', root_text, root_x, padding+(height-root_h)/2, root_w, root_h, text_role='literal', vertical_text=vertical)
    boxes = {'root': root}

    def place(nodes: list[MeasuredNode] | tuple[MeasuredNode, ...], side: str, depth: int,
              near: float, top: float) -> None:
        width = widths[side, depth]
        x = near+link_gap if side == 'right' else near-link_gap-width
        for n in nodes:
            y = top+n.span/2-n.height/2
            box = scene.box(n.id, n.text, x, y, width, n.height, text_role='literal', vertical_text=n.vertical)
            boxes[n.id] = box
            key = f'tree-{side}-{depth}'
            box['measurement_contract'] = {'mode': 'measured-group', 'group': key,
                                          'axis': 'column', 'expected_wh': [width, n.height]}
            if n.children:
                child_height = sum(c.span for c in n.children)+gap*(len(n.children)-1)
                place(n.children, side, depth+1, x+width if side == 'right' else x,
                      top+(n.span-child_height)/2)
            top += n.span+gap

    for side, nodes in sides.items():
        if nodes:
            place(nodes, side, 1, root_x+root_w if side == 'right' else root_x,
                  padding+(height-side_heights[side])/2)
    for (side, depth), ids in members.items():
        scene.measurement_groups[f'tree-{side}-{depth}'] = {'axis': 'column', 'nodes': ids}

    def connect(parent_id: str, nodes: list[MeasuredNode] | tuple[MeasuredNode, ...], side: str) -> None:
        parent = boxes[parent_id]
        outgoing, incoming = ('right', 'left') if side == 'right' else ('left', 'right')
        start = port(parent, outgoing)
        bus = start[0]+(link_gap/2 if side == 'right' else -link_gap/2)
        endpoints = [port(boxes[n.id], incoming) for n in nodes]
        scene.line(f'{parent_id}-{side}-stem', [start, [bus, start[1]]])
        ys = [start[1], *(p[1] for p in endpoints)]
        if max(ys)-min(ys) > 1e-7:
            scene.line(f'{parent_id}-{side}-bus', [[bus, min(ys)], [bus, max(ys)]])
        for node, end in zip(nodes, endpoints, strict=True):
            scene.line(f'edge-{node.id}', [[bus, end[1]], end])
            if node.children:
                connect(node.id, node.children, side)

    for side, nodes in sides.items():
        if nodes:
            connect('root', nodes, side)
    scene.layout_evidence = {'algorithm': 'bilateral leaf-to-root subtree measurement',
                            'parent_map': parents, 'root_branch_sides':
                            {n.id: side for side, nodes in sides.items() for n in nodes},
                            'column_widths_pt': {f'{s}-{d}': w for (s, d), w in widths.items()},
                            'node_count': count+1, 'font_size_kept': size,
                            'whole_artwork_scale': 1, 'link_gap_pt': link_gap}
    return scene.finish(root_x+root_w+extents['right']+padding, height+2*padding)
