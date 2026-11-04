"""Use straight connections when two free rectangular ports can align safely."""
from __future__ import annotations
from copy import deepcopy
from .editorial import ARROW_LENGTH
from .scene import audit_scene


def straighten_connections(scene):
    """Align free ports, retaining node identities, direction and arrow endpoints."""
    nodes={n['id']:n for n in scene.nodes}
    baseline={(i.get('code'),i.get('id'),i.get('path')) for i in audit_scene(scene)}
    for path in scene.paths:
        ends=path.get('endpoint_nodes') or []
        if len(ends)!=2 or not all(isinstance(v,str) and v in nodes for v in ends) or path.get('shared_net'):
            continue
        if len(path['points'])<=2:continue
        first,last=nodes[ends[0]],nodes[ends[1]];a,b=first['rect'],last['rect']
        if first['container'] or last['container'] or first['kind']!='rectangle' or last['kind']!='rectangle':continue
        start,end=path['points'][0],path['points'][-1];eps=.16
        if abs(start[1]-a[3])<eps and abs(end[1]-b[1])<eps and a[3]<b[1]:
            lo=max(a[0],b[0])+1;hi=min(a[2],b[2])-1
            if lo>hi:continue
            coord=min(max(start[0],lo),hi);u=[coord,a[3]];v=[coord,b[1]];sides=['bottom','top'];axis=0
        elif abs(start[1]-a[1])<eps and abs(end[1]-b[3])<eps and b[3]<a[1]:
            lo=max(a[0],b[0])+1;hi=min(a[2],b[2])-1
            if lo>hi:continue
            coord=min(max(start[0],lo),hi);u=[coord,a[1]];v=[coord,b[3]];sides=['top','bottom'];axis=0
        else:continue
        length=abs(v[1]-u[1]);stub=ARROW_LENGTH*scene.size/8
        if path['both'] and length<2*stub or path['arrow'] and length<stub:continue
        sign=1 if v[1]>u[1] else -1
        pts=[u]
        if path['both']:pts.append([coord,u[1]+sign*stub])
        if path['arrow']:pts.append([coord,v[1]-sign*stub])
        pts.append(v)
        if len(pts)>2 and any(pts[i]==pts[i+1] for i in range(len(pts)-1)):continue
        old=deepcopy(path)
        path['points']=pts
        path['endpoint_nodes']=[{'node':ends[0],'side':sides[0],'fraction':(coord-a[0])/(a[2]-a[0])},
                                {'node':ends[1],'side':sides[1],'fraction':(coord-b[0])/(b[2]-b[0])}]
        issues={(i.get('code'),i.get('id'),i.get('path')) for i in audit_scene(scene)}
        if issues-baseline:path.clear();path.update(old)
        else:scene.layout_evidence.setdefault('straightened_connections',[]).append({'path':path['id'],'axis':'vertical'})


def align_connected_nodes(scene, declarations):
    """Align a rightward node to a free source port and update its other paths."""
    from .common import FigureError, contains
    from .fonts import position_text
    baseline={(i.get('code'),i.get('id'),i.get('path')) for i in audit_scene(scene)}
    for item in declarations:
        nodes={n['id']:n for n in scene.nodes}; paths={p['id']:p for p in scene.paths}
        source=nodes.get(item.get('source'));target=nodes.get(item.get('target'));path=paths.get(item.get('path'))
        if not source or not target or not path or path.get('endpoint_nodes')!=[source['id'],target['id']] or source['container'] or target['container']:
            raise FigureError('align_connection_invalid','直线连接须明确普通源框、目标框和原连接')
        fraction=item.get('source_fraction',.5)
        if not isinstance(fraction,(int,float)) or not 0<fraction<1:raise FigureError('align_connection_invalid','源端口位置无效')
        a,b=source['rect'],target['rect']; y=a[1]+(a[3]-a[1])*fraction;dy=y-(b[1]+b[3])/2
        if b[0] <= a[2]+2*ARROW_LENGTH*scene.size/8:raise FigureError('align_connection_invalid','框距不足以保持双向箭头')
        snapshot=deepcopy((scene.nodes,scene.texts,scene.paths))
        old=b[:];b[1]+=dy;b[3]+=dy
        for container in (n for n in scene.nodes if n['container'] and contains(n['rect'],old)):
            if not contains(container['rect'],b):raise FigureError('align_connection_outside','对齐后目标框超出分区')
        for text in scene.texts:
            if text['owner']==target['id']:
                text['y']+=dy;text['position']=position_text(text['measurement'],text['x'],text['y'],text['align'],text['position'].get('rotation',0))
        for other in scene.paths:
            if other is path:continue
            ends=other.get('endpoint_nodes') or []
            indices=[i for i,e in enumerate(ends) if (e.get('node') if isinstance(e,dict) else e)==target['id']]
            if not indices:continue
            if len(ends)!=2 or len(indices)!=1 or len(other['points'])<3:raise FigureError('align_connection_reroute','其他连接不能安全联动')
            idx=0 if indices[0]==0 else -1;adj=1 if idx==0 else -2
            other['points'][idx][1]+=dy;other['points'][adj][1]+=dy
            if any(abs(u[0]-v[0])>.001 and abs(u[1]-v[1])>.001 for u,v in zip(other['points'],other['points'][1:])):
                raise FigureError('align_connection_reroute','其他连接需要重新绕线')
        stub=ARROW_LENGTH*scene.size/8; start=[a[2],y];end=[b[0],y];pts=[start]
        if path['both']:pts.append([start[0]+stub,y])
        if path['arrow']:pts.append([end[0]-stub,y])
        pts.append(end);path['points']=pts
        path['endpoint_nodes']=[{'node':source['id'],'side':'right','fraction':fraction},{'node':target['id'],'side':'left','fraction':.5}]
        issues={(i.get('code'),i.get('id'),i.get('path')) for i in audit_scene(scene)}
        if issues-baseline:
            scene.nodes,scene.texts,scene.paths=snapshot
            raise FigureError('align_connection_collision','直线对齐导致新的碰撞或端口问题',issues=list(issues-baseline))
        scene.layout_evidence.setdefault('aligned_connections',[]).append({'path':path['id'],'target':target['id'],'delta_y_pt':dy})
