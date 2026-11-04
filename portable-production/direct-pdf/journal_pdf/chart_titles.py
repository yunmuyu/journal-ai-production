"""Place source-bound chart titles above measured content without changing data."""
from __future__ import annotations

from .editorial import LABEL_CLEARANCE
from .scene import Scene


def finish_chart_title(scene: Scene, width: float, height: float, title: str | None) -> Scene:
    if title is None:
        return scene.finish(width, height)
    measured = scene.registry.measure(title, scene.size)
    top = min([t['position']['bbox'][1] for t in scene.texts]
              + [a['rect'][1] for a in scene.assets] + [0.0])
    item = scene.text('plot-title', title, width / 2,
                      top - LABEL_CLEARANCE - measured['height'] / 2)
    bounds = item['position']['bbox']
    dx = max(0.0, 1.0 - bounds[0])
    dy = max(0.0, 1.0 - bounds[1])
    for node in scene.nodes:
        x0, y0, x1, y1 = node['rect']
        node['rect'] = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
    for path in scene.paths:
        path['points'] = [[x + dx, y + dy] for x, y in path['points']]
    for asset in scene.assets:
        x0, y0, x1, y1 = asset['rect']
        asset['rect'] = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
    for text in scene.texts:
        text['x'] += dx
        text['y'] += dy
        x0, y0, x1, y1 = text['position']['bbox']
        text['position']['bbox'] = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
        text['position']['offset'][0] += dx
        text['position']['offset'][1] += dy
    scene.layout_evidence['plot_title'] = {
        'source_text': title, 'clearance_pt': LABEL_CLEARANCE,
        'translation_pt': [dx, dy], 'data_geometry_changed': False,
    }
    return scene.finish(max(width + dx, bounds[2] + dx + 1), height + dy)
