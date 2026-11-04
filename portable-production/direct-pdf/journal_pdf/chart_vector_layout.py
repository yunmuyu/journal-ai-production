"""Source-bound chart text layout without altering native vector data."""
from __future__ import annotations
import copy
import math
from pathlib import Path
import pymupdf as fitz
from .common import FigureError, digest_file, resolve_source
from .editorial import TICK_CLEARANCE, LABEL_CLEARANCE, STROKE, display_content
from .fonts import position_text


def _fail(code, message):
    raise FigureError(code,message)


def _point(value):
    if not isinstance(value,list) or len(value)!=2 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in value):
        _fail('chart_vector_point','坐标轴锚点须是有限数值')
    return tuple(value)



def _axis_outer_ink(page,clip,origin,xend,yend,placement_scale,y_outward=-1):
    """Measure axis outside ink at final-size 600 dpi, avoiding crossings."""
    pixels_per_pt=600/72
    factor=placement_scale*pixels_per_pt
    if (clip[2]-clip[0])*(clip[3]-clip[1])*factor*factor>50_000_000:
        _fail('chart_axis_measure_budget','坐标轴实测范围过大')
    pix=page.get_pixmap(matrix=fitz.Matrix(factor,factor),clip=fitz.Rect(clip),colorspace=fitz.csGRAY,alpha=False)
    def sample(x,y,axis):
        px=round(x*factor)-pix.x;py=round(y*factor)-pix.y
        if not (0<=px<pix.width and 0<=py<pix.height):return None
        def value(k):
            xx=px+(k if axis=='y' else 0);yy=py+(k if axis=='x' else 0)
            return pix.samples[yy*pix.stride+xx] if 0<=xx<pix.width and 0<=yy<pix.height else 255
        dark=next((k for k in (0,-1,1,-2,2) if value(k)<160),None)
        if dark is None:return None
        step=1 if axis=='x' else y_outward;edge=dark
        while abs(edge)<40 and value(edge+step)<160:edge+=step
        if abs(edge)>=40:return None
        return max(0.,(edge+.5 if axis=='x' else y_outward*edge+.5)/pixels_per_pt)
    xf=[];yf=[]
    for i in range(2,19):
        f=i/20
        a=sample(origin[0]+(xend[0]-origin[0])*f,origin[1],'x')
        b=sample(origin[0],origin[1]+(yend[1]-origin[1])*f,'y')
        if a is not None:xf.append(a)
        if b is not None:yf.append(b)
    if len(xf)<4 or len(yf)<4:_fail('chart_axis_ink_unmeasurable','无法从实际图形可靠测量坐标轴墨迹')
    return min(xf),min(yf)

def layout_vector_chart(spec,reg,root,size):
    plan=spec.get('chart_vector_layout')
    if not isinstance(plan,dict):_fail('chart_vector_plan','缺少原矢量图表布局计划')
    bodies=[a for a in spec.get('assets',[]) if a.get('id')==plan.get('body_id') and a.get('source_vector_body') is True and a.get('source_kind')=='pdf']
    if len(bodies)!=1:_fail('chart_vector_body','必须绑定唯一的原矢量PDF图体')
    body=bodies[0];path=resolve_source(Path(root),body['path']);sha=digest_file(path)
    if plan.get('source_sha256')!=sha:_fail('chart_vector_source','图表几何须绑定当前源文件')
    legend=spec.get('legend_review',{})
    if legend.get('present') not in (True,False) or legend.get('source_sha256')!=sha or not str(legend.get('reason','')).strip():
        _fail('chart_vector_legend','须明确核对并绑定当前源件的图例')
    clip=body['clip'];target=body['target']
    if len(clip)!=4 or len(target)!=4 or clip[2]<=clip[0] or clip[3]<=clip[1]:_fail('chart_vector_clip','图表原图裁切无效')
    sx=(target[2]-target[0])/(clip[2]-clip[0]);sy=(target[3]-target[1])/(clip[3]-clip[1])
    if sx<=0 or abs(sx-sy)>1e-5:_fail('chart_vector_scale','原矢量图体须等比缩放')
    origin=_point(plan.get('axis_origin'));xend=_point(plan.get('x_axis_end'));yend=_point(plan.get('y_axis_end'))
    if abs(xend[1]-origin[1])>.02 or abs(yend[0]-origin[0])>.02 or xend[0]<=origin[0] or yend[1]>=origin[1]:
        _fail('chart_vector_axis','当前入口仅支持核对过的水平X轴及竖直Y轴')
    with fitz.open(path) as doc:
        page=doc[body.get('page',0)];axis_ink=_axis_outer_ink(page,clip,origin,xend,yend,sx);segments=[]
        right_ink=_axis_outer_ink(page,clip,xend,origin,(xend[0],yend[1]),sx,y_outward=1)[1] if plan.get('secondary_y_axis') else None
        for drawing in page.get_drawings():
            for item in drawing['items']:
                if item[0]=='l' and isinstance(drawing.get('width'),(int,float)) and drawing['width']>0:segments.append((item[1],item[2],drawing['width']))
    tol=.025
    def intersects(point,orientation):
        x,y=point
        for a,b,_ in segments:
            if orientation=='x' and abs(a.y-b.y)<=tol and abs(y-a.y)<=tol and min(a.x,b.x)-tol<=x<=max(a.x,b.x)+tol:return True
            if orientation=='y' and abs(a.x-b.x)<=tol and abs(x-a.x)<=tol and min(a.y,b.y)-tol<=y<=max(a.y,b.y)+tol:return True
        return False
    if not (intersects(origin,'x') and intersects(origin,'y') and intersects(xend,'x') and intersects(yend,'y')):
        _fail('chart_vector_axis_binding','源坐标轴端点未绑定到真实矢量线段')
    def axis_width(orientation):
        x,y=origin;matches=[]
        for a,b,w in segments:
            if orientation=='x' and abs(a.y-b.y)<=tol and abs(y-a.y)<=tol and min(a.x,b.x)-tol<=x<=max(a.x,b.x)+tol:matches.append(w)
            if orientation=='y' and abs(a.x-b.x)<=tol and abs(x-a.x)<=tol and min(a.y,b.y)-tol<=y<=max(a.y,b.y)+tol:matches.append(w)
        if not matches:_fail('chart_vector_stroke','无法读取源坐标轴描边宽度')
        return max(matches)
    xaxis_width=axis_width('x');yaxis_width=axis_width('y')
    out=copy.deepcopy(spec);texts={t['id']:t for t in out.get('texts',[])}
    replacements={x['target_text_id'] for x in body.get('text_replacements',[])}
    ticks=[]
    for axis in ('x','y'):
        entries=plan.get(axis+'_ticks')
        if not isinstance(entries,list) or not entries:_fail('chart_vector_ticks','两轴刻度须明确绑定')
        for e in entries:
            ident=e.get('id');pt=_point(e.get('point'))
            if ident not in texts or ident not in replacements or texts[ident].get('role')!='axis-tick':_fail('chart_vector_tick_id','刻度文本须绑定原字及目标对象')
            replacement=next(r for r in body['text_replacements'] if r['target_text_id']==ident)
            box=replacement.get('source_bbox')
            if not isinstance(box,list) or len(box)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in box):_fail('chart_vector_tick_binding','刻度缺少原文字边界')
            dim=0 if axis=='x' else 1
            if abs((box[dim]+box[dim+2])/2-pt[dim])>(box[dim+2]-box[dim])/2+.1:_fail('chart_vector_tick_binding','刻度文字与源刻线绑定不匹配')
            if axis=='x':ok=abs(pt[1]-origin[1])<=tol and intersects(pt,'x') and intersects(pt,'y') and origin[0]-tol<=pt[0]<=xend[0]+tol
            else:ok=abs(pt[0]-origin[0])<=tol and intersects(pt,'x') and intersects(pt,'y') and yend[1]-tol<=pt[1]<=origin[1]+tol
            if not ok:_fail('chart_vector_tick_geometry','刻度位置未绑定真实轴线和刻线')
            ticks.append((axis,ident,pt))
    ids=[i for _,i,_ in ticks];actual=[t['id'] for t in out['texts'] if t.get('role')=='axis-tick']
    if len(ids)!=len(set(ids)) or sorted(ids)!=sorted(actual):_fail('chart_vector_tick_coverage','刻度文字须完整绑定且不得重复')
    titles=[plan.get('x_title_id'),plan.get('y_title_id')]
    if len(set(titles))!=2 or any(i not in texts or i not in replacements or texts[i].get('role')!='axis-title' for i in titles):_fail('chart_vector_title','两轴标题须绑定原文字')
    if sorted(plan.get('x_title_ids',[titles[0]])+[titles[1]])!=sorted(t['id'] for t in out['texts'] if t.get('role')=='axis-title'):_fail('chart_vector_title_coverage','轴标题须完整绑定')
    def mapx(x):return target[0]+(x-clip[0])*sx
    def mapy(y):return target[1]+(y-clip[1])*sy
    legend_ids=[];legend_bindings=[];legend_frame=None
    if legend.get('present') is True:
        from .chart_vector_legend import layout_legend
        legend_ids,legend_bindings,legend_frame=layout_legend(legend,path,body,texts,reg,size,mapx,mapy)
    elif any(t.get('role')=='legend-label' for t in texts.values()):_fail('chart_vector_legend','无图例声明与图例文字冲突')
    secondary=copy.deepcopy(plan.get('secondary_y_axis'))
    secondary_ids=[]
    if secondary is not None:
        if not isinstance(secondary,dict) or not secondary.get('ticks') or not secondary.get('title_ids'):_fail('chart_secondary_binding','右轴绑定不完整')
        for entry in secondary['ticks']:
            ident=entry.get('id');pt=_point(entry.get('point'))
            if ident not in texts or ident not in replacements or abs(pt[0]-xend[0])>tol or not intersects(pt,'x') or not intersects(pt,'y'):_fail('chart_secondary_binding','右轴刻度未绑定真实线段')
            box=next(r['source_bbox'] for r in body['text_replacements'] if r['target_text_id']==ident)
            if not box[1]-.1<=pt[1]<=box[3]+.1:_fail('chart_secondary_binding','右轴刻度与原文位置不符')
            ends=[max(a.x,b.x) for a,b,_ in segments if abs(a.y-b.y)<=tol and abs(a.y-pt[1])<=tol and min(a.x,b.x)<=pt[0]+tol<=max(a.x,b.x) and max(a.x,b.x)>pt[0]+tol]
            if not ends:_fail('chart_secondary_binding','右轴缺少可确认的向外刻线')
            entry['tick_end']=[max(ends),pt[1]]
            texts[ident].update(x=mapx(max(ends))+right_ink+TICK_CLEARANCE*size/8,y=mapy(pt[1]),align='left',rotation=0)
            secondary_ids.append(ident)
        title_ids=secondary['title_ids']
        if any(i not in texts or i not in replacements for i in title_ids):_fail('chart_secondary_binding','右轴标题缺少原文绑定')
        tick_boxes=[position_text(reg.measure(texts[i]['text'],size),texts[i]['x'],texts[i]['y'],align='left')['bbox'] for i in secondary_ids]
        measures=[reg.measure(texts[i]['text'],size) for i in title_ids]
        x=max(b[2] for b in tick_boxes)+LABEL_CLEARANCE*size/8+max(m['height'] for m in measures)/2
        cursor=(mapy(origin[1])+mapy(yend[1]))/2+(sum(m['width'] for m in measures)+.5*(len(measures)-1))/2
        for ident,m in zip(title_ids,measures):
            texts[ident].update(x=x,y=cursor-m['width']/2,align='center',rotation=90);cursor-=m['width']+.5
        secondary_ids.extend(title_ids)
    annotations=plan.get('annotations',[])
    if not isinstance(annotations,list):_fail('chart_vector_annotation','图内标注须逐项绑定原文')
    if any(not isinstance(row,dict) or not isinstance(row.get('parts'),list) or not row['parts'] or any(not isinstance(p,dict) or not isinstance(p.get('id'),str) for p in row['parts']) for row in annotations):_fail('chart_vector_annotation','图内标注片段格式无效')
    annotation_ids=[part.get('id') for row in annotations if isinstance(row,dict) for part in row.get('parts',[]) if isinstance(part,dict)]
    if len(annotation_ids)!=len(set(annotation_ids)) or any(i not in texts or i not in replacements for i in annotation_ids):_fail('chart_vector_annotation','标注文字缺少唯一原文绑定')
    if set(ids+plan.get('x_title_ids',[titles[0]])+[titles[1]]+legend_ids+secondary_ids+annotation_ids)!=replacements or set(texts)!=replacements:_fail('chart_vector_text_coverage','原文字必须完整绑定刻度、轴题、图例或图内标注')
    axis_x,axis_y=mapx(origin[0]),mapy(origin[1]);scale=size/8
    xrows=[];yrows=[]
    for axis,ident,point in ticks:
        t=texts[ident];measurement=reg.measure(display_content(t['text'],'axis-tick'),size,role='axis-tick')
        (xrows if axis=='x' else yrows).append((t,point,measurement))
    rotation=plan.get('x_tick_rotation','auto')
    if rotation not in ('auto','vertical'):_fail('chart_vector_rotation','横轴刻度布局仅接受自动或竖排')
    def bounds_for(angle):
        return sorted((position_text(m,mapx(pt[0]),0,rotation=angle)['bbox'] for _,pt,m in xrows),key=lambda b:b[0])
    def spacing_ok(boxes):return all(b[0]-a[2]>=2*scale-.1 for a,b in zip(boxes,boxes[1:]))
    angle=90 if rotation=='vertical' or not spacing_ok(bounds_for(0)) else 0
    if not spacing_ok(bounds_for(angle)):_fail('chart_vector_tick_spacing','当前8pt及栏宽下刻度无法满足间距，须重新布局')
    xbottom=[]
    for t,pt,m in xrows:
        box=position_text(m,mapx(pt[0]),0,rotation=angle)['bbox'];height=box[3]-box[1]
        t.update(x=mapx(pt[0]),y=axis_y+axis_ink[0]+TICK_CLEARANCE*scale+height/2,align='center',rotation=angle)
        xbottom.append(t['y']+height/2)
    yleft=[]
    y_boxes=[]
    for t,pt,m in yrows:
        t.update(x=axis_x-axis_ink[1]-TICK_CLEARANCE*scale,y=mapy(pt[1]),align='right',rotation=0)
        box=position_text(m,t['x'],t['y'],align='right')['bbox'];yleft.append(box[0]);y_boxes.append(box)
    adjustment=0.
    for t,pt,m in xrows:
        box=position_text(m,t['x'],t['y'],rotation=angle)['bbox']
        for other in y_boxes:
            if box[0]<other[2] and box[2]>other[0]:adjustment=max(adjustment,other[3]+2*scale-box[1])
    adjustment=max(0.,adjustment)
    if adjustment:
        for t,_,_ in xrows:t['y']+=adjustment
        xbottom=[value+adjustment for value in xbottom]
    xt=texts[titles[0]];xm=reg.measure(display_content(xt['text'],'axis-title'),size,role='axis-title')
    xt.update(x=(axis_x+mapx(xend[0]))/2,y=max(xbottom)+LABEL_CLEARANCE*scale+xm['height']/2,align='center',rotation=0)
    yt=texts[titles[1]];ym=reg.measure(display_content(yt['text'],'axis-title'),size,role='axis-title')
    yt.update(x=min(yleft)-LABEL_CLEARANCE*scale,y=(axis_y+mapy(yend[1]))/2,align='right',rotation=90)
    x_title_ids=plan.get('x_title_ids',[titles[0]])
    if not isinstance(x_title_ids,list) or not x_title_ids or x_title_ids[0]!=titles[0] or len(set(x_title_ids))!=len(x_title_ids) or any(i not in texts or i not in replacements for i in x_title_ids):_fail('chart_vector_title_parts','轴题片段绑定不完整')
    group_measurements=[reg.measure(display_content(texts[i]['text'],'axis-title'),size,role='axis-title') for i in x_title_ids]
    group_width=sum(m['width'] for m in group_measurements)+.5*(len(x_title_ids)-1)
    cursor=xt['x']-group_width/2
    for ident,measurement in zip(x_title_ids,group_measurements):
        texts[ident].update(x=cursor+measurement['width']/2,y=xt['y'],align='center',rotation=0)
        cursor+=measurement['width']+.5
    annotation_evidence=[]
    if annotations:
        from .chart_vector_annotations import place_annotations
        annotation_evidence=place_annotations(annotations,texts,body,path,reg,size,clip,target,origin,xend,yend)
    title_box=position_text(xm,xt['x'],xt['y'])['bbox'];ytitle_box=position_text(ym,yt['x'],yt['y'],align='right',rotation=90)['bbox']
    if ytitle_box[0]<0 or title_box[0]<0 or title_box[2]>out['width_pt']:_fail('chart_vector_layout_capacity','8pt轴标题超出画布；不能裁掉或更改曲线')
    out['height_pt']=max(out['height_pt'],title_box[3]+2)
    evidence={'source_sha256':sha,'source_geometry_verified':True,'x_tick_rotation':angle,'x_tick_ids':[t['id'] for t,_,_ in xrows],
              'y_tick_ids':[t['id'] for t,_,_ in yrows],'x_title_id':titles[0],'x_title_ids':x_title_ids,'y_title_id':titles[1],
              'tick_clearance_pt':TICK_CLEARANCE*scale,'title_clearance_pt':LABEL_CLEARANCE*scale,'corner_tick_adjustment_pt':adjustment,
              'minimum_tick_text_gap_pt':2*scale,'curve_data_reconstructed':False,
              'source_clip':list(clip),'target_rect':list(target),'source_axis_origin':list(origin),
              'source_x_axis_end':list(xend),'source_y_axis_end':list(yend),
              'x_axis_stroke_pt':xaxis_width,'y_axis_stroke_pt':yaxis_width,'source_axis_outer_ink_pt':list(axis_ink),
              'legend_bindings':legend_bindings,'legend_source_frame':legend_frame,'secondary_y_axis':secondary,'annotations':annotation_evidence,
              'source_x_ticks':{ident:list(pt) for axis,ident,pt in ticks if axis=='x'},
              'source_y_ticks':{ident:list(pt) for axis,ident,pt in ticks if axis=='y'}}
    return out,evidence


def audit_vector_chart_pdf(pdf_path,scene):
    evidence=scene.layout_evidence.get('chart_vector_layout')
    if not evidence:return None
    factor=scene.layout_evidence.get('whole_artwork_scale',1.)
    offset=scene.layout_evidence.get('export_canvas_offset_pt',[0,0])
    crop=scene.layout_evidence['export_crop']['crop_box'];clip=evidence['source_clip'];target=evidence['target_rect']
    sx=(target[2]-target[0])/(clip[2]-clip[0]);sy=(target[3]-target[1])/(clip[3]-clip[1])
    def output_point(point):
        return ((target[0]+(point[0]-clip[0])*sx)*factor+offset[0]-crop[0],
                (target[1]+(point[1]-clip[1])*sy)*factor+offset[1]-crop[1])
    origin=output_point(evidence['source_axis_origin']);xe=output_point(evidence['source_x_axis_end']);ye=output_point(evidence['source_y_axis_end'])
    with fitz.open(pdf_path) as doc:
        final_ink=_axis_outer_ink(doc[0],list(doc[0].rect),origin,xe,ye,1.)
        final_right_ink=_axis_outer_ink(doc[0],list(doc[0].rect),xe,origin,(xe[0],ye[1]),1.,y_outward=1)[1] if evidence.get('secondary_y_axis') else None
        segments=[]
        for drawing in doc[0].get_drawings():
            width=drawing.get('width')
            if not isinstance(width,(int,float)) or width<=0:continue
            for item in drawing['items']:
                if item[0]=='l':segments.append((item[1],item[2],width))
    def line_width(point,direction):
        x,y=point;found=[]
        for a,b,w in segments:
            if direction=='x' and abs(a.y-b.y)<.05 and abs(a.y-y)<.08 and min(a.x,b.x)-.08<=x<=max(a.x,b.x)+.08:found.append(w)
            if direction=='y' and abs(a.x-b.x)<.05 and abs(a.x-x)<.08 and min(a.y,b.y)-.08<=y<=max(a.y,b.y)+.08:found.append(w)
        if not found:_fail('chart_pdf_axis_missing','最终PDF未找到绑定的坐标轴或刻线')
        return max(found)
    xw=line_width(origin,'x');yw=line_width(origin,'y')
    line_width(xe,'x');line_width(ye,'y')
    # Axis stroke is measured from the final PDF, not inferred from the source.
    text={t['id']:t for t in scene.texts}
    def bbox(ident):
        if ident not in text:_fail('chart_pdf_text_missing','最终布局缺少轴文字')
        b=text[ident]['position']['bbox'];return [b[0]-crop[0],b[1]-crop[1],b[2]-crop[0],b[3]-crop[1]]
    xboxes=[];xerrors=[];xgaps=[]
    for ident,source_point in evidence['source_x_ticks'].items():
        anchor=output_point(source_point);line_width(anchor,'x');line_width(anchor,'y');b=bbox(ident)
        xerrors.append(abs((b[0]+b[2])/2-anchor[0]));xgaps.append(b[1]-(origin[1]+final_ink[0]));xboxes.append(b)
    yboxes=[];yerrors=[];ygaps=[]
    for ident,source_point in evidence['source_y_ticks'].items():
        anchor=output_point(source_point);line_width(anchor,'x');line_width(anchor,'y');b=bbox(ident)
        yerrors.append(abs((b[1]+b[3])/2-anchor[1]));ygaps.append(origin[0]-final_ink[1]-b[2]);yboxes.append(b)
    scale=scene.size/8;required_tick=TICK_CLEARANCE*scale;required_title=LABEL_CLEARANCE*scale
    xt=bbox(evidence['x_title_id']);yt=bbox(evidence['y_title_id'])
    title_gaps=[xt[1]-max(b[3] for b in xboxes),min(b[0] for b in yboxes)-yt[2]]
    xboxes.sort(key=lambda b:b[0]);spacing=[b[0]-a[2] for a,b in zip(xboxes,xboxes[1:])]
    if max(xerrors+yerrors,default=0)>.12:_fail('chart_pdf_tick_alignment','最终PDF刻度文字未对齐真实刻线')
    required_x=required_tick+evidence.get('corner_tick_adjustment_pt',0)*factor
    if any(abs(v-required_x)>.2 for v in xgaps) or any(abs(v-required_tick)>.2 for v in ygaps):raise FigureError('chart_pdf_tick_gap','最终PDF刻度至轴线净距不符',actual=xgaps+ygaps,expected_x=required_x,expected_y=required_tick,xstroke=xw,ystroke=yw)
    if any(abs(v-required_title)>.2 for v in title_gaps):_fail('chart_pdf_title_gap','最终PDF轴题至刻度净距不符')
    if any(v<2*scale-.1 for v in spacing):_fail('chart_pdf_tick_spacing','最终PDF相邻刻度文字净距不足')
    if text[evidence['y_title_id']]['position']['rotation'] not in (90,270):_fail('chart_pdf_y_title','纵轴标题未竖排')
    if any(text[i]['position']['rotation']!=evidence['x_tick_rotation'] for i in evidence['source_x_ticks']):_fail('chart_pdf_tick_rotation','横轴刻度方向不一致')
    legend_boxes=[]
    for row in evidence.get('legend_bindings',[]):
        group_boxes=[bbox(i) for i in row.get('text_ids',[row['text_id']])];box=[min(b[0] for b in group_boxes),min(b[1] for b in group_boxes),max(b[2] for b in group_boxes),max(b[3] for b in group_boxes)];end=output_point(row['source_swatch_end']);center=output_point(row['source_swatch_center'])
        frame=evidence['legend_source_frame'];first=output_point(frame[:2]);last=output_point(frame[2:]);outer=fitz.Rect(*first,*last)
        if not outer.contains(fitz.Rect(box)+(-.4,-.4,.4,.4)) or abs(box[0]-end[0]-LABEL_CLEARANCE*scale)>.2 or abs((box[1]+box[3])/2-center[1])>.2:
            _fail('chart_pdf_legend_layout','最终PDF图例文字未正确对齐源样符或超出框')
        if any(not (box[3]+2*scale-.1<=other[1] or other[3]+2*scale-.1<=box[1] or box[2]<=other[0] or other[2]<=box[0]) for other in legend_boxes):_fail('chart_pdf_legend_spacing','最终PDF图例文字间距不足')
        legend_boxes.append(box)
    annotation_count=0
    for row in evidence.get('annotations',[]):
        boxes=[bbox(i) for i in row['ids']]
        actual=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
        expected=[row['bbox'][i]*factor+offset[i%2]-crop[i%2] for i in range(4)]
        if any(abs(a-b)>.2 for a,b in zip(actual,expected)):_fail('chart_pdf_annotation_layout','最终PDF图内标注位置与避让结果不一致')
        annotation_count+=1
    secondary=evidence.get('secondary_y_axis')
    if secondary:
        secondary_boxes=[]
        for row in secondary['ticks']:
            anchor=output_point(row['point']);line_width(anchor,'x');width=line_width(anchor,'y');box=bbox(row['id'])
            end=output_point(row['tick_end']);line_width(end,'x')
            if abs((box[1]+box[3])/2-anchor[1])>.12 or abs(box[0]-end[0]-final_right_ink-required_tick)>.2:_fail('chart_pdf_secondary_gap','右轴刻度对齐或净距不符')
            secondary_boxes.append(box)
        title_boxes=[bbox(i) for i in secondary['title_ids']]
        if abs(min(b[0] for b in title_boxes)-max(b[2] for b in secondary_boxes)-required_title)>.2:_fail('chart_pdf_secondary_title','右轴标题净距不符')
    return {'passed':True,'tick_anchor_max_error_pt':max(xerrors+yerrors,default=0),
            'x_tick_gaps_pt':xgaps,'y_tick_gaps_pt':ygaps,'axis_title_gaps_pt':title_gaps,
            'minimum_tick_spacing_pt':min(spacing,default=None),'x_axis_stroke_pt':xw,'y_axis_stroke_pt':yw,
            'axis_outer_ink_pt':list(final_ink),'font_size_pt':scene.size,'source_sha256':evidence['source_sha256'],'curve_data_reconstructed':False,'legend_bindings_verified':len(legend_boxes),'annotations_verified':annotation_count}
