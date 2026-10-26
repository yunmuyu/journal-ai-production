"""Measured diagram templates compile to the same backend-neutral Scene.
No per-author drawing code. Text and topology enter through data-only specs.
"""
from __future__ import annotations
from .flow_shapes import is_flow_terminal
import math, json, subprocess, shutil, re
from pathlib import Path
from .common import FigureError, PT_PER_MM, finite
from .scene import Scene, port, ray_ellipse
from .editorial import diamond_size, ARROW_LENGTH, LABEL_CLEARANCE, STROKE, COMPACT_GAP, display_content, wrap_text


def metrics(reg,size,texts):
    return [reg.measure(t,size) for t in texts]


def stage_size(reg,size,title,items,columns=1):
    p=4.5*size/8;v=2.7*size/8;gap=3*size/8;frame=3*size/8
    ims=metrics(reg,size,items); tm=reg.measure(title,size)
    iw=max(m['width'] for m in ims)+2*p;ih=max(m['height'] for m in ims)+2*v
    rows=math.ceil(len(items)/columns)
    w=max(tm['width']+2*frame,columns*iw+(columns-1)*gap+2*frame)
    h=2*frame+tm['height']+gap+rows*ih+(rows-1)*gap
    return {'width':w,'height':h,'item_w':iw,'item_h':ih,'title_h':tm['height'],'columns':columns,'gap':gap,'pad':frame}


def place_stage(s,id,title,items,x,y,m):
    w,h=m['width'],m['height'];n=s.shape(id,[x,y,x+w,y+h],container=True)
    s.text(id+':title',title,x+w/2,y+m['pad']+m['title_h']/2,owner=id)
    cols=m['columns'];gy=y+m['pad']+m['title_h']+m['gap']
    total=cols*m['item_w']+(cols-1)*m['gap'];gx=x+(w-total)/2
    for i,text in enumerate(items):
        r,c=divmod(i,cols)
        s.box(id+':item'+str(i),text,gx+c*(m['item_w']+m['gap']),gy+r*(m['item_h']+m['gap']),m['item_w'],m['item_h'])
    return n


def cycle(spec,reg,size):
    s=Scene(reg,size);s.template='four-stage-cycle';stages=spec['stages']
    if len(stages)!=4:raise FigureError('cycle_stage_count','此模板要求四阶段；其他拓扑用通用scene或tree')
    ms=[stage_size(reg,size,t['title'],t['items']) for t in stages]
    bw=max(m['width'] for m in ms);bh=max(m['height'] for m in ms)
    for m in ms:m.update(width=bw,height=bh)
    rejects=spec['reject_labels'];rr=metrics(reg,size,rejects)
    unit=size/8;clear=LABEL_CLEARANCE*unit+STROKE/2
    dm=reg.measure(spec['decision'],size)
    dw,dh,devidence=diamond_size(dm['width'],dm['height'],size)
    margin=2.;left=max(ARROW_LENGTH,rr[0]['width']+2*clear+dw/2-bw/2)
    gap=ARROW_LENGTH;rowgap=ARROW_LENGTH
    x1=margin+left;x2=x1+bw+gap;y1=margin;y2=y1+bh+rowgap
    nodes={}
    for index,(x,y) in enumerate(((x1,y1),(x2,y1),(x2,y2),(x1,y2))):
        st=stages[index];nodes[index]=place_stage(s,'stage'+str(index+1),st['title'],st['items'],x,y,ms[index])
    s.line('stage1-to-2',[port(nodes[0],'right'),port(nodes[1],'left')],arrow=True)
    s.line('stage2-to-3',[port(nodes[1],'bottom'),port(nodes[2],'top')],arrow=True)
    s.line('stage3-to-4',[port(nodes[2],'left'),port(nodes[3],'right')],arrow=True)
    cx=x1+bw/2
    # Reentrant labels need space, but no unexplained 30pt fixed band.
    bottom=y2+bh
    cy=max(bottom+ARROW_LENGTH+dh/2,bottom+max(m['height'] for m in rr)+2*clear)
    dy=cy-dh/2
    dec=s.box('decision',spec['decision'],cx-dw/2,dy,dw,dh,'diamond')
    dec['calibration']=devidence
    s.line('stage4-to-decision',[port(nodes[3],'bottom'),port(dec,'top')],arrow=True)
    endm=reg.measure(spec['end'],size);ew=endm['width']+9*unit;eh=endm['height']+5.4*unit
    end=s.box('complete',spec['end'],cx-ew/2,dy+dh+ARROW_LENGTH,ew,eh,'roundrect')
    s.line('decision-to-complete',[port(dec,'bottom'),port(end,'top')],arrow=True)
    rightx=max(x2+bw+ARROW_LENGTH,cx+dw/2+rr[1]['width']+2*clear)
    s.line('reject-model',[port(dec,'left'),[margin,cy],[margin,port(nodes[0],'left')[1]],port(nodes[0],'left')],arrow=True)
    s.line('reject-parameters',[port(dec,'right'),[rightx,cy],[rightx,port(nodes[1],'right')[1]],port(nodes[1],'right')],arrow=True)
    s.text('model-label',rejects[0],(margin+port(dec,'left')[0])/2,cy-rr[0]['height']/2-clear)
    s.text('parameters-label',rejects[1],(port(dec,'right')[0]+rightx)/2,cy-rr[1]['height']/2-clear)
    s.layout_evidence={'diamond':devidence,'edge_label_clearance_pt':clear-STROKE/2,
                      'direct_arrow_length_pt':ARROW_LENGTH,'no_connector_member_gap_pt':COMPACT_GAP,
                      'decision_top_gap_pt':dy-bottom,'sizing_source':'formal-runtime, not divergent root adapter'}
    return s.finish(rightx+margin,end['rect'][3]+margin)


def layered(spec,reg,size):
    s=Scene(reg,size);s.template='layered-support-loop';stages=spec['stages']
    ms=[stage_size(reg,size,t['title'],t['items'],2) for t in stages]
    bw=max(m['width'] for m in ms);bh=max(m['height'] for m in ms)
    for m in ms:m.update(width=bw,height=bh)
    p=2.; supportm=reg.measure(spec['support'],size);sw=supportm['width']+9
    gap=ARROW_LENGTH;rowgap=max(ARROW_LENGTH,max(reg.measure(v,size)['height']+6.5 for v in spec['down_labels']))
    totalh=len(stages)*bh+(len(stages)-1)*rowgap
    support=s.box('support',spec['support'],p,p,sw,totalh)
    x=p+sw+gap;nodes=[]
    for i,t in enumerate(stages):
        n=place_stage(s,'layer'+str(i),t['title'],t['items'],x,p+i*(bh+rowgap),ms[i]);nodes.append(n)
        y=(n['rect'][1]+n['rect'][3])/2
        s.line('support-to-'+str(i),[[p+sw,y],port(n,'left')],arrow=True)
    for i,label in enumerate(spec['down_labels']):
        a,b=port(nodes[i],'bottom'),port(nodes[i+1],'top')
        s.line('layer-next'+str(i),[a,b],arrow=True)
        s.text('layer-next-label'+str(i),label,a[0]+3.25,(a[1]+b[1])/2,align='left')
    gutter=12.;rx=x+bw+gutter;loopy=(port(nodes[-1],'right')[1]+port(nodes[0],'right')[1])/2
    s.line('return-model',[port(nodes[-1],'right'),[rx,port(nodes[-1],'right')[1]],[rx,port(nodes[0],'right')[1]],port(nodes[0],'right')],arrow=True)
    tm=reg.measure(spec['return_label'],size)
    s.text('return-label',spec['return_label'],rx+3.25,loopy,align='left')
    return s.finish(rx+3.25+tm['width']+p,p+totalh+p)


def radial(spec,reg,size):
    s=Scene(reg,size);s.template='radial-capability';corner_texts=spec['corners'];ms=metrics(reg,size,corner_texts)
    bw=max(m['width'] for m in ms)+9;bh=max(m['height'] for m in ms)+5.4
    cm=reg.measure(spec['core'],size);innerw=math.sqrt(2)*(cm['width']+7);innerh=math.sqrt(2)*(cm['height']+5)
    outerw=innerw+26;outerh=innerh+30
    p=2;cx=p+bw+outerw/2-8;cy=p+bh/2+outerh/2+12
    rightx=2*cx-bw-p;bottomy=2*cy-bh-p
    corners=[]
    for i,(x,y) in enumerate(((p,p),(rightx,p),(rightx,bottomy),(p,bottomy))):
        corners.append(s.box('corner'+str(i),corner_texts[i],x,y,bw,bh))
    core=s.box('core',spec['core'],cx-innerw/2,cy-innerh/2,innerw,innerh,'ellipse')
    s.shape('ring',[cx-outerw/2,cy-outerh/2,cx+outerw/2,cy+outerh/2],'ellipse',container=True)
    s.text('ring-top',spec['ring_top'],cx,cy-innerh/2-9)
    s.text('ring-bottom',spec['ring_bottom'],cx,cy+innerh/2+9)
    pairs=[('right','left'),('bottom','top'),('left','right'),('top','bottom')]
    for i,((fp,tp),label) in enumerate(zip(pairs,spec['cycle_labels'])):
        a,b=port(corners[i],fp),port(corners[(i+1)%4],tp)
        s.line('cycle'+str(i),[a,b],arrow=True)
        if i==0:s.text('cyclelabel0',label,cx,a[1]-7)
        elif i==1:s.text('cyclelabel1',label,a[0]+7,cy,align='left')
        elif i==2:s.text('cyclelabel2',label,cx,a[1]+7)
        else:s.text('cyclelabel3',label,a[0]-7,cy,align='right')
    for i,which in enumerate(('se','sw','nw','ne')):
        a=port(corners[i],which);b=ray_ellipse(core['rect'],a)
        s.line('to-core'+str(i),[a,b],arrow=True,dash=[3,2])
    labw=max(reg.measure(spec['cycle_labels'][i],size)['width'] for i in (1,3))
    # Left/right labels are located in the corner-width exterior corridors.
    return s.finish(rightx+bw+p,bottomy+bh+p)


def fanout(spec,reg,size):
    s=Scene(reg,size);s.template='fanout-platform';items=spec['items'];ms=metrics(reg,size,items)
    bw=max(m['width'] for m in ms)+9*size/8;bh=max(m['height'] for m in ms)+5.4*size/8
    gap=3*size/8;p=2.;w=len(items)*bw+(len(items)-1)*gap
    topm=reg.measure(spec['top'],size);bottomm=reg.measure(spec['bottom'],size)
    w=max(w,topm['width']+9,bottomm['width']+9)
    th=topm['height']+6;dh=bottomm['height']+6
    top=s.box('top',spec['top'],p,p,w,th)
    y=p+th+28;space=(w-len(items)*bw)/(len(items)-1) if len(items)>1 else 0
    group=[]
    for i,text in enumerate(items):
        n=s.box('module'+str(i),text,p+i*(bw+space),y,bw,bh);group.append(n)
        s.line('top-to-'+str(i),[port(top,'bottom'),port(n,'top')],arrow=True)
    by=y+bh+max(2*4.4+3,ARROW_LENGTH);bottom=s.box('bottom',spec['bottom'],p,by,w,dh)
    for i,n in enumerate(group):
        a=port(n,'bottom');b=[a[0],by]
        s.line('data-to-'+str(i),[a,b],both=True)
    return s.finish(w+2*p,by+dh+p)


def tree(spec,reg,size):
    """Measured hierarchy. A bundled/external solver bridge can provide the
    block positions; this fallback is explicitly a deterministic tree template."""
    layout=spec.get('tree_layout','right')
    if layout=='bilateral':
        from .bilateral_tree import bilateral_tree
        return bilateral_tree(spec,reg,size)
    if layout!='right':raise FigureError('tree_layout','树布局仅支持right或bilateral')
    s=Scene(reg,size);s.template='hierarchy-tree';p=2.;padx=4.5*size/8;padv=2.7*size/8;gapx=2*float(spec.get('bus_leg_mm',2))*PT_PER_MM;gapy=COMPACT_GAP*size/8
    # Whitespace is measured between visible box edges, including half strokes.
    groupgap=2*(gapy-STROKE)+STROKE
    branches=spec['branches'];roottext=spec['root']
    if spec.get('root_vertical'):roottext='\n'.join(roottext.replace('\n',''))
    rootm=reg.measure(roottext,size);mainms=metrics(reg,size,[b['text'] for b in branches]);leafms=metrics(reg,size,[t for b in branches for t in b['children']])
    rootw=rootm['width']+2*padx;mw=max(m['width'] for m in mainms)+2*padx
    lw=max(m['width'] for m in leafms)+2*padx;lh=max(m['height'] for m in leafms)+2*padv
    mh=max(m['height'] for m in mainms)+2*padv
    gh=[max(mh,len(b['children'])*lh+(len(b['children'])-1)*gapy) for b in branches]
    height=max(sum(gh)+(len(branches)-1)*groupgap,rootm['height']+2*padv)
    rooth=rootm['height']+2*padv
    root=s.box('root',roottext,p,p+(height-rooth)/2,rootw,rooth)
    mx=p+rootw+gapx;lx=mx+mw+gapx;my=p;centers=[]
    for i,b in enumerate(branches):
        cy=my+gh[i]/2;centers.append(cy)
        main=s.box('branch'+str(i),b['text'],mx,cy-mh/2,mw,mh)
        main['measurement_contract']={'mode':'measured-group','group':'tree-branches','axis':'both','expected_wh':[mw,mh]}
        ly=my+(gh[i]-(len(b['children'])*lh+(len(b['children'])-1)*gapy))/2
        lcenters=[]
        for j,text in enumerate(b['children']):
            leaf=s.box('leaf'+str(i)+'-'+str(j),text,lx,ly,lw,lh)
            leaf['measurement_contract']={'mode':'measured-group','group':'tree-leaves','axis':'both','expected_wh':[lw,lh]}
            lcenters.append(ly+lh/2);ly+=lh+gapy
        bus=mx+mw+gapx/2
        s.line('branch-stem'+str(i),[port(main,'right'),[bus,cy]])
        if len(lcenters)>1:s.line('branch-bus'+str(i),[[bus,min(lcenters)],[bus,max(lcenters)]])
        for j,lcy in enumerate(lcenters):s.line('branch-leaf'+str(i)+'-'+str(j),[[bus,lcy],[lx,lcy]])
        my+=gh[i]+groupgap
    s.measurement_groups['tree-branches']={'axis':'both','nodes':['branch'+str(i) for i in range(len(branches))]}
    s.measurement_groups['tree-leaves']={'axis':'both','nodes':['leaf'+str(i)+'-'+str(j) for i,b in enumerate(branches) for j in range(len(b['children']))]}
    bus=p+rootw+gapx/2;rootcy=(root['rect'][1]+root['rect'][3])/2
    s.line('root-stem',[port(root,'right'),[bus,rootcy]])
    if len(centers)>1:s.line('root-bus',[[bus,min(centers)],[bus,max(centers)]])
    for i,cy in enumerate(centers):s.line('root-branch'+str(i),[[bus,cy],[mx,cy]])
    s.layout_evidence={'algorithm':'deterministic measured hierarchy','font_size_kept':size,'whole_artwork_scale':1,
                       'sibling_clearance_pt':gapy-STROKE,'group_clearance_pt':groupgap-STROKE,'group_to_sibling_clearance_ratio':2}
    return s.finish(lx+lw+p,height+2*p)


def network(spec,reg,size):
    s=Scene(reg,size);s.template='network';nodes={};p=2.;positions=spec['nodes']
    for n in positions:
        r=n.get('radius_pt',12.);x=n['x'];y=n['y']
        nodes[n['id']]=s.box(n['id'],n['text'],x-r,y-r,2*r,2*r,'ellipse')
    for i,e in enumerate(spec['edges']):
        a=nodes[e['from']];b=nodes[e['to']]
        ac=port(a,'top');ac[1]=(a['rect'][1]+a['rect'][3])/2
        bc=port(b,'top');bc[1]=(b['rect'][1]+b['rect'][3])/2
        pa=ray_ellipse(a['rect'],bc);pb=ray_ellipse(b['rect'],ac)
        points=[pa,*e.get('via',[]),pb]
        arrow=bool(e.get('arrow',False) or e.get('both',False))
        if arrow:
            dx,dy=pb[0]-points[-2][0],pb[1]-points[-2][1]
            length=math.hypot(dx,dy)
            if length<ARROW_LENGTH:raise FigureError('arrow_terminal_short','网络图箭头末段不足3 mm')
            points.insert(-1,[pb[0]-dx/length*ARROW_LENGTH,pb[1]-dy/length*ARROW_LENGTH])
        if e.get('both',False):
            dx,dy=points[1][0]-pa[0],points[1][1]-pa[1]
            length=math.hypot(dx,dy)
            if length<ARROW_LENGTH:raise FigureError('arrow_terminal_short','网络图双向箭头起始段不足3 mm')
            points.insert(1,[pa[0]+dx/length*ARROW_LENGTH,pa[1]+dy/length*ARROW_LENGTH])
        s.line(e.get('id','edge'+str(i)),points,arrow=e.get('arrow',False),both=e.get('both',False),dash=e.get('dash'),
               exact_terminal=arrow,endpoint_nodes=[e['from'],e['to']])
    return s.finish(spec['width_pt'],spec['height_pt'])


def primitive(spec,reg,size):
    s=Scene(reg,size);s.template='primitive-scene';nodes={}
    s.source_bindings={v.get('path'):v.get('sha256') for v in spec.get('sources',[]) if isinstance(v,dict)}
    node_specs={n['id']:n for n in spec.get('nodes',[])};placed=set()
    for group in spec.get('measured_groups',[]):
        ids=group.get('nodes',[]);axis=group.get('axis');origin=group.get('origin')
        if axis not in ('row','column') or not isinstance(origin,list) or len(origin)!=2 or not ids:
            raise FigureError('measured_group_invalid','测量分组定义无效',group=group.get('id'))
        if not isinstance(group.get('id'),str) or not group['id'] or group['id'] in s.measurement_groups:
            raise FigureError('measured_group_invalid','测量分组ID无效或重复',group=group.get('id'))
        s.measurement_groups[group['id']]={'axis':axis,'nodes':list(ids)}
        members=[]
        for node_id in ids:
            if node_id not in node_specs or node_id in placed:
                raise FigureError('measured_group_invalid','测量分组引用无效节点',group=group.get('id'),node=node_id)
            n=node_specs[node_id]
            if 'rect' in n or 'text' not in n or n.get('container') or n.get('shape','rectangle') not in ('rectangle','roundrect','terminator'):
                raise FigureError('measured_group_invalid','测量分组只接受未指定矩形的普通文字框',group=group.get('id'),node=node_id)
            display=display_content(n['text'],'label')
            if n.get('wrap_chars') is not None:display=wrap_text(display,n['wrap_chars'])
            members.append((n,reg.measure(display,size)))
        gaps=group.get('gap_pts')
        if 'gap_pts' in group and (axis!='column' or 'gap_pt' in group or not isinstance(gaps,list) or
                len(gaps)!=len(ids)-1 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in gaps)):
            raise FigureError('measured_group_gaps','gap_pts仅适用于column，须有n-1个有限非负数且不能与gap_pt并用',group=group.get('id'))
        padx=4.5*size/8;pady=2.7*size/8;gap=float(group.get('gap_pt',9));x,y=map(float,origin)
        equal_width=group.get('equal_width',False)
        if not isinstance(equal_width,bool):
            raise FigureError('measured_group_equal_width','equal_width须为布尔值',group=group.get('id'))
        measured_axis='both' if axis=='row' and equal_width else axis
        s.measurement_groups[group['id']]['axis']=measured_axis
        widths=[m['width']+2*padx for _,m in members];heights=[m['height']+2*pady for _,m in members]
        if axis=='row':
            heights=[max(heights)]*len(heights)
            if equal_width:widths=[max(widths)]*len(widths)
        else:widths=[max(widths)]*len(widths)
        for index,((n,_),w,h) in enumerate(zip(members,widths,heights)):
            kind=n['shape'] if n.get('shape') in ('roundrect','terminator') and n.get('semantic_shape') else 'rectangle'
            node=s.box(n['id'],n['text'],x,y,w,h,kind,wrap_chars=n.get('wrap_chars'),flow_role=n.get('role'))
            node['measurement_contract']={'mode':'measured-group','group':group.get('id'),'axis':measured_axis,'expected_wh':[w,h]}
            nodes[n['id']]=node;placed.add(n['id'])
            if axis=='row':x+=w+gap
            else:y+=h+(gaps[index] if gaps is not None and index<len(gaps) else gap)
    for n in spec.get('nodes',[]):
        if n['id'] in placed:continue
        if 'rect' not in n:raise FigureError('primitive_node_rect_missing','普通节点缺少矩形或测量分组',id=n['id'])
        r=n['rect'];terminal=not n.get('container',False) and is_flow_terminal(n.get('text',''),n.get('role'))
        kind='terminator' if terminal else n.get('shape','rectangle')
        if kind=='roundrect' and not n.get('semantic_shape') and not terminal:
            kind='rectangle'
        nodes[n['id']]=s.shape(n['id'],r,kind,n.get('container',False),dash=n.get('dash'))
        if terminal:nodes[n['id']]['flow_terminal']=True
        if kind in ('rectangle','roundrect','terminator') and not n.get('container',False):
            nodes[n['id']]['padding_pt']=[4.5*size/8,2.7*size/8]
            fixed=n.get('fixed_size');constraints={'table-cell':'tabular-grid','code-panel':'source-code-viewport',
                'device-glyph':'source-symbol-bounds','source-locked-viewport':'source-artwork-bounds'}
            evidence=fixed.get('evidence',{}) if isinstance(fixed,dict) else {}
            purpose=fixed.get('purpose') if isinstance(fixed,dict) else None
            sources={v.get('path'):v.get('sha256') for v in spec.get('sources',[]) if isinstance(v,dict)}
            valid=(purpose in constraints and n.get('role')==purpose and evidence.get('constraint')==constraints[purpose] and
                isinstance(evidence.get('source_id'),str) and bool(evidence['source_id'].strip()) and
                isinstance(evidence.get('source_sha256'),str) and bool(re.fullmatch(r'[0-9a-f]{64}',evidence['source_sha256'])) and
                sources.get(evidence['source_id'])==evidence['source_sha256'])
            if valid:
                nodes[n['id']]['measurement_contract']={'mode':'fixed','fixed_size':fixed}
            elif 'text' in n:
                display=display_content(n['text'],'label')
                if n.get('wrap_chars') is not None:display=wrap_text(display,n['wrap_chars'])
                measurement=reg.measure(display,size)
                nodes[n['id']]['measurement_contract']={'mode':'tight','expected_wh':[
                    measurement['width']+9*size/8,measurement['height']+5.4*size/8]}
        if 'text' in n:s.text(n['id']+':text',n['text'],(r[0]+r[2])/2,(r[1]+r[3])/2,owner=n['id'],wrap_chars=n.get('wrap_chars'))
    for t in spec.get('texts',[]):s.text(t['id'],t['text'],t['x'],t['y'],t.get('align','center'),t.get('rotation',0),t.get('owner'),t.get('role','label'),wrap_chars=t.get('wrap_chars'),gray=t.get('gray',0))
    node_groups=spec.get('node_groups',[])
    if not isinstance(node_groups,list):
        raise FigureError('node_group_invalid','node_groups须为明确成员清单')
    for group in node_groups:
        if not isinstance(group,dict) or set(group)!={'id','nodes'}:
            raise FigureError('node_group_invalid','节点组仅接受id与真实成员nodes')
        s.group(group['id'],group['nodes'])
    for i,e in enumerate(spec.get('connections',[])):
        if e.get('from') not in nodes or e.get('to') not in nodes:raise FigureError('edge_endpoint','连接引用了未知节点')
        points=[port(nodes[e['from']],e['from_port']),*e.get('via',[]),port(nodes[e['to']],e['to_port'])]
        s.line(e.get('id','edge'+str(i)),points,e.get('arrow',False),e.get('both',False),e.get('dash'),
               exact_terminal=bool(e.get('arrow',False) or e.get('both',False)),endpoint_nodes=[e['from'],e['to']],
               shared_net=e.get('shared_net'),semantic_role=e.get('semantic_role','connection'))
    for p in spec.get('paths',[]):s.line(p['id'],p['points'],p.get('arrow',False),p.get('both',False),p.get('dash'),p.get('width',.5),
                                         exact_terminal=p.get('exact_terminal',False),endpoint_nodes=p.get('endpoint_nodes'),
                                         shared_net=p.get('shared_net'),semantic_role=p.get('semantic_role','connection'))
    return s.finish(spec['width_pt'],spec['height_pt'])


DIAGRAMS={'cycle':cycle,'layered':layered,'radial':radial,'fanout':fanout,'tree':tree,'network':network,'scene':primitive}

from .graph_layout import graph
DIAGRAMS["graph"]=graph
from .columns import columns
DIAGRAMS["columns"]=columns
from .grouped_chains import grouped_chains
DIAGRAMS['grouped-chains'] = grouped_chains
