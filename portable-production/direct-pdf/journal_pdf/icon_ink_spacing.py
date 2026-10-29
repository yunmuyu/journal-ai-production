"""Measure source-bound vector icon ink instead of treating its crop as ink."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pymupdf as fitz
from PIL import Image

from .common import FigureError

if TYPE_CHECKING:
    from .scene import Scene

_VECTOR_MODES={'source-bound-vector-icon','source-vector-glyph'}
_PIXELS_PER_PT=20


def parse_icon_ink_checks(value):
    if not isinstance(value,list):raise FigureError('icon_ink_check_invalid','图标间距检查须为数组')
    result=[]
    for item in value:
        if not isinstance(item,dict):raise FigureError('icon_ink_check_invalid','图标间距检查须为对象')
        kind=item.get('kind');required={'kind','asset_id','side'}
        if kind=='icon_text':required=required|{'text_id'}
        if kind=='icon_frame':required=required|{'frame_id'}
        if kind not in ('icon_text','icon_frame') or not required<=set(item) or set(item)-required-{'target_pt','reason'}:
            raise FigureError('icon_ink_check_invalid','图标间距绑定字段无效')
        if any(not isinstance(item[k],str) or not item[k] for k in required-{'kind','side'}):
            raise FigureError('icon_ink_check_invalid','图标间距对象无效')
        side=item['side'];sides={'right','bottom'} if kind=='icon_text' else {'left','right','top','bottom'}
        if not isinstance(side,str) or side not in sides:raise FigureError('icon_ink_check_invalid','图标间距方向无效')
        default=3. if kind=='icon_text' else 4.5 if side in ('left','right') else 2.7
        target=item.get('target_pt',default);reason=item.get('reason')
        if (isinstance(target,bool) or not isinstance(target,(float,int)) or not math.isfinite(target) or target<0
                or ('target_pt' in item and (not isinstance(reason,str) or not reason.strip()))
                or ('reason' in item and 'target_pt' not in item)):
            raise FigureError('icon_ink_check_invalid','图标间距例外须指定非负数值和原因')
        result.append({**item,'target_pt':float(target),'reason':reason})
    return result


def _visible_ink(asset,width,height,cache):
    if asset.kind!='pdf' or asset.audit.get('mode') not in _VECTOR_MODES or asset.doc is None:return None
    key=(asset.key,round(width,6),round(height,6))
    if key in cache:return cache[key]
    if width<=0 or height<=0 or width*height*_PIXELS_PER_PT**2>16_000_000:return None
    source=asset.doc[0]
    if source.get_images(full=True) or source.get_texttrace() or not source.get_drawings():return None
    source_rect=fitz.Rect(asset.rect)
    if source_rect.is_empty or abs(width/height-source_rect.width/source_rect.height)>1e-4:return None
    try:
        with fitz.open() as isolated:
            page=isolated.new_page(width=width,height=height)
            page.show_pdf_page(fitz.Rect(0,0,width,height),asset.doc,0,clip=source_rect,keep_proportion=True)
            pix=page.get_pixmap(matrix=fitz.Matrix(_PIXELS_PER_PT,_PIXELS_PER_PT),colorspace=fitz.csGRAY,alpha=False)
            image=Image.frombytes('L',(pix.width,pix.height),pix.samples)
            ink=image.point(lambda v:255 if v<255 else 0).getbbox()
    except (RuntimeError,ValueError):return None
    if ink is None or ink[0]==0 or ink[1]==0 or ink[2]>=pix.width or ink[3]>=pix.height:return None
    bounds=[v/_PIXELS_PER_PT for v in ink];cache[key]=bounds
    return bounds


def audit_icon_ink_checks(scene: Scene):
    assets={a['id']:a for a in scene.assets};texts={t['id']:t for t in scene.texts};nodes={n['id']:n for n in scene.nodes}
    cache=scene._icon_ink_cache;checks=[];issues=[];notes=[]
    for item in scene.icon_ink_checks:
        placement=assets.get(item['asset_id']);other=texts.get(item.get('text_id')) if item['kind']=='icon_text' else nodes.get(item.get('frame_id'))
        ids=[item['asset_id'],item.get('text_id') or item.get('frame_id')]
        if not placement or not other:
            issues.append({'code':'icon_ink_binding_invalid','ids':ids});continue
        rect=placement['rect'];local=_visible_ink(placement['asset'],rect[2]-rect[0],rect[3]-rect[1],cache)
        if local is None:
            notes.append({'code':'icon_ink_unverified','ids':ids,'message':'图标真实墨迹无法可靠测量，须检查实际PDF。'});continue
        ink=[rect[0]+local[0],rect[1]+local[1],rect[0]+local[2],rect[1]+local[3]]
        side=item['side'];target=item['target_pt']*scene.size/8
        if item['kind']=='icon_text':
            bbox=other['position']['bbox']
            if side=='right':
                if min(ink[3],bbox[3])<=max(ink[1],bbox[1]):
                    issues.append({'code':'icon_ink_alignment_invalid','ids':ids});continue
                gap=bbox[0]-ink[2]
            else:
                if min(ink[2],bbox[2])<=max(ink[0],bbox[0]):
                    issues.append({'code':'icon_ink_alignment_invalid','ids':ids});continue
                gap=bbox[1]-ink[3]
        else:
            frame=other['rect'];width=other.get('width')
            if other.get('kind')!='rectangle' or other.get('invisible') or not isinstance(width,(int,float)) or width<=0:
                issues.append({'code':'icon_ink_binding_invalid','ids':ids});continue
            half=width/2
            gap={'left':ink[0]-(frame[0]+half),'right':(frame[2]-half)-ink[2],
                 'top':ink[1]-(frame[1]+half),'bottom':(frame[3]-half)-ink[3]}[side]
        entry={'kind':item['kind'],'ids':ids,'side':side,'gap_pt':gap,'target_pt':target,'reason':item.get('reason'),
               'ink_bbox_pt':ink,'method':'isolated_vector_pdf_render','pixels_per_pt':_PIXELS_PER_PT,'quantization_pt':1/_PIXELS_PER_PT}
        checks.append(entry)
        differs=abs(gap-target)>.15 if item['kind']=='icon_text' else gap<target-.15
        if differs:
            notes.append({'code':'icon_ink_spacing_review',**entry,'message':'图标墨迹距离偏离参考，按可读性、框对齐和遮挡复核。'})
    return {'checks':checks,'issues':issues,'notes':notes}


def parse_icon_group_centers(value):
    if not isinstance(value,list):raise FigureError('icon_group_center_invalid','组合居中检查须为数组')
    for item in value:
        if (not isinstance(item,dict) or set(item)!={'asset_id','text_id','frame_id','axis'}
                or item['axis'] not in ('horizontal','vertical')
                or any(not isinstance(item[key],str) or not item[key] for key in ('asset_id','text_id','frame_id'))):
            raise FigureError('icon_group_center_invalid','组合居中绑定无效')
    return [dict(item) for item in value]


def audit_icon_group_centers(scene: Scene):
    assets={a['id']:a for a in scene.assets};texts={t['id']:t for t in scene.texts};nodes={n['id']:n for n in scene.nodes}
    checks=[];issues=[];notes=[]
    for item in scene.icon_group_centers:
        ids=[item['asset_id'],item['text_id'],item['frame_id']]
        asset=assets.get(ids[0]);text=texts.get(ids[1]);frame=nodes.get(ids[2])
        if not asset or not text or not frame or frame.get('kind')!='rectangle' or frame.get('invisible'):
            issues.append({'code':'icon_group_center_binding_invalid','ids':ids});continue
        rect=asset['rect'];ink=_visible_ink(asset['asset'],rect[2]-rect[0],rect[3]-rect[1],scene._icon_ink_cache)
        if ink is None:
            notes.append({'code':'icon_ink_unverified','ids':ids,'message':'组合图标真实墨迹不可验证，须核对最终PDF。'});continue
        visual=[rect[0]+ink[0],rect[1]+ink[1],rect[0]+ink[2],rect[1]+ink[3]]
        label=text['position']['bbox'];bounds=frame['rect'];half=(frame.get('width') or 0)/2
        start,end=(0,2) if item['axis']=='horizontal' else (1,3)
        first=min(visual[start],label[start])-bounds[start]-half
        second=bounds[end]-half-max(visual[end],label[end])
        entry={'ids':ids,'axis':item['axis'],'first_margin_pt':first,'second_margin_pt':second,
               'method':'vector_render_ink_and_text_bbox'};checks.append(entry)
        if abs(first-second)>.3*scene.size/8:
            notes.append({'code':'icon_group_center_review',**entry,'message':'图标和文字整体未居中，按框、连线和内容复核。'})
    return {'checks':checks,'issues':issues,'notes':notes}
