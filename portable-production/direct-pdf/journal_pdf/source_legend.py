"""Verify legend swatches against their preserved source series."""
from __future__ import annotations

import re
import fitz
from .common import FigureError


def _fail(message):
    raise FigureError('source_legend_mismatch',message)


def _gray(color):
    if color is None or len(color)!=3 or max(color)-min(color)>.01:
        _fail('源图例系列不是可验证的灰度线')
    return sum(color)/3


def validate_source_legends(scene, bindings):
    if not isinstance(bindings,list) or not bindings:_fail('图例系列绑定须为非空数组')
    assets={a['id']:a for a in scene.assets};paths={p['id']:p for p in scene.paths};nodes={n['id']:n for n in scene.nodes}
    evidence=[]
    for b in bindings:
        if not isinstance(b,dict) or set(b)!={'asset_id','path_id','marker_node_id'} or any(not isinstance(v,str) or not v for v in b.values()):
            _fail('图例绑定须指定源系列、图例线及图例标记')
        if b['asset_id'] not in assets or b['path_id'] not in paths or b['marker_node_id'] not in nodes:
            _fail('图例绑定引用不存在的元素')
        placed=assets[b['asset_id']];asset=placed['asset'];receipt=asset.audit
        if receipt.get('mode')!='source-svg-group':_fail('图例线绑定须引用源 SVG 系列')
        with fitz.open(stream=asset.data,filetype='pdf') as doc:
            drawings=doc[0].get_drawings()
        strokes=[d for d in drawings if d['fill'] is None and d['color'] is not None]
        if len(strokes)!=1:_fail('源系列必须包含一条明确的曲线')
        line=strokes[0];markers=[d for d in drawings if d['fill'] is not None and d['color'] is not None]
        if not markers:_fail('源系列中没有可验证的标记')
        marker=markers[0];r=marker['rect'];clip=receipt['source_clip'];target=placed['rect']
        signature=lambda m: (round(m['rect'].width,4),round(m['rect'].height,4),round(m['width'],4),
                             round(_gray(m['fill']),4),round(_gray(m['color']),4),tuple(x[0] for x in m['items']))
        if any(signature(m)!=signature(marker) for m in markers[1:]):
            _fail('源系列包含不同标记，不能用单一图例标记概括')
        sx=(target[2]-target[0])/(clip[2]-clip[0]);sy=(target[3]-target[1])/(clip[3]-clip[1])
        if abs(sx-sy)>1e-5:_fail('源系列必须等比缩放')
        raw=line['dashes'];match=re.fullmatch(r'\[([^\]]*)\]\s*([-+\d.]+)',raw)
        if not match or abs(float(match.group(2)))>.01:_fail('源虚线相位不受支持')
        try:dash=[float(v)*sx for v in match.group(1).split()]
        except ValueError:_fail('源虚线格式不受支持')
        swatch=paths[b['path_id']];actual=swatch.get('dash') or []
        if (len(actual)!=len(dash) or any(abs(a-e)>.04 for a,e in zip(actual,dash))
                or abs(swatch['width']-line['width']*sx)>.04 or abs(swatch.get('gray',0)-_gray(line['color']))>.01):
            _fail('图例线的虚线节奏、线宽或灰度与曲线不同')
        node=nodes[b['marker_node_id']];kinds={x[0] for x in marker['items']}
        kind='ellipse' if 'c' in kinds else 'rectangle' if kinds <= {'l','re'} else None
        rect=node['rect'];w=rect[2]-rect[0];h=rect[3]-rect[1]
        if (kind is None or node['kind']!=kind or abs(w-r.width*sx)>.05 or abs(h-r.height*sy)>.05
                or abs(node.get('fill',-1)-_gray(marker['fill']))>.01
                or abs(node.get('gray',0)-_gray(marker['color']))>.01
                or abs(node['width']-marker['width']*sx)>.04):
            _fail('图例标记的形状、大小或灰度与曲线标记不同')
        evidence.append({'asset_id':b['asset_id'],'path_id':b['path_id'],'marker_node_id':b['marker_node_id'],
                         'dash_pt':dash,'width_pt':line['width']*sx,'gray':_gray(line['color']),'verified':True})
    scene.layout_evidence['source_legend_bindings']=evidence
