"""Conservative geometry proposals; source objects remain unapproved candidates."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import fitz

_NUMBER=re.compile(r'^[+\-−]?\d+(?:[.,]\d+)?(?:[eE][+\-]?\d+)?$')


def _frames(page: fitz.Rect, drawings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    horizontal=[];vertical=[];frames=[]
    for index,item in enumerate(drawings):
        if item.get('type') not in ('s','fs'):continue
        for part in item['items']:
            if part[0]=='re':
                rect=fitz.Rect(part[1])
                if rect.width>=page.width*.05 and rect.height>=page.height*.05:frames.append((rect,[index]))
            elif part[0]=='l':
                a,b=part[1],part[2]
                if abs(a.y-b.y)<.2 and abs(a.x-b.x)>=page.width*.05:horizontal.append((min(a.x,b.x),max(a.x,b.x),(a.y+b.y)/2,index))
                if abs(a.x-b.x)<.2 and abs(a.y-b.y)>=page.height*.05:vertical.append((min(a.y,b.y),max(a.y,b.y),(a.x+b.x)/2,index))
    if len(horizontal)>300 or len(vertical)>300:return []
    for x0,x1,y0,top in horizontal:
        for xx0,xx1,y1,bottom in horizontal:
            if y1-y0<page.height*.05 or abs(x0-xx0)>.5 or abs(x1-xx1)>.5:continue
            left=[i for a,b,x,i in vertical if abs(x-x0)<.5 and abs(a-y0)<.5 and abs(b-y1)<.5]
            right=[i for a,b,x,i in vertical if abs(x-x1)<.5 and abs(a-y0)<.5 and abs(b-y1)<.5]
            if left and right:frames.append((fitz.Rect(x0,y0,x1,y1),[top,bottom,left[0],right[0]]))
    result=[]
    for rect,indices in frames:
        if any(all(abs(a-b)<1 for a,b in zip(rect,p['bbox'])) for p in result):continue
        result.append({'id':f'panel-{len(result)+1}','bbox':list(rect),'frameDrawingIndices':indices,'evidence':'四条源矢量边形成矩形绘图区候选'})
    return result


def propose_objects(page: fitz.Rect, drawings: list[dict[str, Any]], spans: list[dict[str, Any]], legend_lines: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Associate numeric text and colored paths with actual frame candidates."""
    panels=_frames(page,drawings);assigned=set()
    for panel in panels:
        frame=fitz.Rect(panel['bbox']);xticks=[];yticks=[];titles=[];xtitles=[];ytitles=[];groups=defaultdict(list)
        for i,span in enumerate(spans):
            text=span['text'].strip();box=fitz.Rect(span['bbox']);center=(box.tl+box.br)*.5
            gap=max(8.,float(span.get('size',8))*2.5)
            ref={'id':f'text-{i+1}','text':text,'bbox':list(box)}
            if _NUMBER.fullmatch(re.sub(r'[\s\u2009\u202f]','',text)):
                if frame.x0-1<=center.x<=frame.x1+1 and -1<=box.y0-frame.y1<=gap:xticks.append(ref)
                if frame.y0-1<=center.y<=frame.y1+1 and -1<=frame.x0-box.x1<=gap:yticks.append(ref)
            else:
                if frame.x0<=center.x<=frame.x1 and -1<=frame.y0-box.y1<=gap:titles.append(ref)
                if frame.x0<=center.x<=frame.x1 and -1<=box.y0-frame.y1<=gap*2:xtitles.append(ref)
                if frame.y0<=center.y<=frame.y1 and -1<=frame.x0-box.x1<=gap*2:ytitles.append(ref)
        for index,item in enumerate(drawings):
            color=item.get('color');rect=item['rect']
            if color is None or item.get('type')!='s' or index in panel['frameDrawingIndices']:continue
            if rect.is_empty or not (frame+(-1,-1,1,1)).contains(rect):continue
            key=(tuple(round(x,4) for x in color),item.get('dashes',''))
            groups[key].append(index)
            if len(color)>=3 and max(color)-min(color)>.01:assigned.add(index)
        axes=[{'orientation':'x','side':'bottom','frameDrawingIndices':panel['frameDrawingIndices'],'verified':False},{'orientation':'y','side':'left','frameDrawingIndices':panel['frameDrawingIndices'],'verified':False}]
        panel.update(axisCandidates=axes,xTicks=xticks,yTicks=yticks,titles=titles,xAxisTitles=xtitles,yAxisTitles=ytitles,curveGroups=[{'strokeColor':list(color),'dash':dash,'drawingIndices':indices,'evidence':'源绘图区内同色和线型的路径候选','verified':False} for (color,dash),indices in groups.items()])
    nested=[]
    for panel in panels:
        box=fitz.Rect(panel['bbox'])
        parent=next((other for other in panels if other is not panel and fitz.Rect(other['bbox']).contains(box) and fitz.Rect(other['bbox']).get_area()>box.get_area()),None)
        if parent and (len(panel['xTicks'])<2 or len(panel['yTicks'])<2):nested.append({'id':panel['id'],'bbox':panel['bbox'],'parentId':parent['id'],'frameDrawingIndices':panel['frameDrawingIndices'],'verified':False,'reason':'内嵌框缺少可确认的双轴刻度，可能是图例或嵌套面板'})
    panels=[panel for panel in panels if not any(row['id']==panel['id'] for row in nested)]
    legends=[];swatch_indices=set()
    for line in legend_lines or []:
        box=fitz.Rect(line['bbox']);swatches=[]
        for i,item in enumerate(drawings):
            rect=item['rect'];color=item.get('color')
            if item.get('type')!='s' or color is None or not 1<=rect.width<=page.width*.12 or rect.height>box.height:continue
            if not 0<=box.x0-rect.x1<=page.width*.05 or not box.y0-2<=(rect.y0+rect.y1)/2<=box.y1+2:continue
            swatches.append(i);swatch_indices.add(i)
        colors={tuple(round(x,4) for x in drawings[i]['color']) for i in swatches}
        matching=[p['id'] for p in panels if any(tuple(g['strokeColor']) in colors for g in p['curveGroups'])]
        legends.append({'text':line['text'],'bbox':list(box),'swatchDrawingIndices':swatches,'matchingPanelIds':matching,'verified':False,'evidence':'按图例文字旁的线段及颜色寻找候选；样式、系列和作用域待核对'})
    unassigned=[i for i,d in enumerate(drawings) if d.get('color') is not None and len(d['color'])>=3 and max(d['color'])-min(d['color'])>.01 and i not in assigned and i not in swatch_indices]
    unresolved=defaultdict(list)
    for i in unassigned:unresolved[tuple(round(x,4) for x in drawings[i]['color'])].append(i)
    unassigned_groups=[]
    for color,indices in unresolved.items():
        rect=fitz.Rect(drawings[indices[0]]['rect'])
        for i in indices[1:]:rect.include_rect(drawings[i]['rect'])
        unassigned_groups.append({'strokeColor':list(color),'drawingIndices':indices,'bbox':list(rect),'verified':False,'evidence':'未归属路径按颜色汇总，不能认定是同一曲线或同一面板'})
    return {'status':'needs_semantic_binding','panels':panels,'nestedUnclassified':nested,'legendCandidates':legends,'unassignedColoredPathIndices':unassigned,'unassignedColorGroups':unassigned_groups,'warning':'候选可能缺少3D面板、灰度曲线或共享图例；必须结合当前图核对'}
