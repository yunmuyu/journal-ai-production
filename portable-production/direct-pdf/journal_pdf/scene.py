from __future__ import annotations
import math
from .common import FigureError, contains, intersects, segment_hits, finite
from .fonts import position_text
from .editorial import display_content, wrap_text, PAD_X, PAD_Y, STROKE, ARROW_LENGTH, diamond_size

class Scene:
    def __init__(self,registry,size=8):
        self.registry=registry;self.size=size
        self.nodes=[];self.texts=[];self.paths=[];self.assets=[];self.notes=[]
        self.width=0.;self.height=0.;self.template='';self.layout_evidence={}
        self._ids=set()
    def ident(self,id):
        if id in self._ids:raise FigureError('duplicate_object_id','重复对象ID',id=id)
        self._ids.add(id)
    def text(self,id,content,x,y,align='center',rotation=0,owner=None,role='label',size=None,wrap_chars=None):
        self.ident(id); source_content=content;content=display_content(content,role)
        if wrap_chars is not None:
            content=wrap_text(content,wrap_chars)
        m=self.registry.measure(content,size or self.size)
        p=position_text(m,x,y,align,rotation)
        t={'id':id,'content':content,'source_content':source_content,'measurement':m,'position':p,'owner':owner,'role':role,'x':x,'y':y,'align':align}
        self.texts.append(t);return t
    def shape(self,id,rect,kind='rectangle',container=False,width=.5):
        self.ident(id)
        if kind not in ('rectangle','ellipse','diamond','roundrect','terminator','inputOutput'):raise FigureError('unsupported_shape','形状未支持',kind=kind)
        if not finite(rect) or rect[2]<=rect[0] or rect[3]<=rect[1]:raise FigureError('invalid_node_rect','节点矩形无效',id=id)
        n={'id':id,'rect':list(rect),'kind':kind,'container':container,'width':width};self.nodes.append(n);return n
    def box(self,id,content,x,y,w=None,h=None,kind='rectangle',padx=4.5,pady=2.7,wrap_chars=None):
        display=display_content(content,'label')
        if wrap_chars is not None:
            display=wrap_text(display,wrap_chars)
        m=self.registry.measure(display,self.size)
        scale=self.size/8
        if kind=='diamond':
            dw,dh,_=diamond_size(m['width'],m['height'],self.size)
            if w is None:w=dw
            if h is None:h=dh
        if w is None:w=m['width']+2*padx*scale+(8 if kind=='inputOutput' else 0)
        if h is None:h=m['height']+2*pady*scale
        node=self.shape(id,[x,y,x+w,y+h],kind)
        if kind=='rectangle':node['padding_pt']=[padx*scale,pady*scale]
        self.text(id+':text',display,x+w/2,y+h/2,owner=id)
        return self.nodes[-1]
    def line(self,id,points,arrow=False,both=False,dash=None,width=.5,exact_terminal=False,endpoint_nodes=None):
        self.ident(id); pts=[]
        for p in points:
            if not finite(p) or len(p)!=2:raise FigureError('path_point','无效线段坐标',id=id)
            if not pts or list(p)!=pts[-1]:pts.append(list(p))
        if len(pts)<2:raise FigureError('path_degenerate','零长度连接线',id=id)
        self.paths.append({'id':id,'points':pts,'arrow':arrow or both,'both':both,'dash':dash or [],'width':width,
                           'exact_terminal':bool(exact_terminal),'endpoint_nodes':endpoint_nodes})
    def embed(self,id,asset,target,role='plot'):
        self.ident(id);self.assets.append({'id':id,'asset':asset,'rect':list(target),'role':role})
    def finish(self,width,height):
        self.width=width;self.height=height;return self
    def export(self):
        return {'template':self.template,'width_pt':self.width,'height_pt':self.height,
                'nodes':self.nodes,'texts':[{k:v for k,v in t.items() if k!='measurement'}|{'text':t['measurement']['text'],'font_size_pt':t['measurement']['size'],'ink_bounds':t['position']['bbox']} for t in self.texts],
                'paths':self.paths,'assets':[{'id':a['id'],'rect':a['rect'],'role':a['role'],'asset_key':a['asset'].key,'audit':a['asset'].audit} for a in self.assets],
                'notes':self.notes,'layout_evidence':self.layout_evidence}


def port(n,side):
    x,y,r,b=n['rect'];cx=(x+r)/2;cy=(y+b)/2
    if n['kind']=='inputOutput':
        inset=min((b-y)*.25,4)
        return {'left':[x+inset/2,cy],'right':[r-inset/2,cy],
                'top':[cx,y],'bottom':[cx,b]}[side]
    return {'left':[x,cy],'right':[r,cy],'top':[cx,y],'bottom':[cx,b],
            'nw':[x,y],'ne':[r,y],'sw':[x,b],'se':[r,b]}[side]


def ray_ellipse(rect,point):
    x,y,r,b=rect;cx=(x+r)/2;cy=(y+b)/2;rx=(r-x)/2;ry=(b-y)/2
    dx,dy=point[0]-cx,point[1]-cy;norm=math.sqrt((dx/rx)**2+(dy/ry)**2)
    return [cx+dx/norm,cy+dy/norm]


def arrow_vertices(points,depth=4.4,width=3.7,at_start=False,scale=1.):
    depth*=scale;width*=scale
    tip=points[0] if at_start else points[-1];prev=points[1] if at_start else points[-2]
    dx,dy=tip[0]-prev[0],tip[1]-prev[1];length=math.hypot(dx,dy)
    if length<depth:raise FigureError('arrow_terminal_short','箭头末段太短',length=length,minimum=depth)
    ux,uy=dx/length,dy/length
    return [tip,[tip[0]-ux*depth+uy*width/2,tip[1]-uy*depth-ux*width/2],
            [tip[0]-ux*(depth-.8*scale),tip[1]-uy*(depth-.8*scale)],
            [tip[0]-ux*depth-uy*width/2,tip[1]-uy*depth+ux*width/2]]


def audit_scene(s:Scene):
    issues=[];page=[0,0,s.width,s.height];nmap={n['id']:n for n in s.nodes}
    for t in s.texts:
        b=t['position']['bbox']
        if not contains(page,b,.02):issues.append({'code':'text_outside_page','id':t['id'],'bounds':b})
        if t['owner']:
            if t['owner'] not in nmap:issues.append({'code':'text_owner_missing','id':t['id']});continue
            n=nmap[t['owner']];nb=n['rect'];pad=.3
            if not contains([nb[0]+pad,nb[1]+pad,nb[2]-pad,nb[3]-pad],b):
                issues.append({'code':'text_outside_owner','id':t['id'],'bounds':b,'owner':nb})
            if n['kind'] in ('rectangle','inputOutput') and not n['container']:
                px,py=n.get('padding_pt',[PAD_X*s.size/8,PAD_Y*s.size/8])
                margins=[b[0]-nb[0],b[1]-nb[1],nb[2]-b[2],nb[3]-b[3]]
                if n['kind']=='inputOutput':margins[0]-=min((nb[3]-nb[1])*.25,4);margins[2]-=min((nb[3]-nb[1])*.25,4)
                if any(v<minimum-.15 for v,minimum in zip(margins,[px,py,px,py])):
                    issues.append({'code':'node_text_padding','id':t['id'],'padding_pt':margins,'minimum_pt':[px,py,px,py]})
            if n['kind']=='diamond':
                m=t['measurement'];ew,eh,_=diamond_size(m['width'],m['height'],m['size'])
                if abs(nb[2]-nb[0]-ew)>.15 or abs(nb[3]-nb[1]-eh)>.15:
                    issues.append({'code':'diamond_calibration_mismatch','id':n['id'],
                                   'actual_wh':[nb[2]-nb[0],nb[3]-nb[1]],'expected_wh':[ew,eh]})
            if n['kind'] in ('ellipse','diamond'):
                cx=(nb[0]+nb[2])/2;cy=(nb[1]+nb[3])/2;rx=(nb[2]-nb[0])/2;ry=(nb[3]-nb[1])/2
                vals=[]
                for x in (b[0],b[2]):
                    for y in (b[1],b[3]):
                        vals.append(((x-cx)/rx)**2+((y-cy)/ry)**2 if n['kind']=='ellipse' else abs((x-cx)/rx)+abs((y-cy)/ry))
                if max(vals)>1.00001:issues.append({'code':'text_crosses_shape_boundary','id':t['id']})
    for i,a in enumerate(s.texts):
        for b in s.texts[i+1:]:
            if intersects(a['position']['bbox'],b['position']['bbox'],.05):
                issues.append({'code':'text_overlap','ids':[a['id'],b['id']]})
    for n in s.nodes:
        x,y,r,b=n['rect'];w=n['width']/2
        if not contains(page,[x-w,y-w,r+w,b+w],.02):issues.append({'code':'shape_outside_page','id':n['id']})
        if n['kind']=='rectangle':
            corners=[[x,y],[r,y],[r,b],[x,b],[x,y]]
            for t in s.texts:
                if t['owner']==n['id']:continue
                if any(segment_hits(a,b,t['position']['bbox'],w+.1) for a,b in zip(corners,corners[1:])):
                    issues.append({'code':'text_shape_collision','text':t['id'],'shape':n['id']})
    for p in s.paths:
        pts=p['points'];protection=p['width']/2+.1
        if s.template=='primitive-scene' and p['arrow'] and not p.get('endpoint_nodes'):
            issues.append({'code':'arrow_endpoint_semantics_missing','id':p['id']})
        for t in s.texts:
            if any(segment_hits(a,b,t['position']['bbox'],protection) for a,b in zip(pts,pts[1:])):
                issues.append({'code':'text_path_collision','text':t['id'],'path':p['id']})
        for a in pts:
            if not contains(page,[a[0]-protection,a[1]-protection,a[0]+protection,a[1]+protection],.02):
                issues.append({'code':'path_outside_page','id':p['id']});break
        for start in ([False,True] if p['both'] else [False] if p['arrow'] else []):
            actual=math.dist(pts[0],pts[1]) if start else math.dist(pts[-2],pts[-1])
            required=ARROW_LENGTH*p.get("arrow_scale",1)
            if actual<required-1e-5:
                issues.append({'code':'arrow_terminal_length','id':p['id'],'at_start':start,
                               'actual_pt':actual,'required_pt':required})
            elif p.get('exact_terminal') and abs(actual-required)>1e-5:
                issues.append({'code':'arrow_terminal_not_exact','id':p['id'],'at_start':start,
                               'actual_pt':actual,'required_pt':required})
            try:
                vertices=arrow_vertices(pts,at_start=start,scale=p.get("arrow_scale",1))
                box=[min(q[0] for q in vertices),min(q[1] for q in vertices),max(q[0] for q in vertices),max(q[1] for q in vertices)]
                if not contains(page,box):issues.append({'code':'arrow_outside_page','id':p['id']})
                for t in s.texts:
                    if intersects(box,t['position']['bbox']):issues.append({'code':'arrow_text_collision','path':p['id'],'text':t['id']})
            except FigureError as e:issues.append(e.as_dict()|{'id':p['id']})
    for a in s.assets:
        if not contains(page,a['rect'],.02):issues.append({'code':'asset_outside_page','id':a['id']})
    return issues
