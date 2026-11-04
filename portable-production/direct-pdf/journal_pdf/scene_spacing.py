"""Resolve safe local spacing conflicts before the public scene audit."""
from __future__ import annotations

from .common import FigureError, contains, intersects, segment_hits
from .fonts import position_text


def _node_id(endpoint):
    return endpoint.get('node') if isinstance(endpoint, dict) else endpoint


def apply_scene_spacing(scene):
    """Move an ungrouped text box and its bound orthogonal endpoints together."""
    owners = {t['owner']: t for t in scene.texts if t.get('owner')}
    boxes = [n for n in scene.nodes if not n['container'] and n['kind']=='rectangle' and n['id'] in owners
             and n.get('measurement_contract',{}).get('mode')=='tight']
    if len(boxes)<2:return
    for _ in range(len(boxes) * 2):
        conflict = None
        for i, a in enumerate(boxes):
            for b in boxes[i+1:]:
                if any({_node_id(e) for e in (p.get('endpoint_nodes') or [])}=={a['id'],b['id']} for p in scene.paths):
                    continue
                ar,br=a['rect'],b['rect'];stroke=(a['width']+b['width'])/2
                xover=min(ar[2],br[2])-max(ar[0],br[0]);yover=min(ar[3],br[3])-max(ar[1],br[1])
                if xover>0 and ar[3]<=br[1]+.15:conflict=(a,b,1,br[1]-ar[3]-stroke)
                elif xover>0 and br[3]<=ar[1]+.15:conflict=(b,a,1,ar[1]-br[3]-stroke)
                elif yover>0 and ar[2]<=br[0]+.15:conflict=(a,b,0,br[0]-ar[2]-stroke)
                elif yover>0 and br[2]<=ar[0]+.15:conflict=(b,a,0,ar[0]-br[2]-stroke)
                else:continue
                if conflict[3]<3*scene.size/8-.15:break
                conflict=None
            if conflict:break
        if not conflict:return
        before,target,axis,gap=conflict;delta=3*scene.size/8-gap
        old=target['rect'][:];moved=old[:];moved[axis]+=delta;moved[axis+2]+=delta
        if not contains([0,0,scene.width,scene.height],moved):raise FigureError('scene_spacing_reflow_required','紧凑框调整超出画板',id=target['id'])
        for container in (n for n in scene.nodes if n['container'] and contains(n['rect'],old)):
            if not contains(container['rect'],moved):raise FigureError('scene_spacing_reflow_required','紧凑框调整超出所属区域',id=target['id'])
        if any(n['id'] not in (before['id'],target['id']) and not n['container'] and intersects(moved,n['rect']) for n in scene.nodes):
            raise FigureError('scene_spacing_reflow_required','紧凑框调整会碰撞其他节点',id=target['id'])
        affected=[]
        for p in scene.paths:
            ends=p.get('endpoint_nodes') or [];indices=[i for i,e in enumerate(ends) if _node_id(e)==target['id']]
            if indices:
                if len(ends)!=2 or len(indices)!=1 or len(p['points'])<3:
                    raise FigureError('scene_spacing_reflow_required','连接拓扑无法安全联动',id=target['id'],path=p['id'])
                idx=0 if indices[0]==0 else -1;neighbor=1 if idx==0 else -2;points=[pt[:] for pt in p['points']]
                points[idx][axis]+=delta;points[neighbor][axis]+=delta
                if any(abs(u[0]-v[0])>.001 and abs(u[1]-v[1])>.001 for u,v in zip(points,points[1:])):
                    raise FigureError('scene_spacing_reflow_required','连接需要重新绕线',id=target['id'],path=p['id'])
                affected.append((p,points))
            elif any(segment_hits(a,b,moved,.5) for a,b in zip(p['points'],p['points'][1:])):
                raise FigureError('scene_spacing_reflow_required','调整后会压到其他连接',id=target['id'],path=p['id'])
        target['rect']=moved
        for text in scene.texts:
            if text['owner']==target['id']:
                text['x' if axis==0 else 'y']+=delta
                text['position']=position_text(text['measurement'],text['x'],text['y'],text['align'],text['position'].get('rotation',0))
        for p,points in affected:p['points']=points
        scene.layout_evidence.setdefault('automatic_box_spacing',[]).append({'before':before['id'],'moved':target['id'],'axis':'x' if axis==0 else 'y','delta_pt':delta,'paths':[p['id'] for p,_ in affected]})
    raise FigureError('scene_spacing_reflow_required','自动排布达到迭代上限')
