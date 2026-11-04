"""Check rebuilt geometry against a separately hashed original-source contract."""
from __future__ import annotations

import json
from pathlib import Path

from .boundary_ports import BoundaryGeometry, parse_boundary_port
from .common import FigureError, digest_file, resolve_source


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FigureError('source_structure_schema', '关系合同包含重复字段', field=key)
        result[key] = value
    return result


def node_has_visible_ink(node) -> bool:
    """White paint on white is a possible occluder, not visible reference ink."""
    return not node.get('invisible', False) and (
        bool(node.get('width')) and node.get('gray', 0) < 1 or node.get('fill', 1) < 1)


def audit_source_structure(spec, scene, root: Path, bindings):
    """Resolve original ports from final geometry; candidate endpoint claims are not proof."""
    name = spec.get('source_structure_contract')
    registered = {b['path']: b['sha256'] for b in bindings if b['role'] == 'structure-contract'}
    required = spec.get('policy', {}).get('require_source_structure_contract', False)
    if not isinstance(required, bool):
        raise FigureError('source_structure_schema', '结构合同开关必须为布尔值')
    if name is None:
        if required or registered:
            raise FigureError('source_structure_missing', '已要求或登记结构合同，不能省略检查')
        return {'status': 'not-checked', 'path_count': 0, 'node_count': 0}
    if not isinstance(name, str) or name not in registered:
        raise FigureError('source_structure_unbound', '结构合同必须独立登记并绑定哈希')
    path = resolve_source(root, name)
    if digest_file(path) != registered[name]:
        raise FigureError('source_structure_changed', '结构合同发生变化')
    try:
        contract = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise FigureError('source_structure_schema', '结构合同不是有效JSON') from error
    keys = {'version', 'source_sha256', 'nodes', 'paths'}
    if (not isinstance(contract, dict) or set(contract) not in (keys, keys | {'relations'})
            or type(contract['version']) is not int or contract['version'] != 1
            or not isinstance(contract['source_sha256'], str)):
        raise FigureError('source_structure_schema', '结构合同须为version 1及明确的原件/节点/线清单')
    originals = {b['sha256'] for b in bindings if b['role'] == 'original-artwork'}
    if contract['source_sha256'] not in originals:
        raise FigureError('source_structure_original_unbound', '关系合同未绑定登记的原始图源')
    nodes = {n['id']: n for n in scene.nodes}
    paths = {p['id']: p for p in scene.paths}
    for kind, actual in (('nodes', nodes), ('paths', paths)):
        expected = contract[kind]
        if not isinstance(expected, dict):
            raise FigureError('source_structure_schema', '节点及线清单须为ID映射')
        if set(expected) != set(actual):
            raise FigureError('source_structure_inventory', '重绘对象与独立来源清单不一致', kind=kind,
                              missing=sorted(set(expected)-set(actual)), extra=sorted(set(actual)-set(expected)))
    for ident, expected in contract['nodes'].items():
        if (not isinstance(expected, dict) or set(expected) != {'shape', 'visible'}
                or not isinstance(expected['shape'], str) or not isinstance(expected['visible'], bool)):
            raise FigureError('source_structure_schema', '节点须声明形状和是否有可见框')
        actual = nodes[ident]
        visible = node_has_visible_ink(actual)
        if actual['kind'] != expected['shape'] or visible != expected['visible']:
            raise FigureError('source_structure_node_changed', '节点形状或可见框改变', id=ident)
    geometry = BoundaryGeometry(nodes={key: tuple(n['rect']) for key, n in nodes.items()}, assets={}, paths={})
    for ident, expected in contract['paths'].items():
        if (not isinstance(expected, dict) or set(expected) != {'from', 'to', 'arrow', 'line'}
                or expected['arrow'] not in ('none', 'end', 'both')
                or expected['line'] not in ('solid', 'dashed')):
            raise FigureError('source_structure_schema', '线须声明起终点、箭头方向及实虚线')
        actual = paths[ident]
        if actual.get('closed') or actual.get('fill') is not None:
            raise FigureError('source_structure_line_changed', '来源连线不能替换成闭合或填充图形', id=ident)
        arrow = 'both' if actual['both'] else 'end' if actual['arrow'] else 'none'
        if arrow != expected['arrow'] or bool(actual['dash']) != (expected['line'] == 'dashed'):
            raise FigureError('source_structure_line_changed', '连线方向、双向属性或实虚线改变', id=ident)
        ends = [expected['from'], expected['to']]
        if ends == [None, None] and arrow == 'none':
            continue  # Explicit independent separator, still counted and style-checked.
        for endpoint, point, adjacent in zip(ends, (actual['points'][0], actual['points'][-1]),
                                             (actual['points'][1], actual['points'][-2])):
            try:
                port = parse_boundary_port(endpoint)
                if port.target_kind != 'node' or port.target_id not in nodes:
                    raise FigureError('source_structure_port', '当前合同只接受真实节点端口')
                if nodes[port.target_id]['kind'] != 'rectangle' and port.fraction != .5:
                    raise FigureError('source_structure_port', '非矩形仅支持中点端口，不能以包围盒冒充曲边')
                matched = geometry.matches(endpoint, tuple(point), tuple(adjacent))
            except FigureError as error:
                raise FigureError('source_structure_port', '来源端口无法核验', id=ident, reason=error.code) from error
            if not matched:
                raise FigureError('source_structure_endpoint_changed', '实际连线端点不符合原图关系', id=ident,
                                  expected=endpoint, actual=point)
    relations = contract.get('relations', [])
    if not isinstance(relations, list):
        raise FigureError('source_structure_schema', '相对位置约束须为列表')
    relation_evidence = []
    for relation in relations:
        if (not isinstance(relation, dict) or set(relation) != {'type', 'axis', 'paths'}
                or relation['type'] != 'path_order' or relation['axis'] not in ('x', 'y')):
            raise FigureError('source_structure_schema', '仅支持明确轴向的path_order约束')
        identifiers = relation['paths']
        if (not isinstance(identifiers, list) or len(identifiers) < 2
                or not all(isinstance(key, str) and key in paths for key in identifiers)
                or len(set(identifiers)) != len(identifiers)):
            raise FigureError('source_structure_schema', '顺序约束须引用至少两条不同的真实线')
        axis = 0 if relation['axis'] == 'x' else 1
        bands = [(min(p[axis] for p in paths[key]['points']), max(p[axis] for p in paths[key]['points']))
                 for key in identifiers]
        gaps = [after[0] - before[1] for before, after in zip(bands, bands[1:])]
        if any(gap <= 1e-4 for gap in gaps):
            raise FigureError('source_structure_relation_changed', '独立线条重合、顺序颠倒或跨越原定层级',
                              paths=identifiers, axis=relation['axis'], gaps_pt=gaps)
        relation_evidence.append({'type': 'path_order', 'paths': identifiers, 'axis': relation['axis'], 'gaps_pt': gaps})
    return {'status': 'checked', 'contract_sha256': registered[name], 'source_sha256': contract['source_sha256'],
            'node_count': len(nodes), 'path_count': len(paths), 'node_ids': sorted(nodes), 'path_ids': sorted(paths),
            'visible_node_ids': sorted(key for key, node in contract['nodes'].items() if node['visible']),
            'relation_count': len(relations), 'relations': relation_evidence,
            'scope': 'complete-node/path-inventory, node-shapes, line-directions/styles, node-port-geometry, declared relative path order'}
