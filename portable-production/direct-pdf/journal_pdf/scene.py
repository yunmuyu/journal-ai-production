from __future__ import annotations
import math
from .common import FigureError, contains, intersects, segment_hits, finite, digest_file, resolve_source
from .boundary_ports import BoundaryGeometry, rectangular_path_bounds
from .fonts import position_text
from .flow_shapes import is_flow_terminal
from .editorial import display_content, wrap_text, PAD_X, PAD_Y, STROKE, ARROW_LENGTH, diamond_size
from .text_geometry import oblique,polygons,texts_intersect,segment_intersects_text,arrow_intersects_text

def validate_node_dash(dash, *, id=None):
    if dash is not None and (not isinstance(dash,list) or not dash or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in dash) or not any(dash)):
        raise FigureError('invalid_node_dash','节点虚线须为非负有限数列，且不能全为零',id=id)


class Scene:
    def __init__(self,registry,size=8):
        self.registry=registry;self.size=size
        self.nodes=[];self.texts=[];self.paths=[];self.assets=[];self.notes=[]
        self.width=0.;self.height=0.;self.template='';self.layout_evidence={}
        self.measurement_groups={};self.source_bindings={};self.verified_source_bindings={};self.source_root=None
        self._ids=set();self.node_groups={}
    def ident(self,id):
        if id in self._ids:raise FigureError('duplicate_object_id','重复对象ID',id=id)
        self._ids.add(id)
    def text(self,id,content,x,y,align='center',rotation=0,owner=None,role='label',size=None,wrap_chars=None,vertical=False,gray=0):
        if isinstance(gray,bool) or gray not in (0,1):raise FigureError('text_gray','文字仅支持显式黑0或白1')
        self.ident(id); source_content=content;content=display_content(content,role)
        if wrap_chars is not None:
            content=wrap_text(content,wrap_chars)
        m=self.registry.measure(content,size or self.size,role=role) if role!='label' else self.registry.measure(content,size or self.size)
        if vertical:m=self.registry.measure_vertical(content,size or self.size)
        p=position_text(m,x,y,align,rotation)
        if p['rotation']%90:
            p=position_text(m,x,y,align,p['rotation'],rotated_ink=self.registry.rotated_ink_bounds(m,p['rotation']))
        t={'id':id,'content':content,'source_content':source_content,'measurement':m,'position':p,'owner':owner,'role':role,'x':x,'y':y,'align':align,'gray':gray}
        self.texts.append(t);return t
    def shape(self,id,rect,kind='rectangle',container=False,width=.5,dash=None,checked=False,fill=None):
        self.ident(id)
        if kind not in ('rectangle','ellipse','diamond','roundrect','terminator','inputOutput','checkbox'):raise FigureError('unsupported_shape','形状未支持',kind=kind)
        if not finite(rect) or rect[2]<=rect[0] or rect[3]<=rect[1]:raise FigureError('invalid_node_rect','节点矩形无效',id=id)
        validate_node_dash(dash, id=id)
        if not isinstance(checked,bool):raise FigureError('checkbox_state_invalid','复选框选中态须为布尔值',id=id)
        if kind=='checkbox' and container:raise FigureError('checkbox_container_invalid','复选框是符号图元，不能作为容器',id=id)
        if kind!='checkbox' and checked:raise FigureError('checkbox_state_unsupported','只有复选框图元可声明选中态',id=id)
        if fill is not None:
            if isinstance(fill,bool) or not isinstance(fill,(int,float)) or not math.isfinite(fill) or not 0<=fill<=1:
                raise FigureError('node_fill_invalid','节点填充只接受 0 到 1 的显式灰度',id=id)
            if container:raise FigureError('node_fill_container','容器不参与填充，避免遮住层内对象',id=id)
        if width is not None and (isinstance(width,bool) or not isinstance(width,(int,float)) or not math.isfinite(width) or width<0):
            raise FigureError('node_width_invalid','节点描边宽度须为有限非负数，或显式 None 表示只填充不描边',id=id)
        n={'id':id,'rect':list(rect),'kind':kind,'container':container,'width':width}
        if kind=='checkbox':n['checked']=checked
        if fill is not None:n['fill']=float(fill)
        if dash is not None:n['dash']=list(dash)
        self.nodes.append(n);return n
    def box(self,id,content,x,y,w=None,h=None,kind='rectangle',padx=4.5,pady=2.7,wrap_chars=None,flow_role=None,text_role='label',vertical_text=False):
        terminal=is_flow_terminal(content,flow_role)
        if terminal:kind='terminator'
        display=display_content(content,text_role)
        if wrap_chars is not None:
            display=wrap_text(display,wrap_chars)
        m=self.registry.measure(display,self.size,role=text_role) if text_role!='label' else self.registry.measure(display,self.size)
        if vertical_text:m=self.registry.measure_vertical(display,self.size)
        scale=self.size/8
        if kind=='diamond':
            dw,dh,_=diamond_size(m['width'],m['height'],self.size)
            if w is None:w=dw
            if h is None:h=dh
        expected_w=m['width']+2*padx*scale+(8 if kind=='inputOutput' else 0)
        expected_h=m['height']+2*pady*scale
        if w is None:w=expected_w
        if h is None:h=expected_h
        node=self.shape(id,[x,y,x+w,y+h],kind)
        if terminal:node['flow_terminal']=True
        if kind in ('rectangle','roundrect','terminator'):
            node['padding_pt']=[padx*scale,pady*scale]
            node['measurement_contract']={'mode':'tight','expected_wh':[expected_w,expected_h]}
        self.text(id+':text',display,x+w/2,y+h/2,owner=id,role=text_role,vertical=vertical_text)
        return self.nodes[-1]
    def line(self,id,points,arrow=False,both=False,dash=None,width=.5,exact_terminal=False,endpoint_nodes=None,
             shared_net=None,semantic_role='connection'):
        self.ident(id); pts=[]
        for p in points:
            if not finite(p) or len(p)!=2:raise FigureError('path_point','无效线段坐标',id=id)
            if not pts or list(p)!=pts[-1]:pts.append(list(p))
        if len(pts)<2:raise FigureError('path_degenerate','零长度连接线',id=id)
        self.paths.append({'id':id,'points':pts,'arrow':arrow or both,'both':both,'dash':dash or [],'width':width,
                           'exact_terminal':bool(exact_terminal),'endpoint_nodes':endpoint_nodes,
                           'shared_net':shared_net,'semantic_role':semantic_role})
    def poly(self,id,points,fill=None,gray=0,width=.5,dash=None,closed=True,semantic_role=None,opacity=None):
        """闭合多边形（统计图数据几何）：0..1 墨量填充 + 0..1 灰度描边，不参与连接。"""
        self.ident(id); pts=[]
        for pt in points:
            if not finite(pt) or len(pt)!=2:raise FigureError('path_point','无效多边形坐标',id=id)
            if not pts or list(pt)!=pts[-1]:pts.append(list(pt))
        if closed and len(pts)>1 and pts[0]==pts[-1]:pts.pop()
        need=3 if closed else 2
        if len(pts)<need:raise FigureError('path_degenerate','多边形至少3个顶点',id=id)
        if fill is not None:
            if isinstance(fill,bool) or not isinstance(fill,(int,float)) or not math.isfinite(fill) or not 0<=fill<=1:
                raise FigureError('poly_fill_invalid','多边形填充只接受 0 到 1 的显式灰度',id=id)
        if gray is None or isinstance(gray,bool) or not isinstance(gray,(int,float)) or not math.isfinite(gray) or not 0<=gray<=1:
            raise FigureError('poly_gray_invalid','多边形描边灰度须为 0 到 1 的有限数值',id=id)
        if opacity is not None and (isinstance(opacity,bool) or not isinstance(opacity,(int,float)) or not math.isfinite(opacity) or not 0<opacity<=1):
            raise FigureError('poly_opacity_invalid','多边形填充透明度须为 0 到 1 的有限数值',id=id)
        rec={'id':id,'points':pts,'arrow':False,'both':False,'dash':dash or [],'width':width,
             'exact_terminal':False,'endpoint_nodes':None,'shared_net':None,
             'semantic_role':semantic_role or 'decorative',
             'fill':fill,'gray':gray,'closed':bool(closed)}
        if opacity is not None: rec['opacity']=opacity
        self.paths.append(rec)
    def group(self,id: str,members: list[str]) -> None:
        """Declare non-drawing aggregate ownership over existing real rectangles."""
        real_nodes={n['id'] for n in self.nodes if n['kind']=='rectangle'}
        if not isinstance(id,str) or not id or not isinstance(members,list) or not members or any(not isinstance(v,str) or v not in real_nodes for v in members) or len(set(members))!=len(members):
            raise FigureError('node_group_invalid','节点组须非空且仅含不重复的已存在真实矩形节点',id=id)
        self.ident(id);self.node_groups[id]=tuple(members)
    def embed(self,id,asset,target,role='plot'):
        self.ident(id);self.assets.append({'id':id,'asset':asset,'rect':list(target),'role':role})
    def finish(self,width,height):
        self.width=width;self.height=height;return self
    def export(self):
        result={'template':self.template,'width_pt':self.width,'height_pt':self.height,
                'nodes':self.nodes,'texts':[{k:v for k,v in t.items() if k!='measurement'}|{'text':t['measurement']['text'],'font_size_pt':t['measurement']['size'],'ink_bounds':t['position']['bbox']} for t in self.texts],
                'paths':self.paths,'assets':[{'id':a['id'],'rect':a['rect'],'role':a['role'],'asset_key':a['asset'].key,'audit':a['asset'].audit} for a in self.assets],
                'notes':self.notes,'layout_evidence':self.layout_evidence}
        if self.node_groups:result['node_groups']={key:list(value) for key,value in self.node_groups.items()}
        return result


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


def _matches_node_port(point,node,tolerance=.15):
    if node.get('kind') in {'ellipse','diamond'}:
        x0,y0,x1,y1=node['rect']
        cx,cy=(x0+x1)/2,(y0+y1)/2
        rx,ry=(x1-x0)/2,(y1-y0)/2
        if rx<=0 or ry<=0:return False
        if node['kind']=='ellipse':
            radius=math.hypot((point[0]-cx)/rx,(point[1]-cy)/ry)
        else:
            radius=abs((point[0]-cx)/rx)+abs((point[1]-cy)/ry)
        return abs(radius-1)<=tolerance/min(rx,ry)
    return any(math.dist(point,port(node,side))<=tolerance for side in ('left','right','top','bottom'))


def _matches_path_junction(point,path,tolerance=.15):
    for a,b in zip(path['points'],path['points'][1:]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        squared=dx*dx+dy*dy
        projection=max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/squared))
        nearest=[a[0]+projection*dx,a[1]+projection*dy]
        if math.dist(point,nearest)<=tolerance:
            return True
    return False


def _collinear_overlap_length(a,b,c,d,tolerance=.15):
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=math.hypot(dx,dy)
    ex,ey=d[0]-c[0],d[1]-c[1]
    other=math.hypot(ex,ey)
    if length<=tolerance or other<=tolerance:return 0.
    if abs(dx*ey-dy*ex)>tolerance*length:return 0.
    if abs(dx*(c[1]-a[1])-dy*(c[0]-a[0]))>tolerance*length:return 0.
    if abs(dx*(d[1]-a[1])-dy*(d[0]-a[0]))>tolerance*length:return 0.
    ux,uy=dx/length,dy/length
    c0=(c[0]-a[0])*ux+(c[1]-a[1])*uy
    c1=(d[0]-a[0])*ux+(d[1]-a[1])*uy
    return max(0.,min(length,max(c0,c1))-max(0.,min(c0,c1)))


def audit_scene(s:Scene):
    issues=[];page=[0,0,s.width,s.height];nmap={n['id']:n for n in s.nodes}
    pmap={p['id']:p for p in s.paths}
    boundaries=BoundaryGeometry({n['id']:tuple(n['rect']) for n in s.nodes if n['kind']=='rectangle'},
        {a['id']:tuple(a['rect']) for a in s.assets},
        {p['id']:rectangular_path_bounds(p['points']) for p in s.paths},
        {t['id']:tuple(t['position']['bbox']) for t in s.texts},s.node_groups,page=tuple(page),page_inset_scale=s.layout_evidence.get('whole_artwork_scale',1.))
    from .source_shape_targets import audit_shape_targets
    source_shape_contracts,shape_issues=audit_shape_targets(s)
    issues.extend(shape_issues)
    owner_text={t['owner']:t for t in s.texts if t.get('owner') in nmap}
    for node in s.nodes:
        text=owner_text.get(node['id'])
        terminal=node.get('flow_terminal') or (text is not None and is_flow_terminal(text['content']))
        if terminal and not node['container'] and node['kind']!='terminator':
            issues.append({'code':'flow_terminal_shape','id':node['id'],'expected':'terminator','actual':node['kind']})
    def natural_wh(node,text):
        px,py=node.get('padding_pt',[PAD_X*s.size/8,PAD_Y*s.size/8])
        ink=text['position']['bbox']
        return [ink[2]-ink[0]+2*px,ink[3]-ink[1]+2*py]
    def group_expected(node,text,contract):
        definition=s.measurement_groups.get(contract.get('group'))
        if not isinstance(definition,dict) or definition.get('axis')!=contract.get('axis') or node['id'] not in definition.get('nodes',[]):return None
        peers=[]
        for node_id in definition['nodes']:
            peer=nmap.get(node_id);peer_text=owner_text.get(node_id)
            if peer is None or peer_text is None or peer.get('container') or peer.get('kind') not in ('rectangle','roundrect','terminator'):return None
            peer_contract=peer.get('measurement_contract',{})
            if peer_contract.get('mode')!='measured-group' or peer_contract.get('group')!=contract.get('group') or peer_contract.get('axis')!=definition.get('axis'):return None
            peers.append(natural_wh(peer,peer_text))
        own=natural_wh(node,text);axis=definition['axis']
        width=max(v[0] for v in peers) if axis in ('column','both') else own[0]
        if 'cell_width_pt' in definition:
            target=definition['cell_width_pt']
            if (axis!='both' or isinstance(target,bool) or not isinstance(target,(int,float)) or
                    not math.isfinite(target) or target+1e-7<width):return None
            width=target
        height=max(v[1] for v in peers) if axis in ('row','both') else own[1]
        if 'cell_height_pt' in definition:
            target=definition['cell_height_pt']
            if (axis not in ('row','both') or isinstance(target,bool) or not isinstance(target,(int,float)) or
                    not math.isfinite(target) or target+1e-7<height):return None
            height=target
        return [width,height]
    def fixed_valid(node,contract):
        fixed=contract.get('fixed_size');constraints={'table-cell':'tabular-grid','code-panel':'source-code-viewport',
            'device-glyph':'source-symbol-bounds','source-locked-viewport':'source-artwork-bounds'}
        if not isinstance(fixed,dict):return False
        purpose=fixed.get('purpose');evidence=fixed.get('evidence',{})
        schema_ok=(purpose in constraints and node.get('role')==purpose and isinstance(evidence,dict) and
                evidence.get('constraint')==constraints[purpose] and isinstance(evidence.get('source_id'),str) and
                isinstance(evidence.get('source_sha256'),str) and len(evidence['source_sha256'])==64 and
                all(c in '0123456789abcdef' for c in evidence['source_sha256']))
        if not schema_ok:return False
        source_id=evidence['source_id'];expected=evidence['source_sha256']
        if s.verified_source_bindings.get(source_id)==expected:return True
        if s.source_root is None:return False
        try:return digest_file(resolve_source(s.source_root,source_id))==expected
        except (FigureError,OSError):return False
    for t in s.texts:
        b=t['position']['bbox']
        if not contains(page,b,.02):issues.append({'code':'text_outside_page','id':t['id'],'bounds':b})
        if t['owner']:
            if t['owner'] in pmap:continue
            if t['owner'] not in nmap:issues.append({'code':'text_owner_missing','id':t['id']});continue
            n=nmap[t['owner']];nb=n['rect'];pad=.3
            if not contains([nb[0]+pad,nb[1]+pad,nb[2]-pad,nb[3]-pad],b):
                issues.append({'code':'text_outside_owner','id':t['id'],'bounds':b,'owner':nb})
            if n['kind'] in ('rectangle','roundrect','terminator','inputOutput') and not n['container'] and n['id'] not in source_shape_contracts:
                px,py=n.get('padding_pt',[PAD_X*s.size/8,PAD_Y*s.size/8])
                margins=[b[0]-nb[0],b[1]-nb[1],nb[2]-b[2],nb[3]-b[3]]
                if n['kind']=='inputOutput':margins[0]-=min((nb[3]-nb[1])*.25,4);margins[2]-=min((nb[3]-nb[1])*.25,4)
                if any(v<minimum-.15 for v,minimum in zip(margins,[px,py,px,py])):
                    issues.append({'code':'node_text_padding','id':t['id'],'padding_pt':margins,'minimum_pt':[px,py,px,py]})
                if n['kind'] in ('rectangle','roundrect','terminator'):
                    contract=n.get('measurement_contract',{'mode':'missing'})
                    mode=contract.get('mode')
                    if mode=='tight':expected=natural_wh(n,t)
                    elif mode=='measured-group':expected=group_expected(n,t,contract)
                    elif mode=='fixed' and fixed_valid(n,contract):expected=[]
                    else:expected=None
                    if expected is None:
                        issues.append({'code':'primitive_box_measurement_contract','id':n['id']})
                    elif expected:
                        actual=[nb[2]-nb[0],nb[3]-nb[1]]
                        if any(abs(a-e)>.15 for a,e in zip(actual,expected)):
                            issues.append({'code':'primitive_box_measurement_mismatch','id':n['id'],
                                           'actual_wh':actual,'expected_wh':expected})
            if n['container']:
                margins=[b[0]-nb[0],b[1]-nb[1],nb[2]-b[2],nb[3]-b[3]]
                minimum=[PAD_X*s.size/8,PAD_Y*s.size/8,PAD_X*s.size/8,PAD_Y*s.size/8]
                if any(v<m-.15 for v,m in zip(margins,minimum)):
                    issues.append({'code':'container_title_padding','id':t['id'],'padding_pt':margins,'minimum_pt':minimum})
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
            if (texts_intersect(a,b) if oblique(a) or oblique(b) else intersects(a['position']['bbox'],b['position']['bbox'],.05)):
                issues.append({'code':'text_overlap','ids':[a['id'],b['id']]})
    for n in s.nodes:
        x,y,r,b=n['rect'];w=(n['width'] or 0.)/2
        if not contains(page,[x-w,y-w,r+w,b+w],.02):issues.append({'code':'shape_outside_page','id':n['id']})
        if n['kind']=='rectangle':
            corners=[[x,y],[r,y],[r,b],[x,b],[x,y]]
            for t in s.texts:
                if t['owner']==n['id']:continue
                if any(segment_intersects_text(a,b,t,w+.1) if oblique(t) else segment_hits(a,b,t['position']['bbox'],w+.1) for a,b in zip(corners,corners[1:])):
                    issues.append({'code':'text_shape_collision','text':t['id'],'shape':n['id']})
    s.layout_evidence['source_path_ports']=[]
    s.layout_evidence['page_external_ports']=[]
    for p in s.paths:
        pts=p['points'];protection=p['width']/2+.1
        endpoint_nodes=p.get('endpoint_nodes')
        if not p['arrow'] and isinstance(endpoint_nodes,list) and any(isinstance(row,dict) and 'page' in row for row in endpoint_nodes):
            issues.append({'code':'arrow_endpoint_external_requires_arrow','id':p['id']})
        arrow_exempt=p.get('semantic_role') in {'legend-swatch','decorative'}
        if p['arrow'] and endpoint_nodes is None and not arrow_exempt:
            issues.append({'code':'arrow_endpoint_semantics_missing','id':p['id']})
        if p['arrow'] and endpoint_nodes is not None and (not isinstance(endpoint_nodes,list) or len(endpoint_nodes)!=2):
            issues.append({'code':'arrow_endpoint_semantics_invalid','id':p['id'],'endpoint_nodes':endpoint_nodes})
        elif p['arrow'] and endpoint_nodes is not None:
            for start,node_id,point in ((True,endpoint_nodes[0],pts[0]),(False,endpoint_nodes[-1],pts[-1])):
                if isinstance(node_id,dict):
                    try:
                        if 'source_asset' in node_id:
                            from .source_path_ports import matches_source_port
                            matched=matches_source_port(node_id,tuple(point),s.assets)
                            if matched:s.layout_evidence['source_path_ports'].append({'path':p['id'],'at_start':start,'declaration':node_id,'point':point,'verified':True})
                        else:
                            matched=boundaries.matches(node_id,tuple(point),tuple(pts[1] if start else pts[-2]))
                            if matched and 'page' in node_id:s.layout_evidence['page_external_ports'].append({'path':p['id'],'at_start':start,'declaration':node_id,'point':point,'verified':True})
                        if not matched:
                            issues.append({'code':'arrow_endpoint_boundary_mismatch','id':p['id'],
                                           'at_start':start,'declaration':node_id,'point':point})
                    except FigureError as error:
                        issues.append(error.as_dict()|{'id':p['id'],'at_start':start})
                elif isinstance(node_id,str) or node_id is None:
                    node=nmap.get(node_id)
                    junction=node_id is None and any(q is not p and _matches_path_junction(point,q) for q in s.paths)
                    if not junction and (node is None or not _matches_node_port(point,node)):
                        issues.append({'code':'arrow_endpoint_node_port_mismatch','id':p['id'],'at_start':start,
                                       'node':node_id,'point':point})
                else:
                    issues.append({'code':'arrow_endpoint_declaration_invalid','id':p['id'],'at_start':start})
        segments=list(zip(pts,pts[1:]))
        if p.get('closed') and len(pts)>2:segments.append((pts[-1],pts[0]))
        for t in s.texts:
            if any(segment_intersects_text(a,b,t,protection) if oblique(t) else segment_hits(a,b,t['position']['bbox'],protection) for a,b in segments):
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
                    if arrow_intersects_text(vertices,t) if oblique(t) else intersects(box,t['position']['bbox']):issues.append({'code':'arrow_text_collision','path':p['id'],'text':t['id']})
            except FigureError as e:issues.append(e.as_dict()|{'id':p['id']})
    excluded_roles={'legend-swatch','decorative'}
    for i,p in enumerate(s.paths):
        if p.get('semantic_role') in excluded_roles and not p.get('arrow') and p.get('endpoint_nodes') is None:continue
        for q in s.paths[i+1:]:
            if q.get('semantic_role') in excluded_roles and not q.get('arrow') and q.get('endpoint_nodes') is None:continue
            shared=p.get('shared_net')
            bus_roles={'bus','trunk','branch','merge-leg','outlet'}
            explicitly_shared=(shared and shared==q.get('shared_net') and
                               p.get('semantic_role') in bus_roles and q.get('semantic_role') in bus_roles and
                               not p.get('arrow') and not q.get('arrow'))
            if explicitly_shared:continue
            overlap=0.
            for a,b in zip(p['points'],p['points'][1:]):
                for c,d in zip(q['points'],q['points'][1:]):
                    overlap=max(overlap,_collinear_overlap_length(a,b,c,d))
            if overlap>.15:
                issues.append({'code':'path_collinear_overlap','ids':[p['id'],q['id']],'overlap_pt':overlap})
    for a in s.assets:
        if not contains(page,a['rect'],.02):issues.append({'code':'asset_outside_page','id':a['id']})
    return issues
