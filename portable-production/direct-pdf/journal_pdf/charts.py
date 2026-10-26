"""Original graphic viewport + measured labels + bound legend swatches."""
from __future__ import annotations
import math
from pathlib import Path
from .common import FigureError, resolve_source, contains, segment_hits
from .scene import Scene
from .fonts import position_text
from .axis_units import normalize_axis_title, axis_title_evidence
from .editorial import group_number, TICK_CLEARANCE, LABEL_CLEARANCE, STROKE, PAD_X
from PIL import Image
import io


def place_bar_top_labels(groups, measure, *, ink_gap_pt, plot_rect,
                         min_horizontal_gap_pt=2.):
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
            probe=position_text(measured,(x0+x1)/2,0,align='center',rotation=0)
            h=probe['bbox'][3]-probe['bbox'][1]
            position=position_text(measured,(x0+x1)/2,y0-ink_gap_pt-h/2,align='center',rotation=0)
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


def tick_content(tick, base_size_pt=8):
    """A numeric component plus an explicitly verified suffix, never guessed.

    The original spelling is retained in `text`. A scientific prefix on a
    tick is NOT silently interpreted as an axis-unit conversion.
    `power10` supplies a verified integer exponent; only matching explicit
    power notation is accepted, never a guessed decimal-to-log conversion.
    """
    raw=str(tick['text'])
    if 'power10' in tick:
        from .scientific_text import power_of_ten
        if 'number' in tick or 'suffix' in tick:
            raise FigureError('tick_semantics_conflict','十的幂刻度不能同时声明数值后缀')
        runs=power_of_ten(tick['power10'],base_size_pt=base_size_pt)
        exponent=runs[1]['text']
        superscript=exponent.translate(str.maketrans('-0123456789','⁻⁰¹²³⁴⁵⁶⁷⁸⁹'))
        if raw not in {'10'+superscript,'10^'+exponent,'10^'+exponent.replace('-','−')}:
            raise FigureError('tick_power10_mismatch','刻度原文与显式确认的十的幂指数不一致',text=raw)
        return runs
    if 'number' not in tick:
        return group_number(raw)
    number=str(tick['number']);suffix=tick.get('suffix','')
    if not isinstance(suffix,str) or number+suffix != raw:
        raise FigureError('tick_component_mismatch','刻度数值部分和后缀必须与原文字完全一致',text=raw)
    group_number(number)  # Strict validation; no parsing through float.
    return [{'text':number,'role':'number'},{'text':suffix,'role':'suffix'}]


def chart(spec,reg,size,assets,root):
    s=Scene(reg,size);s.template='chart-'+spec['source_kind'];path=resolve_source(root,spec['source'])
    if spec['source_kind']=='registered-outline-svg':
        from .source_outline_chart import validate_chart_spec
        validate_chart_spec(path,spec)
    clip=spec['plot_clip'];srcw=clip[2]-clip[0];srch=clip[3]-clip[1]
    pw=float(spec.get('plot_width_pt',180));scale=pw/srcw
    if spec['source_kind']=='registered-outline-svg':
        frame=spec['axis_frame_source'];scale=pw/(frame[2]-frame[0]);pw=srcw*scale
    ph=srch*scale
    yms=[reg.measure(tick_content(v,size),size) for v in spec['y_ticks']]
    xms=[reg.measure(tick_content(v,size),size) for v in spec['x_ticks']]
    # Reflow the complete tick row when horizontal ink overlaps. Use the
    # existing native quarter-turn renderer; this is not source-angle recovery.
    ordered=sorted((v['position']*scale,m['width']) for v,m in zip(spec['x_ticks'],xms))
    xrotation=90 if any(a[0]+a[1]/2>b[0]-b[1]/2 for a,b in zip(ordered,ordered[1:])) else 0
    xbounds=[position_text(m,0,0,rotation=xrotation)['bbox'] for m in xms]
    xwidths=[b[2]-b[0] for b in xbounds]
    xheights=[b[3]-b[1] for b in xbounds]
    # Mandatory formatting precedes ALL measurement and capacity decisions.
    xtitlem=reg.measure(normalize_axis_title(spec['x_title']),size)
    titlem=reg.measure(normalize_axis_title(spec['y_title']),size)
    left=max(float(spec.get('left_margin_pt',0)),max(m['width'] for m in yms)+titlem['height']+TICK_CLEARANCE+LABEL_CLEARANCE+2)
    top=max(m['height']/2 for m in yms)+1
    if spec.get('figure_title'):
        tm=reg.measure(spec['figure_title'],size);tb=spec['title_source_bbox']
        top=max(top,1+tm['height']/2-((tb[1]+tb[3])/2-clip[1])*scale)
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
    for xv,xwidth in zip(spec['x_ticks'],xwidths):
        xx=x0+(xv['position']-clip[0])*scale
        xl,xr=xx-xwidth/2,xx+xwidth/2
        for yv,ym in zip(spec['y_ticks'],yms):
            if xl<y_tick_edge and xr>y_tick_edge-ym['width']:
                yy=y0+(yv['position']-clip[1])*scale
                x_tick_edge=max(x_tick_edge,yy+ym['height']/2+corner_gap)
    if spec['source_kind']=='registered-outline-svg':
        a=assets.registered_outline_chart(path,spec['outline_chart_registration'])
    elif spec['source_kind']=='svg':
        a=assets.svg_chart(path,spec['axes_id'],clip,[v['source_group'] for v in spec['series']],spec['legend_source_id'])
    elif spec['source_kind']=='raster':
        a=assets.raster(path,clip,masks=spec.get('masks'),approved_empty_regions=spec.get('approved_empty_regions'))
    elif spec['source_kind']=='pdf':a=assets.pdf(path,spec.get('page',0),clip)
    else:raise FigureError('chart_source_kind','未知曲线来源类型')
    s.embed('plot',a,[x0,y0,x0+pw,y0+ph])
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
        s.text('xtick'+str(i),tick_content(v,size),pos,x_tick_edge+xheights[i]/2,rotation=xrotation,role='axis-tick')
    for i,v in enumerate(spec['y_ticks']):
        pos=y0+(v['position']-clip[1])*scale
        s.text('ytick'+str(i),tick_content(v,size),y_tick_edge,pos,align='right',role='axis-tick')
    xtitle_top=x_tick_edge+max(xheights)+LABEL_CLEARANCE
    s.text('xtitle',spec['x_title'],x0+((axis[0]+axis[2])/2-clip[0])*scale if spec['source_kind']=='registered-outline-svg' else x0+pw/2,xtitle_top+xtitlem['height']/2,role='axis-title')
    # The title's rotated ink height is the unrotated width; measured centering avoids baselines guessed by eye.
    s.text('ytitle',spec['y_title'],y_tick_edge-max(m['width'] for m in yms)-LABEL_CLEARANCE-titlem['height']/2,y0+((axis[1]+axis[3])/2-clip[1])*scale if spec['source_kind']=='registered-outline-svg' else y0+ph/2,rotation=90,role='axis-title')
    entries=spec['series'];ids=[e['id'] for e in entries]
    if len(ids)!=len(set(ids)):raise FigureError('legend_duplicate_series','图例系列ID重复')
    if entries:
        labelms=[reg.measure(e['label'],size) for e in entries]
        swatches=[]
        for e in entries:
            if spec['source_kind']=='registered-outline-svg':a=assets.registered_outline_chart(path,spec['outline_chart_registration'],swatch_id=e['id'])
            elif spec['source_kind']=='svg':a=assets.svg_swatch(path,e['swatch_group'],e['swatch_clip'])
            elif spec['source_kind']=='raster':a=assets.raster(path,e['swatch_clip'],swatch=True)
            else:
                a=assets.pdf(path,spec.get('page',0),e['swatch_clip'])
            swatches.append(a)
        samplew=max((a.rect[2]-a.rect[0])*scale for a in swatches)
        sampleh=max((a.rect[3]-a.rect[1])*scale for a in swatches)
        framed=spec.get('legend_frame',True)
        if not isinstance(framed,bool):raise FigureError('legend_frame_type','legend_frame必须为布尔值')
        pad=float(spec.get('legend_padding_pt',PAD_X if spec['source_kind']=='registered-outline-svg' else (3. if framed else 0.)))
        if not math.isfinite(pad) or pad<0:raise FigureError('legend_padding','图例内边距必须非负且有限')
        sgap=3.;rowh=max(max(m['height'] for m in labelms),sampleh)+3
        lw=2*pad+samplew+sgap+max(m['width'] for m in labelms);lh=2*pad+len(entries)*rowh-3
        placement=spec.get('legend_placement','upper-right')
        if placement=='upper-right':lx=x0+pw-lw-4;ly=y0+5
        elif placement=='lower-right':lx=x0+pw-lw-4;ly=y0+ph-lh-5
        elif placement=='outside-top':
            if spec['source_kind']=='raster' and not spec.get('mask_semantic_evidence',{}).get('approved_empty_background'):
                raise FigureError('legend_move_requires_mask_review','位图图例外移需要原区域无数据背景的核对证据')
            lx=x0;ly=y0-lh-LABEL_CLEARANCE
        elif placement=='above':lx=x0+pw-lw;ly=y0;raise FigureError('legend_above_not_enabled','本版未自动增加上方图例区域，请使用图内安全位置或scene')
        elif placement=='registered-source-region':
            if spec['source_kind']!='registered-outline-svg':raise FigureError('legend_source_binding','该位置需原图元登记')
            region=spec['legend_safe_region'];original=spec['legend_original_region']
            lx=x0+(original[0]-clip[0])*scale;ly=y0+(original[1]-clip[1])*scale
            capacity=[lx,ly,x0+(region[2]-clip[0])*scale,y0+(original[3]-clip[1])*scale]
            # Only the approved width may grow. Never silently move or heighten the legend.
            if not contains(capacity,[lx,ly,lx+lw,ly+lh]):
                raise FigureError('legend_source_region_capacity','8pt实测图例超出原高度或明确允许的宽度；不自动迁移或降字号',required=[lw,lh],capacity=capacity)
            lw=max(lw,(original[2]-original[0])*scale);lh=(original[3]-original[1])*scale
        elif placement=='source-region':
            region=spec['legend_safe_region'];lx=x0+(region[2]-clip[0])*scale-lw-1;ly=y0+(region[1]-clip[1])*scale+1
        else:raise FigureError('legend_placement','未知图例位置')
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
        if spec['source_kind']=='registered-outline-svg':
            for box in spec['protected_ink_boxes']:
                mapped=[x0+(box[0]-clip[0])*scale,y0+(box[1]-clip[1])*scale,x0+(box[2]-clip[0])*scale,y0+(box[3]-clip[1])*scale]
                if mapped[0]<legendbox[2] and mapped[2]>legendbox[0] and mapped[1]<legendbox[3] and mapped[3]>legendbox[1]:
                    raise FigureError('legend_curve_collision','登记图例与原系列墨迹可能重叠')
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
            cy=ly+pad+rowh*i+max(m['height'],sampleh)/2
            w=(sw.rect[2]-sw.rect[0])*scale;h=(sw.rect[3]-sw.rect[1])*scale
            s.embed('swatch:'+e['id'],sw,[lx+pad+(samplew-w)/2,cy-h/2,lx+pad+(samplew+w)/2,cy+h/2],role='legend-swatch')
            s.text('legend:'+e['id'],e['label'],lx+pad+samplew+sgap,cy,align='left',owner='legend-frame' if framed else None,role='legend-label')
    else:
        # Explicit series=[] means no legend: do not invent a frame, swatch,
        # background mask or a safe-region requirement for a heatmap.
        placement='none';framed=False;occupancy_evidence=None
    if spec.get('figure_title'):
        box=spec['title_source_bbox']
        s.text('figure-title',spec['figure_title'],x0+((box[0]+box[2])/2-clip[0])*scale,
               y0+((box[1]+box[3])/2-clip[1])*scale,role='figure-title')
    s.layout_evidence={'plot_width_pt':pw,'plot_height_pt':ph,'source_crop':clip,'scale':scale,'legend_placement':placement,
                      'axis_mapping':'original image/SVG positions, not inferred numeric spacing',
                      'legend_bindings':[{'series_id':e['id'],'source_group':e.get('source_group'),'swatch':e.get('swatch_group',e.get('swatch_clip')),'label':e['label']} for e in entries]}
    s.layout_evidence['axis_title_normalization']={key:axis_title_evidence(spec[key]) for key in ('x_title','y_title')}
    for key,ev in s.layout_evidence['axis_title_normalization'].items():
        if ev['status']=='semantic_review_needed':
            s.notes.append({'code':'axis_unit_semantics_pending','axis':key,'source':ev['source'],'message':'未知括号内容未按单位改写；需核对语义，不宣称全量轴单位通过'})
    s.layout_evidence['numeric_labels']=[{'source':v['text'],'display':m['text']} for v,m in zip(spec['x_ticks']+spec['y_ticks'],xms+yms)]
    s.layout_evidence['corner_tick_adjustment_pt']=x_tick_edge-original_x_tick_edge
    s.layout_evidence['x_tick_layout']={'rotation_degrees':xrotation,
        'reason':'measured-horizontal-overlap' if xrotation else 'horizontal-ink-fits',
        'source_anchors_preserved':True,'source_angle_preservation_claim':False}
    s.layout_evidence['legend_frame']=framed
    s.layout_evidence['legend_background_audit']=occupancy_evidence
    s.layout_evidence['axis_clearance_pt']={'tick':TICK_CLEARANCE,'title':LABEL_CLEARANCE,'source_tick_length':tick_len,'axis_frame_source':axis,'source_evidence':spec.get('tick_source_evidence')}
    if spec.get('tick_length_source_units') is None:
        s.notes.append({'code':'tick_endpoint_verification_pending','message':'未声明独立刻线长度，仅按给定轴框锚点；需核对真实刻线端点'})
    # End labels stay anchored to source ticks; the canvas must include their
    # measured overhang instead of assuming a fixed 3pt right margin is enough.
    content_right=max(x0+pw+right,max(t['position']['bbox'][2] for t in s.texts)+1.)
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
        return s.finish(max(content_right,lx+lw+1),xtitle_top+xtitlem['height']+1+shift)
    return s.finish(content_right,xtitle_top+xtitlem['height']+1)
