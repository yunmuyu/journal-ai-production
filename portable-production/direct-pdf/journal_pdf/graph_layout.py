"""Generic semantic graph -> measured Scene, using the existing editorial rules.
A bounded orthogonal route planner; feasibility, NOT a claim of global optimality.
"""
from __future__ import annotations
import heapq,math
from .common import FigureError,segment_hits,intersects,PT_PER_MM
from .scene import Scene,port
from .editorial import PAD_X,PAD_Y,ARROW_LENGTH,ARROW_DEPTH,ARROW_BOUNDARY_GAP,LABEL_CLEARANCE,diamond_size,display_content

BRANCH_BUS_LEG = 2 * PT_PER_MM
BRANCH_BOUNDARY_GAP = BRANCH_BUS_LEG + ARROW_BOUNDARY_GAP


def _topological(nodes,edges):
    ids=[n['id'] for n in nodes];deg={i:0 for i in ids};nxt={i:[] for i in ids}
    for e in edges:
        if e.get('return_edge'):continue
        nxt[e['from']].append(e['to']);deg[e['to']]+=1
    ready=sorted(i for i in ids if not deg[i]);rank={i:0 for i in ids};seen=[]
    while ready:
        a=ready.pop(0);seen.append(a)
        for b in nxt[a]:
            rank[b]=max(rank[b],rank[a]+1);deg[b]-=1
            if deg[b]==0:ready.append(b)
    if len(seen)!=len(ids):raise FigureError('graph_cycle_requires_semantics','循环需明确标记返回边；不自行反转箭头',nodes=[i for i in ids if deg[i]])
    return rank


def _route(start,end,obstacles,xs,ys):
    """Rectilinear visibility grid: limits enforce predictable running time."""
    xs=sorted(set([round(float(x),5) for x in [*xs,start[0],end[0]]]));ys=sorted(set([round(float(y),5) for y in [*ys,start[1],end[1]]]))
    if len(xs)*len(ys)>22000:raise FigureError('route_budget','路由网格超过候选上限；需分组或专用布局')
    s=(xs.index(round(start[0],5)),ys.index(round(start[1],5)));t=(xs.index(round(end[0],5)),ys.index(round(end[1],5)))
    dist={(s[0],s[1],-1):0.};heap=[(0.,s[0],s[1],-1)];prev={};best=None
    while heap:
        cost,i,j,d=heapq.heappop(heap);key=(i,j,d)
        if cost!=dist.get(key):continue
        if (i,j)==t:best=key;break
        for di,dj,nd in [(1,0,0),(-1,0,0),(0,1,1),(0,-1,1)]:
            ii,jj=i+di,j+dj
            if not (0<=ii<len(xs) and 0<=jj<len(ys)):continue
            a,b=[xs[i],ys[j]],[xs[ii],ys[jj]]
            if any(segment_hits(a,b,r,.3) for r in obstacles):continue
            c=cost+math.dist(a,b)+(5 if d>=0 and d!=nd else 0)
            nk=(ii,jj,nd)
            if c<dist.get(nk,math.inf):dist[nk]=c;prev[nk]=key;heapq.heappush(heap,(c,ii,jj,nd))
    if best is None:raise FigureError('graph_route_blocked','无避开节点的正交连线方案')
    points=[]
    while best in prev:
        points.append([xs[best[0]],ys[best[1]]]);best=prev[best]
    points.append([xs[best[0]],ys[best[1]]]);points.reverse()
    out=[]
    for p in points:
        if len(out)>1 and (abs(out[-2][0]-out[-1][0])<1e-5 and abs(out[-1][0]-p[0])<1e-5 or abs(out[-2][1]-out[-1][1])<1e-5 and abs(out[-1][1]-p[1])<1e-5):out[-1]=p
        else:out.append(p)
    return out


def graph(spec,reg,size):
    nodes=spec.get('nodes',[]);edges=spec.get('edges',[])
    if not nodes or len(nodes)>80 or len(edges)>150:raise FigureError('graph_size','通用图当前支持1—80节点、最多150条边')
    ids=[n['id'] for n in nodes]
    if len(ids)!=len(set(ids)):raise FigureError('graph_duplicate_node','节点ID重复')
    for e in edges:
        if e.get('from') not in ids or e.get('to') not in ids:raise FigureError('graph_missing_endpoint','连接端点不存在',edge=e.get('id'))
        if e['from']==e['to']:raise FigureError('self_loop_requires_adapter','自环需要单独专业布局，不画成零长连接')
    direction=spec.get('direction','TB')
    if direction not in ('TB','LR'):raise FigureError('graph_direction','方向必须TB或LR')
    rank=_topological(nodes,edges);ranks=sorted(set(rank.values()));meas={};dim={};scale=size/8
    for n in nodes:
        m=reg.measure(display_content(n['text'],'label'),size);meas[n['id']]=m;kind=n.get('shape','rectangle')
        if kind=='diamond':w,h,_=diamond_size(m['width'],m['height'],size)
        elif kind=='ellipse':w,h=(m['width']+9*scale)*1.42,(m['height']+5.4*scale)*1.42
        elif kind=='inputOutput':w,h=m['width']+2*PAD_X*scale+8,m['height']+2*PAD_Y*scale
        else:w,h=m['width']+2*PAD_X*scale,m['height']+2*PAD_Y*scale
        dim[n['id']]=(w,h)
    # Same semantic rank: normal boxes share height/width where it doesn't corrupt diamond calibration.
    for r in ranks:
        group=[n for n in nodes if rank[n['id']]==r and n.get('shape','rectangle')=='rectangle']
        if group:
            if direction=='TB':
                h=max(dim[n['id']][1] for n in group)
                for n in group:dim[n['id']]=(dim[n['id']][0],h)
            else:
                w=max(dim[n['id']][0] for n in group)
                for n in group:dim[n['id']]=(w,dim[n['id']][1])
    labels={id(e):reg.measure(display_content(e['label'],'edge-label'),size) for e in edges if e.get('label')}
    labelw=max([m['width'] for m in labels.values()]+[0])
    native_edges=[e for e in edges if not e.get('return_edge') and not e.get('from_port') and not e.get('to_port')
                  and not e.get('label') and e.get('arrow',True) and not e.get('both') and not e.get('dash')
                  and rank[e['to']]==rank[e['from']]+1]
    incoming={};outgoing={}
    for e in native_edges:
        incoming.setdefault(e['to'],[]).append(e);outgoing.setdefault(e['from'],[]).append(e)
    merge_groups={target:group for target,group in incoming.items() if len(group)>=2}
    merge_edges={id(e) for group in merge_groups.values() for e in group}
    fanout_groups={source:[e for e in group if id(e) not in merge_edges] for source,group in outgoing.items()}
    fanout_groups={source:group for source,group in fanout_groups.items() if len(group)>=2}
    rank_gaps={r:ARROW_BOUNDARY_GAP for r in ranks[:-1]}
    for source in fanout_groups:rank_gaps[rank[source]]=max(rank_gaps[rank[source]],BRANCH_BOUNDARY_GAP)
    for target in merge_groups:rank_gaps[rank[target]-1]=max(rank_gaps[rank[target]-1],BRANCH_BOUNDARY_GAP)
    for e in edges:
        if not e.get('label') or e.get('return_edge'):continue
        source_rank,target_rank=rank[e['from']],rank[e['to']]
        if abs(target_rank-source_rank)!=1:continue
        label_axis=labels[id(e)]['height' if direction=='TB' else 'width']
        boundary_rank=min(source_rank,target_rank)
        rank_gaps[boundary_rank]=max(rank_gaps[boundary_rank],label_axis+2*LABEL_CLEARANCE+ARROW_DEPTH)
    sibling_gap=max(ARROW_BOUNDARY_GAP,12*scale);margin=max(12.,labelw+10 if any(e.get('return_edge') and e.get('label') for e in edges) else 12.)
    lengths={};thick={}
    for r in ranks:
        row=[n for n in nodes if rank[n['id']]==r]
        lengths[r]=sum(dim[n['id']][0 if direction=='TB' else 1] for n in row)+(len(row)-1)*sibling_gap
        thick[r]=max(dim[n['id']][1 if direction=='TB' else 0] for n in row)
    cross=max(lengths.values());along=sum(thick.values())+sum(rank_gaps.values())
    s=Scene(reg,size);s.template='semantic-graph';placed={};primary=margin
    for r in ranks:
        secondary=margin+(cross-lengths[r])/2
        for n in [q for q in nodes if rank[q['id']]==r]:
            w,h=dim[n['id']]
            if direction=='TB':x,y=secondary,primary+(thick[r]-h)/2
            else:x,y=primary+(thick[r]-w)/2,secondary
            placed[n['id']]=s.box(n['id'],n['text'],x,y,w,h,n.get('shape','rectangle'))
            secondary+=(w if direction=='TB' else h)+sibling_gap
        primary+=thick[r]+rank_gaps.get(r,0)
    width,height=(cross+2*margin,along+2*margin) if direction=='TB' else (along+2*margin,cross+2*margin)
    xs=[2.,width-2];ys=[2.,height-2]
    for n in placed.values():
        x,y,r,b=n['rect'];xs +=[x-6,r+6,(x+r)/2];ys +=[y-6,b+6,(y+b)/2]
    route_records=[];handled_edges=set();edge_order={id(e):idx for idx,e in enumerate(edges)}
    for source_id,group in fanout_groups.items():
        source=placed[source_id];source_port=port(source,'bottom');targets=[placed[e['to']] for e in group]
        bus_y=source_port[1]+BRANCH_BUS_LEG;target_ports=[port(target,'top') for target in targets]
        identifiers=[e.get('id','edge-'+str(edge_order[id(e)]+1)) for e in group]
        s.line(identifiers[0]+':fanout-trunk',[source_port,[source_port[0],bus_y]])
        left=min(p[0] for p in target_ports);right=max(p[0] for p in target_ports)
        if right-left>1e-4:s.line(identifiers[0]+':fanout-bus',[[left,bus_y],[right,bus_y]])
        for e,target_port,ident in zip(group,target_ports,identifiers):
            s.line(ident,[[target_port[0],bus_y],target_port],arrow=True,exact_terminal=True,
                   endpoint_nodes=[e['from'],e['to']])
            route_records.append({'edge':ident,'from':e['from'],'to':e['to'],'from_port':'bottom','to_port':'top','return_edge':False,'branch_group':'fanout'})
            handled_edges.add(id(e))
    for target_id,group in merge_groups.items():
        target=placed[target_id];target_port=port(target,'top');sources=[placed[e['from']] for e in group]
        source_ports=[port(source,'bottom') for source in sources];bus_y=max(p[1] for p in source_ports)+BRANCH_BUS_LEG
        identifiers=[e.get('id','edge-'+str(edge_order[id(e)]+1)) for e in group]
        for e,source_port,ident in zip(group,source_ports,identifiers):
            s.line(ident,[source_port,[source_port[0],bus_y]])
            handled_edges.add(id(e))
        left=min(p[0] for p in source_ports);right=max(p[0] for p in source_ports)
        if right-left>1e-4:s.line(identifiers[0]+':merge-bus',[[left,bus_y],[right,bus_y]])
        outlet=identifiers[0]+':merge-outlet';mid=(left+right)/2
        outlet_points=[[target_port[0],bus_y],target_port] if left<=target_port[0]<=right else [[mid,bus_y],[target_port[0],bus_y],target_port]
        s.line(outlet,outlet_points,arrow=True,exact_terminal=True,
               endpoint_nodes=[group[0]['from'],group[0]['to']])
        for e,ident in zip(group,identifiers):
            route_records.append({'edge':ident,'from':e['from'],'to':e['to'],'from_port':'bottom','to_port':'top','return_edge':False,'branch_group':'merge','merge_outlet':outlet})
    for idx,e in enumerate(edges):
        if id(e) in handled_edges:continue
        src,dst=placed[e['from']],placed[e['to']]
        if e.get('return_edge'):ss,ts=('left','left') if direction=='TB' else ('top','top')
        else:ss,ts=('bottom','top') if direction=='TB' else ('right','left')
        ss=e.get('from_port',ss);ts=e.get('to_port',ts)
        if ss not in ('left','right','top','bottom') or ts not in ('left','right','top','bottom'):raise FigureError('graph_port','菱形/普通框只接受真实四中点端口')
        a,b=port(src,ss),port(dst,ts);vec={'left':[-1,0],'right':[1,0],'top':[0,-1],'bottom':[0,1]}
        source_stub=4.5;target_stub=ARROW_BOUNDARY_GAP if e.get('arrow',True) else 4.5
        u=[a[i]+vec[ss][i]*source_stub for i in range(2)];v=[b[i]+vec[ts][i]*target_stub for i in range(2)]
        aligned=(abs(a[0]-b[0])<1e-5 and ss=='bottom' and ts=='top' and b[1]>a[1]) or (abs(a[1]-b[1])<1e-5 and ss=='right' and ts=='left' and b[0]>a[0])
        unrelated=[n['rect'] for name,n in placed.items() if name not in (e['from'],e['to'])]
        if aligned and not any(segment_hits(a,b,r,.5) for r in unrelated):pts=[a,b]
        else:
            clearance=source_stub-.4
            obstacles=[[n['rect'][0]-clearance,n['rect'][1]-clearance,n['rect'][2]+clearance,n['rect'][3]+clearance] for n in placed.values()]
            pts=[a]+_route(u,v,obstacles,xs,ys)+[b]
        compact=[]
        for p in pts:
            if compact and math.dist(p,compact[-1])<1e-4:continue
            if len(compact)>1 and ((abs(compact[-2][0]-compact[-1][0])<1e-4 and abs(compact[-1][0]-p[0])<1e-4) or (abs(compact[-2][1]-compact[-1][1])<1e-4 and abs(compact[-1][1]-p[1])<1e-4)):compact[-1]=p
            else:compact.append(p)
        ident=e.get('id','edge-'+str(idx+1));s.line(ident,compact,arrow=e.get('arrow',True),both=e.get('both',False),dash=e.get('dash'),
                                                   exact_terminal=not e.get('label') and bool(e.get('arrow',True) or e.get('both',False)),
                                                   endpoint_nodes=[e['from'],e['to']])
        if e.get('label'):
            m=labels[id(e)];candidates=[]
            segments=list(zip(compact,compact[1:]))
            if e.get('return_edge'):segments.sort(key=lambda pair:math.dist(*pair),reverse=True)
            for p,q in segments:
                cx,cy=(p[0]+q[0])/2,(p[1]+q[1])/2
                if abs(p[0]-q[0])<1e-5:candidates +=[(cx+m['width']/2+3.3,cy),(cx-m['width']/2-3.3,cy)]
                else:candidates +=[(cx,cy-m['height']/2-3.3),(cx,cy+m['height']/2+3.3)]
            chosen=None
            for x,y in candidates:
                box=[x-m['width']/2,y-m['height']/2,x+m['width']/2,y+m['height']/2]
                if box[0]<.5 or box[1]<.5 or box[2]>width-.5 or box[3]>height-.5:continue
                if any(intersects(box,n['rect'],.5) for n in placed.values()):continue
                if any(intersects(box,t['position']['bbox'],.5) for t in s.texts):continue
                if any(segment_hits(a,b,box,.3) for pp in s.paths for a,b in zip(pp['points'],pp['points'][1:])):continue
                chosen=(x,y);break
            if chosen is None:raise FigureError('edge_label_capacity','连接标签无安全版位',edge=ident)
            s.text(ident+':label',e['label'],*chosen,role='edge-label')
        route_records.append({'edge':ident,'from':e['from'],'to':e['to'],'from_port':ss,'to_port':ts,'return_edge':bool(e.get('return_edge'))})
    s.layout_evidence={'layout_algorithm':'measured-ranks-and-bounded-orthogonal-routing','rank':rank,'edge_bindings':route_records,
        'no_curve_data_reconstruction':True,'semantic_nodes':len(nodes),'semantic_edges':len(edges),'design_font_size_pt':size,
        'global_optimum_proven':False,'source_semantics_review_required':True,
        'arrow5_shaft_length_pt':ARROW_LENGTH,'arrow5_depth_pt':ARROW_DEPTH,
        'unlabeled_boundary_gap_pt':ARROW_BOUNDARY_GAP,'rank_gaps_pt':rank_gaps}
    return s.finish(width,height)
