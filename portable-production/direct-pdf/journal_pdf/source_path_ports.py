from __future__ import annotations

import math
from pathlib import Path
from typing import TypedDict

import pymupdf as fitz

from .assets import Asset
from .boundary_ports import JsonValue
from .common import FigureError, digest_file


class SourcePlacement(TypedDict):
    id: str
    asset: Asset
    rect: list[float]


def matches_source_port(value: dict[str, JsonValue], endpoint: tuple[float, float], placements: list[SourcePlacement]) -> bool:
    required={'source_asset','source_sha256','path_index','primitive_index','primitive','t','source_point'}
    if not required.issubset(value) or not set(value).issubset(required|{'source_group','edge'}):
        raise FigureError('source_port_declaration','原路径端口须明确源资产、hash、路径/primitive及真实源点')
    row=next((row for row in placements if row['id']==value['source_asset']),None)
    if row is None:
        raise FigureError('source_port_asset','原路径端口引用了不存在的资产')
    asset=row['asset'];receipt=asset.audit
    if receipt.get('mode') not in ('source-vector-body','source-svg-group','source-bound-vector-icon','source-vector-glyph'):
        raise FigureError('source_port_asset','原路径端口仅接受源绑定保真资产')
    if value['source_sha256']!=asset.source_hash or digest_file(Path(asset.source_path))!=asset.source_hash or value.get('source_group')!=receipt.get('source_group'):
        raise FigureError('source_port_source','原路径端口的源hash或源对象不匹配')
    for key in ('path_index','primitive_index'):
        if isinstance(value[key],bool) or not isinstance(value[key],int) or value[key]<0:
            raise FigureError('source_port_index','原路径端口索引须为非负整数')
    t=value['t'];declared=value['source_point']
    if isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) or not 0<=t<=1:
        raise FigureError('source_port_parameter','原路径参数t须为0到1有限数值')
    if not isinstance(declared,list) or len(declared)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in declared):
        raise FigureError('source_port_point','原路径源点须为两个有限坐标')
    native_glyph=receipt['mode']=='source-vector-glyph'
    if native_glyph and value['path_index'] not in receipt['selected_source_path_indices']:
        raise FigureError('source_port_index','端口未绑定所选原glyph路径')
    with (fitz.open(asset.source_path) if native_glyph else fitz.open(stream=asset.data,filetype='pdf')) as document:
        drawings=document[receipt['source_page'] if native_glyph else 0].get_drawings()
        if value['path_index']>=len(drawings) or value['primitive_index']>=len(drawings[value['path_index']]['items']):
            raise FigureError('source_port_index','原路径或primitive索引越界')
        primitive=drawings[value['path_index']]['items'][value['primitive_index']]
        if primitive[0]!=value['primitive']:
            raise FigureError('source_port_primitive','原路径primitive类型不符')
        match primitive[0]:
            case 'c':
                points=primitive[1:]
                point=fitz.Point(*(sum(weight*getattr(p,axis) for weight,p in zip(((1-t)**3,3*(1-t)**2*t,3*(1-t)*t*t,t**3),points)) for axis in ('x','y')))
            case 'l':
                point=primitive[1]+(primitive[2]-primitive[1])*t
            case 're':
                edge=value.get('edge')
                if isinstance(edge,bool) or not isinstance(edge,int) or not 0<=edge<=3:
                    raise FigureError('source_port_edge','矩形原primitive须明确0至3的真实边')
                rect=primitive[1];corners=[rect.tl,rect.tr,rect.br,rect.bl,rect.tl]
                point=corners[edge]+(corners[edge+1]-corners[edge])*t
            case _:
                raise FigureError('source_port_primitive','尚未支持此原路径primitive端口')
    clip=receipt['source_clip']
    source_point=(point.x,point.y) if native_glyph else (point.x+clip[0],point.y+clip[1])
    if native_glyph:point=point-fitz.Point(clip[0],clip[1])
    if math.dist(source_point,declared)>.0001:
        raise FigureError('source_port_point','声明源点不在已绑定的原primitive参数位置',actual_source_point=source_point)
    target=fitz.Rect(row['rect']);viewport=fitz.Rect(asset.rect)
    scale=min(target.width/viewport.width,target.height/viewport.height)
    actual=(target.x0+(target.width-viewport.width*scale)/2+(point.x-viewport.x0)*scale,
            target.y0+(target.height-viewport.height*scale)/2+(point.y-viewport.y0)*scale)
    return math.dist(actual,endpoint)<=.0001
