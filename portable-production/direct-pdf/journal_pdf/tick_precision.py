"""Review decimal consistency within an explicitly identified axis."""
from __future__ import annotations
import re
from .common import FigureError

_NUMERIC = re.compile(r'^[+\-−]?\d+(?:\.\d+)?$')


def precision_notice(axis, values):
    """Flag mixed decimal places; do not infer scientific or categorical labels."""
    numbers=[v.strip().replace(' ', '').replace('\u00a0','').replace('\u202f','') for v in values]
    if len(numbers)<3 or not all(_NUMERIC.fullmatch(v) for v in numbers):
        return None
    places=[len(v.split('.',1)[1]) if '.' in v else 0 for v in numbers]
    if sum(p>0 for p in places)<2 or len(set(places))==1:
        return None
    return {'code':'axis_decimal_precision_mismatch','axis':axis,'labels':values,
            'decimal_places':places,'message':'同一数值轴的刻度小数位不一致；请核对是否统一，不自动改变数值或精度。'}


def scene_axis_notices(scene, groups):
    """Review explicit tick groups; warn when scene axes lack a grouping."""
    ticks={t['id']:t for t in scene.texts if t.get('role')=='axis-tick'}
    if not ticks:
        return []
    if groups is None:
        return [{'code':'axis_tick_group_missing','message':'场景包含坐标刻度但未声明轴分组，不能检查同轴小数位一致性。'}]
    if not isinstance(groups,list):
        raise FigureError('axis_tick_groups_invalid','axis_tick_groups 应为数组')
    seen=set();notices=[]
    for group in groups:
        if not isinstance(group,dict) or not isinstance(group.get('id'),str) or not isinstance(group.get('text_ids'),list):
            raise FigureError('axis_tick_groups_invalid','每个轴分组必须声明 id 与 text_ids')
        ids=group['text_ids']
        if not ids or any(not isinstance(i,str) or i not in ticks or i in seen for i in ids) or len(ids)!=len(set(ids)):
            raise FigureError('axis_tick_groups_invalid','轴分组含未知、重复或非刻度文字')
        seen.update(ids)
        notice=precision_notice(group['id'],[ticks[i]['measurement']['text'] for i in ids])
        if notice:notices.append(notice)
    if set(ticks)-seen:
        notices.append({'code':'axis_tick_group_missing','text_ids':sorted(set(ticks)-seen),'message':'存在未分组的轴刻度，不能完整检查同轴小数位。'})
    return notices
