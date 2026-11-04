"""Verify editable bar annotations against original SVG groups and axis values."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from lxml import etree

from .assets import svg_root,element
from .common import FigureError,resolve_source


@dataclass(frozen=True,slots=True)
class BarLabel:
    id: str
    text: str
    rect: tuple[float,float,float,float]


def _source_text(root,ident):
    group=element(root,ident)
    comments=[(x.text or '').strip() for x in group if isinstance(x,etree._Comment)]
    children=[x for x in group if isinstance(x.tag,str)]
    if len(comments)!=1 or len(children)!=1:raise FigureError('bar_source_text','原SVG文字对象必须有唯一来源文本和变换')
    match=re.search(r'translate\(([-.\d]+)\s+([-.\d]+)\)',children[0].get('transform',''))
    if not match:raise FigureError('bar_source_text','原SVG文字对象缺少位置')
    return comments[0],tuple(map(float,match.groups()))


def bind_bar_labels(spec,root: Path):
    rows=spec.get('bar_labels',[])
    if not isinstance(rows,list) or len(rows)>200:raise FigureError('bar_binding','柱顶绑定必须为不超过200项的数组')
    if not rows:
        if spec.get('source_kind')=='svg' and any(entry.get('source_groups') for entry in spec.get('series',[])):
            svg=svg_root(resolve_source(root,spec['source']));axes=element(svg,spec.get('axes_id',''))
            original={node.get('id') for node in axes if isinstance(node.tag,str) and node.get('id','').startswith('text_') and any(isinstance(child,etree._Comment) and (child.text or '').strip() for child in node)}
            title=spec.get('ingest_provenance',{}).get('plot_title_ref')
            missing=original-({title} if title else set())
            if missing:raise FigureError('bar_binding','图内原始文字尚未完整绑定',missing=sorted(missing))
        return (),()
    if spec.get('source_kind')!='svg':raise FigureError('bar_binding','柱顶文字必须绑定原SVG')
    svg=svg_root(resolve_source(root,spec['source']))
    declared={group for entry in spec.get('series',[]) for group in entry.get('source_groups',[entry.get('source_group')])}
    ticks=spec.get('y_ticks',[])
    try:
        a,b=ticks[0],ticks[-1];v0,v1=float(a['text']),float(b['text']);y0,y1=float(a['position']),float(b['position'])
    except (IndexError,KeyError,TypeError,ValueError) as error:raise FigureError('bar_binding','柱顶文字需要明确的数值轴刻度') from error
    if y0==y1 or v0==v1:raise FigureError('bar_binding','数值轴范围无效')
    out=[];used_text=set();used_bar=set()
    for row in rows:
        ident=row.get('id');tg=row.get('text_group');bg=row.get('bar_group')
        if not all(isinstance(x,str) and x for x in (ident,tg,bg)) or tg in used_text or bg in used_bar or bg not in declared:raise FigureError('bar_binding','柱顶文字、柱形须唯一且属于已绑定系列')
        text,(x,y)=_source_text(svg,tg)
        if not re.fullmatch(r'\d+(?:\.\d+)?',text):raise FigureError('bar_binding','柱顶源文字不是已识别的数值')
        node=element(svg,bg);paths=[x for x in node if isinstance(x.tag,str) and etree.QName(x).localname=='path']
        if len(paths)!=1:raise FigureError('bar_binding','柱形须为唯一原矩形路径')
        d=paths[0].get('d','');nums=[float(n) for n in re.findall(r'-?\d+(?:\.\d+)?',d)]
        if len(nums)!=8 or re.sub(r'[-.\d\sMLZmlz]+','',d):raise FigureError('bar_binding','柱形路径不是显式矩形')
        xs=nums[::2];ys=nums[1::2];left,right,top,bottom=min(xs),max(xs),min(ys),max(ys)
        if len(set(xs))!=2 or len(set(ys))!=2 or not left<=x<=right or not 0<=top-y<=12:raise FigureError('bar_binding','原文字位置不对应柱顶')
        value=v0+(top-y0)*(v1-v0)/(y1-y0)
        if abs(value-float(text))>max(.5,abs(value)*.002):raise FigureError('bar_binding','柱顶数值与原柱及坐标轴不一致')
        out.append(BarLabel(ident,text,(left,top,right,bottom)));used_text.add(tg);used_bar.add(bg)
    if used_bar!=declared:raise FigureError('bar_binding','所有已绑定柱形必须有且仅有一项柱顶文字')
    sections=[];used=set();section_groups=set()
    for row in spec.get('section_labels',[]):
        ident=row.get('id');group=row.get('text_group')
        if not ident or not group or ident in used or ident in {item.id for item in out} or group in section_groups or group in used_text:raise FigureError('bar_binding','区段标题身份重复')
        text,anchor=_source_text(svg,group);sections.append((ident,text,anchor));used.add(ident);section_groups.add(group)
    axes=element(svg,spec.get('axes_id',''))
    original={node.get('id') for node in axes if isinstance(node.tag,str) and node.get('id','').startswith('text_') and any(isinstance(child,etree._Comment) and (child.text or '').strip() for child in node)}
    declared_text=used_text|section_groups
    title_ref=spec.get('ingest_provenance',{}).get('plot_title_ref')
    if title_ref:declared_text.add(title_ref)
    if original!=declared_text:raise FigureError('bar_binding','图内原始文字尚未完整绑定',missing=sorted(original-declared_text),extra=sorted(declared_text-original))
    return tuple(out),tuple(sections)
