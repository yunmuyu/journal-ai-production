from __future__ import annotations

import copy
import math

from .common import FigureError, intersects, segment_hits
from .editorial import ARROW_BOUNDARY_GAP
from .graph_layout import graph
from .scene import Scene, audit_scene, port

def _namespace(identifier: str, prefix: str) -> str:
    return f"{prefix}:{identifier}"


def _append_child(target: Scene, child: Scene, prefix: str, dx: float, dy: float) -> None:
    for identifier, group in child.measurement_groups.items():
        translated = copy.deepcopy(group)
        translated['nodes'] = [_namespace(name, prefix) for name in group['nodes']]
        target.measurement_groups[_namespace(identifier, prefix)] = translated
    target.source_bindings.update(child.source_bindings)
    for source in child.nodes:
        node = copy.deepcopy(source)
        node["id"] = _namespace(node["id"], prefix)
        node["rect"] = [node["rect"][0] + dx, node["rect"][1] + dy, node["rect"][2] + dx, node["rect"][3] + dy]
        if node.get('measurement_contract', {}).get('mode') == 'measured-group':
            node['measurement_contract']['group'] = _namespace(node['measurement_contract']['group'], prefix)
        target.ident(node["id"])
        target.nodes.append(node)
    for source in child.texts:
        text = copy.deepcopy(source)
        text["id"] = _namespace(text["id"], prefix)
        if text["owner"] is not None:
            text["owner"] = _namespace(text["owner"], prefix)
        text["x"] += dx
        text["y"] += dy
        bbox = text["position"]["bbox"]
        text["position"]["bbox"] = [bbox[0] + dx, bbox[1] + dy, bbox[2] + dx, bbox[3] + dy]
        text["position"]["offset"][0] += dx
        text["position"]["offset"][1] += dy
        target.ident(text["id"])
        target.texts.append(text)
    for source in child.paths:
        path = copy.deepcopy(source)
        path["id"] = _namespace(path["id"], prefix)
        translated = [[point[0] + dx, point[1] + dy] for point in path['points']]
        path['points'] = [point for i, point in enumerate(translated) if not i or point != translated[i-1]]
        if path["endpoint_nodes"] is not None:
            path["endpoint_nodes"] = [_namespace(node, prefix) if node is not None else None for node in path["endpoint_nodes"]]
        target.ident(path["id"])
        target.paths.append(path)
    for source in child.assets:
        asset = source.copy()
        asset["id"] = _namespace(asset["id"], prefix)
        rect = asset["rect"]
        asset["rect"] = [rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy]
        target.ident(asset["id"])
        target.assets.append(asset)


def _scopes(scene, column_specs):
    anchors = {}
    for column in column_specs:
        prefix = column['id']
        for scope in column.get('scopes', []):
            if not isinstance(scope.get('id'), str) or not scope['id']:
                raise FigureError('columns_scope', '作用域必须有非空字符串ID')
            names = [_namespace(name, prefix) for name in scope.get('nodes', [])]
            nodes = [node for node in scene.nodes if node['id'] in names]
            if not names or len(nodes) != len(set(names)) or scope.get('side') != 'right':
                raise FigureError('columns_scope', '作用域必须绑定存在的节点并使用右侧括号', scope=scope.get('id'))
            key = (prefix, scope['id'])
            if key in anchors:
                raise FigureError('columns_scope', '作用域ID重复', scope=scope['id'])
            x = max(node['rect'][2] for node in nodes) + 5
            top = min(node['rect'][1] for node in nodes) - 2
            bottom = max(node['rect'][3] for node in nodes) + 2
            scene.line(f'scope:{prefix}:{scope["id"]}', [[x-2, top], [x, top], [x, bottom], [x-2, bottom]], semantic_role='scope-boundary')
            anchors[key] = (x, top, bottom)
            if scope.get('label'):
                scene.text(f'scope:{prefix}:{scope["id"]}:label', scope['label'], x+3, top, align='left', role='scope-label')
    return anchors


def _endpoint(scene, declaration, scopes):
    prefix = declaration.get('column')
    if ('scope' in declaration) == ('node' in declaration):
        raise FigureError('columns_anchor', '锚点必须且只能声明scope或node')
    if 'scope' in declaration:
        key = (prefix, declaration['scope'])
        fraction = declaration.get('fraction')
        if key not in scopes or not isinstance(fraction, (int, float)) or not 0 < fraction < 1:
            raise FigureError('columns_anchor', '作用域锚点不存在或fraction不在0与1之间')
        x, top, bottom = scopes[key]
        return [x, top+(bottom-top)*fraction], None, 'right'
    node_id = _namespace(declaration.get('node', ''), prefix)
    nodes = [node for node in scene.nodes if node['id'] == node_id]
    side = declaration.get('port')
    if not nodes or side not in ('left', 'right', 'top', 'bottom'):
        raise FigureError('columns_anchor', '节点锚点不存在或端口无效', node=node_id)
    return port(nodes[0], side), node_id, side


def _relations(scene, relations, placements, scopes):
    records = []
    vectors = {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}
    for relation in relations:
        source, target = relation['source'], relation['target']
        a, source_id, source_side = _endpoint(scene, source, scopes)
        b, target_id, target_side = _endpoint(scene, target, scopes)
        left = next((p for p in placements if p['id'] == source['column']), None)
        right = next((p for p in placements if p['id'] == target['column']), None)
        if left is None or right is None or left is right:
            raise FigureError('columns_relation', '关系必须连接两个存在的独立列')
        direction = 'LR' if left['x_pt'] < right['x_pt'] else 'RL'
        if relation.get('direction') != direction:
            raise FigureError('columns_relation_direction', '声明方向与列位置不符')
        low, high = sorted((left, right), key=lambda p: p['x_pt'])
        corridor_left = low['x_pt'] + low['width_pt']
        corridor_right = high['x_pt']
        lane = corridor_left + (corridor_right-corridor_left)*(.35 if direction == 'LR' else .7)
        u = [a[i]+vectors[source_side][i]*ARROW_BOUNDARY_GAP for i in range(2)]
        v = [b[i]+vectors[target_side][i]*ARROW_BOUNDARY_GAP for i in range(2)]
        points = [a, u, [lane, u[1]], [lane, v[1]], v, b]
        compact = []
        for point in points:
            if not compact or math.dist(point, compact[-1]) > 1e-5:
                compact.append(point)
        if len(compact) < 2 or math.dist(a, b) < 1e-5:
            raise FigureError('columns_relation_anchor_overlap', '跨列关系锚点重合')
        ident = 'relation:' + relation['id']
        if any(segment_hits(p, q, node['rect']) for p, q in zip(compact, compact[1:]) for node in scene.nodes):
            raise FigureError('columns_relation_crosses_node', '跨列连线穿过节点', relation=relation['id'])
        scene.line(ident, compact, arrow=True, exact_terminal=True, endpoint_nodes=[source_id, target_id])
        records.append({'id': relation['id'], 'source': copy.deepcopy(source), 'target': copy.deepcopy(target), 'direction': direction, 'geometry': 'orthogonal', 'points_pt': compact})
    for relation in relations:
        if not relation.get('label'):
            continue
        ident = 'relation:' + relation['id']
        path = next(path for path in scene.paths if path['id'] == ident)
        m = scene.registry.measure(relation['label'], scene.size)
        chosen = None
        for a, b in sorted(zip(path['points'], path['points'][1:]), key=lambda pair: math.dist(*pair), reverse=True):
            if abs(a[0]-b[0]) < 1e-5:
                candidates = [((a[0]+b[0])/2+sign*(m['width']/2+3.3), (a[1]+b[1])/2) for sign in (1, -1)]
            else:
                candidates = [((a[0]+b[0])/2, (a[1]+b[1])/2+sign*(m['height']/2+3.3)) for sign in (-1, 1)]
            for x, y in candidates:
                box = [x-m['width']/2, y-m['height']/2, x+m['width']/2, y+m['height']/2]
                if box[0] < .5 or box[1] < .5 or box[2] > scene.width-.5 or box[3] > scene.height-.5:
                    continue
                if any(intersects(box, node['rect'], .5) for node in scene.nodes) or any(intersects(box, text['position']['bbox'], .5) for text in scene.texts):
                    continue
                if any(segment_hits(p, q, box, .4) for item in scene.paths for p, q in zip(item['points'], item['points'][1:])):
                    continue
                chosen = (x, y)
                break
            if chosen is not None:
                break
        if chosen is None:
            raise FigureError('columns_relation_label_capacity', '跨列关系标签无安全版位', relation=relation['id'])
        scene.text(ident+':label', relation['label'], *chosen, owner=ident, role='edge-label')
    issues = audit_scene(scene)
    if issues:
        raise FigureError('columns_relation_geometry', '跨列关系公共几何审计失败', issues=issues)
    return records


def columns(spec, registry, size):
    """Pack independent flows, drawing only explicitly declared cross-column relations."""
    column_specs = spec.get("columns", [])
    if not column_specs:
        raise FigureError("columns_empty", "多列流程至少需要一列")
    prefixes = [column.get("id") for column in column_specs]
    if any(not isinstance(prefix, str) or not prefix for prefix in prefixes):
        raise FigureError("column_id", "每列必须有非空字符串ID")
    if len(prefixes) != len(set(prefixes)):
        raise FigureError("column_duplicate_id", "列ID重复")
    direction = spec.get("direction", "LR")
    if direction not in ("LR", "TB"):
        raise FigureError("columns_direction", "多列流程方向必须LR或TB")

    relations = [relation for relation in spec.get('relations', []) if relation.get('type') == 'cross-column']
    if relations and direction != 'LR':
        raise FigureError('columns_relation_layout', '跨列关系目前只支持左右布局')
    from .layouts import primitive
    children = []
    for column in column_specs:
        match column.get('kind', 'graph'):
            case 'graph': children.append(graph(column, registry, size))
            case 'scene': children.append(primitive(column, registry, size))
            case _: raise FigureError('columns_child_kind', '子列仅支持graph或scene')
    scale = size / 8
    outer_margin = 0
    column_gap = max(ARROW_BOUNDARY_GAP, 12 * scale)
    if relations:
        label_width = max([registry.measure(r['label'], size)['width'] for r in relations if r.get('label')] + [0])
        column_gap = max(column_gap, 4*ARROW_BOUNDARY_GAP+2*label_width+12)
    title_gap = 6 * scale
    if relations:
        ink_tops = [n['rect'][1]-n['width']/2 for child in children for n in child.nodes]
        ink_tops += [t['position']['bbox'][1] for child in children for t in child.texts]
        ink_tops += [min(p[1] for p in path['points'])-path['width']/2 for child in children for path in child.paths]
        ink_tops += [asset['rect'][1] for child in children for asset in child.assets]
        for relation in relations:
            for endpoint in (relation['source'], relation['target']):
                if endpoint.get('port') != 'top' or endpoint.get('column') not in prefixes: continue
                child = children[prefixes.index(endpoint['column'])]
                node = next((n for n in child.nodes if n['id'] == endpoint.get('node')), None)
                if node is not None: ink_tops.append(node['rect'][1]-ARROW_BOUNDARY_GAP-.25)
        title_gap = 3-min(ink_tops)
    title_measurements = [registry.measure(column["title"], size) if column.get("title") else None for column in column_specs]
    scene = Scene(registry, size)
    scene.template = "independent-graph-columns"
    placements = []
    if direction == "LR":
        title_height = max([measurement["height"] for measurement in title_measurements if measurement is not None] + [0])
        content_y = outer_margin + (title_height + title_gap if title_height else 0)
        x = outer_margin
        for column, child, title_measurement in zip(column_specs, children, title_measurements):
            prefix = column["id"]
            if title_measurement is not None:
                scene.text(f"column:{prefix}:title", column["title"], x + child.width / 2, outer_margin + title_height / 2, role="column-title")
            _append_child(scene, child, prefix, x, content_y)
            placements.append({"id": prefix, "x_pt": x, "y_pt": content_y, "width_pt": child.width, "height_pt": child.height})
            x += child.width + column_gap
        width = x - column_gap + outer_margin
        height = content_y + max(child.height for child in children) + outer_margin
    else:
        content_width = max(child.width for child in children)
        y = outer_margin
        for column, child, title_measurement in zip(column_specs, children, title_measurements):
            prefix = column["id"]
            x = outer_margin + (content_width - child.width) / 2
            if title_measurement is not None:
                scene.text(f"column:{prefix}:title", column["title"], outer_margin + content_width / 2, y + title_measurement["height"] / 2, role="column-title")
                y += title_measurement["height"] + title_gap
            _append_child(scene, child, prefix, x, y)
            placements.append({"id": prefix, "x_pt": x, "y_pt": y, "width_pt": child.width, "height_pt": child.height})
            y += child.height + column_gap
        width = content_width + 2 * outer_margin
        height = y - column_gap + outer_margin
    scene.finish(width, height)
    scopes = _scopes(scene, column_specs) if relations else {}
    relation_records = _relations(scene, relations, placements, scopes) if relations else []
    scene.notes = copy.deepcopy(spec.get("relations", []))
    scene.layout_evidence = {
        "layout_algorithm": "independent-graphs-top-aligned-columns",
        "direction": direction,
        "column_gap_pt": column_gap,
        "outer_margin_pt": outer_margin,
        "title_gap_pt": title_gap if any(measurement is not None for measurement in title_measurements) else 0,
        "columns": placements,
        "cross_column_edges": len(relation_records),
        "relations_recorded_as_notes": len(scene.notes),
        "design_font_size_pt": size,
        "global_optimum_proven": False,
    }
    if relation_records:
        scene.layout_evidence['cross_column_bindings'] = relation_records
        scene.layout_evidence['scope_anchor_relayout'] = 'source relations share a real loop scope; distinct declared fractions prevent collinear overlap'
        scene.layout_evidence['source_curve_relayout'] = 'source curves replaced by orthogonal corridor paths; source pixel geometry is not preserved'
    return scene.finish(width, height)

