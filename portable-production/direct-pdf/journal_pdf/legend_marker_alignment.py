"""Center explicitly bound native point markers on their legend sample lines."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .common import FigureError

if TYPE_CHECKING:
    from .scene import Scene


def prepare_legend_marker_centers(scene: Scene,value):
    if not isinstance(value,list):raise FigureError('legend_marker_invalid','图例标记居中须为数组')
    nodes={n['id']:n for n in scene.nodes};paths={p['id']:p for p in scene.paths};seen=set();result=[]
    for item in value:
        if (not isinstance(item,dict) or set(item)-{'sample_path_id','marker_node_id','apply','reason'}
                or any(not isinstance(item.get(k),str) or not item[k] for k in ('sample_path_id','marker_node_id'))):
            raise FigureError('legend_marker_invalid','须绑定样线和原生标记')
        apply=item.get('apply',True);reason=item.get('reason');marker=nodes.get(item['marker_node_id']);path=paths.get(item['sample_path_id'])
        if (not isinstance(apply,bool) or (not apply and (not isinstance(reason,str) or not reason.strip()))
                or (apply and reason is not None) or item['marker_node_id'] in seen):
            raise FigureError('legend_marker_invalid','保留非居中位置须填写原因，且不能重复绑定标记')
        seen.add(item['marker_node_id'])
        if (not marker or marker.get('kind') not in ('ellipse','rectangle') or marker.get('container')
                or marker.get('fill') is None or not path or path.get('arrow') or path.get('both')
                or path.get('closed') or len(path.get('points',[]))!=2
                or abs(path['points'][0][1]-path['points'][1][1])>.01
                or abs(path['points'][0][0]-path['points'][1][0])<.01):
            raise FigureError('legend_marker_invalid','仅支持独立圆点或方块及水平原生样线')
        if any(t.get('owner')==marker['id'] for t in scene.texts):
            raise FigureError('legend_marker_invalid','带文字的节点不能作为图例标记移动')
        for p in scene.paths:
            ids=[v.get('node') if isinstance(v,dict) else v for v in (p.get('endpoint_nodes') or [])]
            if marker['id'] in ids:raise FigureError('legend_marker_invalid','有连接的节点不能作为图例标记移动')
        rect=marker['rect'];x=(rect[0]+rect[2])/2;y=(rect[1]+rect[3])/2
        line=path['points'];target_x=(line[0][0]+line[1][0])/2;target_y=(line[0][1]+line[1][1])/2
        if apply:
            dx=target_x-x;dy=target_y-y;marker['rect']=[rect[0]+dx,rect[1]+dy,rect[2]+dx,rect[3]+dy]
        result.append({'sample_path_id':path['id'],'marker_node_id':marker['id'],'applied':apply,'reason':reason})
    return result


def audit_legend_marker_centers(scene: Scene):
    nodes={n['id']:n for n in scene.nodes};paths={p['id']:p for p in scene.paths};checks=[];notes=[]
    for item in scene.legend_marker_centers:
        marker=nodes.get(item['marker_node_id']);path=paths.get(item['sample_path_id'])
        if marker is None or path is None:continue
        rect=marker['rect'];points=path['points'];dx=(rect[0]+rect[2]-points[0][0]-points[1][0])/2
        dy=(rect[1]+rect[3]-points[0][1]-points[1][1])/2
        entry={**item,'offset_pt':dx,'vertical_offset_pt':dy}
        checks.append(entry)
        if abs(dx)>.15 or abs(dy)>.15:
            notes.append({'code':'legend_marker_alignment_review',**entry,
                          'message':'图例标记偏离样线中点，需核对原图特殊组合及最终可辨性。'})
    return {'checks':checks,'notes':notes}
