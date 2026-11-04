"""Expand explicitly confirmed shared prefixes and final arrow stubs."""
from copy import deepcopy
import math
from .common import FigureError
from .editorial import ARROW_LENGTH


def prepare_bound_paths(spec, size):
    result=deepcopy(spec)
    paths=result.setdefault('paths',[])
    for group in result.get('shared_branch_groups',[]):
        ids=group.get('paths',[]);junction=group.get('junction')
        selected=[p for p in paths if p['id'] in ids]
        if len(ids)<2 or len(set(ids))!=len(ids) or len(selected)!=len(ids):
            raise FigureError('shared_branch_binding','支线须绑定不同的真实路径')
        start=selected[0]['points'][0]
        for path in selected:
            a,b=path['points'][:2]
            if a!=start or not isinstance(junction,list) or len(junction)!=2:
                raise FigureError('shared_branch_binding','支线没有共同起点')
            length=math.dist(a,b)
            if length<=0 or abs(math.dist(a,junction)+math.dist(junction,b)-length)>.01 or math.dist(a,junction)<.01:
                raise FigureError('shared_branch_binding','接点不在每条原路径首段内')
        paths.append({'id':group['id'],'points':[start[:],junction[:]],'arrow':False,
                      'endpoint_nodes':[selected[0]['endpoint_nodes'][0],None],
                      'shared_net':group['id'],'semantic_role':'trunk'})
        for path in selected:
            path['points'][0]=junction[:]
            if path['points'][0]==path['points'][1]:path['points'].pop(1)
            path['endpoint_nodes'][0]=None
    for path in paths:
        if not path.pop('auto_terminal',False):continue
        if not (path.get('arrow') or path.get('both')) or len(path['points'])<2:
            raise FigureError('arrow_terminal_plan','自动末段只适用于已声明箭头')
        from .connection_layout import terminal_points
        path['points']=terminal_points(path['points'],arrow=path.get('arrow',False),both=path.get('both',False),
                                       size=size if path.get('arrow_style')=='block-outline' else 8)
        path['exact_terminal']=True
    return result
