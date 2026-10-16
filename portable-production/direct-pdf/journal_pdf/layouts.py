"""Measured diagram templates compile to the same backend-neutral Scene.
No per-author drawing code. Text and topology enter through data-only specs.
"""
from __future__ import annotations
import math, json, subprocess, shutil
from pathlib import Path
from .common import FigureError, PT_PER_MM, finite
from .scene import Scene, port, ray_ellipse
from .editorial import diamond_size, ARROW_LENGTH, LABEL_CLEARANCE, STROKE, COMPACT_GAP


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
    s=Scene(reg,size);s.template='hierarchy-tree';p=2.;padx=4.5*size/8;padv=2.7*size/8;gapx=2*float(spec.get('bus_leg_mm',2))*PT_PER_MM;gapy=3*size/8;groupgap=16.
    branches=spec['branches'];roottext=spec['root']
    if spec.get('root_vertical'):roottext='\n'.join(roottext.replace('\n',''))
    rootm=reg.measure(roottext,size);mainms=metrics(reg,size,[b['text'] for b in branches]);leafms=metrics(reg,size,[t for b in branches for t in b['children']])
    rootw=rootm['width']+2*padx;mw=max(m['width'] for m in mainms)+2*padx
    lw=max(m['width'] for m in leafms)+2*padx;lh=max(m['height'] for m in leafms)+2*padv
    mh=max(m['height'] for m in mainms)+2*padv
    gh=[max(mh,len(b['children'])*lh+(len(b['children'])-1)*gapy) for b in branches]
    height=max(sum(gh)+(len(branches)-1)*groupgap,rootm['height']+2*padv)
    root=s.box('root',roottext,p,p,rootw,height)
    mx=p+rootw+gapx;lx=mx+mw+gapx;my=p;centers=[]
    for i,b in enumerate(branches):
        cy=my+gh[i]/2;centers.append(cy)
        main=s.box('branch'+str(i),b['text'],mx,cy-mh/2,mw,mh)
        ly=my+(gh[i]-(len(b['children'])*lh+(len(b['children'])-1)*gapy))/2
        lcenters=[]
        for j,text in enumerate(b['children']):
            s.box('leaf'+str(i)+'-'+str(j),text,lx,ly,lw,lh);lcenters.append(ly+lh/2);ly+=lh+gapy
        bus=mx+mw+gapx/2
        s.line('branch-stem'+str(i),[port(main,'right'),[bus,cy]])
        if len(lcenters)>1:s.line('branch-bus'+str(i),[[bus,min(lcenters)],[bus,max(lcenters)]])
        for j,lcy in enumerate(lcenters):s.line('branch-leaf'+str(i)+'-'+str(j),[[bus,lcy],[lx,lcy]])
        my+=gh[i]+groupgap
    bus=p+rootw+gapx/2;rootcy=p+height/2
    s.line('root-stem',[port(root,'right'),[bus,rootcy]])
    if len(centers)>1:s.line('root-bus',[[bus,min(centers)],[bus,max(centers)]])
    for i,cy in enumerate(centers):s.line('root-branch'+str(i),[[bus,cy],[mx,cy]])
    s.layout_evidence={'algorithm':'deterministic measured hierarchy','font_size_kept':size,'whole_artwork_scale':1}
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
        s.line(e.get('id','edge'+str(i)),[pa,*e.get('via',[]),pb],arrow=e.get('arrow',False),both=e.get('both',False),dash=e.get('dash'))
    return s.finish(spec['width_pt'],spec['height_pt'])


def primitive(spec,reg,size):
    s=Scene(reg,size);s.template='primitive-scene';nodes={}
    for n in spec.get('nodes',[]):
        r=n['rect'];kind=n.get('shape','rectangle')
        if kind=='roundrect' and not n.get('semantic_shape'):
            kind='rectangle'
        nodes[n['id']]=s.shape(n['id'],r,kind,n.get('container',False))
        if kind=='rectangle' and not n.get('container',False):
            nodes[n['id']]['padding_pt']=[4.5*size/8,2.7*size/8]
        if 'text' in n:s.text(n['id']+':text',n['text'],(r[0]+r[2])/2,(r[1]+r[3])/2,owner=n['id'],wrap_chars=n.get('wrap_chars'))
    for t in spec.get('texts',[]):s.text(t['id'],t['text'],t['x'],t['y'],t.get('align','center'),t.get('rotation',0),t.get('owner'),t.get('role','label'),wrap_chars=t.get('wrap_chars'))
    for i,e in enumerate(spec.get('connections',[])):
        if e.get('from') not in nodes or e.get('to') not in nodes:raise FigureError('edge_endpoint','连接引用了未知节点')
        points=[port(nodes[e['from']],e['from_port']),*e.get('via',[]),port(nodes[e['to']],e['to_port'])]
        s.line(e.get('id','edge'+str(i)),points,e.get('arrow',False),e.get('both',False),e.get('dash'),
               exact_terminal=bool(e.get('arrow',False) or e.get('both',False)),endpoint_nodes=[e['from'],e['to']])
    for p in spec.get('paths',[]):s.line(p['id'],p['points'],p.get('arrow',False),p.get('both',False),p.get('dash'),p.get('width',.5),
                                         exact_terminal=p.get('exact_terminal',False),endpoint_nodes=p.get('endpoint_nodes'))
    return s.finish(spec['width_pt'],spec['height_pt'])


DIAGRAMS={'cycle':cycle,'layered':layered,'radial':radial,'fanout':fanout,'tree':tree,'network':network,'scene':primitive}

from .graph_layout import graph
DIAGRAMS["graph"]=graph
