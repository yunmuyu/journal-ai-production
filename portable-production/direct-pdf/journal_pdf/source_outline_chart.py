"""Explicit, source-bound registration of a bounded outlined SVG chart.

No chart recognition, OCR, numeric reconstruction or author-specific coordinates.
Primitive identity includes its ancestry; changing the source invalidates registration.
"""
from __future__ import annotations
import copy, math, re
from pathlib import Path
from lxml import etree as ET
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from fontTools.misc.transform import Transform
from .common import FigureError, digest_file, digest_json

PRIMITIVES={'path','line','rect','circle','ellipse','polyline','polygon'}
NUM=r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?'


def need(ok, message):
    if not ok: raise FigureError('outline_chart_registration',message)


def numbers(value):
    parts=re.findall(NUM,value or '')
    need(not re.sub(NUM,'',value or '').strip(' ,\t\r\n'),'无效数值')
    out=list(map(float,parts));need(all(math.isfinite(v) for v in out),'非有限坐标')
    return out


def transform(value):
    matrix=Transform();end=0
    for m in re.finditer(r'(matrix|translate|scale|rotate)\s*\(([^)]*)\)',value or ''):
        need(not (value or '')[end:m.start()].strip(' ,'),'不支持的SVG变换');end=m.end()
        op=m[1];v=numbers(m[2])
        if op=='matrix':need(len(v)==6,'matrix需六个数');t=Transform(*v)
        elif op=='translate':need(len(v) in (1,2),'translate参数');t=Transform().translate(v[0],v[1] if len(v)==2 else 0)
        elif op=='scale':need(len(v) in (1,2),'scale参数');t=Transform().scale(v[0],v[-1])
        else:
            need(len(v) in (1,3),'rotate参数');x,y=v[1:] if len(v)==3 else (0,0)
            t=Transform().translate(x,y).rotate(math.radians(v[0])).translate(-x,-y)
        matrix=matrix.transform(t)
    need(not (value or '')[end:].strip(' ,'),'不支持的SVG变换')
    need(abs(matrix.xx*matrix.yy-matrix.xy*matrix.yx)>1e-12,'退化变换')
    return matrix


def inherited(node):
    out={};matrix=Transform()
    for q in [*reversed(list(node.iterancestors())),node]:
        matrix=matrix.transform(transform(q.get('transform','')))
        out.update({k:v for k,v in q.attrib.items() if k not in ('id','transform','style')})
        out.update(dict(term.strip().split(':',1) for term in q.get('style','').split(';') if ':' in term))
    return out,matrix


def path_data(node):
    tag=ET.QName(node).localname
    def f(k,default='0'):
        v=numbers(node.get(k,default));need(len(v)==1,'长度须为无单位有限数');return v[0]
    if tag=='path':return node.get('d','')
    if tag=='line':return f'M{f("x1")} {f("y1")} L{f("x2")} {f("y2")}'
    if tag in ('polygon','polyline'):
        v=numbers(node.get('points',''));need(len(v)>=4 and len(v)%2==0,'点列无效')
        return 'M'+' L'.join(f'{x} {y}' for x,y in zip(v[::2],v[1::2]))+(' Z' if tag=='polygon' else '')
    if tag=='rect':
        need(f('rx')==f('ry')==0,'本登记不支持圆角矩形')
        x,y,w,h=f('x'),f('y'),f('width'),f('height');need(w>0 and h>0,'矩形尺寸无效')
        return f'M{x} {y} L{x+w} {y} L{x+w} {y+h} L{x} {y+h} Z'
    x,y=f('cx'),f('cy');rx=f('r') if tag=='circle' else f('rx');ry=rx if tag=='circle' else f('ry')
    need(rx>0 and ry>0,'椭圆尺寸无效')
    return f'M{x-rx} {y} A{rx} {ry} 0 1 0 {x+rx} {y} A{rx} {ry} 0 1 0 {x-rx} {y} Z'


def primitive_inventory(path:Path):
    from .assets import svg_root
    root=svg_root(path);need(not any(isinstance(q,ET._Entity) for q in root.iter()),'不支持XML实体')
    need(not root.findall('.//{*}style'),'样式表尚未支持；仅接受显式属性')
    view=numbers(root.get('viewBox',''))
    if not view:
        w=numbers(root.get('width',''));h=numbers(root.get('height',''))
        need(len(w)==len(h)==1 and w[0]>0 and h[0]>0,'无viewBox时需明确无单位宽高');view=[0,0,w[0],h[0]]
    need(len(view)==4 and view[2]>0 and view[3]>0,'viewBox无效')
    rows=[];tree=root.getroottree()
    for node in root.iter():
        if not isinstance(node.tag,str):continue
        tag=ET.QName(node).localname
        if any(ET.QName(a).localname in ('defs','clipPath') for a in node.iterancestors()):continue
        if tag=='svg':need(node is root,'不支持嵌套SVG坐标系')
        if tag in ('svg','g','defs','clipPath','title','desc','metadata'):continue
        need(tag in PRIMITIVES,'登记只支持静态独立矢量图元，不支持文字、use或图像')
        attrs,matrix=inherited(node);data=path_data(node)
        pen=BoundsPen(None)
        try:parse_path(data,TransformPen(pen,matrix))
        except Exception as e:raise FigureError('outline_chart_path','不能验证SVG路径边界') from e
        need(pen.bounds is not None,'空图元不支持')
        x0,y0,x1,y1=pen.bounds
        stroke=attrs.get('stroke','none').strip();width=numbers(attrs.get('stroke-width','1'))
        need(len(width)==1 and width[0]>=0,'描边宽度无效')
        # Conservative ink extent; not used as numerical data or tick anchors.
        scale=math.sqrt(matrix.xx**2+matrix.xy**2+matrix.yx**2+matrix.yy**2)
        margin=0 if stroke=='none' else width[0]*scale/2
        if stroke!='none' and attrs.get('stroke-linejoin','miter').strip()=='miter':
            limit=numbers(attrs.get('stroke-miterlimit','4'));need(len(limit)==1 and limit[0]>=1,'miterlimit无效');margin*=limit[0]
        points=[]
        if tag=='line':
            vals=[numbers(node.get(k,'0'))[0] for k in ('x1','y1','x2','y2')]
            points=[list(matrix.transformPoint(vals[:2])),list(matrix.transformPoint(vals[2:]))]
        # Structural address is generated, never a naming convention or a chart heuristic.
        address=tree.getpath(node)
        record={'address':address,'attributes':dict(node.attrib),'ancestors':[dict(a.attrib) for a in reversed(list(node.iterancestors()))],'tag':tag}
        rows.append({'id':'primitive-'+str(len(rows)),'kind':'svg-primitive','tag':tag,'address':address,
                     'sha256':digest_json(record),'bbox':[x0,y0,x1,y1],'ink_bbox':[x0-margin,y0-margin,x1+margin,y1+margin],
                     'line_points':points,'path_data':data,'matrix':list(matrix),'fill':attrs.get('fill','black').strip(),'stroke':stroke})
    need(0<len(rows)<=2000,'图元数量超出登记边界')
    return {'source_sha256':digest_file(path),'viewbox':view,'objects':rows}


def bind_registration(inventory,registration):
    """Validate a complete explicit partition, then derive all layout coordinates."""
    r=copy.deepcopy(registration);objects=inventory['objects'];byid={o['id']:o for o in objects}
    fields={'source_sha256','bindings','frame','x_ticks','y_ticks','x_title','y_title','title','legend','series','protected_refs'}
    need(isinstance(r,dict) and set(r)==fields,'登记字段不完整或含未知字段')
    need(r['source_sha256']==inventory['source_sha256'],'源hash不匹配')
    need(isinstance(r['bindings'],dict) and set(r['bindings'])==set(byid),'每个源图元须绑定hash')
    need(all(r['bindings'][k]==v['sha256'] for k,v in byid.items()),'图元hash不匹配')
    def get(ref):need(isinstance(ref,str) and ref in byid,'图元引用无效');return byid[ref]
    def refs(rows):
        need(isinstance(rows,list) and bool(rows) and all(isinstance(x,str) for x in rows) and len(set(rows))==len(rows),'图元列表为空或重复')
        return [get(x) for x in rows]
    removed=[];semantic_ids=[]
    def label(row):
        need(isinstance(row,dict) and set(row)=={'refs','text'},'文字只接受图元refs与核对原文')
        need(isinstance(row['text'],str) and bool(row['text'].strip()),'文字原文为空')
        q=refs(row['refs']);need(all(v['tag']=='path' and v['stroke']=='none' for v in q),'转曲字须为独立填充path')
        removed.extend(row['refs']);return row['text']
    frame=get(r['frame']);f=frame['bbox']
    # Exact rectangle outline, not merely the bbox of a curve.
    from .ingest_native import simple_path_points
    p=simple_path_points(frame['path_data']);m=Transform(*frame['matrix']);p=[m.transformPoint(q) for q in p]
    need((frame['path_data'].rstrip().lower().endswith('z') or (len(p)==5 and p[0]==p[-1])) and len(p) in (4,5) and (len(p)==4 or p[0]==p[-1]),'轴框必须显式矩形路径')
    p=p[:4];corners={(f[0],f[1]),(f[2],f[1]),(f[2],f[3]),(f[0],f[3])}
    need(set(p)==corners and all(a[0]==b[0] or a[1]==b[1] for a,b in zip(p,p[1:]+p[:1])),'轴框不是轴对齐矩形')
    need(f[2]>f[0] and f[3]>f[1],'轴框退化')
    def ticks(rows,axis):
        need(isinstance(rows,list) and 1<=len(rows)<=150,'需完整标记刻度');out=[]
        for row in rows:
            need(isinstance(row,dict) and set(row)<={'tick_ref','label','text','power10'} and {'tick_ref','label','text'}<=set(row),'刻度登记字段无效')
            q=get(row['tick_ref']);pts=q['line_points'];need(len(pts)==2,'刻度必须为原独立直线')
            a,b=pts
            if axis=='x':need(abs(a[0]-b[0])<1e-6 and abs(max(a[1],b[1])-f[3])<1e-6 and min(a[1],b[1])<f[3] and f[0]-1e-6<=a[0]<=f[2]+1e-6,'需绑定底部向内刻线');position=a[0]
            else:need(abs(a[1]-b[1])<1e-6 and abs(min(a[0],b[0])-f[0])<1e-6 and max(a[0],b[0])>f[0] and f[1]-1e-6<=a[1]<=f[3]+1e-6,'需绑定左侧向内刻线');position=a[1]
            source_text=label(row['label']);need(source_text==row['text'],'刻度原文不一致')
            item={'text':row['text'],'position':position}
            if 'power10' in row:item['power10']=row['power10']
            from .charts import tick_content
            tick_content(item);out.append(item);semantic_ids.append(row['tick_ref'])
        need(len({v['position'] for v in out})==len(out),'重复刻度位置')
        return sorted(out,key=lambda x:x['position'])
    xt=ticks(r['x_ticks'],'x');yt=ticks(r['y_ticks'],'y')
    titles={}
    for key in ('x_title','y_title'):
        row=r[key];need(isinstance(row,dict) and set(row)=={'source','text','correction_evidence'},'轴题需明确来源、目标与更正证据')
        original=label(row['source']);need(isinstance(row['text'],str) and row['text'].strip(),'轴题为空')
        need(row['text']==original or (isinstance(row['correction_evidence'],str) and row['correction_evidence'].strip()),'改写轴题缺少授权证据')
        titles[key]=row['text']
    title=label(r['title']);titlebox=union([get(x)['bbox'] for x in r['title']['refs']])
    legend=r['legend'];need(isinstance(legend,dict) and set(legend)=={'decoration_refs','region_ref','width_extension','extension_evidence'},'图例登记字段无效')
    decorations=refs(legend['decoration_refs']);need(legend['region_ref'] in legend['decoration_refs'],'图例区域必须绑定装饰图元')
    region=get(legend['region_ref'])['bbox'];need(region[0]>=f[0] and region[1]>=f[1] and region[2]<=f[2] and region[3]<=f[3],'原图例须在轴框内')
    for q in decorations:
        pp=simple_path_points(q['path_data']);mm=Transform(*q['matrix']);pp=[mm.transformPoint(z) for z in pp];pp=pp[:-1] if len(pp)==5 and pp[0]==pp[-1] else pp
        need(q['path_data'].rstrip().lower().endswith('z') and len(pp)==4 and set(pp)=={(region[0],region[1]),(region[2],region[1]),(region[2],region[3]),(region[0],region[3])},'图例装饰必须与同一矩形区域严格一致')
    extra=legend['width_extension'];need(isinstance(extra,(int,float)) and not isinstance(extra,bool) and math.isfinite(extra) and extra>=0,'图例扩宽无效')
    need(extra==0 or (isinstance(legend['extension_evidence'],str) and bool(legend['extension_evidence'].strip())),'扩宽缺少授权证据')
    safe=[region[0],region[1],region[2]+extra,region[3]];need(safe[2]<=f[2],'图例扩宽超出绘图区')
    removed.extend(legend['decoration_refs']);entries=[];series_refs=[]
    need(isinstance(r['series'],list) and 1<=len(r['series'])<=30,'需完整系列登记')
    for series in r['series']:
        need(isinstance(series,dict) and set(series)=={'id','label','source_refs','swatch_refs'},'系列字段无效')
        need(isinstance(series['id'],str) and series['id'],'系列ID无效');text=label(series['label']);refs(series['source_refs']);sw=refs(series['swatch_refs'])
        from .common import contains
        need(all(contains(region,q['ink_bbox']) for q in sw),'原图例区域未完整包含样符')
        need(all(contains(region,get(x)['bbox']) for x in series['label']['refs']),'原图例区域未包含标签')
        series_refs.extend(series['source_refs']);removed.extend(series['swatch_refs'])
        entries.append({'id':series['id'],'label':text,'source_label_bbox':union([get(x)['bbox'] for x in series['label']['refs']]),'swatch_refs':series['swatch_refs'],'swatch_clip':union([q['ink_bbox'] for q in sw])})
    for left,right in zip(entries,entries[1:]):
        need(left['source_label_bbox'][1]<right['source_label_bbox'][1] and left['swatch_clip'][1]<right['swatch_clip'][1],
             '系列顺序必须保持原图例从上到下的单列顺序')
    need(len({s['id'] for s in entries})==len(entries) and len(set(series_refs))==len(series_refs),'系列或原图元重复')
    need(len(set(removed))==len(removed),'删除图元重复；文字/样符/装饰不可重叠')
    refs(r['protected_refs']);need(set(r['protected_refs'])==set(byid)-set(removed),'须全量保护所有未登记删除的原图元')
    need(set(series_refs+[r['frame']]+semantic_ids)<=set(r['protected_refs']),'曲线、轴框或刻线被登记删除')
    background_refs=[];boundary_refs=[]
    for ref in set(r['protected_refs'])-set(series_refs):
        q=get(ref);pts=q['line_points']
        if len(pts)==2 and (abs(pts[0][0]-pts[1][0])<1e-6 or abs(pts[0][1]-pts[1][1])<1e-6):
            need(contains(f,q['bbox'],1e-6),'受保护轴线/网格几何超出原轴框；不隐式裁切')
            boundary_refs.append(ref);continue
        pp=simple_path_points(q['path_data']);mm=Transform(*q['matrix']);pp=[mm.transformPoint(z) for z in pp]
        pp=pp[:-1] if len(pp)==5 and pp[0]==pp[-1] else pp
        box=q['bbox'];corners={(box[0],box[1]),(box[2],box[1]),(box[2],box[3]),(box[0],box[3])}
        need(q['path_data'].rstrip().lower().endswith('z') and len(pp)==4 and set(pp)==corners
             and box[0]<=f[0] and box[1]<=f[1] and box[2]>=f[2] and box[3]>=f[3],
             '未归属的受保护非轴线/背景图元；须补全系列或转曲文字登记')
        if q['bbox']==f:boundary_refs.append(ref)
        else:background_refs.append(ref)
    need(all(contains(f,get(ref)['bbox'],1e-6) for ref in series_refs),
         '受保护系列几何超出原轴框；本路线不推断原始裁切意图')
    # Preserve full boundary stroke ink rather than claiming protection after frame cropping.
    viewport=union([f]+[get(ref)['ink_bbox'] for ref in series_refs+boundary_refs])
    view=inventory['viewbox'];canvas=[view[0],view[1],view[0]+view[2],view[1]+view[3]]
    need(contains(canvas,viewport,1e-6),'受保护墨迹超出原SVG画布；不猜测边界裁切')
    # Every curve/marker bbox is conservative, including curves and transformed markers.
    protected=[get(x)['ink_bbox'] for x in series_refs]
    def overlaps(a,b):return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]
    need(not any(overlaps(box,safe) for box in protected),'图例原区或已授权扩宽区与受保护系列墨迹可能相交')
    return {'registration':r,'plot_clip':viewport,'axis_frame_source':f,'x_ticks':xt,'y_ticks':yt,**titles,
            'figure_title':title,'title_source_bbox':titlebox,'series':entries,'legend_safe_region':safe,
            'legend_original_region':region,'protected_ink_boxes':protected,'remove_refs':removed,
            'source_sha256':inventory['source_sha256'],'viewbox':inventory['viewbox'],
            'background_viewport_trimmed_refs':background_refs,'protected_geometry_inside_frame':True,'protected_ink_inside_viewport':True}


def union(boxes):
    return [min(q[0] for q in boxes),min(q[1] for q in boxes),max(q[2] for q in boxes),max(q[3] for q in boxes)]


def prepare_registered_svg(path,registration,*,swatch_id=None):
    from .assets import svg_root
    inv=primitive_inventory(path);bound=bind_registration(inv,registration);root=svg_root(path);tree=root.getroottree()
    selected=None
    if swatch_id is not None:
        matches=[s for s in bound['series'] if s['id']==swatch_id];need(len(matches)==1,'样符ID不存在');selected=set(matches[0]['swatch_refs'])
    removed=set(bound['remove_refs']) if selected is None else set(q['id'] for q in inv['objects'])-selected
    keep=[q for q in inv['objects'] if q['id'] not in removed]
    # Resolve nodes before deleting siblings, so positional addresses cannot drift.
    nodes={q['id']:tree.xpath(q['address'],namespaces={k:v for k,v in root.nsmap.items() if k})[0] for q in inv['objects']}
    before=digest_json([(q['id'],q['sha256']) for q in keep])
    for ref in removed:
        node=nodes[ref];node.getparent().remove(node)
    # Exact retained element + ancestor attribute identity (including nested transforms).
    for q in keep:
        node=nodes[q['id']];record={'address':q['address'],'attributes':dict(node.attrib),'ancestors':[dict(a.attrib) for a in reversed(list(node.iterancestors()))],'tag':q['tag']}
        need(digest_json(record)==q['sha256'],'保留图元发生改变')
    # Explicit unit normalization, no content geometry changes. Cairo PDF units become SVG user units.
    v=inv['viewbox'];root.set('viewBox',' '.join(map(str,v)));root.set('width',str(v[2])+'pt');root.set('height',str(v[3])+'pt')
    need(v[:2]==[0,0],'首版只支持原点为零的viewBox')
    return root,bound,{'mode':'registered-outlined-svg-chart','source_sha256':inv['source_sha256'],'retained_geometry_sha256':before,
                       'retained_primitive_count':len(keep),'removed_primitive_refs':sorted(removed),'geometry_unchanged':True,'curve_values_reconstructed':False,
                       'coordinate_conversion':{'original_root_attributes':dict(svg_root(path).attrib),'viewbox':v,'pdf_points_per_source_unit':1},
                       'semantic_review_required':True,'protected_geometry_inside_frame':True,'protected_ink_inside_viewport':True,
                       'background_viewport_trimmed_refs':bound['background_viewport_trimmed_refs']}


def validate_chart_spec(path,spec):
    bound=bind_registration(primitive_inventory(path),spec['outline_chart_registration'])
    keys=('plot_clip','axis_frame_source','x_ticks','y_ticks','x_title','y_title','figure_title',
          'title_source_bbox','series','legend_safe_region','legend_original_region','protected_ink_boxes')
    need(all(spec.get(k)==bound[k] for k in keys),'图表坐标或语义偏离当前源登记')
    need(spec.get('legend_placement')=='registered-source-region' and spec.get('legend_frame') is True
         and spec.get('tick_length_source_units')==0 and spec.get('restore_verified_tick_stubs') is False,
         '登记图表不得迁移图例或恢复虚构外向刻线')
    return bound
