"""Explicit minimum clearance checks for independent orthogonal route segments."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .common import FigureError

if TYPE_CHECKING:
    from .scene import Scene


def parse_route_clearances(value):
    if not isinstance(value,list):raise FigureError('route_clearance_invalid','线段净距检查须为数组')
    checks=[]
    for item in value:
        if not isinstance(item,dict):raise FigureError('route_clearance_invalid','线段检查须为对象')
        kind=item.get('kind');required={'kind','first_id','first_segment','second_id'}
        if kind=='line_line':required=required|{'second_segment'}
        if kind not in ('line_line','line_frame') or not required<=set(item) or set(item)-required-{'min_pt','reason'}:
            raise FigureError('route_clearance_invalid','线段检查字段无效')
        if (any(not isinstance(item[k],str) or not item[k] for k in ('first_id','second_id'))
                or item['first_id']==item['second_id']
                or any(type(item[k]) is not int or item[k]<0 for k in ('first_segment','second_segment') if k in item)):
            raise FigureError('route_clearance_invalid','线段编号或对象无效')
        minimum=item.get('min_pt',3.);reason=item.get('reason')
        if (isinstance(minimum,bool) or not isinstance(minimum,(int,float)) or not math.isfinite(minimum) or minimum<0
                or ('min_pt' in item and (not isinstance(reason,str) or not reason.strip()))
                or ('reason' in item and 'min_pt' not in item)):
            raise FigureError('route_clearance_invalid','例外须指定非负净距和原因')
        checks.append({**item,'min_pt':float(minimum),'reason':reason})
    return checks


def _segment(path,index):
    if path is None:return None
    points=path.get('points',[])
    if index>=len(points)-1:return None
    if (path.get('arrow') and index==len(points)-2) or (path.get('both') and index==0):return None
    a,b=points[index:index+2];width=path.get('width')
    if (not isinstance(width,(int,float)) or isinstance(width,bool) or not math.isfinite(width) or width<=0
            or len(a)!=2 or len(b)!=2):return None
    if abs(a[0]-b[0])<.01 and abs(a[1]-b[1])>.01:return ('vertical',a[0],min(a[1],b[1]),max(a[1],b[1]),width)
    if abs(a[1]-b[1])<.01 and abs(a[0]-b[0])>.01:return ('horizontal',a[1],min(a[0],b[0]),max(a[0],b[0]),width)
    return None


def _segments_touch(a,b,c,d):
    """Treat geometric crossings or T-junctions as needing semantic review."""
    def cross(p,q,r):return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on(p,q,r):
        return (abs(cross(p,q,r))<1e-8 and min(p[0],q[0])-1e-8<=r[0]<=max(p[0],q[0])+1e-8
                and min(p[1],q[1])-1e-8<=r[1]<=max(p[1],q[1])+1e-8)
    ab_c=cross(a,b,c);ab_d=cross(a,b,d);cd_a=cross(c,d,a);cd_b=cross(c,d,b)
    return ((ab_c*ab_d<0 and cd_a*cd_b<0) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b))


def audit_route_clearances(scene: Scene):
    paths={p['id']:p for p in scene.paths};nodes={n['id']:n for n in scene.nodes}
    checks=[];issues=[]
    for item in scene.route_clearance_checks:
        a=paths.get(item['first_id']);first=_segment(a,item['first_segment'])
        b=paths.get(item['second_id']) if item['kind']=='line_line' else nodes.get(item['second_id'])
        second=_segment(b,item['second_segment']) if item['kind']=='line_line' else None
        if item['kind']=='line_line' and a and b and a.get('shared_net') and a.get('shared_net')==b.get('shared_net'):
            issues.append({'code':'route_clearance_shared_net','ids':[item['first_id'],item['second_id']]});continue
        if item['kind']=='line_line' and a and b:
            def endpoints(path):
                return {v.get('node') if isinstance(v,dict) else v for v in (path.get('endpoint_nodes') or [])}
            shared_vertex=any(math.dist(p,q)<.01 for p in a.get('points',[]) for q in b.get('points',[]))
            ap=a.get('points',[]);bp=b.get('points',[])
            crossing=any(_segments_touch(p,q,r,s) for p,q in zip(ap,ap[1:]) for r,s in zip(bp,bp[1:]))
            if endpoints(a)&endpoints(b) or shared_vertex or crossing:
                issues.append({'code':'route_clearance_connected','ids':[item['first_id'],item['second_id']]});continue
        if item['kind']=='line_frame' and a:
            endpoint_ids=[v.get('node') if isinstance(v,dict) else v for v in (a.get('endpoint_nodes') or [])]
            if item['second_id'] in endpoint_ids:
                issues.append({'code':'route_clearance_connected','ids':[item['first_id'],item['second_id']]});continue
        if item['kind']=='line_frame' and first and b:
            width=b.get('width');rect=b.get('rect')
            if (b.get('kind')=='rectangle' and isinstance(width,(int,float)) and not isinstance(width,bool)
                    and math.isfinite(width) and width>0 and isinstance(rect,list) and len(rect)==4):
                if first[0]=='vertical':second=('vertical',rect[0] if first[1]<rect[0] else rect[2],rect[1],rect[3],width)
                else:second=('horizontal',rect[1] if first[1]<rect[1] else rect[3],rect[0],rect[2],width)
                if (first[0]=='vertical' and rect[0]<=first[1]<=rect[2]) or (first[0]=='horizontal' and rect[1]<=first[1]<=rect[3]):
                    second=None
        if not first or not second or first[0]!=second[0] or min(first[3],second[3])<=max(first[2],second[2]):
            issues.append({'code':'route_clearance_unverified','ids':[item['first_id'],item['second_id']]});continue
        actual=abs(first[1]-second[1])-(first[4]+second[4])/2;minimum=item['min_pt']*scene.size/8
        result={'kind':item['kind'],'ids':[item['first_id'],item['second_id']],
                'segments':[item['first_segment'],item.get('second_segment')],
                'actual_pt':actual,'minimum_pt':minimum,'reason':item.get('reason')}
        checks.append(result)
        if actual<=0 or actual+1e-7<minimum:issues.append({'code':'route_clearance_too_small',**result})
    return {'checks':checks,'issues':issues}
