"""Measured horizontal connections from a real source node to distinct targets."""
from __future__ import annotations

from .common import FigureError
from .editorial import ARROW_LENGTH, PAD_X, PAD_Y
from .fonts import position_text


def apply_multiport_groups(scene, nodes, groups):
    if not isinstance(groups,list):raise FigureError('multiport_schema','多端口组必须是列表')
    claimed=set()
    for group in groups:
        if not isinstance(group,dict) or set(group)-{'node','side','targets','both','arrow_style'}:
            raise FigureError('multiport_schema','多端口组参数无效')
        ident=group.get('node');targets=group.get('targets');side=group.get('side')
        if ident not in nodes or ident in claimed or side not in ('left','right') or not isinstance(targets,list) or len(targets)<2 or len(set(targets))!=len(targets) or ident in targets or any(x not in nodes for x in targets):
            raise FigureError('multiport_schema','源节点及目标节点须存在且互不重复')
        if not isinstance(group.get('both',False),bool):raise FigureError('multiport_schema','双向箭头须为布尔值')
        style=group.get('arrow_style','standard')
        if style not in ('standard','block-outline'):raise FigureError('multiport_schema','未知箭头类型')
        source=nodes[ident];parts=[nodes[x] for x in targets]
        if source['container'] or source['kind']!='rectangle' or any(n['container'] or n['kind']!='rectangle' for n in parts):
            raise FigureError('multiport_node','多端口仅接受真实普通框')
        text=next((t for t in scene.texts if t.get('owner')==ident),None)
        if text is None:raise FigureError('multiport_text','源框必须有可测量文字')
        ys=[(n['rect'][1]+n['rect'][3])/2 for n in parts]
        if len(set(round(y,5) for y in ys))!=len(ys):raise FigureError('multiport_ambiguous','目标中心重合，无法安排独立直线')
        scale=scene.size/8;natural=text['measurement'];width=natural['width']+2*PAD_X*scale
        height=max(natural['height']+2*PAD_Y*scale,max(ys)-min(ys)+8*scale)
        center=(max(ys)+min(ys))/2;left=source['rect'][0];top=center-height/2
        source['rect']=[left,top,left+width,top+height]
        source['measurement_contract']={'mode':'multiport','targets':list(targets),'side':side}
        text['x']=left+width/2;text['y']=center;text['position']=position_text(natural,text['x'],center,text['align'],0)
        for target,y in zip(parts,ys):
            x0=source['rect'][2] if side=='right' else source['rect'][0]
            x1=target['rect'][0] if side=='right' else target['rect'][2]
            direction=1 if side=='right' else -1
            if (x1-x0)*direction < 2*ARROW_LENGTH*scale:
                raise FigureError('multiport_gap','直连端点之间不足两个箭头末段')
            fraction=(y-top)/height
            pts=[[x0,y],[x0+direction*ARROW_LENGTH*scale,y],[x1-direction*ARROW_LENGTH*scale,y],[x1,y]]
            scene.line('multiport:'+ident+':'+target['id'],pts,arrow=True,both=group.get('both',False),exact_terminal=True,
                       endpoint_nodes=[{'node':ident,'side':side,'fraction':fraction},target['id']],arrow_style=style)
        scene.layout_evidence.setdefault('multiport_groups',[]).append({'node':ident,'side':side,'targets':list(targets),'port_padding_pt':4*scale})
        claimed.add(ident)
