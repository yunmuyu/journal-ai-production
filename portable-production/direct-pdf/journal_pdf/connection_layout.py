"""Generate confirmed connections with shared shape ports and arrow dimensions."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import math
from typing import TYPE_CHECKING, TypedDict

from .boundary_ports import JsonValue, Side, node_boundary_point
from .common import FigureError
from .editorial import ARROW_LENGTH

if TYPE_CHECKING:
    from .scene import Scene


class Node(TypedDict):
    id: str
    rect: list[float]
    kind: str


@dataclass(frozen=True, slots=True)
class RoutedConnection:
    points: list[list[float]]
    endpoints: list[dict[str, JsonValue]]


def terminal_points(points: list[list[float]], *, arrow: bool, both: bool, size: float) -> list[list[float]]:
    """Insert exact final-size stubs without changing the original path or ends."""
    result=deepcopy(points)
    required=ARROW_LENGTH*size/8
    if not arrow and not both:return result
    if len(result)==2 and both and math.dist(*result)<2*required-1e-5:
        raise FigureError('arrow_terminal_space','双向连接需预留两个箭头末段',actual_pt=math.dist(*result),required_pt=2*required)
    for start in ([False,True] if both else [False]):
        a,b=(result[1],result[0]) if start else (result[-2],result[-1])
        length=math.dist(a,b)
        if length<required-1e-5:
            raise FigureError('arrow_terminal_space','生成连接的末段空间不足，须调整布局',actual_pt=length,required_pt=required,
                              additional_space_pt=required-length,at_start=start)
        if length>required+1e-5:
            point=[b[i]+(a[i]-b[i])*required/length for i in (0,1)]
            result.insert(1 if start else len(result)-1,point)
    return result


def route_connection(nodes: Mapping[str,Node], request: Mapping[str,JsonValue], size: float) -> RoutedConnection:
    """Bind declared ends, route facing ports, and leave topology unchanged."""
    source,target=request.get('from'),request.get('to')
    if not isinstance(source,str) or not isinstance(target,str) or source not in nodes or target not in nodes:
        raise FigureError('edge_endpoint','连接须引用真实源节点和目标节点',connection=request.get('id'))
    a,b=nodes[source],nodes[target]
    start_side,end_side=request.get('from_port'),request.get('to_port')
    if start_side not in ('left','right','top','bottom') or end_side not in ('left','right','top','bottom'):
        raise FigureError('connection_port_required','生成连接须明确两端方向',connection=request.get('id'))
    fa,fb=request.get('from_fraction',.5),request.get('to_fraction',.5)
    start=list(node_boundary_point(tuple(a['rect']),a['kind'],start_side,fa))
    end=list(node_boundary_point(tuple(b['rect']),b['kind'],end_side,fb))
    points=[start,end];terminal_size=size if request.get('arrow_style')=='block-outline' else 8
    if abs(start[0]-end[0])>.001 and abs(start[1]-end[1])>.001:
        horizontal=start_side in ('left','right') and end_side in ('left','right')
        vertical=start_side in ('top','bottom') and end_side in ('top','bottom')
        if not (horizontal or vertical) or start_side==end_side:
            raise FigureError('connection_route_binding','复杂绕线须提供已确认的路径，不能猜测拓扑',connection=request.get('id'))
        axis=0 if horizontal else 1
        sign=1 if start_side in ('right','bottom') else -1
        gap=(end[axis]-start[axis])*sign;required=2*ARROW_LENGTH*terminal_size/8
        if gap<required:
            raise FigureError('connection_channel_space','折线两端箭头通道不足',connection=request.get('id'),
                              actual_pt=gap,required_pt=required,additional_space_pt=required-gap)
        middle=(start[axis]+end[axis])/2
        first=start[:];first[axis]=middle
        last=end[:];last[axis]=middle
        points=[start,first,last,end]
    points=terminal_points(points,arrow=bool(request.get('arrow')),both=bool(request.get('both')),size=terminal_size)
    endpoints=[{'node':source,'side':start_side,'fraction':fa},{'node':target,'side':end_side,'fraction':fb}]
    return RoutedConnection(points,endpoints)


def generate_connection(scene: Scene, nodes: Mapping[str,Node], request: Mapping[str,JsonValue]) -> None:
    """Add a generated path to the existing Scene backend."""
    routed=route_connection(nodes,request,scene.size)
    _append(scene,request,routed)


def _append(scene: Scene, request: Mapping[str,JsonValue], routed: RoutedConnection) -> None:
    scene.line(request['id'],routed.points,request.get('arrow',False),request.get('both',False),request.get('dash'),
               exact_terminal=bool(request.get('arrow') or request.get('both')),endpoint_nodes=routed.endpoints,
               shared_net=request.get('shared_net'),semantic_role=request.get('semantic_role','connection'),
               arrow_style=request.get('arrow_style','standard'))
    scene.paths[-1]['generated_connection']=deepcopy(request)


def generate_connections(scene: Scene, nodes: Mapping[str,Node], requests: list[dict[str,JsonValue]]) -> None:
    """Validate all independent generated routes before adding any path."""
    ready=[];issues=[]
    for request in requests:
        try:ready.append((request,route_connection(nodes,request,scene.size)))
        except FigureError as error:issues.append(error.as_dict()|{'id':request.get('id')})
    if issues:raise FigureError('connection_generation_failed','生成连接存在未满足的约束',issues=issues)
    for request,routed in ready:_append(scene,request,routed)
