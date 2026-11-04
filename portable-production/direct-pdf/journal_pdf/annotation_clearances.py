"""Explicit, flexible chart-label clearance checks using conservative ink bounds."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .common import FigureError
from .text_geometry import convex_intersects,polygons,texts_intersect

if TYPE_CHECKING:
    from .scene import Scene

TARGETS={'labels':2.5,'ticks':2.,'legend_frame':3.,'plot_frame':1.}


def _point_segment_distance(point,a,b):
    dx=b[0]-a[0];dy=b[1]-a[1];length=dx*dx+dy*dy
    t=max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length)) if length else 0.
    return math.hypot(point[0]-a[0]-t*dx,point[1]-a[1]-t*dy)


def _glyph_envelope_distance(first,second):
    result=[]
    for a in polygons(first):
        for b in polygons(second):
            if convex_intersects(a,b,0):return 0.
            result.extend(_point_segment_distance(p,u,v) for p in a for u,v in zip(b,b[1:]+b[:1]))
            result.extend(_point_segment_distance(p,u,v) for p in b for u,v in zip(a,a[1:]+a[:1]))
    return min(result) if result else None


def parse_annotation_clearances(value):
    if not isinstance(value,list):raise FigureError('annotation_clearance_invalid','数据标注间距检查须为数组')
    result=[]
    for item in value:
        if (not isinstance(item,dict) or set(item)-{'kind','first_id','second_id','target_pt','reason'}
                or not isinstance(item.get('kind'),str) or item['kind'] not in TARGETS
                or any(not isinstance(item.get(k),str) or not item[k] for k in ('first_id','second_id'))
                or item['first_id']==item['second_id']):
            raise FigureError('annotation_clearance_invalid','数据标注间距绑定无效')
        target=item.get('target_pt',TARGETS[item['kind']]);reason=item.get('reason')
        if (isinstance(target,bool) or not isinstance(target,(float,int)) or not math.isfinite(target) or target<0
                or ('target_pt' in item and (not isinstance(reason,str) or not reason.strip()))
                or ('reason' in item and 'target_pt' not in item)):
            raise FigureError('annotation_clearance_invalid','间距调整须指定非负数值和原因')
        result.append({**item,'target_pt':float(target),'reason':reason})
    return result


def _frame(path):
    if path is None or path.get('arrow') or path.get('both'):return None
    pts=path.get('points',[]);width=path.get('width')
    if (len(pts)!=5 or pts[0]!=pts[-1] or len({tuple(p) for p in pts[:-1]})!=4
            or len({p[0] for p in pts})!=2 or len({p[1] for p in pts})!=2
            or any(a[0]!=b[0] and a[1]!=b[1] for a,b in zip(pts,pts[1:]))
            or not isinstance(width,(int,float)) or isinstance(width,bool) or not math.isfinite(width) or width<=0):return None
    return [min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts),width]


def audit_annotation_clearances(scene: Scene):
    texts={t['id']:t for t in scene.texts};paths={p['id']:p for p in scene.paths}
    checks=[];issues=[];notes=[]
    for item in scene.annotation_clearance_checks:
        first=texts.get(item['first_id']);second=texts.get(item['second_id']) if item['kind'] in ('labels','ticks') else paths.get(item['second_id'])
        if first is None or second is None:
            issues.append({'code':'annotation_clearance_unverified','ids':[item['first_id'],item['second_id']]});continue
        bbox=first['position']['bbox'];kind=item['kind'];target=item['target_pt']*scene.size/8;overlap=False
        measurement='ink_bounding_box_conservative'
        if kind=='ticks':
            gap=_glyph_envelope_distance(first,second)
            if gap is None:
                issues.append({'code':'annotation_clearance_unverified','ids':[item['first_id'],item['second_id']]});continue
            measurement='glyph_ink_envelope_conservative'
        elif kind=='labels':
            other=second['position']['bbox']
            dx=max(bbox[0]-other[2],other[0]-bbox[2],0);dy=max(bbox[1]-other[3],other[1]-bbox[3],0)
            gap=math.hypot(dx,dy)
            overlap=texts_intersect(first,second,0)
            if overlap:issues.append({'code':'annotation_text_overlap','ids':[item['first_id'],item['second_id']]})
        else:
            rect=_frame(second)
            if rect is None:
                issues.append({'code':'annotation_clearance_unverified','ids':[item['first_id'],item['second_id']]});continue
            x0,y0,x1,y1,width=rect;half=width/2
            if kind=='plot_frame':
                gap=min(bbox[0]-(x0+half),bbox[1]-(y0+half),(x1-half)-bbox[2],(y1-half)-bbox[3])
                if gap<=0:
                    overlap=any(x<=x0+half or x>=x1-half or y<=y0+half or y>=y1-half
                                for polygon in polygons(first) for x,y in polygon)
            else:
                dx=max((x0-half)-bbox[2],bbox[0]-(x1+half),0);dy=max((y0-half)-bbox[3],bbox[1]-(y1+half),0)
                gap=math.hypot(dx,dy)
                if gap<=0:
                    area=[(x0-half,y0-half),(x1+half,y0-half),(x1+half,y1+half),(x0-half,y1+half)]
                    overlap=any(convex_intersects(poly,area,0) for poly in polygons(first))
            if overlap:issues.append({'code':'annotation_frame_overlap','ids':[item['first_id'],item['second_id']]})
        entry={'kind':kind,'ids':[item['first_id'],item['second_id']],'gap_pt':gap,'target_pt':target,
               'reason':item.get('reason'),'measurement':measurement}
        checks.append(entry)
        tolerance=.15*scene.size/8 if kind=='ticks' else 1e-7
        if gap<target-tolerance and not overlap:
            notes.append({'code':'annotation_spacing_review',**entry,
                          'message':'数值小于起排参考，需结合真实字形和数据归属复核。'})
    return {'checks':checks,'issues':issues,'notes':notes}
