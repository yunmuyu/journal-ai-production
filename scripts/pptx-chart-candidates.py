"""Propose source-bound simple PPTX series; never invent curve points or labels."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from verify_pptx_geometry import NS, shapes


def point_in(rect: list[float], p: tuple[float,float], margin: float=0) -> bool:
    return rect[0]-margin<=p[0]<=rect[2]+margin and rect[1]-margin<=p[1]<=rect[3]+margin


def geometry(element: ET.Element) -> tuple[tuple[float,float],tuple[float,float]] | None:
    transform=element.find('./p:spPr/a:xfrm',NS)
    if transform is None or int(transform.get('rot','0'))!=0:return None
    offset=transform.find('./a:off',NS);extent=transform.find('./a:ext',NS)
    if offset is None or extent is None:return None
    x,y=int(offset.get('x'))/12700,int(offset.get('y'))/12700
    dx,dy=int(extent.get('cx'))/12700,int(extent.get('cy'))/12700
    start=(x+(dx if transform.get('flipH')=='1' else 0),y+(dy if transform.get('flipV')=='1' else 0))
    end=(x+(0 if transform.get('flipH')=='1' else dx),y+(0 if transform.get('flipV')=='1' else dy))
    return start,end


def proposal(file: Path,slide: int,plot: list[float],legend: list[float]) -> dict:
    all_shapes=shapes(file)  # Reject unsupported composite objects before proposing a rewrite.
    if any(len(r)!=4 or any(not math.isfinite(x) for x in r) or r[2]<=r[0] or r[3]<=r[1] for r in (plot,legend)):
        raise ValueError('pptx_proposal_region_invalid')
    with ZipFile(file) as z:
        root=ET.fromstring(z.read(f'ppt/slides/slide{slide}.xml'))
    markers=[];lines=[];shadow_ids=[]
    for obj in root.findall('.//p:sp',NS)+root.findall('.//p:cxnSp',NS):
        node=obj.find('./p:nvSpPr/p:cNvPr',NS)
        if node is None:node=obj.find('./p:nvCxnSpPr/p:cNvPr',NS)
        if node is None:raise ValueError('pptx_shape_identity')
        ident=int(node.get('id'));shadow_ids.append(ident);geom=geometry(obj)
        if geom is None:continue
        start,end=geom;center=((start[0]+end[0])/2,(start[1]+end[1])/2)
        if obj.tag.endswith('cxnSp'):
            color=obj.find('./p:spPr/a:ln/a:solidFill/a:srgbClr',NS)
            dash=obj.find('./p:spPr/a:ln/a:prstDash',NS)
            if color is not None:lines.append({'id':ident,'color':color.get('val').upper(),'start':start,'end':end,'dash':dash.get('val') if dash is not None else 'solid'})
        else:
            color=obj.find('./p:spPr/a:solidFill/a:srgbClr',NS);shape=obj.find('./p:spPr/a:prstGeom',NS)
            if color is not None and shape is not None and shape.get('prst') in ('triangle','ellipse','rect','diamond'):
                markers.append({'id':ident,'color':color.get('val').upper(),'shape':shape.get('prst'),'center':center,
                                'tolerance':max(abs(end[0]-start[0]),abs(end[1]-start[1]))/2+1.5})
    plot_lines=[x for x in lines if point_in(plot,x['start'],1) and point_in(plot,x['end'],1)]
    legend_lines=[x for x in lines if point_in(legend,x['start']) and point_in(legend,x['end'])]
    series=[];unresolved=[]
    for line in legend_lines:
        color=line['color'];legend_mark=[m for m in markers if m['color']==color and point_in(legend,m['center'])]
        data_mark=[m for m in markers if m['color']==color and point_in(plot,m['center'],5)]
        data_lines=[x for x in plot_lines if x['color']==color]
        if len([v for v in legend_lines if v['color']==color])!=1 or len(legend_mark)!=1 or len(data_mark)<2 or len(data_lines)!=len(data_mark)-1:
            unresolved.append({'color':color,'reason':'图例、标记或曲线段数量不唯一'});continue
        edges=[]
        for segment in data_lines:
            matched=[]
            for pt in (segment['start'],segment['end']):
                close=[m for m in data_mark if math.dist(pt,m['center'])<=m['tolerance']]
                if len(close)!=1:break
                matched.append(close[0]['id'])
            if len(matched)!=2 or matched[0]==matched[1]:break
            edges.append(matched)
        degrees={m['id']:0 for m in data_mark}
        for a,b in edges:degrees[a]+=1;degrees[b]+=1
        seen={data_mark[0]['id']};previous=-1
        while previous!=len(seen):
            previous=len(seen)
            for a,b in edges:
                if a in seen:seen.add(b)
                if b in seen:seen.add(a)
        if len(edges)!=len(data_lines) or len(seen)!=len(data_mark) or sorted(degrees.values())!=[1,1]+[2]*(len(data_mark)-2):
            unresolved.append({'color':color,'reason':'曲线段与数据标记无法唯一构成连续路径'});continue
        if any(v['dash']!=line['dash'] for v in data_lines):
            unresolved.append({'color':color,'reason':'图例样线与源曲线线型不一致'});continue
        marker=legend_mark[0]['shape']
        if any(m['shape']!=marker for m in data_mark):
            unresolved.append({'color':color,'reason':'图例标记与数据标记不一致'});continue
        rgb=[int(color[i:i+2],16) for i in (0,2,4)]
        gray=round(sum(c*w for c,w in zip(rgb,(.299,.587,.114),strict=True)))
        series.append({'color':color,'gray':gray,'marker':marker,'curveShapeIds':[x['id'] for x in data_lines],
                       'legendShapeIds':[line['id']],'pointCount':len(data_mark),'dash':line['dash']})
    return {'version':1,'sourceSha256':hashlib.sha256(file.read_bytes()).hexdigest(),'slide':slide,
            'shapeCount':len(all_shapes),'shadowCandidates':shadow_ids,'strokeShapeIds':[x['id'] for x in plot_lines+legend_lines],
            'sourcePlotWidthPt':plot[2]-plot[0],'series':series,'unresolved':unresolved,
            'warning':'仅为对象候选，图号、区域、系列名称和阴影语义仍须核对；不代表成图'}


if __name__=='__main__':
    print(json.dumps(proposal(Path(sys.argv[1]),int(sys.argv[2]),json.loads(sys.argv[3]),json.loads(sys.argv[4])),ensure_ascii=False))
