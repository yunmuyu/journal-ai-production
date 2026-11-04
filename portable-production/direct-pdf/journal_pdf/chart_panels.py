"""Compose measured chart scenes while retaining each original vector viewport."""
from __future__ import annotations

import copy

from .common import FigureError
from .editorial import LABEL_CLEARANCE
from .scene import Scene


def compose_chart_panels(spec, reg, size, assets, root, build) -> Scene:
    panels = spec['panels']
    if not isinstance(panels, list) or not 2 <= len(panels) <= 12:
        raise FigureError('chart_panel_count', '组合图须明确2至12个完整面板')
    if any(not isinstance(p, dict) or p.get('kind') != 'chart' or 'panels' in p for p in panels):
        raise FigureError('chart_panel_kind', '组合图只接受直接绑定原图的非嵌套图表面板')
    scene = Scene(reg, size)
    scene.template = 'chart-panels'
    evidence = []
    x = 0.0
    height = 0.0
    gap = 2 * LABEL_CLEARANCE * size / 8
    for index, panel in enumerate(panels):
        child = build(panel, reg, size, assets, root)
        prefix = f'panel-{index + 1}:'
        for node in child.nodes:
            row = copy.deepcopy(node)
            row['id'] = prefix + row['id']
            a, b, c, d = row['rect']
            row['rect'] = [a + x, b, c + x, d]
            scene.nodes.append(row)
        for path in child.paths:
            row = copy.deepcopy(path)
            row['id'] = prefix + row['id']
            row['points'] = [[a + x, b] for a, b in row['points']]
            scene.paths.append(row)
        for asset in child.assets:
            row = dict(asset)
            row['id'] = prefix + row['id']
            a, b, c, d = row['rect']
            row['rect'] = [a + x, b, c + x, d]
            scene.assets.append(row)
        for text in child.texts:
            row = dict(text)
            row['id'] = prefix + row['id']
            if row.get('owner'):
                row['owner'] = prefix + row['owner']
            row['position'] = copy.deepcopy(row['position'])
            a, b, c, d = row['position']['bbox']
            row['position']['bbox'] = [a + x, b, c + x, d]
            row['position']['offset'][0] += x
            row['x'] += x
            scene.texts.append(row)
        scene.notes.extend(child.notes)
        evidence.append({'prefix': prefix, 'source': panel['source'],
                         'axes_id': panel.get('axes_id'), 'layout': child.layout_evidence})
        height = max(height, child.height)
        x += child.width + gap
    for note in spec.get('review_notes', []):
        if not isinstance(note, str) or not note.strip():
            raise FigureError('chart_panel_note', '语义待确认说明须为非空文字')
        scene.notes.append({'code': 'source_semantics_pending', 'message': note})
    scene.layout_evidence = {'chart_panels': evidence, 'panel_gap_pt': gap,
                             'composition': 'horizontal; original panel order; no data reconstruction'}
    return scene.finish(x - gap, height)
