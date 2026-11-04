"""Translate explicitly bound mixed regions after real assets are embedded."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from .boundary_ports import BoundaryGeometry, rectangular_path_bounds
from .common import FigureError, contains, intersects, segment_hits
from .connection_layout import route_connection, terminal_points
from .fonts import position_text
from .editorial import ARROW_LENGTH
from .region_layout import horizontal_band, content_region, align_region_bottoms
from .scene import audit_scene

if TYPE_CHECKING:
    from .scene import Scene


class MixedGroup(TypedDict):
    container: str
    nodes: NotRequired[list[str]]
    assets: NotRequired[list[str]]
    texts: NotRequired[list[str]]
    paths: NotRequired[list[str]]
    fit_container: NotRequired[bool]


class MixedLayout(TypedDict):
    id: str
    axis: Literal['row','column']
    origin: list[float]
    groups: list[MixedGroup]
    gap_pt: NotRequired[float]
    align_bottoms: NotRequired[bool]


def _geometry(scene: Scene) -> BoundaryGeometry:
    return BoundaryGeometry({n['id']:tuple(n['rect']) for n in scene.nodes},
        {a['id']:tuple(a['rect']) for a in scene.assets},
        {p['id']:rectangular_path_bounds(p['points']) for p in scene.paths},
        {t['id']:tuple(t['position']['bbox']) for t in scene.texts},scene.node_groups,
        page=(0,0,scene.width,scene.height),node_shapes={n['id']:n['kind'] for n in scene.nodes})


def _overlaps(scene: Scene) -> set[tuple[str,str]]:
    items=[('node:'+n['id'],n['rect']) for n in scene.nodes if not n['container']]
    items += [('asset:'+a['id'],a['rect']) for a in scene.assets]
    items += [('text:'+t['id'],t['position']['bbox']) for t in scene.texts]
    return {(a,c) for i,(a,b) in enumerate(items) for c,d in items[i+1:] if intersects(b,d)}


def _asset_crossings(scene: Scene) -> set[tuple[str,str]]:
    return {(p['id'],a['id']) for p in scene.paths for a in scene.assets
            if any(segment_hits(x,y,a['rect'],.1) for x,y in zip(p['points'],p['points'][1:]))}


def _extent(scene: Scene) -> tuple[float,float]:
    rects=[n['rect'] for n in scene.nodes]+[a['rect'] for a in scene.assets]+[t['position']['bbox'] for t in scene.texts]
    points=[point for p in scene.paths for point in p['points']]
    return max([r[2] for r in rects]+[p[0] for p in points]),max([r[3] for r in rects]+[p[1] for p in points])


def apply_mixed_layout(scene: Scene, declarations: list[MixedLayout]) -> None:
    """Apply declared region membership atomically, preserving assets and topology."""
    if not declarations:return
    # Keep the real Asset objects and open PDF handles; snapshot geometry only.
    snapshot=(deepcopy(scene.nodes),deepcopy(scene.texts),deepcopy(scene.paths),
              [dict(a,rect=a['rect'][:]) for a in scene.assets],deepcopy(scene.layout_evidence),scene.width,scene.height)
    baseline={json.dumps(i,sort_keys=True) for i in audit_scene(scene)}
    overlaps,crossings=_overlaps(scene),_asset_crossings(scene)
    right,bottom=_extent(scene);margins=(max(4,scene.width-right),max(4,scene.height-bottom))
    try:
        for layout in declarations:_apply(scene,layout)
        if not any(isinstance(e,dict) and 'page' in e for p in scene.paths for e in (p.get('endpoint_nodes') or [])):
            right,bottom=_extent(scene)
            scene.width=right+margins[0];scene.height=bottom+margins[1]
        issues=[i for i in audit_scene(scene) if json.dumps(i,sort_keys=True) not in baseline]
        extra_overlaps=_overlaps(scene)-overlaps
        extra_crossings=_asset_crossings(scene)-crossings
        if issues or extra_overlaps or extra_crossings:
            raise FigureError('mixed_layout_collision','联动排版产生新的碰撞或端口问题',issues=issues,
                              overlaps=sorted(extra_overlaps),asset_crossings=sorted(extra_crossings))
    except FigureError:
        scene.nodes,scene.texts,scene.paths,scene.assets,scene.layout_evidence,scene.width,scene.height=snapshot
        raise


def _apply(scene: Scene, layout: MixedLayout) -> None:
    nodes={n['id']:n for n in scene.nodes};assets={a['id']:a for a in scene.assets}
    texts={t['id']:t for t in scene.texts};paths={p['id']:p for p in scene.paths}
    groups=layout.get('groups',[]);axis=layout.get('axis');origin=layout.get('origin')
    if axis not in ('row','column') or not isinstance(origin,list) or len(origin)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in origin) or not isinstance(groups,list) or not groups:
        raise FigureError('mixed_layout_invalid','混合排版须指定行列方向、有限原点和明确分组')
    if not isinstance(layout.get('align_bottoms',False),bool) or layout.get('align_bottoms') and axis!='row':
        raise FigureError('mixed_layout_alignment','底边对齐仅适用于明确并列的分区')
    ownership={};prepared=[]
    for group in groups:
        if not isinstance(group,dict) or any(not isinstance(group.get(key,[]),list) or any(not isinstance(i,str) for i in group.get(key,[])) or len(set(group.get(key,[])))!=len(group.get(key,[])) for key in ('nodes','assets','texts','paths')) or not isinstance(group.get('fit_container',False),bool):
            raise FigureError('mixed_layout_members','分组成员须为不重复的ID列表，fit_container须为布尔值')
        ident=group.get('container');container=nodes.get(ident)
        if not container or not container['container']:
            raise FigureError('mixed_layout_container','混合分组须绑定真实容器',container=ident)
        ids=set(group.get('nodes',[]))|{ident}
        aids=set(group.get('assets',[]));tids=set(group.get('texts',[]));pids=set(group.get('paths',[]))
        if not ids<=nodes.keys() or not aids<=assets.keys() or not tids<=texts.keys() or not pids<=paths.keys():
            raise FigureError('mixed_layout_members','混合分组引用了未知成员',container=ident)
        tids|={t['id'] for t in scene.texts if t['owner'] in ids}
        bound=[('node',i) for i in ids]+[('asset',i) for i in aids]+[('text',i) for i in tids]+[('path',i) for i in pids]
        for key in bound:
            if key in ownership:raise FigureError('mixed_layout_duplicate','成员不能同时属于两个移动分组',member=key)
            ownership[key]=ident
        rect=container['rect'][:]
        missing=[i for i,a in assets.items() if contains(rect,a['rect']) and i not in aids]
        missing += [i for i,n in nodes.items() if contains(rect,n['rect']) and i not in ids]
        missing += [i for i,t in texts.items() if contains(rect,t['position']['bbox']) and i not in tids]
        if missing:raise FigureError('mixed_layout_unbound_members','分区内存在未绑定成员，不能留下原位',container=ident,missing=missing)
        members=[nodes[i]['rect'] for i in ids if i!=ident]+[assets[i]['rect'] for i in aids]+[texts[i]['position']['bbox'] for i in tids]
        if any(not contains(rect,r,.15) for r in members):
            raise FigureError('mixed_layout_members_outside','成员不在已确认分区内',container=ident)
        if group.get('fit_container'):
            rect=content_region(members,padding=6*scene.size/8)
            container['rect']=rect[:]
        prepared.append((ident,ids,aids,tids,pids,rect))
    primary=0 if axis=='row' else 1;secondary=1-primary
    gap=layout.get('gap_pt',6)*scene.size/8
    ordering={item[0]:i for i,item in enumerate(prepared)};geometry=_geometry(scene)
    for p in scene.paths:
        ends=p.get('endpoint_nodes') or []
        owners=[ownership.get(('node',e.get('node'))) if isinstance(e,dict) else ownership.get(('node',e)) for e in ends]
        if len(owners)==2 and all(owners) and owners[0]!=owners[1] and p['arrow']:
            if not all(isinstance(e,dict) for e in ends):continue
            a,b=sorted(range(2),key=lambda i:ordering[owners[i]])
            ia,ib=ordering[owners[a]],ordering[owners[b]]
            if ib!=ia+1:continue
            ra,rb=prepared[ia][-1],prepared[ib][-1]
            pa,pb=geometry.expected_point(ends[a]),geometry.expected_point(ends[b])
            offset=abs((pa[secondary]-ra[secondary])-(pb[secondary]-rb[secondary]))
            required=ARROW_LENGTH*p.get('arrow_scale',1)*(2 if p['both'] or offset>.001 else 1)
            inner=(ra[primary+2]-pa[primary])+(pb[primary]-rb[primary])
            gap=max(gap,required-inner)
    starts=horizontal_band([r[primary+2]-r[primary] for *_,r in prepared],origin=origin[primary],minimum_gap=gap)
    moves={}
    for start,(ident,ids,aids,tids,pids,rect) in zip(starts,prepared):
        delta=[0.,0.];delta[primary]=start-rect[primary];delta[secondary]=origin[secondary]-rect[secondary]
        dx,dy=delta
        for i in ids:nodes[i]['rect']=[v+delta[j%2] for j,v in enumerate(nodes[i]['rect'])]
        for i in aids:assets[i]['rect']=[v+delta[j%2] for j,v in enumerate(assets[i]['rect'])]
        for i in tids:
            t=texts[i];t['x']+=dx;t['y']+=dy
            t['position']=position_text(t['measurement'],t['x'],t['y'],t['align'],t['position'].get('rotation',0))
        for i in pids:paths[i]['points']=[[x+dx,y+dy] for x,y in paths[i]['points']]
        for kind,items in (('node',ids),('asset',aids),('text',tids)):
            for i in items:moves[(kind,i)]=delta
        scene.layout_evidence.setdefault('mixed_layout',[]).append({'layout':layout.get('id'),'container':ident,
            'nodes':sorted(ids),'assets':sorted(aids),'texts':sorted(tids),'delta_pt':delta})
    if layout.get('align_bottoms'):
        align_region_bottoms([nodes[item[0]]['rect'] for item in prepared])
    geometry=_geometry(scene)
    for p in scene.paths:
        if ('path',p['id']) in ownership:continue
        if p.get('generated_connection'):
            routed=route_connection(nodes,p['generated_connection'],scene.size)
            p['points']=routed.points;p['endpoint_nodes']=routed.endpoints
            continue
        ends=p.get('endpoint_nodes') or []
        moved=any(isinstance(e,dict) and any((kind,e.get(kind)) in moves for kind in ('node','asset','text')) or
                  isinstance(e,str) and ('node',e) in moves for e in ends)
        if not moved:
            if any(all(contains(r,[x,y,x,y]) for x,y in p['points']) for *_,r in prepared):
                raise FigureError('mixed_layout_unbound_path','分区内路径须明确归属',path=p['id'])
            continue
        if len(ends)!=2 or not all(isinstance(e,dict) for e in ends):
            raise FigureError('mixed_layout_path_binding','外部连接须明确side/fraction或采用公共生成连接',path=p['id'])
        points=deepcopy(p['points']);start=list(geometry.expected_point(ends[0]));end=list(geometry.expected_point(ends[1]))
        straight=all(abs(a[0]-b[0])<.001 for a,b in zip(points,points[1:])) or all(abs(a[1]-b[1])<.001 for a,b in zip(points,points[1:]))
        if not straight or abs(start[0]-end[0])>.001 and abs(start[1]-end[1])>.001:
            raise FigureError('mixed_layout_reroute_required','复杂连接需已确认的联动方案，不擅自改变绕线',path=p['id'])
        p['points']=terminal_points([start,end],arrow=p['arrow'],both=p['both'],size=8*p.get('arrow_scale',1))
