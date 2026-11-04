"""Preserve uniquely bound rectangular ports while measured groups change."""
import math
from .common import FigureError, segment_hits, intersects
from .editorial import ARROW_LENGTH, display_content, wrap_text


def identity(e):return e.get('node') if isinstance(e,dict) else e


def measured_rectangles(spec, groups, reg, size):
    nodes={n['id']:n for n in spec['nodes']};rectangles={}
    for g in groups:
        ids=g['nodes'];scale=size/8
        measurements=[]
        for k in ids:
            n=nodes[k];text=display_content(n['text'],'label')
            if n.get('wrap_chars') is not None:text=wrap_text(text,n['wrap_chars'])
            measurements.append(reg.measure(text,size))
        widths=[m['width']+9*scale for m in measurements];heights=[m['height']+5.4*scale for m in measurements]
        widths=[max(widths)]*len(ids)
        if g['axis']=='row':heights=[max(heights)]*len(ids)
        gap=3*scale+.5
        for path in spec.get('paths',[]):
            ends=[identity(e) for e in path.get('endpoint_nodes') or []]
            if len(ends)==2 and set(ends)<=set(ids):
                if path.get('arrow') or path.get('both'):gap=max(gap,ARROW_LENGTH*scale*(2 if path.get('both') else 1))
        # Adjacent external one-corner ports impose extra occupied space.
        # Derive that space before placing the row/column, rather than route
        # around a group packed with an unconditional 3pt gap.
        base={};x,y=g['origin'];axis=1 if g['axis']=='column' else 0
        for j,(k,w,h) in enumerate(zip(ids,widths,heights)):
            base[k]=([x,y,x+w,y+h],j)
            if axis==1:y+=h
            else:x+=w
        normals={'left':(-1,0),'right':(1,0),'top':(0,-1),'bottom':(0,1)}
        for path in spec.get('paths',[]):
            ends=[identity(e) for e in path.get('endpoint_nodes') or []];pts=path.get('points',[])
            if len(ends)!=2 or len(pts)<3 or not any(k in base for k in ends):continue
            if any(k not in nodes or not nodes[k].get('rect') for k in ends):continue
            bindings=[bind_port(nodes[k]['rect'],pts[i]) for k,i in zip(ends,(0,-1))]
            n1,n2=[normals[b[0]] for b in bindings]
            if n1[0]*n2[0]+n1[1]*n2[1]!=0:continue
            points=[];coeff=[]
            for k,(side,f) in zip(ends,bindings):
                rect,j=base.get(k,(nodes[k]['rect'],0));points.append(port(rect,side,f));coeff.append(j if k in base else 0)
            u,v=points;first_axis=0 if n1[0] else 1
            for dim,sign,reverse in ((first_axis,n1[first_axis],False),(1-first_axis,n2[1-first_axis],True)):
                value=sign*((u[dim]-v[dim]) if reverse else (v[dim]-u[dim]))
                coefficient=sign*((coeff[0]-coeff[1]) if reverse else (coeff[1]-coeff[0])) if dim==axis else 0
                if coefficient>0:gap=max(gap,(ARROW_LENGTH*scale-value)/coefficient)
        g['gap_pt']=gap
        x,y=g['origin']
        for k,w,h in zip(ids,widths,heights):
            rectangles[k]=[x,y,x+w,y+h]
            if g['axis']=='column':y+=h+gap
            else:x+=w+gap
    return rectangles


def bind_port(rect, point):
    sides=[(side,axis,index) for side,axis,index in [('left',0,0),('right',0,2),('top',1,1),('bottom',1,3)]
           if abs(point[axis]-rect[index])<.15 and rect[1-axis]+.15<point[1-axis]<rect[3-axis]-.15]
    if len(sides)!=1:raise FigureError('layout_port_binding','端口联动缺少唯一框边绑定，不能猜测',point=point)
    side,axis,_=sides[0];fraction=(point[1-axis]-rect[1-axis])/(rect[3-axis]-rect[1-axis])
    return side,fraction


def port(rect, side, fraction):
    x,y,r,b=rect
    return {'left':[x,y+(b-y)*fraction],'right':[r,y+(b-y)*fraction],
            'top':[x+(r-x)*fraction,y],'bottom':[x+(r-x)*fraction,b]}[side]


def adapt_group_paths(spec, rectangles, size):
    nodes={n['id']:n for n in spec['nodes']};normals={'left':(-1,0),'right':(1,0),'top':(0,-1),'bottom':(0,1)}
    originals={p['id']:[point[:] for point in p.get('points',[])] for p in spec.get('paths',[])}
    if any(c.get('from') in rectangles or c.get('to') in rectangles for c in spec.get('connections',[])):
        raise FigureError('layout_connections_require_joint_plan','端口联动须先把连接绑定成明确路径')
    for p in spec.get('paths',[]):
        ends=p.get('endpoint_nodes') or [];ids=[identity(e) for e in ends]
        if not any(k in rectangles for k in ids):continue
        if None in ids and p.get('shared_net'):continue
        if len(ids)!=2 or any(k not in nodes or not nodes[k].get('rect') for k in ids):
            raise FigureError('layout_connections_require_joint_plan','端口联动缺少节点、原框或共享总线绑定',path=p.get('id'))
        points=p.get('points',[])
        if len(points)<2:raise FigureError('layout_port_binding','端口联动缺少原始路径',path=p.get('id'))
        if any(nodes[k].get('shape','rectangle')!='rectangle' for k in ids):
            raise FigureError('layout_port_binding','非矩形端口需要明确几何绑定',path=p.get('id'))
        if any(abs(a[0]-b[0])>.001 and abs(a[1]-b[1])>.001 for a,b in zip(points,points[1:])):
            raise FigureError('layout_port_binding','非正交路径不能自动改成正交线',path=p.get('id'))
        # Remove only collinear terminal witnesses, not actual routing corners.
        corners=[points[0]]
        for a,b,c in zip(points,points[1:],points[2:]):
            if abs((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))>.001:corners.append(b)
        corners.append(points[-1])
        if len(corners)>3:raise FigureError('layout_connections_require_joint_plan','多折角路线需要更高层联合求解',path=p.get('id'))
        bindings=[bind_port(nodes[k]['rect'],points[i]) for k,i in zip(ids,(0,-1))]
        start,end=[port(rectangles.get(k,nodes[k]['rect']),side,f) for k,(side,f) in zip(ids,bindings)]
        n1,n2=[normals[b[0]] for b in bindings];stub=ARROW_LENGTH*size/8
        if len(corners)==2:
            axis=0 if n1[0] else 1
            if n1[axis]!=-n2[axis] or abs(start[1-axis]-end[1-axis])>.15:
                raise FigureError('layout_straight_alignment_conflict','同列排版与原直线端口冲突，不改成折线',path=p.get('id'))
            if (end[axis]-start[axis])*n1[axis]+1e-7<stub*(2 if p.get('both') else int(bool(p.get('arrow')))):
                raise FigureError('layout_arrow_gap','分组后的箭头空间不足',path=p.get('id'))
            route=[start,end]
        else:
            if n1[0]*n2[0]+n1[1]*n2[1]!=0:raise FigureError('layout_connections_require_joint_plan','当前仅支持垂直出入侧的单折角')
            corner=[end[0],start[1]] if n1[0] else [start[0],end[1]]
            legs=[sum((corner[i]-pt[i])*normal[i] for i in (0,1)) for pt,normal in ((start,n1),(end,n2))]
            if any(length+1e-7<stub for length in legs):
                raise FigureError('layout_arrow_gap','单折角端口空间不足，不增加折角',path=p.get('id'),legs_pt=legs,minimum_pt=stub)
            route=[start,corner,end]
        if p.get('both'):route.insert(1,[start[i]+stub*n1[i] for i in (0,1)])
        if p.get('arrow') or p.get('both'):route.insert(-1,[end[i]+stub*n2[i] for i in (0,1)])
        p['points']=route
        p['endpoint_nodes']=[{'node':k,'side':side,'fraction':f} for k,(side,f) in zip(ids,bindings)]
    from .layout_relation_junctions import move_junctions
    move_junctions(spec,originals,rectangles,size)
    rects={k:rectangles.get(k,n.get('rect')) for k,n in nodes.items() if not n.get('container')}
    for k,r in rectangles.items():
        for other,q in rects.items():
            if other!=k and q and intersects(r,q):raise FigureError('layout_group_collision','行列排版碰撞邻框',node=k,other=other)
    for p in spec.get('paths',[]):
        ids=[identity(e) for e in p.get('endpoint_nodes') or []]
        for endpoint in p.get('endpoint_nodes') or []:
            if isinstance(endpoint,dict) and 'group' in endpoint:
                members=next((g['nodes'] for g in spec.get('node_groups',[]) if g['id']==endpoint['group']),None)
                if not members:raise FigureError('layout_port_binding','端口引用的节点组不存在')
                ids.extend(members)
        for a,b in zip(p.get('points',[]),p.get('points',[])[1:]):
            for k,r in rects.items():
                if r and k not in ids and segment_hits(a,b,r,.25):raise FigureError('layout_group_collision','行列排版连线穿框',path=p.get('id'),node=k)
