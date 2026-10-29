"""Verify a declared reconstructed plot frame against source SVG spines."""
from __future__ import annotations

import math
import re
from pathlib import Path

from lxml import etree as ET
from .assets import element, svg_root
from .common import FigureError

_LINE = re.compile(r'\s*M\s*([-+\d.eE]+)[ ,]+([-+\d.eE]+)\s*L\s*([-+\d.eE]+)[ ,]+([-+\d.eE]+)\s*')


def _fail(message):
    raise FigureError('source_plot_frame_invalid', message)


def validate_source_plot_frame(scene, binding):
    if not isinstance(binding, dict) or set(binding) != {'asset_id', 'frame_path_id', 'spine_ids'}:
        _fail('源绘图区绑定必须声明资产、框线和四条源坐标轴')
    if any(not isinstance(binding[k],str) or not binding[k] for k in ('asset_id','frame_path_id')):
        _fail('源资产和框线编号必须为非空字符串')
    ids = binding['spine_ids']
    if not isinstance(ids, list) or len(ids) != 4 or any(not isinstance(i,str) or not i for i in ids) or len(set(ids)) != 4:
        _fail('源绘图区须指定四条不同轴线')
    assets = {a['id']: a for a in scene.assets}
    paths = {p['id']: p for p in scene.paths}
    if binding['asset_id'] not in assets or binding['frame_path_id'] not in paths:
        _fail('源资产或绘图区框线不存在')
    placement = assets[binding['asset_id']]; asset = placement['asset']; receipt = asset.audit
    if receipt.get('mode') != 'source-svg-group':
        _fail('源绘图区绑定只支持已登记 SVG 图元')
    root = svg_root(Path(asset.source_path))
    if root.get('transform') or root.get('style') or root.xpath('//*[local-name()="style" and contains(.,"transform")]'):
        _fail('源 SVG 根变换未受支持')
    view = root.get('viewBox', '').replace(',', ' ').split()
    try:
        values = [float(v) for v in view]
        dims = [float(re.fullmatch(r'([\d.]+)pt', root.get(k, '')).group(1)) for k in ('width','height')]
    except (ValueError, AttributeError):
        _fail('源 SVG 坐标比例未明确')
    if len(values) != 4 or values[:2] != [0, 0] or dims != values[2:] or not all(math.isfinite(v) and v > 0 for v in dims):
        _fail('源 SVG 坐标比例未明确')
    segments=[]
    for ident in ids:
        group=element(root,ident)
        if ET.QName(group).localname != 'g' or group.get('transform') or any(a.get('transform') for a in group.iterancestors()):
            _fail('源坐标轴组含不支持的变换')
        children=list(group)
        if (len(children)!=1 or not isinstance(children[0].tag,str) or ET.QName(children[0]).localname!='path'
                or children[0].get('transform') or 'transform' in children[0].get('style','').lower()):
            _fail('源坐标轴必须为简单的独立直线')
        match=_LINE.fullmatch(children[0].get('d',''))
        if not match:_fail('源坐标轴不是简单直线')
        segment=tuple(float(v) for v in match.groups())
        if not all(math.isfinite(v) for v in segment):_fail('源坐标轴包含无效坐标')
        segments.append(segment)
    xs=[v for line in segments for v in (line[0],line[2])];ys=[v for line in segments for v in (line[1],line[3])]
    box=(min(xs),min(ys),max(xs),max(ys));x0,y0,x1,y1=box
    expected_edges={tuple(x) for x in (((x0,y0),(x1,y0)),((x0,y1),(x1,y1)),((x0,y0),(x0,y1)),((x1,y0),(x1,y1)))}
    edges={tuple(sorted(((line[0],line[1]),(line[2],line[3])))) for line in segments}
    if edges != {tuple(sorted(edge)) for edge in expected_edges} or x0>=x1 or y0>=y1:
        _fail('四条源坐标轴未构成矩形')
    clip=receipt['source_clip'];target=placement['rect']
    sx=(target[2]-target[0])/(clip[2]-clip[0]);sy=(target[3]-target[1])/(clip[3]-clip[1])
    if abs(sx-sy)>1e-5:_fail('源绘图区必须保持等比缩放')
    mapped=[target[0]+(x0-clip[0])*sx,target[1]+(y0-clip[1])*sy,target[0]+(x1-clip[0])*sx,target[1]+(y1-clip[1])*sy]
    points=paths[binding['frame_path_id']]['points']
    if len(points)!=5 or points[0]!=points[-1]:_fail('目标绘图区必须是闭合矩形框')
    frame=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
    if any(abs(a-b)>.15 for a,b in zip(frame,mapped)):_fail('目标绘图区框边与源坐标轴不一致')
    if (set(tuple(p) for p in points[:-1]) != {(frame[0],frame[1]),(frame[2],frame[1]),(frame[2],frame[3]),(frame[0],frame[3])}
            or any(a[0]!=b[0] and a[1]!=b[1] for a,b in zip(points,points[1:]))):
        _fail('目标绘图区必须是矩形')
    scene.layout_evidence['source_plot_frame']={'source_sha256':asset.source_hash,'spine_ids':ids,'source_rect':list(box),'target_rect':frame,'verified':True}
