"""Compact a proven reciprocal connection without changing its endpoints."""
from __future__ import annotations

from copy import deepcopy

from .common import FigureError, contains, intersects, segment_hits
from .editorial import ARROW_LENGTH
from .fonts import position_text


def _node_id(endpoint):
    return endpoint.get('node') if isinstance(endpoint, dict) else endpoint


def infer_container_bands(scene, nodes, containers, rows):
    """Recognise vertically stacked layers with an explicitly declared sub-row."""
    if not rows or len(containers) < 3:
        return []
    available = {item['id'] for item in containers}
    used = set()
    bands = []
    for row in rows:
        ids = row.get('containers', [])
        if len(ids) < 2 or any(i not in available or i in used for i in ids):
            raise FigureError('container_bands_ambiguous', '容器行无法明确绑定分层，请显式声明等宽层')
        used.update(ids)
        if any(abs(nodes[i]['rect'][1] - nodes[ids[0]]['rect'][1]) > 2 for i in ids):
            raise FigureError('container_bands_ambiguous', '并列容器顶边不一致，请显式声明等宽层')
        bands.append(list(ids))
    bands.extend([[i] for i in available - used])
    bands.sort(key=lambda band: nodes[band[0]]['rect'][1])
    if len(bands) < 2:
        return []
    left = nodes[bands[0][0]]['rect'][0]
    if any(abs(nodes[band[0]]['rect'][0] - left) > .15 for band in bands):
        raise FigureError('container_bands_ambiguous', '分层左边界不一致，请显式声明等宽层')
    if any(max(nodes[i]['rect'][3] for i in a) >= min(nodes[i]['rect'][1] for i in b) for a, b in zip(bands, bands[1:])):
        raise FigureError('container_bands_ambiguous', '分层上下重叠，请显式声明等宽层')
    owned = {i for c in containers for i in c.get('texts', [])}
    top = min(nodes[i]['rect'][1] for i in bands[0])
    right = max(nodes[band[-1]]['rect'][2] for band in bands)
    titles = [t['id'] for t in scene.texts if t['owner'] is None and t['id'] not in owned
              and t['y'] < top and left <= t['x'] <= right]
    if len(titles) > 1:
        raise FigureError('container_bands_ambiguous', '分层上方有多个独立文字，请显式指定标题')
    scene.layout_evidence.setdefault('inferred_container_bands', []).append({'bands': bands, 'titles': titles})
    return [{'bands': bands, 'titles': titles}]


def equal_width_container_bands(scene, nodes, declarations, containers, paths, connections, linked):
    """Equalise explicitly corresponding layer spans after compact placement."""
    groups = {c['id']: c for c in containers}
    safe_paths = {p for link in linked for p in link.get('paths', [])}
    for declaration in declarations:
        bands = declaration.get('bands')
        if not isinstance(bands, list) or len(bands) < 2 or any(not isinstance(b, list) or not b for b in bands):
            raise FigureError('container_bands_invalid', '等宽层须指定至少两层容器')
        ids = [i for band in bands for i in band]
        if len(ids) != len(set(ids)) or any(i not in groups or i not in nodes for i in ids):
            raise FigureError('container_bands_invalid', '等宽层须绑定不重复的紧凑容器')
        left = nodes[bands[0][0]]['rect'][0]
        if any(abs(nodes[band[0]]['rect'][0] - left) > .15 for band in bands):
            raise FigureError('container_bands_alignment', '等宽层左边界须对齐')
        width = max(nodes[band[-1]]['rect'][2] - left for band in bands)
        titles = declaration.get('titles', [])
        text_by_id = {text['id']: text for text in scene.texts}
        if not isinstance(titles, list) or len(titles) != len(set(titles)) or any(i not in text_by_id or text_by_id[i]['owner'] is not None for i in titles):
            raise FigureError('container_bands_title', '等宽层标题须绑定独立文字')
        for ident in titles:
            text = text_by_id[ident]
            text['x'] = left + width / 2
            text['position'] = position_text(text['measurement'], text['x'], text['y'], text['align'], text['position'].get('rotation', 0))
        for band in bands:
            extra = width - (nodes[band[-1]]['rect'][2] - left)
            if extra < .001:
                continue
            increment = extra / len(band)
            for index, ident in enumerate(band):
                decl, container = groups[ident], nodes[ident]
                members = set(decl.get('nodes', []))
                affected = members | {ident}
                if any(any(_node_id(e) in members or (_node_id(e) == ident and p.get('id') not in safe_paths) for e in (p.get('endpoint_nodes') or [])) for p in paths) or any(c.get('from') in affected or c.get('to') in affected for c in connections):
                    raise FigureError('container_bands_connected', '等宽层含未联动的连接，不能自动调整')
                shift, content_shift = index * increment, (index + .5) * increment
                container['rect'][0] += shift
                container['rect'][2] += shift + increment
                for node_id in members:
                    nodes[node_id]['rect'][0] += content_shift
                    nodes[node_id]['rect'][2] += content_shift
                explicit = set(decl.get('texts', []))
                for text in scene.texts:
                    if text['owner'] in members or text['id'] in explicit:
                        text['x'] += content_shift
                        text['position'] = position_text(text['measurement'], text['x'], text['y'], text['align'], text['position'].get('rotation', 0))
        scene.layout_evidence.setdefault('equal_width_container_bands', []).append({'bands': bands, 'width_pt': width})


def compact_container_rows(scene, nodes, rows, containers, paths, connections):
    """Move explicitly owned, unconnected container groups into compact rows."""
    declarations = {item['id']: item for item in containers}
    for row in rows:
        ids = row.get('containers')
        if not isinstance(ids, list) or len(ids) < 2 or len(set(ids)) != len(ids) or any(i not in declarations or i not in nodes for i in ids):
            raise FigureError('compact_container_row_invalid', '容器行须绑定至少两个已声明的紧凑容器')
        for left_id, right_id in zip(ids, ids[1:]):
            left, right = nodes[left_id], nodes[right_id]
            decl = declarations[right_id]
            owned = set(decl.get('nodes', [])) | {right_id}
            if any(_node_id(e) in owned for p in paths for e in (p.get('endpoint_nodes') or [])) or any(c.get('from') in owned or c.get('to') in owned for c in connections):
                raise FigureError('compact_container_row_connected', '待移动的容器组有连接，不能自动移动')
            desired = left['rect'][2] + 6 * scene.size / 8 + (left['width'] + right['width']) / 2
            delta = desired - right['rect'][0]
            moved = [right['rect'][0] + delta, right['rect'][1], right['rect'][2] + delta, right['rect'][3]]
            if any(n['id'] not in owned and intersects(moved, n['rect']) and not (n['container'] and contains(n['rect'], right['rect']) and contains(n['rect'], moved)) for n in scene.nodes):
                raise FigureError('compact_container_row_collision', '紧凑容器组与其他节点碰撞')
            if any(segment_hits(a, b, moved, .5) for p in paths for a, b in zip(p.get('points', []), p.get('points', [])[1:])):
                raise FigureError('compact_container_row_collision', '紧凑容器组与其他连线碰撞')
            for node_id in owned:
                nodes[node_id]['rect'][0] += delta
                nodes[node_id]['rect'][2] += delta
            explicit = set(decl.get('texts', []))
            for text in scene.texts:
                if text['owner'] in owned or text['id'] in explicit:
                    text['x'] += delta
                    text['position'] = position_text(text['measurement'], text['x'], text['y'], text['align'], text['position'].get('rotation', 0))
            scene.layout_evidence.setdefault('compact_container_rows', []).append({'left': left_id, 'right': right_id, 'gap_pt': 6 * scene.size / 8})


def compact_links(scene, nodes, declarations, paths, connections):
    paths = deepcopy(paths)
    by_id = {p.get('id'): p for p in paths}
    for item in declarations:
        anchor, target = nodes.get(item.get('anchor')), nodes.get(item.get('target'))
        ids = item.get('paths')
        if not anchor or not anchor['container'] or not target or target['container'] or not isinstance(ids, list) or len(ids) != 2 or len(set(ids)) != 2 or any(i not in by_id for i in ids):
            raise FigureError('compact_link_invalid', '紧凑连接须指定容器、普通目标及两条连接')
        refs = [p for p in paths if target['id'] in [_node_id(e) for e in (p.get('endpoint_nodes') or [])]]
        if {p['id'] for p in refs} != set(ids) or any(target['id'] in (c.get('from'), c.get('to')) for c in connections):
            raise FigureError('compact_link_attachments', '目标节点还有其他连接，不能自动移动')
        selected = [by_id[i] for i in ids]
        orientations = []
        for p in selected:
            endpoints = p.get('endpoint_nodes') or []
            points = p.get('points') or []
            if len(endpoints) != 2 or len(points) < 2 or not p.get('arrow') or p.get('both') or {_node_id(e) for e in endpoints} != {anchor['id'], target['id']} or any(abs(v[0] - points[0][0]) > .15 for v in points):
                raise FigureError('compact_link_topology', '仅支持两条独立的竖直反向连接')
            for e in endpoints:
                expected = 'bottom' if _node_id(e) == anchor['id'] else 'top'
                if not isinstance(e, dict) or e.get('side') != expected:
                    raise FigureError('compact_link_ports', '紧凑连接须明确容器底边和目标顶边端口')
            orientations.append(_node_id(endpoints[0]))
        if set(orientations) != {anchor['id'], target['id']}:
            raise FigureError('compact_link_topology', '两条连接须方向相反')
        old = target['rect'][:]
        top = anchor['rect'][3] + 12 * scene.size / 8
        if top > old[1] + .01:
            raise FigureError('compact_link_direction', '目标已过近或在容器内部，不能自动收紧')
        delta = top - old[1]
        moved = [old[0], old[1] + delta, old[2], old[3] + delta]
        if any(n['id'] not in (anchor['id'], target['id']) and intersects(moved, n['rect']) and
               (not n['container'] or not (contains(n['rect'], old) and contains(n['rect'], moved))) for n in scene.nodes):
            raise FigureError('compact_link_collision', '紧凑目标与其他节点碰撞')
        if any(segment_hits(a, b, moved, .5) for p in paths if p.get('id') not in ids
               for a, b in zip(p.get('points', []), p.get('points', [])[1:])):
            raise FigureError('compact_link_collision', '紧凑目标与其他连线碰撞')
        target['rect'] = moved
        for text in scene.texts:
            if text['owner'] == target['id']:
                text['y'] += delta
                text['position'] = position_text(text['measurement'], text['x'], text['y'], text['align'], text['position'].get('rotation', 0))
        for p in selected:
            x = p['points'][0][0]
            for e in p['endpoint_nodes']:
                n = nodes[_node_id(e)]
                e['fraction'] = (x - n['rect'][0]) / (n['rect'][2] - n['rect'][0])
                if not 0 <= e['fraction'] <= 1:
                    raise FigureError('compact_link_ports', '连接线不落在目标边界')
            start = top if _node_id(p['endpoint_nodes'][0]) == target['id'] else anchor['rect'][3]
            end = anchor['rect'][3] if start == top else top
            p['points'] = [[x, start], [x, end + (ARROW_LENGTH * scene.size / 8 if end < start else -ARROW_LENGTH * scene.size / 8)], [x, end]]
            p['exact_terminal'] = True
        scene.layout_evidence.setdefault('compact_links', []).append({'anchor': anchor['id'], 'target': target['id'], 'paths': ids, 'gap_pt': top - anchor['rect'][3]})
    return paths
