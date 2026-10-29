"""Measured diagram templates compile to the same backend-neutral Scene.
No per-author drawing code. Text and topology enter through data-only specs.
"""
from __future__ import annotations
from .flow_shapes import is_flow_terminal
import math, json, subprocess, shutil, re
from pathlib import Path
from .common import FigureError, PT_PER_MM, finite
from .scene import Scene, port, ray_ellipse
from .editorial import diamond_size, ARROW_LENGTH, LABEL_CLEARANCE, TICK_CLEARANCE, STROKE, COMPACT_GAP, display_content, wrap_text
from .label_fit import plan as plan_label
from .fonts import position_text


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
    s=Scene(reg,size);s.template='hierarchy-tree';p=2.;padx=4.5*size/8;padv=2.7*size/8;gapx=2*float(spec.get('bus_leg_mm',2))*PT_PER_MM;gapy=2.5*size/8+STROKE
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
        connected=any(e.get('from') in ids and e.get('to') in ids for e in spec.get('connections',[]))
        # Unbound line paths make connectivity ambiguous; retain the older
        # larger spacing unless this is clearly a group without connections.
        ambiguous=any(p.get('semantic_role','connection')=='connection' for p in spec.get('paths',[]))
        default_gap=9 if connected or ambiguous else 2.5*size/8+STROKE
        padx=4.5*size/8;pady=2.7*size/8;gap=float(group.get('gap_pt',default_gap));x,y=map(float,origin)
        equal_width=group.get('equal_width',False)
        if not isinstance(equal_width,bool):
            raise FigureError('measured_group_equal_width','equal_width须为布尔值',group=group.get('id'))
        target_width=group.get('target_width_pt')
        if 'target_width_pt' in group:
            if (axis!='row' or not equal_width or isinstance(target_width,bool) or
                    not isinstance(target_width,(int,float)) or not math.isfinite(target_width) or target_width<=0 or
                    not math.isfinite(gap) or gap<0):
                raise FigureError('measured_group_target_width','目标组宽仅支持等宽横排及有限非负间距',group=group.get('id'))
        measured_axis='both' if axis=='row' and equal_width else axis
        s.measurement_groups[group['id']]['axis']=measured_axis
        widths=[m['width']+2*padx for _,m in members];heights=[m['height']+2*pady for _,m in members]
        if axis=='row':
            heights=[max(heights)]*len(heights)
            if 'target_height_pt' in group:
                target_height=group['target_height_pt']
                if (isinstance(target_height,bool) or not isinstance(target_height,(int,float))
                        or not math.isfinite(target_height) or target_height<max(heights)):
                    raise FigureError('measured_group_target_height','目标高度不足以保留文字和框内留白')
                heights=[target_height]*len(heights)
                s.measurement_groups[group['id']]['cell_height_pt']=target_height
            if equal_width:widths=[max(widths)]*len(widths)
            if 'target_width_pt' in group:
                cell_width=(target_width-gap*(len(widths)-1))/len(widths)
                if cell_width+1e-7<max(widths):
                    raise FigureError('measured_group_target_width','目标组宽不足以保留文字与框内留白',group=group.get('id'))
                widths=[cell_width]*len(widths)
                s.measurement_groups[group['id']]['cell_width_pt']=cell_width
        else:
            if 'target_height_pt' in group:raise FigureError('measured_group_target_height','目标高度仅支持横排')
            widths=[max(widths)]*len(widths)
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
        nodes[n['id']]=s.shape(n['id'],r,kind,n.get('container',False),width=n.get('width',.5),dash=n.get('dash'),checked=n.get('checked',False),fill=n.get('fill'),gray=n.get('gray',0))
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
    def place_text(t):
        """装载一条文本；声明了 fit 的先做标签排版决策，再落到场景。"""
        content=t['text'];x=t['x'];y=t['y'];angle=t.get('rotation',0);align=t.get('align','center')
        fit=t.get('fit')
        if fit is None:
            s.text(t['id'],content,x,y,align,angle,t.get('owner'),t.get('role','label'),wrap_chars=t.get('wrap_chars'),gray=t.get('gray',0));return
        if not isinstance(fit,dict):raise FigureError('label_fit_declaration','文本的fit须为显式对象',id=t['id'])
        unknown=set(fit)-{'width_pt','max_lines','allow_angles','anchor'}
        if unknown:raise FigureError('label_fit_declaration','fit只接受width_pt、max_lines、allow_angles、anchor',id=t['id'],unknown=sorted(unknown))
        if 'width_pt' not in fit:raise FigureError('label_fit_declaration','fit必须给出可用宽度width_pt',id=t['id'])
        anchor=fit.get('anchor','center')
        if anchor not in ('center','top','bottom'):raise FigureError('label_fit_declaration','fit的anchor只接受center、top、bottom',id=t['id'],anchor=anchor)
        planned=plan_label(content,width_pt=fit['width_pt'],measure=reg.measure,size=size,
                           max_lines=fit.get('max_lines',2),allow_angles=fit.get('allow_angles',(0.0,)))
        content='\n'.join(planned['lines'])
        if planned['angle']:angle=planned['angle']
        if anchor!='center':
            probe=position_text(reg.measure(content,size),0,0,align,angle)
            height=probe['bbox'][3]-probe['bbox'][1]
            y=y+height/2 if anchor=='top' else y-height/2
        s.text(t['id'],content,x,y,align,angle,t.get('owner'),t.get('role','label'),wrap_chars=t.get('wrap_chars'),gray=t.get('gray',0))
        s.layout_evidence.setdefault('label_fit',[]).append({
            'text_id':t['id'],'source':t['text'],'display':content.replace('\n',' / '),
            'lines':list(planned['lines']),'angle':planned['angle'],'reason':planned['reason'],
            'width_pt':round(planned['width_pt'],3),'availability_pt':planned['availability_pt'],'anchor':anchor})
    for t in spec.get('texts',[]):place_text(t)
    from .confirmed_spacing import parse_confirmed_spacing
    s.confirmed_spacing_checks=parse_confirmed_spacing(spec.get('confirmed_spacing_checks',[]))
    from .route_clearances import parse_route_clearances
    s.route_clearance_checks=parse_route_clearances(spec.get('route_clearance_checks',[]))
    from .annotation_clearances import parse_annotation_clearances
    s.annotation_clearance_checks=parse_annotation_clearances(spec.get('annotation_clearance_checks',[]))
    from .icon_ink_spacing import parse_icon_ink_checks
    s.icon_ink_checks=parse_icon_ink_checks(spec.get('icon_ink_checks',[]))
    from .icon_ink_spacing import parse_icon_group_centers
    s.icon_group_centers=parse_icon_group_centers(spec.get('icon_group_centers',[]))
    from .container_auto_spacing import parse_container_spacing_exceptions
    s.container_spacing_exceptions=parse_container_spacing_exceptions(spec.get('container_spacing_exceptions',[]))
    from .parallel_slants import parse_parallel_slants
    s.parallel_slant_checks=parse_parallel_slants(spec.get('parallel_slant_checks',[]))
    from .curve_label_spacing import parse_curve_label_checks
    s.curve_label_checks=parse_curve_label_checks(spec.get('curve_label_checks',[]))
    rows=spec.get('image_row_gap_checks',[])
    if not isinstance(rows,list):raise FigureError('image_row_gap_invalid','图片行间距检查须为数组')
    for row in rows:
        if (not isinstance(row,dict) or set(row)!={'asset_ids'} or not isinstance(row['asset_ids'],list)
                or len(row['asset_ids'])<2 or any(not isinstance(x,str) or not x for x in row['asset_ids'])
                or len(set(row['asset_ids']))!=len(row['asset_ids'])):
            raise FigureError('image_row_gap_invalid','图片行须列出至少两个不同的素材编号')
        s.image_row_gap_checks.append({'asset_ids':row['asset_ids']})
    checks=spec.get('image_label_gap_checks',[])
    if not isinstance(checks,list):raise FigureError('image_label_gap_invalid','图片说明间距检查须为数组')
    for check in checks:
        if (not isinstance(check,dict) or set(check)-{'asset_id','title_id','caption_id'}
                or not isinstance(check.get('asset_id'),str) or not check['asset_id']
                or not any(k in check for k in ('title_id','caption_id'))
                or any(not isinstance(check[k],str) or not check[k] for k in ('title_id','caption_id') if k in check)):
            raise FigureError('image_label_gap_invalid','须明确绑定图片与上方或下方说明')
        s.image_label_gap_checks.append(dict(check))
    checks=spec.get('legend_data_checks',[])
    if not isinstance(checks,list):raise FigureError('legend_data_check_invalid','图例数据避让检查须为数组')
    for check in checks:
        if (not isinstance(check,dict) or set(check)!={'frame_id','data_path_ids'}
                or not isinstance(check['frame_id'],str) or not check['frame_id']
                or not isinstance(check['data_path_ids'],list) or not check['data_path_ids']
                or any(not isinstance(i,str) or not i for i in check['data_path_ids'])
                or len(set(check['data_path_ids']))!=len(check['data_path_ids'])):
            raise FigureError('legend_data_check_invalid','须明确绑定图例框和真实数据路径')
        s.legend_data_checks.append(dict(check))
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
    for p in spec.get('paths',[]):
        if p.get('fill') is not None or p.get('closed') or p.get('gray') not in (None,0):
            if p.get('arrow') or p.get('both') or p.get('endpoint_nodes'):
                raise FigureError('polygon_connection_unsupported','填充或灰度多边形不支持连接语义',id=p['id'])
            s.poly(p['id'],p['points'],fill=p.get('fill'),gray=p.get('gray',0),width=p.get('width',.5),
                   dash=p.get('dash'),closed=bool(p.get('closed')),
                   semantic_role=p.get('semantic_role','decorative'),opacity=p.get('opacity'))
        else:
            s.line(p['id'],p['points'],p.get('arrow',False),p.get('both',False),p.get('dash'),p.get('width',.5),
                   exact_terminal=p.get('exact_terminal',False),endpoint_nodes=p.get('endpoint_nodes'),
                   shared_net=p.get('shared_net'),semantic_role=p.get('semantic_role','connection'))
    from .legend_marker_alignment import prepare_legend_marker_centers
    s.legend_marker_centers=prepare_legend_marker_centers(s,spec.get('legend_marker_centers',[]))
    from .tick_precision import scene_axis_notices
    s.notes.extend(scene_axis_notices(s,spec.get('axis_tick_groups')))
    spacing=spec.get('straight_vertical_spacing',[])
    if not isinstance(spacing,list):
        raise FigureError('vertical_spacing_invalid','直连跨行间距组必须是数组')
    seen=set()
    for group in spacing:
        if not isinstance(group,dict) or set(group)-{'paths','gap_pt'} or not isinstance(group.get('paths'),list) or not group['paths']:
            raise FigureError('vertical_spacing_invalid','直连跨行间距组须列出路径')
        ids=group['paths'];gap=group.get('gap_pt',ARROW_LENGTH)
        if any(not isinstance(item,str) or not item or item in seen for item in ids) or len(set(ids))!=len(ids):
            raise FigureError('vertical_spacing_invalid','直连路径编号无效或重复')
        if isinstance(gap,bool) or not isinstance(gap,(int,float)) or not math.isfinite(gap) or gap<ARROW_LENGTH:
            raise FigureError('vertical_spacing_invalid','直连间距必须是满足箭头最小长度的有限值')
        seen.update(ids);s.straight_vertical_spacing.append({'paths':ids,'gap_pt':float(gap)})
    legend_checks=spec.get('legend_dash_checks',[])
    if not isinstance(legend_checks,list):raise FigureError('legend_dash_invalid','虚线图例检查须为数组')
    for item in legend_checks:
        if not isinstance(item,dict) or set(item)-{'path_id','min_length_pt'} or not isinstance(item.get('path_id'),str) or not item['path_id']:
            raise FigureError('legend_dash_invalid','虚线图例检查须指定线段')
        length=item.get('min_length_pt',12.)
        if isinstance(length,bool) or not isinstance(length,(int,float)) or not math.isfinite(length) or length<=0:
            raise FigureError('legend_dash_invalid','虚线图例最小长度必须为有限正数')
        s.legend_dash_checks.append({'path_id':item['path_id'],'min_length_pt':float(length)})
    series_checks=spec.get('legend_series_checks',[])
    if not isinstance(series_checks,list):raise FigureError('legend_series_invalid','图例线型绑定须为数组')
    for item in series_checks:
        if (not isinstance(item,dict) or set(item)!={'series_path_id','swatch_path_id'}
                or any(not isinstance(v,str) or not v for v in item.values())):
            raise FigureError('legend_series_invalid','须指定数据曲线与图例线段')
        s.legend_series_checks.append(item.copy())
    axis_checks=spec.get('axis_label_gap_checks',[])
    if not isinstance(axis_checks,list):raise FigureError('axis_gap_invalid','轴题间距检查须为数组')
    for item in axis_checks:
        if (not isinstance(item,dict) or set(item)-{'title_id','tick_ids','gap_pt','side'} or not isinstance(item.get('title_id'),str)
                or not item['title_id'] or not isinstance(item.get('tick_ids'),list) or not item['tick_ids']
                or any(not isinstance(i,str) or not i for i in item['tick_ids'])):
            raise FigureError('axis_gap_invalid','轴题间距检查须指定轴题与刻度')
        gap=item.get('gap_pt',LABEL_CLEARANCE)
        if isinstance(gap,bool) or not isinstance(gap,(int,float)) or not math.isfinite(gap) or gap<0:
            raise FigureError('axis_gap_invalid','轴题间距须为有限非负数')
        side=item.get('side','bottom')
        if side not in ('bottom','left','right'):raise FigureError('axis_gap_invalid','轴题间距方向须为 bottom、left 或 right')
        s.axis_label_gap_checks.append({'title_id':item['title_id'],'tick_ids':item['tick_ids'],'gap_pt':float(gap),'side':side})
    legend_gaps=spec.get('legend_frame_gap_checks',[])
    if not isinstance(legend_gaps,list):raise FigureError('legend_frame_gap_invalid','图例框间距检查须为数组')
    for item in legend_gaps:
        if (not isinstance(item,dict) or set(item)-{'frame_id','text_ids','gap_pt','side'} or not isinstance(item.get('frame_id'),str)
                or not item['frame_id'] or not isinstance(item.get('text_ids'),list) or not item['text_ids']
                or any(not isinstance(i,str) or not i for i in item['text_ids'])):
            raise FigureError('legend_frame_gap_invalid','图例框间距检查须指定框线与文字')
        gap=item.get('gap_pt',LABEL_CLEARANCE)
        if isinstance(gap,bool) or not isinstance(gap,(int,float)) or not math.isfinite(gap) or gap<0:
            raise FigureError('legend_frame_gap_invalid','图例框间距须为有限非负数')
        side=item.get('side','bottom')
        if side not in ('bottom','right'):raise FigureError('legend_frame_gap_invalid','图例框间距方向须为 bottom 或 right')
        s.legend_frame_gap_checks.append({'frame_id':item['frame_id'],'text_ids':item['text_ids'],'gap_pt':float(gap),'side':side})
    tick_checks=spec.get('axis_tick_gap_checks',[])
    if not isinstance(tick_checks,list):raise FigureError('axis_tick_gap_invalid','刻度间距检查须为数组')
    for item in tick_checks:
        if (not isinstance(item,dict) or set(item)-{'text_id','path_id','side','gap_pt'}
                or any(not isinstance(item.get(k),str) or not item[k] for k in ('text_id','path_id'))
                or item.get('side') not in ('left','right','bottom')):
            raise FigureError('axis_tick_gap_invalid','刻度间距检查须指定文字、刻度线和方向')
        gap=item.get('gap_pt',TICK_CLEARANCE)
        if isinstance(gap,bool) or not isinstance(gap,(int,float)) or not math.isfinite(gap) or gap<0:
            raise FigureError('axis_tick_gap_invalid','刻度间距须为有限非负数')
        s.axis_tick_gap_checks.append({'text_id':item['text_id'],'path_id':item['path_id'],'side':item['side'],'gap_pt':float(gap)})
    new_ticks=spec.get('new_tick_length_checks',[])
    if not isinstance(new_ticks,list):raise FigureError('new_tick_length_invalid','新绘刻度检查须为数组')
    for item in new_ticks:
        if (not isinstance(item,dict) or set(item)-{'path_id','length_pt','reason'}
                or not isinstance(item.get('path_id'),str) or not item['path_id']):
            raise FigureError('new_tick_length_invalid','新绘刻度须明确指定路径')
        length=item.get('length_pt',2.5);reason=item.get('reason')
        if (isinstance(length,bool) or not isinstance(length,(int,float)) or not math.isfinite(length) or length<=0
                or ('length_pt' in item and (not isinstance(reason,str) or not reason.strip()))
                or ('reason' in item and 'length_pt' not in item)):
            raise FigureError('new_tick_length_invalid','新绘刻度例外须指定正长度与原因')
        s.new_tick_length_checks.append({'path_id':item['path_id'],'length_pt':float(length),'reason':reason})
    backgrounds=spec.get('legend_backgrounds',[])
    if not isinstance(backgrounds,list):raise FigureError('legend_background_invalid','图例白底须为数组')
    path_map={p['id']:p for p in s.paths};text_ids={t['id'] for t in s.texts};node_ids={n['id'] for n in s.nodes}
    foreground=set();foreground_text=set();foreground_nodes=set()
    for item in backgrounds:
        if (not isinstance(item,dict) or set(item)!={'frame_id','foreground_path_ids','foreground_text_ids','foreground_node_ids'} or not isinstance(item.get('frame_id'),str)
                or not isinstance(item.get('foreground_path_ids'),list) or not item['foreground_path_ids']
                or any(not isinstance(i,str) or not i or i not in path_map or i in foreground for i in item['foreground_path_ids'])
                or not isinstance(item.get('foreground_text_ids'),list) or any(not isinstance(i,str) or i not in text_ids or i in foreground_text for i in item['foreground_text_ids'])
                or not isinstance(item.get('foreground_node_ids'),list) or any(not isinstance(i,str) or i not in node_ids or i in foreground_nodes for i in item['foreground_node_ids'])
                or any(len(set(item[k]))!=len(item[k]) for k in ('foreground_path_ids','foreground_text_ids','foreground_node_ids'))
                or item['frame_id'] not in item['foreground_path_ids']):
            raise FigureError('legend_background_invalid','图例白底须绑定框线和全部前景路径')
        frame=path_map[item['frame_id']];pts=frame['points']
        if len(pts)!=5 or pts[0]!=pts[-1] or any(a[0]!=b[0] and a[1]!=b[1] for a,b in zip(pts,pts[1:])):
            raise FigureError('legend_background_invalid','图例白底只支持真实闭合矩形框')
        xs=[p[0] for p in pts];ys=[p[1] for p in pts];rect=[min(xs),min(ys),max(xs),max(ys)]
        if set(tuple(p) for p in pts[:-1])!={(rect[0],rect[1]),(rect[2],rect[1]),(rect[2],rect[3]),(rect[0],rect[3])}:
            raise FigureError('legend_background_invalid','图例白底框线必须为矩形')
        if any(rect[0]<b['rect'][2] and rect[2]>b['rect'][0] and rect[1]<b['rect'][3] and rect[3]>b['rect'][1] for b in s.legend_backgrounds):
            raise FigureError('legend_background_invalid','多个图例白底不能互相遮盖')
        def contained(box):return box[0]>=rect[0]-.01 and box[1]>=rect[1]-.01 and box[2]<=rect[2]+.01 and box[3]<=rect[3]+.01
        for path_id in item['foreground_path_ids']:
            points=path_map[path_id]['points'];box=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
            if not contained(box):raise FigureError('legend_background_invalid','图例前景线越过白底框',id=path_id)
        for node_id in item['foreground_node_ids']:
            node=next(n for n in s.nodes if n['id']==node_id)
            if not contained(node['rect']):raise FigureError('legend_background_invalid','图例标记越过白底框',id=node_id)
        for text_id in item['foreground_text_ids']:
            text=next(t for t in s.texts if t['id']==text_id)
            if not contained(text['position']['bbox']):raise FigureError('legend_background_invalid','图例文字越过白底框',id=text_id)
        foreground.update(item['foreground_path_ids']);foreground_text.update(item['foreground_text_ids']);foreground_nodes.update(item['foreground_node_ids'])
        s.legend_backgrounds.append({'frame_id':item['frame_id'],'foreground_path_ids':item['foreground_path_ids'],
            'foreground_text_ids':item['foreground_text_ids'],'foreground_node_ids':item['foreground_node_ids'],'rect':rect})
    return s.finish(spec['width_pt'],spec['height_pt'])


DIAGRAMS={'cycle':cycle,'layered':layered,'radial':radial,'fanout':fanout,'tree':tree,'network':network,'scene':primitive}

from .graph_layout import graph
DIAGRAMS["graph"]=graph
from .columns import columns
DIAGRAMS["columns"]=columns
from .grouped_chains import grouped_chains
DIAGRAMS['grouped-chains'] = grouped_chains
from .stage_grid import stage_grid
DIAGRAMS['stage-grid'] = stage_grid
