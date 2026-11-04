"""Source layout candidates and explicit adaptation to existing measured groups."""
from copy import deepcopy
import math
from .common import FigureError, contains


def extract_layout_relations(objects, source_sha256, page_id, unit):
    """Geometry is evidence, not automatic permission to align or merge nodes."""
    texts=[o for o in objects if o.get('text') and o.get('rect')]
    boxes=[]
    for o in objects:
        rect=o.get('rect')
        if not rect or o.get('shape_hint')!='rectangle' or rect[2]<=rect[0] or rect[3]<=rect[1]:continue
        members=[t['id'] for t in texts if t['id']!=o['id'] and contains(rect,t['rect'])]
        if not members:continue
        # A container enclosing other text rectangles is not an ordinary node.
        if any(p is not o and p.get('shape_hint')=='rectangle' and p.get('rect') and
               contains(rect,p['rect']) and p['rect']!=rect and
               any(contains(p['rect'],t['rect']) for t in texts) for p in objects):continue
        if any(set(members)==set(p['text_refs']) and max(abs(a-b) for a,b in zip(rect,p['rect']))<max(.2,(rect[3]-rect[1])*.1) for p in boxes):continue
        boxes.append({'id':o['id'],'rect':list(rect),'text_refs':members})
    candidates=[]
    if len(boxes)>250:
        return {'source_sha256':source_sha256,'page_id':page_id,'unit':unit,'nodes':boxes,
                'candidates':[],'status':'budget-exceeded'}
    for i,a in enumerate(boxes):
        for b in boxes[i+1:]:
            ar,br=a['rect'],b['rect'];w=min(ar[2]-ar[0],br[2]-br[0]);h=min(ar[3]-ar[1],br[3]-br[1])
            xgap=max(ar[0],br[0])-min(ar[2],br[2]);ygap=max(ar[1],br[1])-min(ar[3],br[3])
            for axis,gap,offset,extent in [('column',ygap,abs((ar[0]+ar[2]-br[0]-br[2])/2),w),
                                           ('row',xgap,abs((ar[1]+ar[3]-br[1]-br[3])/2),h)]:
                if gap<0 or offset>extent*.15:continue
                dimension=0 if axis=='column' else 1
                ordered=sorted([a,b],key=lambda n:n['rect'][1-dimension])
                candidates.append({'id':f'{page_id}:layout:{len(candidates)}','axis':axis,
                    'nodes':[n['id'] for n in ordered],'status':'needs-semantic-confirmation',
                    'basis':{'centre_offset':offset,'relative_offset':offset/extent,
                             'extent_difference':abs((ar[dimension+2]-ar[dimension])-(br[dimension+2]-br[dimension])),
                             'source_gap':gap,'unit':unit}})
    return {'source_sha256':source_sha256,'page_id':page_id,'unit':unit,'nodes':boxes,
            'candidates':candidates,'status':'candidates-ready'}


def prepare_layout_relations(spec, reg=None, size=8):
    """Bind reviewed candidates and reuse measured groups with safe port adaptation."""
    request=spec.get('source_layout')
    if request is None:return spec
    source=request.get('source',{});evidence=request.get('evidence',{})
    if (source.get('sha256')!=evidence.get('source_sha256') or
        not any(s.get('path')==source.get('path') and s.get('sha256')==source.get('sha256') for s in spec.get('sources',[]))):
        raise FigureError('layout_source_mismatch','行列候选的来源哈希与任务不一致')
    result=deepcopy(spec);nodes={n['id']:n for n in result['nodes']}
    mapping=request.get('node_bindings',{});native={n['id'] for n in evidence.get('nodes',[])}
    if any(k not in native or v not in nodes for k,v in mapping.items()) or len(set(mapping.values()))!=len(mapping):
        raise FigureError('layout_node_binding','原图节点与当前节点须唯一对应')
    candidates={c['id']:c for c in evidence.get('candidates',[])}
    claimed={k for g in result.get('measured_groups',[])+result.get('measured_node_groups',[]) for k in g.get('nodes',[])}
    added=[];connected=False
    for approval in request.get('confirmed',[]):
        c=candidates.get(approval.get('candidate'));origin=approval.get('origin')
        if not c or not approval.get('basis') or not isinstance(origin,list) or len(origin)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in origin):
            raise FigureError('layout_confirmation','行列确认须指定候选、语义依据与当前布局锚点')
        ids=[mapping.get(k) for k in c['nodes']]
        if None in ids or claimed.intersection(ids):
            raise FigureError('layout_joint_binding','缺少对象绑定，或分组相互依赖，须联合求解')
        def node(e):return e.get('node') if isinstance(e,dict) else e
        linked=any(node(e) in ids for p in result.get('paths',[]) for e in p.get('endpoint_nodes') or []) or any(
            p.get('from') in ids or p.get('to') in ids for p in result.get('connections',[]))
        if linked and reg is None:
            raise FigureError('layout_connections_require_joint_plan','已有行列路线但连接仍需端口联动绑定',nodes=ids,candidate=c['id'])
        connected=connected or linked
        for k in ids:
            if nodes[k].get('container') or nodes[k].get('shape','rectangle')!='rectangle' or not nodes[k].get('text'):
                raise FigureError('layout_node_binding','测量行列仅接受有文字的普通矩形')
        claimed.update(ids)
        group={'id':'source-layout:'+c['id'],'axis':c['axis'],'nodes':ids,'origin':origin,'equal_width':True}
        result.setdefault('measured_groups',[]).append(group);added.append(group)
    if connected:
        from .layout_relation_paths import measured_rectangles, adapt_group_paths
        rectangles=measured_rectangles(result,added,reg,size)
        adapt_group_paths(result,rectangles,size)
    for group in added:
        for k in group['nodes']:nodes[k].pop('rect',None)
    return result
