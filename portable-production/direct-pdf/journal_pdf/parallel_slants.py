"""Compare explicitly related diagonal arrows without changing connection geometry."""
from __future__ import annotations
import math
from .common import FigureError

def parse_parallel_slants(value):
    if not isinstance(value,list):raise FigureError('parallel_slant_invalid','斜线组须为数组')
    for item in value:
        if (not isinstance(item,dict) or set(item)!={'path_ids'} or not isinstance(item['path_ids'],list)
                or len(item['path_ids'])<2 or any(not isinstance(x,str) or not x for x in item['path_ids'])
                or len(set(item['path_ids']))!=len(item['path_ids'])):
            raise FigureError('parallel_slant_invalid','须明确绑定至少两条不同的斜箭头')
    return [{'path_ids':list(item['path_ids'])} for item in value]

def audit_parallel_slants(scene):
    paths={p['id']:p for p in scene.paths};checks=[];notes=[];issues=[]
    for item in scene.parallel_slant_checks:
        angles=[]
        for identifier in item['path_ids']:
            path=paths.get(identifier);points=path.get('points',[]) if path else []
            if not path or not path.get('arrow') or len(points)!=2:
                issues.append({'code':'parallel_slant_path_invalid','id':identifier});break
            dx=abs(points[1][0]-points[0][0]);dy=abs(points[1][1]-points[0][1])
            if dx<1e-6 or dy<1e-6:
                issues.append({'code':'parallel_slant_path_invalid','id':identifier});break
            angles.append(math.degrees(math.atan2(dx,dy)))
        else:
            spread=max(angles)-min(angles);row={'path_ids':item['path_ids'],'angles_degrees':angles,'spread_degrees':spread}
            checks.append(row)
            if spread>.5:notes.append({'code':'parallel_slant_review',**row,'message':'同组斜线倾斜不一致，须核对原图关系和空间。'})
    return {'checks':checks,'issues':issues,'notes':notes}
