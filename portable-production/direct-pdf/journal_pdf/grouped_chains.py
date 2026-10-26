"""Bounded measured two-container chains; not a general clustered-graph solver."""
from __future__ import annotations

import math

from .common import FigureError
from .editorial import (PAD_X, PAD_Y, COMPACT_GAP, LABEL_CLEARANCE, ARROW_DEPTH,
                        ARROW_BOUNDARY_GAP, STROKE, EXPORT_PAD, display_content)
from .fonts import position_text
from .scene import Scene, port, audit_scene, validate_node_dash


def validate_grouped_chains(spec):
    def need(ok, message):
        if not ok:
            raise FigureError('grouped_chains_unsupported', message)
    groups = spec.get('groups')
    nodes, edges = spec.get('nodes', []), spec.get('edges', [])
    need(isinstance(groups, list) and len(groups) == 2, '仅支持两个上下排列的明确容器')
    need(isinstance(nodes, list) and 2 <= len(nodes) <= 80 and isinstance(edges, list), '节点/连接预算无效')
    ids = [n.get('id') for n in nodes]
    need(all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)), '节点ID无效或重复')
    need(all(n.get('shape', 'rectangle') == 'rectangle' for n in nodes), '当前分组链仅支持普通矩形，不改写源形状')
    members = []
    for group in groups:
        need(isinstance(group, dict) and {'id', 'title', 'direction', 'nodes'} <= set(group) <= {'id', 'title', 'direction', 'nodes', 'dash'}, '分组仅接受ID、原文标题、方向、成员和可选源线型')
        if 'dash' in group:
            need(group['dash'] is not None, '显式虚线样式必须为有效数列；实线须省略dash')
            validate_node_dash(group['dash'], id=group['id'])
        need(isinstance(group['id'], str) and group['id'] and group['id'] not in ids, '容器ID无效或与节点冲突')
        need(group['direction'] in ('LR', 'RL') and isinstance(group['nodes'], list) and group['nodes'], '需明确非空有序链及LR/RL方向')
        need(all(isinstance(i, str) and i in ids for i in group['nodes']), '分组引用未知节点')
        members += group['nodes']
    need(groups[0]['id'] != groups[1]['id'] and len(members) == len(set(members)), '容器ID或成员重复')
    need(groups[0]['direction'] != groups[1]['direction'], '当前仅支持反向的两条水平链')
    side = 'right' if groups[0]['direction'] == 'LR' else 'left'
    bridge = spec.get('bridge')
    if bridge is not None:
        need(isinstance(bridge, dict) and set(bridge) == {'node', 'side'}, '桥接只接受一个外部节点及侧向')
        need(bridge['node'] in ids and bridge['node'] not in members and bridge['side'] == side, '桥接节点必须在链的外向侧且不属于容器')
        members.append(bridge['node'])
    need(set(members) == set(ids), '所有节点必须属于两条链或唯一外部桥接节点')
    expected = [(a, b) for g in groups for a, b in zip(g['nodes'], g['nodes'][1:])]
    ends = [groups[0]['nodes'][-1], groups[1]['nodes'][0]]
    connection = [ends[0], bridge['node'], ends[1]] if bridge else ends
    expected += list(zip(connection, connection[1:]))
    need(all(isinstance(e, dict) and not set(e) - {'id', 'from', 'to', 'label', 'arrow', 'return_edge', 'dash'}
             and e.get('arrow', True) is True for e in edges), '仅支持明确单向链边；不接受自定端口、双箭头或几何字段')
    actual = [(e.get('from'), e.get('to')) for e in edges]
    need(len(actual) == len(expected) and set(actual) == set(expected), '连接须精确保持有序链与跨组桥接；不补边、删边或反转')
    edge_ids = [e.get('id', 'edge-' + str(i + 1)) for i, e in enumerate(edges)]
    need(len(edge_ids) == len(set(edge_ids)), '连接ID重复')
    return side


def grouped_chains(spec, reg, size):
    side = validate_grouped_chains(spec)
    scale = size / 8
    px, py = PAD_X * scale, PAD_Y * scale
    clear, compact = LABEL_CLEARANCE * scale, COMPACT_GAP * scale
    margin = STROKE / 2 + EXPORT_PAD
    nodes = {n['id']: n for n in spec['nodes']}
    edges = {(e['from'], e['to']): dict(e, id=e.get('id', 'edge-' + str(i + 1)))
             for i, e in enumerate(spec['edges'])}
    measured = {i: reg.measure(display_content(n['text']), size) for i, n in nodes.items()}
    labels = {e['id']: reg.measure(display_content(e['label'], 'edge-label'), size)
              for e in edges.values() if e.get('label')}
    dimensions = {i: (m['width'] + 2 * px, m['height'] + 2 * py) for i, m in measured.items()}
    rows = []
    for group in spec['groups']:
        members = group['nodes']
        local_edges = [edges[a, b] for a, b in zip(members, members[1:])]
        gaps = [max(ARROW_BOUNDARY_GAP, labels[e['id']]['width'] + 2 * clear + ARROW_DEPTH)
                if e['id'] in labels else ARROW_BOUNDARY_GAP for e in local_edges]
        title = reg.measure(display_content(group['title']), size)
        label_h = max([labels[e['id']]['height'] for e in local_edges if e['id'] in labels] + [0])
        height = max(dimensions[i][1] for i in members)
        width = sum(dimensions[i][0] for i in members) + sum(gaps)
        center = py + title['height'] + compact + (label_h + clear if label_h else 0) + height / 2
        rows.append(dict(group=group, edges=local_edges, gaps=gaps, title=title, node_h=height,
                         row_w=width, width=max(width + 2 * px, title['width'] + 2 * px),
                         center=center, height=center + height / 2 + py))
    group_width = max(r['width'] for r in rows)
    bridge = spec.get('bridge')
    bridge_height = dimensions[bridge['node']][1] if bridge else 0
    envelope_delta = rows[0]['height'] - rows[0]['center'] + compact + rows[1]['center']
    bridge_delta = bridge_height + 2 * ARROW_BOUNDARY_GAP if bridge else 0
    delta = max(envelope_delta, bridge_delta)
    row_centers = [margin + rows[0]['center'], margin + rows[0]['center'] + delta]
    chain_pairs = {(a, b) for g in spec['groups'] for a, b in zip(g['nodes'], g['nodes'][1:])}
    cross_edges = [e for pair, e in edges.items() if pair not in chain_pairs]
    outside_label_w = max([labels[e['id']]['width'] for e in cross_edges if e['id'] in labels] + [0])
    # The outside horizontal slots must contain labels without intersecting the frame.
    corridor = max(ARROW_BOUNDARY_GAP, outside_label_w + 2 * clear)
    channel_x = margin + group_width + corridor
    bridge_half_width = dimensions[bridge['node']][0] / 2 if bridge else 0
    # Keep the external node completely outside both frame envelopes.
    channel_x = max(channel_x, margin + group_width + compact + bridge_half_width)
    width = channel_x + bridge_half_width + margin
    height = row_centers[1] - rows[1]['center'] + rows[1]['height'] + margin
    scene = Scene(reg, size)
    scene.template = 'measured-grouped-chains'
    placed = {}
    records = []

    def draw_edge(edge, points, label_position=None):
        exact = not edge.get('label')
        if exact:
            previous, target = points[-2:]
            length = math.dist(previous, target)
            if length > ARROW_BOUNDARY_GAP:
                stub = [target[i] + (previous[i] - target[i]) * ARROW_BOUNDARY_GAP / length for i in range(2)]
                points = [*points[:-1], stub, target]
        scene.line(edge['id'], points, arrow=True, endpoint_nodes=[edge['from'], edge['to']],
                   dash=edge.get('dash'), exact_terminal=exact)
        if edge['id'] in labels:
            scene.text(edge['id'] + ':label', edge['label'], *label_position, role='edge-label')
        records.append({'edge': edge['id'], 'from': edge['from'], 'to': edge['to'],
                        'return_edge': bool(edge.get('return_edge')), 'geometry': 'orthogonal'})

    for row, cy in zip(rows, row_centers):
        group = row['group']
        gy = cy - row['center']
        scene.shape(group['id'], [margin, gy, margin + group_width, gy + row['height']], container=True, dash=group.get('dash'))
        scene.text(group['id'] + ':title', group['title'], margin + group_width / 2,
                   gy + py + row['title']['height'] / 2, owner=group['id'])
        # Build canonical upper LR/lower RL geometry; mirror the full result for left bridge.
        physical_order = group['nodes'] if row is rows[0] else list(reversed(group['nodes']))
        x = margin + group_width - px - row['row_w']
        gaps = row['gaps'] if row is rows[0] else list(reversed(row['gaps']))
        measurement_group = group['id'] + ':row'
        scene.measurement_groups[measurement_group] = {'axis': 'row', 'nodes': list(group['nodes'])}
        for j, identifier in enumerate(physical_order):
            w = dimensions[identifier][0]
            placed[identifier] = scene.box(identifier, nodes[identifier]['text'], x, cy - row['node_h'] / 2, w, row['node_h'])
            placed[identifier]['measurement_contract'] = {'mode': 'measured-group', 'group': measurement_group,
                                                          'axis': 'row', 'expected_wh': [w, row['node_h']]}
            x += w + (gaps[j] if j < len(gaps) else 0)
        for edge in row['edges']:
            source_side, target_side = ('right', 'left') if row is rows[0] else ('left', 'right')
            a, b = port(placed[edge['from']], source_side), port(placed[edge['to']], target_side)
            m = labels.get(edge['id'])
            pos = ((a[0] + b[0]) / 2, cy - row['node_h'] / 2 - clear - m['height'] / 2) if m else None
            draw_edge(edge, [a, b], pos)
    a = port(placed[spec['groups'][0]['nodes'][-1]], 'right')
    b = port(placed[spec['groups'][1]['nodes'][0]], 'right')
    if bridge:
        identifier = bridge['node']
        bw, bh = dimensions[identifier]
        mid = (row_centers[0] + row_centers[1]) / 2
        placed[identifier] = scene.box(identifier, nodes[identifier]['text'], channel_x - bw / 2, mid - bh / 2, bw, bh)
        routes = [[a, [channel_x, a[1]], port(placed[identifier], 'top')],
                  [port(placed[identifier], 'bottom'), [channel_x, b[1]], b]]
        pairs = [(spec['groups'][0]['nodes'][-1], identifier), (identifier, spec['groups'][1]['nodes'][0])]
    else:
        routes = [[a, [channel_x, a[1]], [channel_x, b[1]], b]]
        pairs = [(spec['groups'][0]['nodes'][-1], spec['groups'][1]['nodes'][0])]
    for j, (pair, points) in enumerate(zip(pairs, routes)):
        edge = edges[pair]
        m = labels.get(edge['id'])
        line_y = a[1] if j == 0 else b[1]
        pos = ((margin + group_width + channel_x) / 2,
               line_y + (-1 if j == 0 else 1) * (clear + m['height'] / 2)) if m else None
        draw_edge(edge, points, pos)
    if side == 'left':
        for node in scene.nodes:
            x0, y0, x1, y1 = node['rect']
            node['rect'] = [width - x1, y0, width - x0, y1]
        for text in scene.texts:
            text['x'] = width - text['x']
            text['position'] = position_text(text['measurement'], text['x'], text['y'], text['align'])
        for path in scene.paths:
            path['points'] = [[width - x, y] for x, y in path['points']]
    # Final page bounds come from the complete ink envelope, including outside labels.
    rectangles = [n['rect'] for n in scene.nodes] + [t['position']['bbox'] for t in scene.texts]
    left = min(r[0] for r in rectangles)
    top = min(r[1] for r in rectangles)
    dx, dy = max(0, margin - left), max(0, margin - top)
    width = max(width, max(r[2] for r in rectangles) + margin) + dx
    height = max(height, max(r[3] for r in rectangles) + margin) + dy
    if dx or dy:
        for node in scene.nodes:
            node['rect'] = [v + (dx if i % 2 == 0 else dy) for i, v in enumerate(node['rect'])]
        for text in scene.texts:
            text['x'] += dx
            text['y'] += dy
            text['position'] = position_text(text['measurement'], text['x'], text['y'], text['align'])
        for path in scene.paths:
            path['points'] = [[x + dx, y + dy] for x, y in path['points']]
    scene.layout_evidence = {'layout_algorithm': 'bounded-two-group-measured-chains',
        'design_font_size_pt': size, 'global_optimum_proven': False, 'source_semantics_review_required': True,
        'group_styles': [{'id': group['id'], 'pattern_space': 'design-pt', 'dash_pt': list(group['dash']) if 'dash' in group else None,
                          'basis': spec.get('group_style_bindings', {}).get(group['id'],
                              {'method': 'reviewed-declaration' if 'dash' in group else 'solid-default',
                               'mechanically_verified': False})} for group in spec['groups']],
        'edge_bindings': records, 'group_width_pt': group_width, 'bridge_side': side,
        'constraints': {'group_envelope_delta_pt': envelope_delta, 'bridge_delta_pt': bridge_delta,
                        'chosen_row_center_delta_pt': delta, 'outside_label_width_pt': outside_label_w,
                        'outside_corridor_pt': channel_x - margin - group_width},
        'group_envelopes': [{'id': r['group']['id'], 'row_width_pt': r['row_w'], 'height_pt': r['height'],
                             'title_ink_wh_pt': [r['title']['width'], r['title']['height']], 'edge_gaps_pt': r['gaps']} for r in rows]}
    scene.finish(width, height)
    issues = audit_scene(scene)
    if issues:
        raise FigureError('grouped_chains_no_feasible_layout', '测量约束布局未通过公共审计；不缩字号或手动挪单个对象', issues=issues)
    return scene
