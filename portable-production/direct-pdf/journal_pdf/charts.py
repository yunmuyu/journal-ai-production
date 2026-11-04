"""Original graphic viewport + measured labels + bound legend swatches."""
from __future__ import annotations
import math
from pathlib import Path
from .common import FigureError, resolve_source, contains, segment_hits, digest_file, digest_json
from .scene import Scene
from .chart_titles import finish_chart_title
from .legend_grid import pack_legend_columns
from .chart_annotations import source_annotations, place_source_annotations
from .fonts import position_text
from .axis_units import normalize_axis_title, axis_title_evidence
from .editorial import group_number, TICK_CLEARANCE, LABEL_CLEARANCE, STROKE
from PIL import Image
import io


def place_bar_top_labels(groups, measure, *, ink_gap_pt, plot_rect,
                         min_horizontal_gap_pt=2., rotation=0):
    if rotation not in (0,90):raise FigureError('bar_label_rotation','柱顶标签只支持横排或竖排')
    if not math.isfinite(ink_gap_pt) or ink_gap_pt < 0:
        raise FigureError('bar_label_gap','柱顶标签净距必须为有限非负值')
    if not math.isfinite(min_horizontal_gap_pt) or min_horizontal_gap_pt < 0:
        raise FigureError('bar_label_horizontal_gap','柱顶标签横向净距必须为有限非负值')
    if len(plot_rect) != 4:
        raise FigureError('bar_plot_rect','柱图绘图区必须为四元边界')
    placed=[]
    for group_index,group in enumerate(groups):
        for bar_index,bar in enumerate(group):
            rect=bar.get('rect');runs=bar.get('runs')
            if not isinstance(rect,(list,tuple)) or len(rect)!=4 or runs is None:
                raise FigureError('bar_label_input','每个柱必须显式提供rect和runs',group=group_index,bar=bar_index)
            x0,y0,x1,y1=map(float,rect)
            if not all(math.isfinite(v) for v in (x0,y0,x1,y1)) or x1<=x0 or y1<=y0:
                raise FigureError('bar_rect','柱边界无效',group=group_index,bar=bar_index,rect=rect)
            measured=measure(runs)
            probe=position_text(measured,(x0+x1)/2,0,align='center',rotation=rotation)
            h=probe['bbox'][3]-probe['bbox'][1]
            position=position_text(measured,(x0+x1)/2,y0-ink_gap_pt-h/2,align='center',rotation=rotation)
            bbox=position['bbox']
            if bbox[0] < plot_rect[0]-1e-6 or bbox[2] > plot_rect[2]+1e-6 or bbox[1] < plot_rect[1]-1e-6:
                raise FigureError('bar_label_outside_plot','柱顶标签超出绘图区',group=group_index,bar=bar_index,bbox=bbox)
            placed.append({'group':group_index,'bar':bar_index,'runs':runs,
                           'measurement':measured,'position':position,'bar_rect':[x0,y0,x1,y1]})
    ordered=sorted(placed,key=lambda item:item['position']['bbox'][0])
    separations=[]
    for left,right in zip(ordered,ordered[1:]):
        sep=right['position']['bbox'][0]-left['position']['bbox'][2]
        separations.append(sep)
        if sep < min_horizontal_gap_pt-1e-6:
            raise FigureError('bar_label_collision','柱顶标签横向净距不足',actual=sep,required=min_horizontal_gap_pt)
    gaps=[item['bar_rect'][1]-item['position']['bbox'][3] for item in placed]
    return placed, {'count':len(placed),'required_ink_gap_pt':ink_gap_pt,
                    'actual_ink_gaps_pt':gaps,
                    'required_horizontal_gap_pt':min_horizontal_gap_pt,
                    'minimum_horizontal_gap_pt':min(separations) if separations else None}


def tick_content(tick):
    """A numeric component plus an explicitly verified suffix, never guessed.

    The original spelling is retained in `text`. A scientific prefix on a
    tick is NOT silently interpreted as an axis-unit conversion.
    """
    if tick.get('categorical') is True:
        return tick['text']
    raw=str(tick['text'])
    if 'number' not in tick:
        return group_number(raw)
    number=str(tick['number']);suffix=tick.get('suffix','')
    if not isinstance(suffix,str) or number+suffix != raw:
        raise FigureError('tick_component_mismatch','刻度数值部分和后缀必须与原文字完全一致',text=raw)
    group_number(number)  # Strict validation; no parsing through float.
    return [{'text':number,'role':'number'},{'text':suffix,'role':'suffix'}]


def choose_tick_rotation(positions,measurements,gap):
    """Preserve all tick anchors and rotate labels if horizontal text cannot fit."""
    for rotation in (0,90):
        boxes=sorted((position_text(m,x,0,rotation=rotation)['bbox'] for x,m in zip(positions,measurements)),key=lambda box:box[0])
        if all(right[0]-left[2]>=gap-.1 for left,right in zip(boxes,boxes[1:])):return rotation
    raise FigureError('chart_tick_spacing','刻度文字在现有字号和栏宽下无法满足间距')


def chart(spec,reg,size,assets,root):
    if 'panels' in spec:
        from .chart_panels import compose_chart_panels
        return compose_chart_panels(spec,reg,size,assets,root,chart)
    s=Scene(reg,size);s.template='chart-'+spec['source_kind'];path=resolve_source(root,spec['source'])
    entries=spec.get('series')
    if not isinstance(entries,list):raise FigureError('legend_series','图例系列须为数组')
    if any(e.get('line_style') not in (None,'dashed') for e in entries):raise FigureError('svg_series_style_unsupported','不支持的系列线型')
    if spec.get('source_kind')!='svg' and any(e.get('line_style') for e in entries):raise FigureError('svg_series_style_unsupported','线型调整仅支持已绑定的SVG系列')
    no_legend=not entries
    if no_legend:
        review=spec.get('legend_review',{})
        if not isinstance(review,dict) or review.get('present') is not False or review.get('source_sha256')!=digest_file(path) or not isinstance(review.get('reason'),str) or not review['reason'].strip():
            raise FigureError('legend_absence_review','无图例须绑定当前源文件及明确核对依据')
        if spec.get('masks') or spec.get('approved_empty_regions'):
            raise FigureError('no_legend_mask','无图例不能清除图例区域或遮盖曲线')
        if spec['source_kind']=='svg' and (not isinstance(spec.get('series_source_groups'),list) or not spec['series_source_groups']):
            raise FigureError('svg_series_identity','无图例时仍须绑定原始曲线系列')
    clip=spec['plot_clip'];srcw=clip[2]-clip[0];srch=clip[3]-clip[1]
    pw=float(spec.get('plot_width_pt',180));scale=pw/srcw;ph=srch*scale
    yms=[reg.measure(tick_content(v),size) for v in spec['y_ticks']]
    xms=[reg.measure(tick_content(v),size) for v in spec['x_ticks']]
    from .chart_bar_bindings import bind_bar_labels
    bar_rows,sections=bind_bar_labels(spec,Path(root))
    x_positions=[(v['position']-clip[0])*scale for v in spec['x_ticks']]
    tick_rotation=choose_tick_rotation(x_positions,xms,2*size/8)
    x_boxes=[position_text(m,0,0,rotation=tick_rotation)['bbox'] for m in xms]
    x_widths=[b[2]-b[0] for b in x_boxes];x_heights=[b[3]-b[1] for b in x_boxes]
    # Mandatory formatting precedes ALL measurement and capacity decisions.
    xtitlem=reg.measure(normalize_axis_title(spec['x_title']),size)
    titlem=reg.measure(normalize_axis_title(spec['y_title']),size)
    tick_len=float(spec.get('tick_length_source_units',0))*scale
    left=max(float(spec.get('left_margin_pt',0)),max(m['width'] for m in yms)+titlem['height']+TICK_CLEARANCE+LABEL_CLEARANCE+2+tick_len+STROKE/2)
    top=max(m['height']/2 for m in yms)+1
    if bar_rows:top=max(top,max(reg.measure(r.text,size,role='numeric-value')['width'] for r in bar_rows)+2*size/8+2)
    bottom=25.;right=3.;x0=left;y0=top
    # SVG tick endpoints must be identified in source units, not guessed from frame.
    tick_len=float(spec.get('tick_length_source_units',0))*scale
    tick_gap=TICK_CLEARANCE+STROKE/2
    axis=spec.get('axis_frame_source',clip)
    x_tick_edge=y0+(axis[3]-clip[1])*scale+tick_len+tick_gap
    y_tick_edge=x0+(axis[0]-clip[0])*scale-tick_len-tick_gap
    # Keep source tick x anchors. If the lower-left labels collide, move the
    # x-label ROW outward just enough rather than shrinking 8pt or moving data.
    original_x_tick_edge=x_tick_edge
    corner_gap=float(spec.get('corner_tick_clearance_pt',1.))
    if not math.isfinite(corner_gap) or corner_gap<0:raise FigureError('corner_tick_clearance','角部刻度净距必须非负且有限')
    for xv,x_width in zip(spec['x_ticks'],x_widths):
        xx=x0+(xv['position']-clip[0])*scale
        xl,xr=xx-x_width/2,xx+x_width/2
        for yv,ym in zip(spec['y_ticks'],yms):
            if xl<y_tick_edge and xr>y_tick_edge-ym['width']:
                yy=y0+(yv['position']-clip[1])*scale
                x_tick_edge=max(x_tick_edge,yy+ym['height']/2+corner_gap)
    dashed=[v['source_group'] for v in entries if v.get('line_style')=='dashed']
    if spec['source_kind']=='svg':
        if not dashed and len(entries)==2 and not any(entry.get('source_groups') for entry in entries):
            from .assets import indistinct_solid_pair
            dashed=indistinct_solid_pair(path,[v['source_group'] for v in entries])
        source_groups=spec['series_source_groups'] if no_legend else [group for entry in entries for group in entry.get('source_groups',[entry['source_group']])]
        a=assets.svg_chart(path,spec['axes_id'],clip,source_groups,spec.get('legend_source_id'),dashed_series=dashed)
    elif spec['source_kind']=='raster':
        a=assets.raster(path,clip,masks=spec.get('masks'),approved_empty_regions=spec.get('approved_empty_regions'))
    elif spec['source_kind']=='pdf':a=assets.pdf(path,spec.get('page',0),clip)
    else:raise FigureError('chart_source_kind','未知曲线来源类型')
    if no_legend and spec['source_kind']=='svg' and a.audit.get('geometry_before')==digest_json([]):
        raise FigureError('svg_series_empty','无图例时原始系列必须包含可核验的曲线几何')
    s.embed('plot',a,[x0,y0,x0+pw,y0+ph])
    bar_layout=None
    if bar_rows:
        mapped=[{'rect':[x0+(r.rect[0]-clip[0])*scale,y0+(r.rect[1]-clip[1])*scale,x0+(r.rect[2]-clip[0])*scale,y0+(r.rect[3]-clip[1])*scale],'runs':r.text} for r in bar_rows]
        measure=lambda value:reg.measure(group_number(value),size,role='numeric-value')
        kwargs={'ink_gap_pt':2*size/8,'plot_rect':[x0,1,x0+pw,y0+ph],'min_horizontal_gap_pt':2*size/8}
        try:placed,bar_proof=place_bar_top_labels([mapped],measure,**kwargs);bar_rotation=0
        except FigureError as error:
            if error.code!='bar_label_collision':raise
            placed,bar_proof=place_bar_top_labels([mapped],measure,rotation=90,**kwargs);bar_rotation=90
        for row,placement in zip(bar_rows,placed):
            bbox=placement['position']['bbox'];s.text(row.id,row.text,(bbox[0]+bbox[2])/2,(bbox[1]+bbox[3])/2,role='numeric-value',rotation=bar_rotation)
        bar_layout={'count':len(bar_rows),'rotation':bar_rotation,'bindings':[{**binding,'source_text':row.text,'source_bar_rect':list(row.rect)} for binding,row in zip(spec['bar_labels'],bar_rows)],'section_bindings':[{'id':ident,'source_text':text,'source_anchor':list(anchor),'text_group':binding['text_group']} for binding,(ident,text,anchor) in zip(spec.get('section_labels',[]),sections)],'layout':bar_proof}
    if sections:
        bar_tops=[t['position']['bbox'][1] for t in s.texts if any(t['id']==r.id for r in bar_rows)]
        if not bar_tops:raise FigureError('bar_binding','区段标题需要已绑定柱顶文字')
        for ident,text,anchor in sections:
            measured=reg.measure(text,size)
            s.text(ident,text,x0+(anchor[0]-clip[0])*scale,min(bar_tops)-LABEL_CLEARANCE-measured['height']/2,align='left')
    annotations=source_annotations(spec,root)
    annotation_right=place_source_annotations(s,annotations,clip,scale,x0,y0)
    right=max(right,annotation_right-x0-pw+2)
    # Restore clipped outward tick stubs ONLY when verified in the SVG source.
    if spec.get('restore_verified_tick_stubs'):
        if spec['source_kind']!='svg' or not spec.get('tick_source_evidence') or tick_len<=0:
            raise FigureError('tick_source_identity','重建刻线需要SVG源坐标与明确证据')
        for i,v in enumerate(spec['x_ticks']):
            x=x0+(v['position']-clip[0])*scale;y=y0+(axis[3]-clip[1])*scale
            s.line('source-xtick-'+str(i),[[x,y],[x,y+tick_len]])
        for i,v in enumerate(spec['y_ticks']):
            x=x0+(axis[0]-clip[0])*scale;y=y0+(v['position']-clip[1])*scale
            s.line('source-ytick-'+str(i),[[x,y],[x-tick_len,y]])
    for i,v in enumerate(spec['x_ticks']):
        pos=x0+(v['position']-clip[0])*scale
        s.text('xtick'+str(i),tick_content(v),pos,x_tick_edge+x_heights[i]/2,rotation=tick_rotation,role='label' if v.get('categorical') else 'axis-tick')
    for i,v in enumerate(spec['y_ticks']):
        pos=y0+(v['position']-clip[1])*scale
        s.text('ytick'+str(i),tick_content(v),y_tick_edge,pos,align='right',role='label' if v.get('categorical') else 'axis-tick')
    xtitle_top=x_tick_edge+max(x_heights)+LABEL_CLEARANCE
    s.text('xtitle',spec['x_title'],x0+pw/2,xtitle_top+xtitlem['height']/2,role='axis-title')
    # The title's rotated ink height is the unrotated width; measured centering avoids baselines guessed by eye.
    s.text('ytitle',spec['y_title'],y_tick_edge-max(m['width'] for m in yms)-LABEL_CLEARANCE-titlem['height']/2,y0+ph/2,rotation=90,role='axis-title')
    if no_legend:
        s.layout_evidence={'plot_width_pt':pw,'plot_height_pt':ph,'source_crop':clip,'scale':scale,
                           'legend_review':dict(spec['legend_review']),'legend_bindings':[],
                           'source_annotation_bindings':spec.get('source_annotations',[]),
                           'axis_mapping':'original image/SVG positions, not inferred numeric spacing',
                           'axis_title_normalization':{key:axis_title_evidence(spec[key]) for key in ('x_title','y_title')},
                           'numeric_labels':[{'source':v['text'],'display':m['text']} for v,m in zip(spec['x_ticks']+spec['y_ticks'],xms+yms)],
                           'corner_tick_adjustment_pt':x_tick_edge-original_x_tick_edge,'x_tick_rotation':tick_rotation,
                           'axis_clearance_pt':{'tick':TICK_CLEARANCE,'title':LABEL_CLEARANCE,'source_tick_length':tick_len,'axis_frame_source':axis,'source_evidence':spec.get('tick_source_evidence')}}
        if bar_layout:s.layout_evidence['source_bar_labels']=bar_layout
        for key,ev in s.layout_evidence['axis_title_normalization'].items():
            if ev['status']=='semantic_review_needed':
                s.notes.append({'code':'axis_unit_semantics_pending','axis':key,'source':ev['source'],'message':'未知括号内容未按单位改写；需核对语义，不宣称全量轴单位通过'})
        if spec.get('tick_length_source_units') is None:
            s.notes.append({'code':'tick_endpoint_verification_pending','message':'未声明独立刻线长度，仅按给定轴框锚点；需核对真实刻线端点'})
        return finish_chart_title(s,x0+pw+right,xtitle_top+xtitlem['height']+1,spec.get('plot_title'))
    ids=[e['id'] for e in entries]
    if len(ids)!=len(set(ids)):raise FigureError('legend_duplicate_series','图例系列ID重复')
    labelms=[reg.measure(e['label'],size) for e in entries]
    swatches=[]
    for e in entries:
        if spec['source_kind']=='svg':a=assets.svg_swatch(path,e['swatch_group'],e['swatch_clip'],dashed=e['source_group'] in dashed)
        elif spec['source_kind']=='raster':a=assets.raster(path,e['swatch_clip'],swatch=True)
        else:
            a=assets.pdf(path,spec.get('page',0),e['swatch_clip'])
        swatches.append(a)
    samplew=max((a.rect[2]-a.rect[0])*scale for a in swatches)
    sampleh=max((a.rect[3]-a.rect[1])*scale for a in swatches)
    framed=spec.get('legend_frame',True)
    if not isinstance(framed,bool):raise FigureError('legend_frame_type','legend_frame必须为布尔值')
    pad=float(spec.get('legend_padding_pt',3. if framed else 0.))
    if not math.isfinite(pad) or pad<0:raise FigureError('legend_padding','图例内边距必须非负且有限')
    sgap=3.;rowh=max(max(m['height'] for m in labelms),sampleh)+3
    lw=2*pad+samplew+sgap+max(m['width'] for m in labelms);lh=2*pad+len(entries)*rowh-3
    columns=1;column_offsets=(0.,)
    placement=spec.get('legend_placement','upper-right')
    if placement=='auto-inside':
        if spec['source_kind']!='svg' or not spec.get('protected_path_points'):raise FigureError('legend_occupancy_missing','自动放置须有源曲线占位证据')
        widths=[samplew+sgap+m['width'] for m in labelms]
        inside_grid=pack_legend_columns(widths,pw-8.-2*pad,gap=6.*size/8.)
        outside_grid=pack_legend_columns(widths,x0+pw+right-2*pad,gap=6.*size/8.)
        columns=inside_grid.columns;column_offsets=inside_grid.offsets
        lw=2*pad+inside_grid.width;lh=2*pad+inside_grid.rows*rowh-3
        points=[[[x0+(x-clip[0])*scale,y0+(y-clip[1])*scale] for x,y in line] for line in spec['protected_path_points']]
        candidates=[(x0+pw-lw-4,y0+5),(x0+4,y0+5),(x0+pw-lw-4,y0+ph-lh-5),(x0+4,y0+ph-lh-5)]
        safe=[(x,y) for x,y in candidates if x>=x0 and y>=y0 and x+lw<=x0+pw and y+lh<=y0+ph and not any(segment_hits(a,b,[x,y,x+lw,y+lh],3*scale) for line in points for a,b in zip(line,line[1:]))]
        if safe and inside_grid.rows<=outside_grid.rows:
            lx,ly=safe[0]
        else:
            placement='outside-top'
            lx=x0;ly=y0-lh-LABEL_CLEARANCE
    elif placement=='upper-right':lx=x0+pw-lw-4;ly=y0+5
    elif placement=='lower-right':lx=x0+pw-lw-4;ly=y0+ph-lh-5
    elif placement=='outside-top':
        if spec['source_kind']=='raster' and not spec.get('mask_semantic_evidence',{}).get('approved_empty_background'):
            raise FigureError('legend_move_requires_mask_review','位图图例外移需要原区域无数据背景的核对证据')
        lx=x0;ly=y0-lh-LABEL_CLEARANCE
    elif placement=='above':lx=x0+pw-lw;ly=y0;raise FigureError('legend_above_not_enabled','本版未自动增加上方图例区域，请使用图内安全位置或scene')
    elif placement=='source-region':
        region=spec['legend_safe_region'];lx=x0+(region[2]-clip[0])*scale-lw-1;ly=y0+(region[1]-clip[1])*scale+1
    else:raise FigureError('legend_placement','未知图例位置')
    if placement=='outside-top':
        grid=pack_legend_columns([samplew+sgap+m['width'] for m in labelms],x0+pw+right-2*pad,gap=6.*size/8.)
        columns=grid.columns;column_offsets=grid.offsets
        lw=2*pad+grid.width;lh=2*pad+grid.rows*rowh-3
        lx=max(0.,(x0+pw+right-lw)/2);ly=y0-lh-LABEL_CLEARANCE
        protected_ids={r.id for r in bar_rows}|{ident for ident,_,_ in sections}
        annotation_tops=[t['position']['bbox'][1] for t in s.texts if t['id'] in protected_ids]
        if annotation_tops:ly=min(ly,min(annotation_tops)-LABEL_CLEARANCE-lh)
    legendbox=[lx,ly,lx+lw,ly+lh]
    if spec['source_kind']=='raster' and placement!='outside-top':
        if placement!='source-region':raise FigureError('raster_legend_move','位图图例只允许放入已核对的原始安全区域')
        r=spec['legend_safe_region'];safe=[x0+(r[0]-clip[0])*scale,y0+(r[1]-clip[1])*scale,x0+(r[2]-clip[0])*scale,y0+(r[3]-clip[1])*scale]
        if not contains(safe,legendbox):raise FigureError('legend_safe_region_capacity','真实文字排版后图例放不进已核对的安全区域',legend=legendbox,safe=safe)
    else:
        # Optional occupancy lines come from original SVG path coordinates, NOT reconstructed data.
        for line in spec.get('protected_path_points',[]):
            pts=[[x0+(x-clip[0])*scale,y0+(y-clip[1])*scale] for x,y in line]
            if any(segment_hits(a,b,legendbox,3*scale) for a,b in zip(pts,pts[1:])):
                raise FigureError('legend_curve_collision','图例与原始曲线路径重叠')
    occupancy_evidence=None
    if spec['source_kind']=='raster' and placement!='outside-top' and spec.get('verify_legend_background',False):
        gap=float(spec.get('legend_clearance_pt',3.))
        if not math.isfinite(gap) or gap<0:raise FigureError('legend_clearance','图例净距必须非负且有限')
        footprint=[(legendbox[0]-gap-x0)/scale,(legendbox[1]-gap-y0)/scale,
                   (legendbox[2]+gap-x0)/scale,(legendbox[3]+gap-y0)/scale]
        viewport=s.assets[0]['asset']
        with Image.open(io.BytesIO(viewport.data)) as img:
            q=[max(0,math.floor(footprint[0])),max(0,math.floor(footprint[1])),
               min(img.width,math.ceil(footprint[2])),min(img.height,math.ceil(footprint[3]))]
            occupied=img.convert('L').crop(tuple(q)).point(lambda v:255 if v<180 else 0).getbbox()
        if occupied is not None:
            raise FigureError('legend_background_occupied','图例及其净距范围仍有原图墨迹，禁止覆盖',source_local_rect=q,ink_bbox=occupied)
        occupancy_evidence={'checked':True,'clearance_pt':gap,'source_local_rect_px':q,
                            'dark_pixel_threshold':180,'occupied':False,
                            'scope':'post-approved-mask pixel occupancy; source mask semantic safety is reviewed separately'}

    # Figure background patch is explicitly an opaque legend, not an erased data region.
    if framed:
        n=s.shape('legend-frame',legendbox,container=True,width=.5);n['fill']=1.;n['gray']=.75
    for i,(e,m,sw) in enumerate(zip(entries,labelms,swatches)):
        column=i%columns;row=i//columns
        column_left=lx+pad+column_offsets[column]
        cy=ly+pad+rowh*row+max(m['height'],sampleh)/2
        w=(sw.rect[2]-sw.rect[0])*scale;h=(sw.rect[3]-sw.rect[1])*scale
        s.embed('swatch:'+e['id'],sw,[column_left+(samplew-w)/2,cy-h/2,column_left+(samplew+w)/2,cy+h/2],role='legend-swatch')
        s.text('legend:'+e['id'],e['label'],column_left+samplew+sgap,cy,align='left',owner='legend-frame' if framed else None,role='legend-label')
    s.layout_evidence={'plot_width_pt':pw,'plot_height_pt':ph,'source_crop':clip,'scale':scale,'legend_placement':placement,
                      'axis_mapping':'original image/SVG positions, not inferred numeric spacing',
                      'legend_bindings':[{'series_id':e['id'],'source_group':e.get('source_group'),'swatch':e.get('swatch_group',e.get('swatch_clip')),'label':e['label']} for e in entries]}
    if bar_layout:s.layout_evidence['source_bar_labels']=bar_layout
    s.layout_evidence['axis_title_normalization']={key:axis_title_evidence(spec[key]) for key in ('x_title','y_title')}
    for key,ev in s.layout_evidence['axis_title_normalization'].items():
        if ev['status']=='semantic_review_needed':
            s.notes.append({'code':'axis_unit_semantics_pending','axis':key,'source':ev['source'],'message':'未知括号内容未按单位改写；需核对语义，不宣称全量轴单位通过'})
    s.layout_evidence['numeric_labels']=[{'source':v['text'],'display':m['text']} for v,m in zip(spec['x_ticks']+spec['y_ticks'],xms+yms)]
    s.layout_evidence['corner_tick_adjustment_pt']=x_tick_edge-original_x_tick_edge
    s.layout_evidence['x_tick_rotation']=tick_rotation
    s.layout_evidence['legend_frame']=framed
    s.layout_evidence['source_annotation_bindings']=spec.get('source_annotations',[])
    s.layout_evidence['legend_columns']=columns
    s.layout_evidence['legend_rows']=math.ceil(len(entries)/columns)
    s.layout_evidence['legend_layout_priority']='measure-columns-before-placement; fewest-fitting-rows; safe-inside-on-tie'
    s.layout_evidence['legend_background_audit']=occupancy_evidence
    s.layout_evidence['axis_clearance_pt']={'tick':TICK_CLEARANCE,'title':LABEL_CLEARANCE,'source_tick_length':tick_len,'axis_frame_source':axis,'source_evidence':spec.get('tick_source_evidence')}
    if spec.get('tick_length_source_units') is None:
        s.notes.append({'code':'tick_endpoint_verification_pending','message':'未声明独立刻线长度，仅按给定轴框锚点；需核对真实刻线端点'})
    if placement=='outside-top':
        # One algebraic translation of the entire scene; layout/render is not retried.
        shift=max(0.,1.-ly)
        for n in s.nodes:n['rect']=[n['rect'][0],n['rect'][1]+shift,n['rect'][2],n['rect'][3]+shift]
        for p in s.paths:p['points']=[[x,y+shift] for x,y in p['points']]
        for a in s.assets:a['rect']=[a['rect'][0],a['rect'][1]+shift,a['rect'][2],a['rect'][3]+shift]
        for t in s.texts:
            t['y']+=shift;t['position']['bbox']=[t['position']['bbox'][0],t['position']['bbox'][1]+shift,t['position']['bbox'][2],t['position']['bbox'][3]+shift]
            t['position']['offset'][1]+=shift
        s.layout_evidence['outside_legend_translation_pt']=shift
        s.layout_evidence['legend_mask_review']=spec.get('mask_semantic_evidence')
        return finish_chart_title(s,max(x0+pw+right,lx+lw+1),xtitle_top+xtitlem['height']+1+shift,spec.get('plot_title'))
    return finish_chart_title(s,x0+pw+right,xtitle_top+xtitlem['height']+1,spec.get('plot_title'))
