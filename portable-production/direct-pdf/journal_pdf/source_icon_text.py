"""Explicit source glyph ownership for native PDF icon relettering."""
from __future__ import annotations

import math
from typing import TypedDict, NotRequired

import pymupdf as fitz
from PIL import Image, ImageChops, ImageDraw

from .common import FigureError


class TextReplacement(TypedDict):
    source_text: str
    source_bbox: list[float]
    target_text_id: str
    source_occurrences: NotRequired[int]
    source_instances: NotRequired[list[list[float]]]
    target_text: NotRequired[str]
    change_reason: NotRequired[str]


def validate_raster_replacements(replacements: list[TextReplacement], masks: list[list[float]]) -> list[TextReplacement]:
    """Bind reviewed raster text regions to masks; pixel lettering cannot be OCR-proven here."""
    if not isinstance(replacements,list) or len(replacements)!=len(masks):
        raise FigureError('raster_replacement_mapping','每个遮字区域须登记且仅登记一个目标文字')
    targets=set();boxes=[]
    for row in replacements:
        if not isinstance(row,dict) or not {'source_text','source_bbox','target_text_id'}.issubset(row) or not set(row).issubset({'source_text','source_bbox','target_text_id','target_text','change_reason'}):
            raise FigureError('raster_replacement_mapping','位图换字须明确原文、像素区域及目标文字ID')
        if any(not isinstance(row[key],str) or not row[key].strip() for key in ('source_text','target_text_id')) or row['target_text_id'] in targets:
            raise FigureError('raster_replacement_mapping','位图换字原文或目标ID为空、重复')
        bbox=row['source_bbox']
        if not isinstance(bbox,list) or len(bbox)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v!=int(v) for v in bbox) or bbox[2]<=bbox[0] or bbox[3]<=bbox[1] or bbox not in masks or bbox in boxes:
            raise FigureError('raster_replacement_mapping','原字像素区域须逐一绑定唯一遮罩')
        if 'target_text' in row and (not isinstance(row['target_text'],str) or not row['target_text'].strip()):
            raise FigureError('raster_replacement_mapping','目标文字为空')
        if row.get('target_text',row['source_text'])!=row['source_text'] and (not isinstance(row.get('change_reason'),str) or not row['change_reason'].strip()):
            raise FigureError('raster_replacement_mapping','异文替换须明确更正原因')
        targets.add(row['target_text_id']);boxes.append(bbox)
    return [dict(row) for row in replacements]


def validate_replacements(page, clip: fitz.Rect, replacements, *, allow_target_text: bool=False, allow_intersecting_text: bool=False, allow_grouped: bool=False) -> list[TextReplacement]:
    spans = [span for block in page.get_text('dict', **({} if allow_intersecting_text else {'clip':clip}))['blocks'] if block['type'] == 0
             for line in block['lines'] for span in line['spans'] if span['text'].strip() and (not allow_intersecting_text or clip.intersects(fitz.Rect(span['bbox'])))]
    if replacements is None:
        replacements = []
    if not isinstance(replacements, list):
        raise FigureError('source_icon_replacements', '换字声明须为列表')
    used = set()
    output = []
    targets = set()
    for row in replacements:
        required={'source_text','source_bbox','target_text_id'}
        allowed=required | ({'target_text','change_reason','source_occurrences'} if allow_target_text else set())
        if allow_grouped:allowed.add('source_instances')
        if not isinstance(row, dict) or not required.issubset(row) or not set(row).issubset(allowed):
            raise FigureError('source_icon_replacements', '换字须明确原字、原字真实bbox和目标文字ID')
        if not isinstance(row['source_text'], str) or not row['source_text'].strip() or not isinstance(row['target_text_id'], str) or not row['target_text_id'] or row['target_text_id'] in targets:
            raise FigureError('source_icon_replacements', '换字原字及目标ID无效或重复')
        if 'target_text' in row and (not isinstance(row['target_text'],str) or not row['target_text'].strip()):
            raise FigureError('source_body_target_text','目标文字须明确且非空')
        if row.get('target_text',row['source_text'])!=row['source_text'] and (not isinstance(row.get('change_reason'),str) or not row['change_reason'].strip()):
            raise FigureError('source_body_change_reason','异文替换须明确语义更正原因')
        bbox = row['source_bbox']
        if not isinstance(bbox, list) or len(bbox) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bbox):
            raise FigureError('source_icon_replacements', '换字bbox无效')
        if not (clip.intersects(fitz.Rect(bbox)) if allow_intersecting_text else clip.contains(fitz.Rect(bbox))):
            raise FigureError('source_icon_replacements', '换字bbox越过图标裁区')
        found = next((index for index, span in enumerate(spans) if index not in used and span['text'] == row['source_text']
                      and all(abs(a-b) < .01 for a, b in zip(span['bbox'], bbox))), None)
        if found is None:
            raise FigureError('source_icon_replacements', '换字声明与真实源字及bbox不匹配')
        matches = [index for index, span in enumerate(spans) if index not in used and span == spans[found]] if allow_target_text else [found]
        if 'source_instances' in row:
            instances=row['source_instances']
            if not isinstance(instances,list) or len(instances)<2 or instances[0]!=bbox or len({tuple(b) for b in instances if isinstance(b,list)})!=len(instances):
                raise FigureError('source_icon_replacements','合并原字须逐项登记不重复的真实bbox，首项须为主原字')
            matches=[]
            for box in instances:
                if not isinstance(box,list) or len(box)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in box) or max(abs(a-b) for a,b in zip(box,bbox))>2:
                    raise FigureError('source_icon_replacements','只接受相邻重叠的同文原字合并')
                found_instance=next((i for i,s in enumerate(spans) if i not in used and i not in matches and s['text']==row['source_text'] and all(abs(a-b)<.01 for a,b in zip(s['bbox'],box))),None)
                overlap=fitz.Rect(box)&fitz.Rect(bbox)
                if found_instance is None or overlap.is_empty or overlap.get_area()<.6*min(fitz.Rect(box).get_area(),fitz.Rect(bbox).get_area()):
                    raise FigureError('source_icon_replacements','合并声明与真实重叠同文原字不符')
                matches.append(found_instance)
        if 'source_occurrences' in row and (type(row['source_occurrences']) is not int or row['source_occurrences'] != len(matches)):
            raise FigureError('source_icon_replacements', '重复源字数量与实际来源不符')
        used.update(matches)
        targets.add(row['target_text_id'])
        replacement=TextReplacement(source_text=row['source_text'], source_bbox=list(bbox), target_text_id=row['target_text_id'])
        if len(matches) > 1:replacement['source_occurrences']=len(matches)
        if 'source_instances' in row:replacement['source_instances']=[list(b) for b in row['source_instances']]
        if 'target_text' in row:replacement['target_text']=row['target_text']
        if 'change_reason' in row:replacement['change_reason']=row['change_reason']
        output.append(replacement)
    if len(used) != len(spans):
        raise FigureError('source_icon_contains_text', '裁区含未登记原字；禁止隐式删除')
    return output


def assert_clear_text_region(page, replacements: list[TextReplacement]) -> None:
    for row in replacements:
        pix = page.get_pixmap(matrix=fitz.Matrix(8, 8), clip=fitz.Rect(row['source_bbox']), colorspace=fitz.csRGB, alpha=False)
        if min(pix.samples) < 254:
            raise FigureError('source_icon_text_over_graphic', '原字bbox含必要图形或非白背景，不能按此换字')


def compare_pixels(source, derived, clip: fitz.Rect, replacements: list[TextReplacement], zoom: int) -> None:
    if (source.width, source.height) != (derived.width, derived.height):
        raise FigureError('source_icon_pixels_changed', '图标隔离尺寸改变')
    original = Image.frombytes('RGB', (source.width, source.height), source.samples)
    result = Image.frombytes('RGB', (derived.width, derived.height), derived.samples)
    diff = ImageChops.difference(original, result)
    mask = ImageDraw.Draw(diff)
    for row in replacements:
        for bounds in row.get('source_instances',[row['source_bbox']]):
            box = fitz.Rect(bounds)
            mask.rectangle((math.floor((box.x0-clip.x0)*zoom)-1, math.floor((box.y0-clip.y0)*zoom)-1,
                            math.ceil((box.x1-clip.x0)*zoom)+1, math.ceil((box.y1-clip.y0)*zoom)+1), fill=(0, 0, 0))
    if diff.getbbox() is not None:
        raise FigureError('source_icon_pixels_changed', '图标非登记文字区域像素改变，拒绝继续')
