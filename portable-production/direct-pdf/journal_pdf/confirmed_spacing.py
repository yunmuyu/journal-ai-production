"""Explicitly bound spacing checks for user-confirmed figure rules."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING
from .common import FigureError

if TYPE_CHECKING:
    from .scene import Scene

RULES={'legend_key_text':(3.,'horizontal'), 'image_grid_vertical':(4.,'vertical'),
       'caption_lines':(3.,'vertical'), 'container_horizontal':(4.5,'left'),
       'title_to_frame':(3.,'vertical'), 'sibling_frames':(2.5,'horizontal'),
       'container_vertical':(3.,'top'), 'container_title':(3.,'top'),
       'image_row_label':(6.,'horizontal'), 'stage_arrow_before':(1.,'vertical'),
       'stage_arrow_after':(1.,'vertical'), 'connector_label':(3.,'right')}
SIDES={'legend_key_text':{'horizontal'},'image_grid_vertical':{'vertical'},'caption_lines':{'vertical'},
       'container_horizontal':{'left','right'},'title_to_frame':{'vertical'},
       'sibling_frames':{'horizontal','vertical'},'container_vertical':{'top','bottom'},
       'container_title':{'top'},'image_row_label':{'horizontal'},
       'stage_arrow_before':{'vertical'},'stage_arrow_after':{'vertical'},
       'connector_label':{'left','right','top','bottom'}}
TYPES={'legend_key_text':({'node','path'},{'text'}),'image_grid_vertical':({'asset'},{'asset'}),
       'caption_lines':({'text'},{'text'}),'container_horizontal':({'node'},{'node'}),
       'title_to_frame':({'text'},{'node'}),'sibling_frames':({'node'},{'node'}),
       'container_vertical':({'node'},{'node'}),'container_title':({'node'},{'text'}),
       'image_row_label':({'text'},{'asset'}),'stage_arrow_before':({'node'},{'path'}),
       'stage_arrow_after':({'path'},{'node'}),'connector_label':({'path'},{'text'})}


def horizontal_stroke_bounds(path) -> list[float]:
    """Visible ink bounds of a PDF butt-capped, zero-phase horizontal sample."""
    points=path['points'];half=(path.get('width') or 0)/2
    if len(points)!=2 or abs(points[0][1]-points[1][1])>.01:
        raise FigureError('confirmed_spacing_path_invalid','图例样线须为独立水平线')
    start,end=points[0][0],points[1][0];length=abs(end-start);direction=1 if end>=start else -1
    dash=path.get('dash') or []
    if not dash:return [min(start,end),points[0][1]-half,max(start,end),points[0][1]+half]
    if len(dash)%2 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<=0 for v in dash):
        raise FigureError('confirmed_spacing_path_invalid','图例样线须使用可核验的偶数段虚线')
    position=0.;index=0;painted=[]
    while position<length-1e-9:
        next_position=min(length,position+dash[index%len(dash)])
        if index%2==0:painted.extend((start+direction*position,start+direction*next_position))
        position=next_position;index+=1
        if index>10000:raise FigureError('confirmed_spacing_path_invalid','虚线段数过多，不能可靠核验')
    if not painted:raise FigureError('confirmed_spacing_path_invalid','图例样线没有可见墨迹')
    return [min(painted),points[0][1]-half,max(painted),points[0][1]+half]


def polygon_stroke_bounds(points: list[list[float]], width: float) -> list[float]:
    """Bounds of a closed polygon with PDF's default miter joins (limit 10)."""
    half=width/2;vertices=[]
    for i,p in enumerate(points):
        prev=points[i-1];nxt=points[(i+1)%len(points)]
        ax,ay=p[0]-prev[0],p[1]-prev[1];bx,by=nxt[0]-p[0],nxt[1]-p[1]
        al,bl=math.hypot(ax,ay),math.hypot(bx,by)
        if not al or not bl:raise FigureError('confirmed_spacing_path_invalid','符号包含零长度边')
        n1=(-ay/al,ax/al);n2=(-by/bl,bx/bl);denom=1+n1[0]*n2[0]+n1[1]*n2[1]
        if denom<=1e-10:
            vectors=[(half*n1[0],half*n1[1]),(half*n2[0],half*n2[1])]
        else:
            v=(half*(n1[0]+n2[0])/denom,half*(n1[1]+n2[1])/denom)
            vectors=[v] if math.hypot(*v)<=10*half+1e-9 else [(half*n1[0],half*n1[1]),(half*n2[0],half*n2[1])]
        for vx,vy in vectors:vertices.extend(((p[0]+vx,p[1]+vy),(p[0]-vx,p[1]-vy)))
    return [min(p[0] for p in vertices),min(p[1] for p in vertices),
            max(p[0] for p in vertices),max(p[1] for p in vertices)]


def parse_confirmed_spacing(value):
    if not isinstance(value,list):raise FigureError('confirmed_spacing_invalid','确认间距检查须为数组')
    result=[]
    for item in value:
        if (not isinstance(item,dict) or set(item)-{'rule','first_id','second_id','side','gap_pt','reason'}
                or not isinstance(item.get('rule'),str) or item['rule'] not in RULES
                or any(not isinstance(item.get(k),str) or not item[k] for k in ('first_id','second_id'))):
            raise FigureError('confirmed_spacing_invalid','须指定有效规则与两个明确对象')
        rule=item['rule'];side=item.get('side',RULES[rule][1]);gap=item.get('gap_pt',RULES[rule][0]);reason=item.get('reason')
        if (not isinstance(side,str) or side not in SIDES[rule] or isinstance(gap,bool) or not isinstance(gap,(float,int))
                or not math.isfinite(gap) or gap<0 or ('gap_pt' in item and (not isinstance(reason,str) or not reason.strip()))
                or ('reason' in item and 'gap_pt' not in item)):
            raise FigureError('confirmed_spacing_invalid','间距方向无效，例外须填写数值和原因')
        result.append({'rule':rule,'first_id':item['first_id'],'second_id':item['second_id'],
                       'side':side,'gap_pt':float(gap),'reason':reason})
    return result


def audit_confirmed_spacing(scene: Scene):
    objects={}
    for typ,items in (('node',scene.nodes),('text',scene.texts),('asset',scene.assets),('path',scene.paths)):
        for item in items:objects[item['id']]=(typ,item)
    results=[];issues=[]
    for check in scene.confirmed_spacing_checks:
        rule=check['rule'];side=check.get('side',RULES[rule][1]);a=objects.get(check['first_id']);b=objects.get(check['second_id'])
        if a is None or b is None or a[0] not in TYPES[rule][0] or b[0] not in TYPES[rule][1]:
            issues.append({'code':'confirmed_spacing_binding_invalid','ids':[check['first_id'],check['second_id']]});continue
        if rule=='connector_label':
            text=b[1]['position']['bbox'];path=a[1];half=(path.get('width') or 0)/2;gaps=[]
            for p,q in zip(path['points'],path['points'][1:]):
                if side in ('left','right') and abs(p[0]-q[0])<.01 and min(p[1],q[1])<text[3] and max(p[1],q[1])>text[1]:
                    gap=(p[0]-half-text[2]) if side=='left' else (text[0]-p[0]-half)
                elif side in ('top','bottom') and abs(p[1]-q[1])<.01 and min(p[0],q[0])<text[2] and max(p[0],q[0])>text[0]:
                    gap=(p[1]-half-text[3]) if side=='top' else (text[1]-p[1]-half)
                else:continue
                if gap>=0:gaps.append(gap)
            if not gaps:
                issues.append({'code':'confirmed_spacing_alignment_invalid','ids':[check['first_id'],check['second_id']]});continue
            actual=min(gaps);expected=check['gap_pt']*scene.size/8
            result={'rule':rule,'ids':[check['first_id'],check['second_id']],'side':side,
                    'actual_pt':actual,'expected_pt':expected,'reason':check.get('reason')}
            results.append(result)
            if abs(actual-expected)>.15:issues.append({'code':'confirmed_spacing_mismatch',**result})
            continue
        def bounds(entry):
            typ,item=entry
            if typ=='text':return list(item['position']['bbox'])
            if typ=='asset':return list(item['rect'])
            if typ=='node':
                r=item['rect'];half=(item.get('width') or 0)/2
                return [r[0]-half,r[1]-half,r[2]+half,r[3]+half]
            pts=item['points'];half=(item.get('width') or 0)/2
            if item.get('closed') and len(pts)>=3:
                return polygon_stroke_bounds(pts,item.get('width') or 0)
            return horizontal_stroke_bounds(item)
        x=bounds(a);y=bounds(b)
        if rule in ('container_horizontal','container_vertical','container_title'):
            rect=a[1]['rect'];half=(a[1].get('width') or 0)/2
            inner=[rect[0]+half,rect[1]+half,rect[2]-half,rect[3]-half]
            if y[0]<inner[0] or y[1]<inner[1] or y[2]>inner[2] or y[3]>inner[3]:
                issues.append({'code':'confirmed_spacing_not_contained','ids':[check['first_id'],check['second_id']]});continue
            actual={'left':y[0]-inner[0],'right':inner[2]-y[2],
                    'top':y[1]-inner[1],'bottom':inner[3]-y[3]}[side]
        else:
            if side=='horizontal' and min(x[3],y[3])<=max(x[1],y[1]):
                issues.append({'code':'confirmed_spacing_alignment_invalid','ids':[check['first_id'],check['second_id']]});continue
            if side=='vertical' and min(x[2],y[2])<=max(x[0],y[0]):
                issues.append({'code':'confirmed_spacing_alignment_invalid','ids':[check['first_id'],check['second_id']]});continue
            if rule=='sibling_frames' and any(set(path.get('endpoint_nodes') or [])=={check['first_id'],check['second_id']}
                                               for path in scene.paths):
                issues.append({'code':'confirmed_spacing_connected','ids':[check['first_id'],check['second_id']]});continue
            if side=='horizontal':actual=y[0]-x[2]
            else:actual=y[1]-x[3]
        expected=check.get('gap_pt',RULES[rule][0])*scene.size/8
        result={'rule':rule,'ids':[check['first_id'],check['second_id']],'side':side,
                'actual_pt':actual,'expected_pt':expected,'reason':check.get('reason')}
        results.append(result)
        if abs(actual-expected)>.15:issues.append({'code':'confirmed_spacing_mismatch',**result})
    return {'checks':results,'issues':issues}
