"""Lock original route geometry independently of a candidate's topology claims.

Coordinates are reviewed source evidence, not extracted from the output being
checked. One declared source-to-design map is shared by every route; only the
compiler's recorded whole-artwork scale is composed with it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .common import FigureError, digest_file, resolve_source

# Match the existing endpoint audit's point-coordinate tolerance. This is not a
# layout clearance, and callers cannot relax it in their contract.
POINT_TOLERANCE_PT = .15
COLLINEAR_EPSILON_PT = 1e-7


def _schema(message):
    raise FigureError('source_route_schema', message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _schema('原图路线合同包含重复字段')
        result[key] = value
    return result


def _number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _matrix(value):
    if (not isinstance(value, dict) or set(value) != {'kind', 'matrix'}
            or value['kind'] not in ('uniform', 'affine')
            or not isinstance(value['matrix'], list) or len(value['matrix']) != 6
            or not all(_number(v) for v in value['matrix'])):
        _schema('全图变换须明确uniform/affine及六个有限矩阵数值')
    a, b, c, d, tx, ty = value['matrix']
    length = max(abs(a), abs(b), abs(c), abs(d))
    if not length or abs((a/length)*(d/length)-(b/length)*(c/length)) <= 1e-12:
        _schema('全图变换不得退化或不可逆')
    if value['kind'] == 'uniform' and (a <= 0 or d != a or b != 0 or c != 0):
        _schema('uniform仅允许正等比缩放和平移；其他变换须显式声明affine')
    return a, b, c, d, tx, ty


def _points(value):
    if (not isinstance(value, list) or len(value) < 2
            or any(not isinstance(p, (list, tuple)) or len(p) != 2
                   or not all(_number(v) for v in p) for p in value)):
        _schema('原图路线须包含至少两个有限二维坐标')
    points = [tuple(p) for p in value]
    if any(a == b for a, b in zip(points, points[1:])):
        _schema('原图路线不得包含零长度线段')
    return points


def _canonical(points):
    """Remove only forward collinear samples, never a reversal or a real bend."""
    result = []
    for point in points:
        while len(result) >= 2:
            a, b = result[-2:]
            u = (b[0]-a[0], b[1]-a[1])
            v = (point[0]-b[0], point[1]-b[1])
            length = math.hypot(*u)
            if (not length or u[0]*v[0]+u[1]*v[1] <= 0
                    or abs(u[0]*v[1]-u[1]*v[0])/length > COLLINEAR_EPSILON_PT):
                break
            result.pop()
        result.append(point)
    return result


def audit_source_routes(spec, scene, root: Path, bindings):
    """Fail closed on missing evidence, rerouting, or an unaccounted Scene path."""
    name = spec.get('source_route_contract')
    registered = {b['path']: b['sha256'] for b in bindings if b['role'] == 'route-contract'}
    required = spec.get('policy', {}).get('require_source_route_contract', False)
    if not isinstance(required, bool):
        _schema('原图路线合同开关必须为布尔值')
    if name is None:
        if required or registered:
            raise FigureError('source_route_missing', '已要求或登记原图路线合同，不能省略检查')
        return {'status': 'not-checked', 'route_count': 0, 'path_count': 0}
    if not isinstance(name, str) or name not in registered:
        raise FigureError('source_route_unbound', '原图路线合同须独立登记并绑定哈希')
    path = resolve_source(root, name)
    if digest_file(path) != registered[name]:
        raise FigureError('source_route_changed', '原图路线合同发生变化')
    try:
        contract = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise FigureError('source_route_schema', '原图路线合同不是有效JSON') from error
    if (not isinstance(contract, dict)
            or set(contract) != {'version', 'source_sha256', 'transform', 'routes'}
            or type(contract['version']) is not int or contract['version'] != 1
            or not isinstance(contract['source_sha256'], str)):
        _schema('原图路线合同须为version 1，绑定原件、全图变换及完整路线清单')
    originals = {b['sha256'] for b in bindings if b['role'] == 'original-artwork'}
    if contract['source_sha256'] not in originals:
        raise FigureError('source_route_original_unbound', '路线合同未绑定登记的original-artwork原件')
    a, b, c, d, tx, ty = _matrix(contract['transform'])
    scale = scene.layout_evidence.get('whole_artwork_scale')
    if not _number(scale) or not 0 < scale <= 1+1e-9:
        raise FigureError('source_route_scale_unproven', '缺少编译器记录的最终全图等比缩放证据')
    effective_matrix = [v*scale for v in (a, b, c, d, tx, ty)]

    def mapped(point):
        x, y = point
        result = ((a*x+c*y+tx)*scale, (b*x+d*y+ty)*scale)
        if not all(math.isfinite(v) for v in result):
            _schema('全图变换产生了非有限坐标')
        return result

    routes = contract['routes']
    if not isinstance(routes, dict) or not routes:
        _schema('原图路线须为非空的稳定ID映射')
    paths = {p['id']: p for p in scene.paths}
    used = set()
    measurements = []
    for ident, route in routes.items():
        if (not ident or not isinstance(route, dict)
                or set(route) != {'points', 'components', 'arrow', 'arrow_style', 'line'}
                or route['arrow'] not in ('none', 'end', 'both')
                or route['arrow_style'] not in ('standard', 'block-outline')
                or route['line'] not in ('solid', 'dashed')):
            _schema('每条路线须声明源坐标、输出路径顺序、箭头种类及实虚线')
        components = route['components']
        if (not isinstance(components, list) or not components
                or not all(isinstance(key, str) and key for key in components)
                or len(set(components)) != len(components)):
            _schema('路线输出路径须为非空、无重复且有序的ID列表')
        missing = sorted(set(components)-set(paths))
        if missing:
            raise FigureError('source_route_inventory', '原图路线缺少实际输出路径', id=ident, missing=missing)
        if route['arrow_style'] == 'block-outline' and (route['arrow'] == 'none' or len(components) != 1):
            _schema('轮廓块箭头只支持单条完整有向路径')
        observed = []
        for index, key in enumerate(components):
            actual = paths[key]
            # A split bidirectional route has the start head on its first path;
            # Scene has no start-only arrow, so only a single path supports both.
            if route['arrow'] == 'both' and len(components) != 1:
                _schema('双向箭头须使用单条完整路径')
            expected_arrow = route['arrow'] if index == len(components)-1 else 'none'
            actual_arrow = 'both' if actual.get('both') else 'end' if actual.get('arrow') else 'none'
            if (actual.get('closed') or actual.get('fill') is not None
                    or not actual.get('width') or actual.get('gray', 0) == 1
                    or actual_arrow != expected_arrow
                    or actual.get('arrow_style', 'standard') != route['arrow_style']
                    or bool(actual.get('dash')) != (route['line'] == 'dashed')):
                raise FigureError('source_route_style_changed', '原图路线箭头、方向、线型或可见描边改变', id=ident, path=key)
            points = _points(actual['points'])
            if observed:
                # Components represent literally shared ink, not permission to
                # bridge a gap or silently drop a displaced junction endpoint.
                if math.dist(observed[-1], points[0]) > COLLINEAR_EPSILON_PT:
                    raise FigureError('source_route_disconnected', '原图路线输出组件没有精确接续', id=ident, path=key)
                observed.extend(points[1:])
            else:
                observed.extend(points)
            used.add(key)
        expected = _canonical([mapped(p) for p in _points(route['points'])])
        observed = _canonical(observed)
        if len(expected) != len(observed):
            raise FigureError('source_route_bends_changed', '原图路线折角数或折返改变', id=ident,
                              expected_points=len(expected), actual_points=len(observed))
        deltas = [math.dist(p, q) for p, q in zip(expected, observed)]
        if max(deltas) > POINT_TOLERANCE_PT:
            raise FigureError('source_route_geometry_changed', '原图端点或折角偏离唯一全图变换', id=ident,
                              max_delta_pt=max(deltas), tolerance_pt=POINT_TOLERANCE_PT)
        for p, q, u, v in zip(expected, expected[1:], observed, observed[1:]):
            if (q[0]-p[0])*(v[0]-u[0])+(q[1]-p[1])*(v[1]-u[1]) <= 0:
                raise FigureError('source_route_direction_changed', '原图线段遍历方向改变', id=ident)
        measurements.append({'id': ident, 'components': components, 'bend_count': len(expected)-2,
                             'max_delta_pt': max(deltas), 'endpoints_and_bends_checked': True,
                             'direction_checked': True})
    if used != set(paths):
        raise FigureError('source_route_inventory', '实际输出存在未登记路线，不接受decorative豁免',
                          extra=sorted(set(paths)-used))
    return {'status': 'checked', 'contract_sha256': registered[name], 'source_sha256': contract['source_sha256'],
            'route_count': len(routes), 'path_count': len(paths), 'path_ids': sorted(paths),
            'transform': contract['transform'], 'whole_artwork_scale': scale,
            'effective_matrix': effective_matrix, 'point_tolerance_pt': POINT_TOLERANCE_PT,
            'routes': measurements,
            'scope': 'complete Scene path inventory, source endpoints/bends/traversal and arrow/line styles under one declared global transform; excludes source extraction, node identity, text and embedded asset routes'}
