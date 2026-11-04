"""Move explicitly named single-corner branch junctions on their existing bus."""
import math
from .common import FigureError


def move_junctions(spec, originals, rectangles, size):
    from .layout_relation_paths import identity, bind_port, port
    from .editorial import ARROW_LENGTH
    paths={p['id']:p for p in spec.get('paths',[])};nodes={n['id']:n for n in spec['nodes']}
    def corners(points):
        return [points[0]]+[b for a,b,c in zip(points,points[1:],points[2:])
            if abs((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))>.001]+[points[-1]]
    normals={'left':(-1,0),'right':(1,0),'top':(0,-1),'bottom':(0,1)}
    for key,p in paths.items():
        ids=[identity(e) for e in p.get('endpoint_nodes') or []]
        if None not in ids:continue
        bus_id=p.get('shared_net');bus=paths.get(bus_id)
        bus_ids=[identity(e) for e in bus.get('endpoint_nodes') or []] if bus else []
        if not any(k in rectangles for k in ids+bus_ids):continue
        if len(ids)!=2 or ids[0] not in nodes or ids[1] is not None or not bus:
            raise FigureError('layout_junction_binding','共享总线接点缺少明确的支线与主线绑定',path=key)
        old_branch=corners(originals[key]);old_bus=corners(originals[bus_id]);new_bus=corners(bus['points'])
        if len(old_branch)!=3 or len(old_bus)!=3 or len(new_bus)!=3:
            raise FigureError('layout_junction_scope','当前仅支持已绑定单折角支线与单折角总线',path=key)
        # The source endpoint must lie strictly inside the first bus segment.
        a,b=old_bus[:2];point=old_branch[-1];axis=0 if abs(a[1]-b[1])<.001 else 1
        if abs(a[1-axis]-b[1-axis])>.001 or abs(point[1-axis]-a[1-axis])>.15 or abs(b[axis]-a[axis])<.001:
            raise FigureError('layout_junction_binding','原支线端点不在已指定总线上',path=key)
        fraction=(point[axis]-a[axis])/(b[axis]-a[axis])
        if not 0<fraction<1:raise FigureError('layout_junction_binding','接点不是总线内部接点',path=key)
        a,b=new_bus[:2]
        if abs(a[1-axis]-b[1-axis])>.001:raise FigureError('layout_junction_scope','总线段方向发生变化',path=key)
        end=a[:];end[axis]=a[axis]+fraction*(b[axis]-a[axis])
        side,f=bind_port(nodes[ids[0]]['rect'],originals[key][0]);n=normals[side]
        start=port(rectangles.get(ids[0],nodes[ids[0]]['rect']),side,f)
        corner=[end[0],start[1]] if n[0] else [start[0],end[1]]
        old_delta=[old_branch[1][i]-old_branch[2][i] for i in (0,1)]
        length=math.hypot(*old_delta);terminal=[v/length for v in old_delta]
        stub=ARROW_LENGTH*size/8
        if sum((corner[i]-start[i])*n[i] for i in (0,1))+1e-7<stub or sum((corner[i]-end[i])*terminal[i] for i in (0,1))+1e-7<stub:
            raise FigureError('layout_junction_gap','总线支线没有足够箭头占位',path=key)
        route=[start,corner,end]
        if p.get('both'):route.insert(1,[start[i]+stub*n[i] for i in (0,1)])
        if p.get('arrow') or p.get('both'):route.insert(-1,[end[i]+stub*terminal[i] for i in (0,1)])
        p['points']=route;p['endpoint_nodes'][0]={'node':ids[0],'side':side,'fraction':f}
