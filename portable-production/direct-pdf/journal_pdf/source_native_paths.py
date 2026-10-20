from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict,replace
from io import BytesIO
from pathlib import Path

import pymupdf as fitz
from PIL import Image

from .common import FigureError,digest_file,digest_json
from .source_icons import PreparedIcon,consume_paths,path_record


def prepare_native_glyph(source: Path,page_no: int,clip: list[float],source_path_indices: list[int],*,gray: bool=True,text_replacements=None) -> PreparedIcon:
    try:
        import pypdf
        from pypdf import PdfReader,PdfWriter
        from pypdf.generic import ContentStream
    except ImportError as error:
        raise FigureError('source_native_parser_unavailable','原生paint选择须显式可用的pypdf解析器') from error

    if not isinstance(source_path_indices,list) or not source_path_indices or any(isinstance(i,bool) or not isinstance(i,int) or i<0 for i in source_path_indices) or len(set(source_path_indices))!=len(source_path_indices):
        raise FigureError('source_glyph_indices','原glyph须明确不重复的非负路径索引')
    if not isinstance(clip,list) or len(clip)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in clip):
        raise FigureError('source_glyph_clip','原glyph须指定四个有限裁切坐标')
    with fitz.open(source) as original:
        if isinstance(page_no,bool) or not isinstance(page_no,int) or not 0<=page_no<len(original) or original[page_no].rotation or not original[page_no].rect.contains(fitz.Rect(clip)):
            raise FigureError('source_glyph_page','仅验证有效页内未旋转的源glyph')
        source_drawings=original[page_no].get_drawings()
        if max(source_path_indices)>=len(source_drawings):
            raise FigureError('source_glyph_indices','原glyph路径索引越界')
        from .source_icon_text import validate_replacements
        replacements=validate_replacements(original[page_no],fitz.Rect(clip),text_replacements,allow_target_text=True,allow_intersecting_text=True)
        selected=[source_drawings[i] for i in source_path_indices]
        boxes=[]
        for drawing in selected:
            rect=drawing['rect'];margin=(drawing.get('width') or 0)/2
            boxes.append([rect.x0-margin,rect.y0-margin,rect.x1+margin,rect.y1+margin])
        extent=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
        if not fitz.Rect(clip).contains(fitz.Rect(extent)):
            raise FigureError('source_glyph_extent','裁区截断所选原glyph或原描边',extent=extent)
        expected=[path_record(row) for row in selected]
        original[page_no].set_cropbox(fitz.Rect(clip))
        cropped_expected=[path_record(original[page_no].get_drawings()[i]) for i in source_path_indices]
    reader=PdfReader(source);writer=PdfWriter();writer.add_page(reader.pages[page_no]);page=writer.pages[0]
    stream=ContentStream(page.get_contents(),writer)
    base=[];base_positions=[];text=False
    for original_position,(args,op) in enumerate(stream.operations):
        if op==b'BT':
            if text:raise FigureError('source_glyph_content','不接受嵌套文字对象')
            text=True
        elif op==b'ET':text=False
        elif not text and op!=b'Do':
            base.append((args,op));base_positions.append(original_position)
    if text:raise FigureError('source_glyph_content','原文字对象未闭合')
    stream.operations=base;page.replace_contents(stream)
    buffer=BytesIO();writer.write(buffer)
    with fitz.open(stream=buffer.getvalue(),filetype='pdf') as base_document:
        base_drawings=base_document[0].get_drawings()
        retained=consume_paths(expected,[path_record(row) for row in base_drawings])
        allowed=set()
        for index in retained:
            row=base_drawings[index];allowed.add(row['seqno'])
            if row['type']=='fs':allowed.add(row['seqno']+1)
        events=[(index,row[0]) for index,row in enumerate(base_document[0].get_bboxlog()) if row[0] in ('fill-path','stroke-path','fill-shade')]
    operators={b'S':1,b's':1,b'f':1,b'F':1,b'f*':1,b'B':2,b'B*':2,b'b':2,b'b*':2}
    consumed=0;filtered=[];paint_receipt=[]
    for position,(args,op) in enumerate(base):
        if op==b'sh':raise FigureError('source_glyph_content','未归属原路径的直接shading不进入glyph选择')
        if op not in operators:
            filtered.append((args,op));continue
        count=operators[op];group=events[consumed:consumed+count];consumed+=count
        if len(group)!=count:
            raise FigureError('source_glyph_paint_map','源paint操作与真实绘制序列不匹配')
        keep=[index in allowed for index,kind in group]
        if any(keep) and not all(keep):
            raise FigureError('source_glyph_paint_map','不拆分原复合paint操作')
        filtered.append((args,op) if all(keep) else ([],b'n'))
        paint_receipt.append({'source_operation_index':base_positions[position],'selection_base_operation_index':position,'operator':op.decode('ascii'),'selection_base_seqnos':[index for index,kind in group],'retained':all(keep)})
    if consumed!=len(events):
        raise FigureError('source_glyph_paint_map','有未映射的源绘制操作')
    stream.operations=filtered;page.replace_contents(stream)
    buffer=BytesIO();writer.write(buffer)
    with fitz.open(stream=buffer.getvalue(),filetype='pdf') as selected_document:
        selected_page=selected_document[0];selected_page.clean_contents(sanitize=1)
        records=[path_record(row) for row in selected_page.get_drawings()]
        consume_paths(expected,records);consume_paths(records,expected)
        if selected_page.get_fonts(full=True) or selected_page.get_texttrace() or selected_page.get_images(full=True):
            raise FigureError('source_glyph_resources','纯矢量glyph仍含原字体、字或图片')
        pix=selected_page.get_pixmap(dpi=288,alpha=True)
        ink=Image.frombytes('RGBA',(pix.width,pix.height),pix.samples).getchannel('A').getbbox()
        full_ink_extent=[v/4 for v in ink] if ink else None
        if full_ink_extent is None or not fitz.Rect(clip).contains(fitz.Rect(full_ink_extent)):
            raise FigureError('source_glyph_ink_extent','裁区未完整包含原glyph实际墨迹',actual_ink_extent_288dpi=full_ink_extent)
        selected_document.set_metadata({})
        native_data=selected_document.tobytes(garbage=4,deflate=True,no_new_id=True)
    color_proof=[];data=native_data
    if gray:
        from .source_native_gray import native_gray
        data,color_proof=native_gray(data)
    with fitz.open(stream=data,filetype='pdf') as final:
        final[0].set_cropbox(fitz.Rect(clip))
        data=final.tobytes(garbage=4,deflate=True,no_new_id=True)
    with fitz.open(stream=data,filetype='pdf') as final:
        actual=[path_record(row) for row in final[0].get_drawings()]
        def protected(record):
            style=json.loads(record.style);style.pop('color',None);style.pop('fill',None)
            return replace(record,style=json.dumps(style,sort_keys=True))
        compare=protected if gray else lambda record:record
        consume_paths([compare(row) for row in cropped_expected],[compare(row) for row in actual])
        consume_paths([compare(row) for row in actual],[compare(row) for row in cropped_expected])
        if final[0].get_fonts(full=True) or final[0].get_images(full=True) or final[0].get_texttrace():
            raise FigureError('source_glyph_resources','最终glyph仍有非图体资源')
        receipt={'mode':'source-vector-glyph','text_replacements':replacements,'parser_version':pypdf.__version__,'source_full_ink_extent_288dpi':full_ink_extent,'source_path':str(source.resolve()),'source_sha256':digest_file(source),'source_page':page_no,'source_clip':clip,'selected_source_path_indices':source_path_indices,'selected_source_path_records':[asdict(row) for row in expected],'source_path_instances_preserved':True,'original_native_paint_retained':True,'path_geometry_replayed':False,'paint_selection':paint_receipt,'native_selection_sha256':hashlib.sha256(native_data).hexdigest(),'grayscale':gray,'color_conversion':color_proof,'prepared_sha256':hashlib.sha256(data).hexdigest(),'path_count':len(actual),'font_count':0,'image_count':0,'source_text':'','source_text_character_count':0,'complete_glyph_extent':extent,'complete_glyph_extent_proven':True,'noncolor_geometry_and_style_exact':True,'native_operation_map_sha256':digest_json(paint_receipt)}
    return PreparedIcon(data,json.dumps(receipt,ensure_ascii=False))
