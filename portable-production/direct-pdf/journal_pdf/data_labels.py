"""Conservative source-bound SVG series labels for dense plots."""
from __future__ import annotations

import math
import re
from pathlib import Path

from lxml import etree as ET

from .assets import element, svg_root
from .common import FigureError

_SVG = '{http://www.w3.org/2000/svg}'
_ZERO_ROTATION = re.compile(r'rotate\(\s*-?0(?:\.0+)?(?:[\s,]+-?[\d.]+){0,2}\s*\)')


def _fail(message: str) -> None:
    raise FigureError('data_label_binding_invalid', message)


def _color(node, key: str) -> str:
    for entry in node.get('style', '').split(';'):
        parts = entry.split(':', 1)
        if len(parts) == 2 and parts[0].strip() == key:
            return parts[1].strip().lower()
    return (node.get(key) or '').lower()


def _number(node, name: str) -> float:
    try:
        number = float(node.get(name))
    except (TypeError, ValueError) as error:
        raise FigureError('data_label_binding_invalid', '源点坐标缺失或无效') from error
    if not math.isfinite(number):
        _fail('源点坐标必须有限')
    return number


def validate_data_label_bindings(scene, bindings):
    """Bind numeric scene labels to a same-color source SVG series marker.

    Supports direct SVG marker uses and direct source text x coordinates only.
    Unsupported or ambiguous sources fail closed; this is not visual approval.
    """
    if not isinstance(bindings, list) or not bindings:
        _fail('数据标签绑定必须是非空数组')
    assets = {row['id']: row for row in scene.assets}
    texts = {row['id']: row for row in scene.texts}
    seen_labels, seen_sources, evidence = set(), set(), []
    cache = {}
    for row in bindings:
        if not isinstance(row, dict) or set(row) != {'text_id', 'asset_id', 'source_label_id', 'marker_index'}:
            _fail('数据标签绑定字段不完整或未知')
        text_id, asset_id, source_id, index = (row['text_id'], row['asset_id'], row['source_label_id'], row['marker_index'])
        if not all(isinstance(v, str) and v for v in (text_id, asset_id, source_id)) or type(index) is not int or index < 0:
            _fail('数据标签或源点标识无效')
        if text_id in seen_labels or (asset_id, source_id) in seen_sources:
            _fail('数据标签或源标签重复绑定')
        seen_labels.add(text_id); seen_sources.add((asset_id, source_id))
        if text_id not in texts or asset_id not in assets:
            _fail('数据标签或源系列资产不存在')
        placement = assets[asset_id]; asset = placement['asset']; receipt = asset.audit
        if receipt.get('mode') != 'source-svg-group':
            _fail('数据标签需要已绑定源SVG系列资产')
        source = Path(asset.source_path)
        if source not in cache:
            cache[source] = svg_root(source)
        root = cache[source]
        view = root.get('viewBox', '').replace(',', ' ').split()
        try:
            view_values = [float(v) for v in view]
            dimensions = [float(re.fullmatch(r'([\d.]+)pt', root.get(k, '')).group(1)) for k in ('width','height')]
        except (AttributeError, ValueError):
            _fail('源SVG坐标到PDF坐标的比例未明确')
        if (len(view_values) != 4 or view_values[:2] != [0,0] or dimensions != view_values[2:]
                or not all(math.isfinite(v) and v > 0 for v in dimensions)):
            _fail('仅支持无偏移、以pt为单位的源SVG坐标')
        if root.get('transform') or re.search(r'(?:^|;)\s*transform\s*:', root.get('style',''), re.I):
            _fail('源SVG根变换未受支持')
        for sheet in root.xpath('//*[local-name()="style"]'):
            style = re.fullmatch(r'\s*\*\s*\{([^{}]*)\}\s*', sheet.text or '')
            if not style:
                _fail('源SVG样式表使系列身份不明确')
            for declaration in style.group(1).split(';'):
                if not declaration.strip():
                    continue
                pair = declaration.split(':', 1)
                if len(pair) != 2 or pair[0].strip() not in {'stroke-linejoin', 'stroke-linecap'} or '!important' in pair[1].lower():
                    _fail('源SVG样式表使系列身份不明确')
        series = element(root, receipt['source_group'])
        markers = series.findall('.//'+_SVG+'use')
        if index >= len(markers):
            _fail('源系列中不存在指定点')
        marker = markers[index]
        for node in [marker, *marker.iterancestors()]:
            if node is root:
                break
            if node.get('transform') or re.search(r'(?:^|;)\s*transform\s*:', node.get('style',''), re.I):
                _fail('源系列含未验证的坐标变换')
        original = element(root, source_id)
        if ET.QName(original).localname != 'g':
            _fail('源标签必须是明确的SVG文本组')
        labels = original.findall('.//'+_SVG+'text')
        if len(labels) != 1 or len(labels[0]):
            _fail('源标签必须是单个未拆分文本')
        label = labels[0]
        transform = label.get('transform', '')
        if (transform and not _ZERO_ROTATION.fullmatch(transform)) or re.search(r'(?:^|;)\s*transform\s*:', label.get('style',''), re.I):
            _fail('源标签变换未受支持')
        if any(node.get('transform') for node in original.iterancestors() if node is not root):
            _fail('源标签祖先变换未受支持')
        raw = ''.join(label.itertext()).strip()
        if raw != texts[text_id]['measurement']['text']:
            _fail('目标数值与源标签不一致')
        mx, my = _number(marker, 'x'), _number(marker, 'y')
        if abs(_number(label, 'x')-mx) > 1e-4:
            _fail('源标签横坐标与指定系列点不一致')
        if abs(_number(label, 'y')-my) > 20:
            _fail('源标签纵坐标离指定点过远')
        if sum(abs(_number(candidate, 'x')-mx) <= 1e-4 for candidate in markers) != 1:
            _fail('同系列同横坐标存在多个点，无法确定归属')
        line = series.find(_SVG+'path')
        if (line is None or not _color(line, 'stroke') or _color(line, 'stroke') != _color(label, 'fill')
                or _color(marker, 'fill') != _color(line, 'stroke')):
            _fail('源标签与系列颜色身份无法确认')
        for other in root.findall('.//'+_SVG+'g'):
            other_line = other.find(_SVG+'path')
            if other is series or other_line is None or _color(other_line, 'stroke') != _color(line, 'stroke'):
                continue
            for candidate in other.findall('.//'+_SVG+'use'):
                try:
                    duplicate_x = abs(float(candidate.get('x'))-mx) <= 1e-4
                except (TypeError, ValueError):
                    continue
                if duplicate_x:
                    _fail('同色系列在相同横坐标上使数值归属不明确')
        clip = receipt['source_clip']; target = placement['rect']
        if not (clip[0] <= mx <= clip[2] and clip[1] <= my <= clip[3]):
            _fail('源系列点不在保留的绘图区')
        px = target[0]+(mx-clip[0])/(clip[2]-clip[0])*(target[2]-target[0])
        py = target[1]+(my-clip[1])/(clip[3]-clip[1])*(target[3]-target[1])
        box = texts[text_id]['position']['bbox']
        if not (target[0] <= box[0] <= box[2] <= target[2] and target[1] <= box[1] <= box[3] <= target[3]):
            _fail('目标数值必须完整位于绘图区内')
        dx = max(box[0]-px, 0, px-box[2]); dy = max(box[1]-py, 0, py-box[3])
        if math.hypot(dx, dy) > 14 or abs((box[0]+box[2])/2-px) > 5:
            _fail('目标数值离源点过远或偏向相邻点')
        evidence.append({'text_id': text_id, 'asset_id': asset_id, 'source_label_id': source_id,
                         'source_group': receipt['source_group'], 'source_sha256': asset.source_hash,
                         'marker_index': index, 'source_marker': [mx,my],
                         'marker_target_pt': [px,py], 'target_bbox_pt': list(box),
                         'scope': 'declared direct SVG marker and same-color source label; design coordinates'})
    scene.layout_evidence['data_label_bindings'] = evidence
