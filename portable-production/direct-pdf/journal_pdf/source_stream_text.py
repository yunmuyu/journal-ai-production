"""Remove explicitly bound PDF text without rewriting native drawing operations."""
from __future__ import annotations

import hashlib
import json
import re
import math
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from pypdf import PdfReader
from pypdf.generic import ContentStream, DecodedStreamObject

from .common import FigureError, digest_file
from .source_icon_text import compare_pixels, validate_replacements
from .source_icons import PreparedIcon, consume_paths, path_record


def prepare_stream_body(source: Path, page_no: int, clip: list[float], text_replacements) -> PreparedIcon:
    """Accept only a full-page, one-stream vector source with fully registered text."""
    with fitz.open(source) as original, fitz.open(source) as edited:
        if len(original)!=1 or page_no!=0 or original[0].rotation or fitz.Rect(clip)!=original[0].rect:
            raise FigureError('source_stream_scope','仅支持单页、未旋转、完整页面的源图')
        page=original[0]
        if page.get_images(full=True) or page.get_xobjects():
            raise FigureError('source_stream_resources','图体含图片或表单，不能采用原始流清字')
        replacements=validate_replacements(page,page.rect,text_replacements,allow_target_text=True,allow_grouped=True)
        streams=edited[0].get_contents()
        if len(streams)!=1 or not replacements:
            raise FigureError('source_stream_content','须有单一内容流及已登记原字')
        raw=edited.xref_stream(streams[0])
        blocks=re.findall(rb'(?ms)^BT\r?\n.*?^ET\r?\n',raw)
        reader=PdfReader(source);parsed=ContentStream(reader.pages[0].get_contents(),reader)
        if not blocks or len(blocks)!=sum(op==b'BT' for _,op in parsed.operations) or len(blocks)!=sum(op==b'ET' for _,op in parsed.operations):
            raise FigureError('source_stream_content','不能可靠识别全部原始文字对象')
        text_ops={b'BT',b'ET',b'Tf',b'Tm',b'Td',b'TD',b'T*',b'Tj',b'TJ',b"'",b'"',b'Tc',b'Tw',b'Tz',b'TL',b'Ts',b'Tr'}
        safe_state_ops={b'g',b'G',b'rg',b'RG',b'k',b'K',b'gs'}
        inside=False
        for args,op in parsed.operations:
            if op==b'BT':
                if inside:raise FigureError('source_stream_content','不接受嵌套文字对象')
                inside=True
            if inside and (op not in text_ops | safe_state_ops or (op==b'Tr' and int(args[0])>=4)):
                raise FigureError('source_stream_content','文字对象内含绘图、剪裁或图形状态操作')
            if op==b'ET':inside=False
        retained_state_operations=0
        for block in blocks:
            fragment=DecodedStreamObject();fragment.set_data(block)
            content=ContentStream(fragment,reader)
            kept=[(args,op) for args,op in content.operations if op in safe_state_ops]
            retained_state_operations+=len(kept)
            content.operations=kept
            raw=raw.replace(block,content.get_data(),1)
        edited.update_stream(streams[0],raw)
        owners=sorted({font[-1] or edited[0].xref for font in edited[0].get_fonts(full=True)})
        for owner in owners:edited.xref_set_key(owner,'Resources/Font','null')
        data=edited.tobytes(garbage=4,deflate=True,no_new_id=True)
        with fitz.open(stream=data,filetype='pdf') as saved:
            result=saved[0]
            if result.get_fonts(full=True) or result.get_texttrace() or result.get_images(full=True):
                raise FigureError('source_icon_resources','原始流清字仍含文字、字体或图片')
            before=page.get_drawings();after=result.get_drawings()
            consume_paths([path_record(row) for row in before],[path_record(row) for row in after])
            consume_paths([path_record(row) for row in after],[path_record(row) for row in before])
            comparisons=[]
            for zoom in (4,8):
                a=page.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False)
                b=result.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False)
                # Use the original glyph raster, including italic overhang, rather
                # than widening reported span rectangles over nearby circuitry.
                with fitz.open(source) as glyph_document:
                    glyph_stream=ContentStream(reader.pages[0].get_contents(),reader)
                    paint_ops={b'S',b's',b'f',b'F',b'f*',b'B',b'B*',b'b',b'b*'}
                    if any(op in (b'Do',b'sh') for _,op in glyph_stream.operations):
                        raise FigureError('source_stream_glyph_mask','不接受图像或shading参与文字墨迹遮罩')
                    glyph_stream.operations=[([],b'n') if op in paint_ops else (args,op) for args,op in glyph_stream.operations]
                    glyph_document.update_stream(glyph_document[0].get_contents()[0],glyph_stream.get_data())
                    for state_reference in reader.pages[0].get('/Resources',{}).get('/ExtGState',{}).values():
                        for opacity in ('ca','CA'):
                            glyph_document.xref_set_key(state_reference.idnum,opacity,'1')
                    glyphs=glyph_document[0].get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=True)
                mask=Image.frombytes('RGBA',(glyphs.width,glyphs.height),glyphs.samples).getchannel('A').point(lambda value:255 if value else 0).filter(ImageFilter.MaxFilter(3))
                difference=ImageChops.difference(Image.frombytes('RGB',(a.width,a.height),a.samples),Image.frombytes('RGB',(b.width,b.height),b.samples))
                difference.paste((0,0,0),mask=mask)
                registered=ImageDraw.Draw(difference)
                for row in replacements:
                    for box in row.get('source_instances',[row['source_bbox']]):
                        registered.rectangle((math.floor(box[0]*zoom)-1,math.floor(box[1]*zoom)-1,math.ceil(box[2]*zoom)+1,math.ceil(box[3]*zoom)+1),fill=(0,0,0))
                if difference.getbbox() is not None:
                    raise FigureError('source_icon_pixels_changed','原文字实际墨迹之外像素改变，拒绝继续')
                comparisons.append({'dpi':zoom*72,'width':a.width,'height':a.height,'pixel_sha256':hashlib.sha256(a.samples).hexdigest(),'exact':False,'nontext_exact':True})
            receipt={'mode':'source-vector-body','preparation_mode':'source-vector-reletter','text_replacements':replacements,'whitespace_spans_removed':[],'outside_clip_text_removed':[],'unused_font_resource_owners_removed':owners,'source_path':str(source.resolve()),'source_sha256':digest_file(source),'source_page':page_no,'source_clip':list(page.rect),'source_cropbox_position':list(page.cropbox_position),'absolute_mediabox_clip':list(page.cropbox),'prepared_sha256':hashlib.sha256(data).hexdigest(),'font_count':0,'image_count':0,'path_count':len(after),'source_visible_path_count':len(before),'source_path_multiset_preserved':True,'pixels':comparisons,'native_operations':{'raw_text_objects_removed':len(blocks),'nontext_stream_bytes_preserved':retained_state_operations==0,'text_block_graphic_state_operations_preserved':retained_state_operations},'source_text':'','source_text_character_count':0,'complete_icon_extent_proven':False,'extent_review_required':'完整页面源图仍须核对原始裁切范围'}
            return PreparedIcon(data,json.dumps(receipt,ensure_ascii=False))
