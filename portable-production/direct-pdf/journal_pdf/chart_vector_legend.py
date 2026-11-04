"""Source-bound legend text for an unchanged native vector chart body."""
from __future__ import annotations

import math
from pathlib import Path

import pymupdf as fitz

from .common import FigureError
from .editorial import LABEL_CLEARANCE, display_content
from .fonts import position_text


def _error(message):
    raise FigureError('chart_vector_legend',message)


def _near_line(point, drawing):
    for item in drawing['items']:
        if item[0]!='l':continue
        a,b=item[1],item[2];dx=b.x-a.x;dy=b.y-a.y
        u=max(0.,min(1.,((point.x-a.x)*dx+(point.y-a.y)*dy)/(dx*dx+dy*dy or 1.)))
        if math.hypot(point.x-a.x-u*dx,point.y-a.y-u*dy)<=5:return True
    return False


def propose_series_binding(drawings, swatch_index, marker_index, frame_rect, plot_rect):
    """Propose, never approve, one series representative even when paths are fragmented."""
    if any(type(i) is not int or i<0 or i>=len(drawings) for i in (swatch_index,marker_index)):
        _error('图例样符路径索引无效')
    swatch=drawings[swatch_index];sample=drawings[marker_index]
    color=swatch.get('color');signature=''.join(item[0] for item in sample['items'])
    if color is None or sample.get('fill') is None or not signature:_error('图例样符不包含可识别的颜色及标记')
    frame=fitz.Rect(frame_rect);plot=fitz.Rect(plot_rect);markers=[]
    for index,item in enumerate(drawings):
        if item.get('fill')!=sample.get('fill') or ''.join(row[0] for row in item['items'])!=signature:continue
        rect=item['rect'];center=(rect.tl+rect.br)*.5
        if frame.intersects(rect) or not plot.contains(center):continue
        markers.append((index,center))
    markers.sort(key=lambda row:row[1].x)
    if len(markers)<2 or any(abs(a[1].x-b[1].x)<.01 for a,b in zip(markers,markers[1:])):
        _error('图例系列标记不足或存在同位置歧义')
    marker,center=markers[len(markers)//2];near=[]
    for index,item in enumerate(drawings):
        if item.get('type')!='s' or item.get('color')!=color:continue
        for part in item['items']:
            if part[0]!='l':continue
            a,b=part[1],part[2];dx=b.x-a.x;dy=b.y-a.y
            u=max(0.,min(1.,((center.x-a.x)*dx+(center.y-a.y)*dy)/(dx*dx+dy*dy or 1.)))
            distance=math.hypot(center.x-a.x-u*dx,center.y-a.y-u*dy)
            if distance<=5:near.append((distance,index))
    if not near:_error('找不到与原图标记相连的曲线段')
    near.sort()
    return {'series_path_index':near[0][1],'series_marker_index':marker,'swatch_path_index':swatch_index,'swatch_marker_index':marker_index,'marker_count':len(markers),'candidate_path_count':len(set(i for _,i in near)),'verified':False}


def local_crop_box(box,target,clip):
    """Convert final legend bounds into the prepared crop's local coordinate system."""
    sx=(target[2]-target[0])/(clip[2]-clip[0]);sy=(target[3]-target[1])/(clip[3]-clip[1])
    return fitz.Rect(*[(box[i]-target[i%2])/([sx,sy][i%2]) for i in range(4)])


def layout_legend(review, source: Path, body, texts, reg, size, mapx, mapy):
    """Bind each legend string to a source swatch, marker and curve before positioning."""
    entries=review.get('entries');frame=review.get('frame_rect');indices=review.get('frame_path_indices')
    if not isinstance(entries,list) or not entries or not isinstance(frame,list) or len(frame)!=4 or not isinstance(indices,list) or (not indices and review.get('frame_mode')!='region-without-frame'):_error('图例必须绑定完整文字、源框、样符和曲线')
    frame=fitz.Rect(frame)
    if frame.is_empty:_error('图例源框无效')
    with fitz.open(source) as document:
        page=document[body.get('page',0)];drawings=page.get_drawings();paint_bounds=page.get_bboxlog()
        if any(type(i) is not int or i<0 or i>=len(drawings) for i in indices):_error('图例源框索引无效')
        framepaths=[drawings[i] for i in indices]
        actual=fitz.Rect(min(x['rect'].x0 for x in framepaths),min(x['rect'].y0 for x in framepaths),max(x['rect'].x1 for x in framepaths),max(x['rect'].y1 for x in framepaths)) if framepaths else frame
        if any(abs(a-b)>.1 for a,b in zip(actual,frame)):_error('图例框与真实源路径不一致')
        edges=set()
        for drawing in framepaths:
            for item in drawing['items']:
                if item[0]=='re' and all(abs(a-b)<.1 for a,b in zip(item[1],frame)):edges.update(('left','right','top','bottom'))
                if item[0]=='l':
                    a,b=item[1],item[2]
                    if abs(a.x-b.x)<.1 and abs(a.x-frame.x0)<.1:edges.add('left')
                    if abs(a.x-b.x)<.1 and abs(a.x-frame.x1)<.1:edges.add('right')
                    if abs(a.y-b.y)<.1 and abs(a.y-frame.y0)<.1:edges.add('top')
                    if abs(a.y-b.y)<.1 and abs(a.y-frame.y1)<.1:edges.add('bottom')
        if framepaths and edges!={'left','right','top','bottom'}:_error('图例源框必须保留四条边')
        replacements={r['target_text_id']:r for r in body['text_replacements']}
        ids=[];used_series=set();used_swatch=set();bindings=[];boxes=[]
        prepared=None
        for entry in entries:
            name=entry.get('text_id');keys=('series_path_index','series_marker_index','swatch_path_index','swatch_marker_index')
            if name in ids or name not in texts or name not in replacements or texts[name].get('role')!='legend-label':_error('图例文字绑定不完整')
            if any(type(entry.get(k)) is not int or not 0<=entry[k]<len(drawings) for k in keys):_error('图例源路径索引无效')
            series,mark,swatch,smark=[drawings[entry[k]] for k in keys]
            if entry['series_path_index'] in used_series or entry['swatch_path_index'] in used_swatch:_error('图例系列或样符重复绑定')
            used_series.add(entry['series_path_index']);used_swatch.add(entry['swatch_path_index'])
            color=series.get('color');sample=swatch.get('color')
            if color is None or sample is None or any(abs(a-b)>.001 for a,b in zip(color,sample)):_error('图例样符与源曲线颜色不一致')
            if ''.join(x[0] for x in mark['items'])!=''.join(x[0] for x in smark['items']) or mark.get('fill')!=smark.get('fill'):_error('图例标记与源曲线标记不一致')
            center=(mark['rect'].tl+mark['rect'].br)*.5;sample_center=(smark['rect'].tl+smark['rect'].br)*.5
            if not _near_line(center,series) or not _near_line(sample_center,swatch):_error('图例标记不位于对应曲线或样符上')
            original=fitz.Rect(replacements[name]['source_bbox'])
            if not frame.contains(original) or not frame.contains(swatch['rect']) or abs((original.y0+original.y1)/2-sample_center.y)>max(2,original.height):_error('图例源文字与样符行不对应')
            group=entry.get('text_ids',[name])
            if not isinstance(group,list) or not group or group[0]!=name or len(set(group))!=len(group) or any(i not in texts or i not in replacements or i in ids for i in group):_error('图例文字片段绑定无效')
            if any(not frame.contains(fitz.Rect(replacements[i]['source_bbox'])) for i in group):_error('图例片段超出已绑定源区域')
            measurements=[reg.measure(display_content(texts[i]['text'],'legend-label'),size,role='legend-label') for i in group]
            measured={'width':sum(m['width'] for m in measurements)+.5*(len(group)-1),'height':max(m['height'] for m in measurements)}
            x=mapx(swatch['rect'].x1)+LABEL_CLEARANCE*size/8;y=mapy(sample_center.y)
            box=[x,y-measured['height']/2,x+measured['width'],y+measured['height']/2]
            mapped=fitz.Rect(mapx(frame.x0),mapy(frame.y0),mapx(frame.x1),mapy(frame.y1))
            if not mapped.contains(fitz.Rect(box)+(-.5,-.5,.5,.5)):_error('图例文字在当前字号和栏宽下放不进原图例框')
            if any(not (box[3]+2*size/8<=other[1] or other[3]+2*size/8<=box[1] or box[2]<=other[0] or other[2]<=box[0]) for other in boxes):_error('图例文字间距不足')
            if prepared is None:
                from .source_icons import prepare_icon
                cleaned=prepare_icon(source,body.get('page',0),body['clip'],text_replacements=body['text_replacements'],source_vector_body=True)
                prepared=fitz.open(stream=cleaned.data,filetype='pdf')
            # prepare_icon returns a cropped page whose origin is the source clip origin.
            source_box=local_crop_box(box,body['target'],body['clip'])
            pix=prepared[0].get_pixmap(matrix=fitz.Matrix(4,4),clip=source_box,colorspace=fitz.csGRAY,alpha=False)
            if pix.samples and min(pix.samples)<250:
                grid=review.get('source_grid_path_indices',[])
                if review.get('frame_mode')!='region-without-frame' or not isinstance(grid,list) or not grid:_error('图例文字区域有原图墨迹，不能覆盖曲线或样符')
                for index in grid:
                    if type(index) is not int or not 0<=index<len(drawings):_error('原网格索引无效')
                    item=drawings[index];color=item.get('color')
                    if item['type']!='s' or not color or min(color)<.7 or max(color)-min(color)>.01 or any(part[0]!='l' or (abs(part[1].x-part[2].x)>.001 and abs(part[1].y-part[2].y)>.001) for part in item['items']):_error('仅允许已绑定浅灰正交网格位于原无框图例后方')
                absolute=source_box+(body['clip'][0],body['clip'][1],body['clip'][0],body['clip'][1])
                for index,item in enumerate(drawings):
                    # MuPDF drawing widths can remain in local Form coordinates.
                    # The display-list paint bounds already include the complete CTM.
                    seq=item['seqno'];bounds=fitz.Rect(paint_bounds[seq][1])
                    if item['type']=='fs' and seq+1<len(paint_bounds) and paint_bounds[seq+1][0]=='stroke-path':bounds|=fitz.Rect(paint_bounds[seq+1][1])
                    if not bounds.intersects(absolute):continue
                    if item.get('fill')==(1.,1.,1.) and item.get('color') is None:continue
                    if index not in grid:_error('原无框图例文字覆盖了非网格图形 '+str(index)+' '+str(absolute)+' '+str(item['rect']))
            cursor=x
            for ident,measurement in zip(group,measurements):
                texts[ident].update(x=cursor,y=y,align='left',rotation=0)
                cursor+=measurement['width']+.5
            boxes.append(box);ids.extend(group)
            bindings.append({'text_id':name,'text_ids':group,'series_path_index':entry['series_path_index'],'series_marker_index':entry['series_marker_index'],'swatch_path_index':entry['swatch_path_index'],'swatch_marker_index':entry['swatch_marker_index'],'source_swatch_center':list(sample_center),'source_swatch_end':[swatch['rect'].x1,sample_center.y]})
        if prepared is not None:prepared.close()
    return ids,bindings,list(frame)
