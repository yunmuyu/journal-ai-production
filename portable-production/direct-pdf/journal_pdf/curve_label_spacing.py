"""Conservative clearance checks for explicitly bound chart curves."""
from __future__ import annotations

import math
import pymupdf as fitz

from .common import FigureError
from .legend_collision import segment_box_distance


def parse_curve_label_checks(value):
    if not isinstance(value,list):raise FigureError('curve_label_check_invalid','曲线标注检查须为数组')
    result=[]
    for item in value:
        if (not isinstance(item,dict) or set(item)-{'text_id','path_id','asset_id','target_pt','reason'}
                or not isinstance(item.get('text_id'),str) or not item['text_id']
                or ('path_id' in item)==('asset_id' in item)):
            raise FigureError('curve_label_check_invalid','须绑定文字和一条曲线')
        key='path_id' if 'path_id' in item else 'asset_id'
        if not isinstance(item[key],str) or not item[key]:raise FigureError('curve_label_check_invalid','曲线绑定无效')
        target=item.get('target_pt',1.);reason=item.get('reason')
        if (isinstance(target,bool) or not isinstance(target,(int,float)) or not math.isfinite(target) or target<0
                or ('target_pt' in item and (not isinstance(reason,str) or not reason.strip()))
                or ('reason' in item and 'target_pt' not in item)):
            raise FigureError('curve_label_check_invalid','间距例外须指定非负数值和原因')
        result.append({**item,'target_pt':float(target),'reason':reason})
    return result


def _source_segments(placement):
    asset=placement['asset'];target=placement['rect']
    if (asset.kind!='pdf' or asset.doc is None or asset.audit.get('mode')!='source-svg-group'
            or asset.audit.get('clipped_viewport') is not False):return None
    clip=fitz.Rect(asset.rect);tw=target[2]-target[0];th=target[3]-target[1]
    if clip.is_empty or tw<=0 or th<=0 or abs(tw/th-clip.width/clip.height)>1e-4:return None
    drawings=asset.doc[0].get_drawings(extended=True)
    lines=[d for d in drawings if d.get('type') in ('s','fs') and not d.get('closePath')
           and len(d.get('items',[]))>=2 and all(i[0]=='l' for i in d['items'])]
    if len(lines)!=1:return None
    line=lines[0];width=line.get('width')
    if not isinstance(width,(int,float)) or width<=0:return None
    extent=fitz.Rect(line['rect']);extent+=(-width/2,-width/2,width/2,width/2)
    if not clip.contains(extent):return None
    for d in drawings:
        if d.get('type')=='clip':
            if not all(i[0]=='re' for i in d.get('items',[])) or not fitz.Rect(d['scissor']).contains(extent):return None
    sx=tw/clip.width;sy=th/clip.height
    def transform(point):return (target[0]+(point.x-clip.x0)*sx,target[1]+(point.y-clip.y0)*sy)
    return [(transform(i[1]),transform(i[2])) for i in line['items']],width*sx


def audit_curve_label_checks(scene):
    texts={t['id']:t for t in scene.texts};paths={p['id']:p for p in scene.paths};assets={a['id']:a for a in scene.assets}
    checks=[];issues=[];notes=[]
    for item in scene.curve_label_checks:
        curve_id=item.get('path_id') or item.get('asset_id');ids=[item['text_id'],curve_id]
        text=texts.get(item['text_id']);curve=paths.get(curve_id) if 'path_id' in item else assets.get(curve_id)
        if text is None or curve is None:
            issues.append({'code':'curve_label_binding_invalid','ids':ids});continue
        if 'path_id' in item:
            points=curve.get('points',[]);width=curve.get('width')
            resolved=([(a,b) for a,b in zip(points,points[1:])],width) if (len(points)>=2 and not curve.get('closed')
                       and not curve.get('arrow') and isinstance(width,(int,float)) and not isinstance(width,bool)
                       and math.isfinite(width) and width>0) else None
        else:resolved=_source_segments(curve)
        if resolved is None:
            notes.append({'code':'data_curve_unverified','ids':ids,'message':'曲线几何或裁剪无法可靠确认，须检查实际PDF。'});continue
        segments,width=resolved;bbox=text['position']['bbox']
        gap=min(segment_box_distance(a,b,bbox) for a,b in segments)-width/2
        target=item['target_pt']*scene.size/8
        entry={'ids':ids,'gap_pt':gap,'target_pt':target,'reason':item.get('reason'),
               'method':'stroke_envelope_to_text_bbox_conservative'}
        checks.append(entry)
        if gap<target-.15:
            notes.append({'code':'data_curve_spacing_review',**entry,'message':'文字接近曲线，需核对真实笔画及数据对应关系。'})
    return {'checks':checks,'issues':issues,'notes':notes}
