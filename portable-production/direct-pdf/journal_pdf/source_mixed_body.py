from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pymupdf as fitz

from .common import FigureError,digest_file
from .source_icon_text import compare_pixels,validate_replacements
from .source_icons import PreparedIcon,consume_paths,path_record


def image_records(doc,page) -> list[dict]:
    records=[]
    for info in page.get_image_info(xrefs=True):
        xref=info['xref']
        if not xref:raise FigureError('source_mixed_inline_image','未验证内联图像')
        values={key:doc.xref_get_key(xref,key) for key in ('Width','Height','BitsPerComponent','ColorSpace','Decode','Interpolate','SMask')}
        width=int(values['Width'][1]);height=int(values['Height'][1])
        if values['BitsPerComponent']!=('int','8') or values['ColorSpace']!=('name','/DeviceRGB') or values['Decode'][0]!='null':
            raise FigureError('source_mixed_image_format','仅验证原8bit默认Decode DeviceRGB图像')
        rgb=doc.xref_stream(xref)
        if len(rgb)!=width*height*3:raise FigureError('source_mixed_image_decode','RGB解码像素尺寸不匹配')
        mask_ref=values['SMask'];mask=int(mask_ref[1].split()[0]) if mask_ref[0]=='xref' else 0
        alpha=doc.xref_stream(mask) if mask else b''
        matte=doc.xref_get_key(mask,'Matte') if mask else ('null','null')
        neutral_matte=matte[0]=='null' or (matte[0]=='array' and len(matte[1].strip('[]').split())==3 and len(set(matte[1].strip('[]').split()))==1 and 0<=float(matte[1].strip('[]').split()[0])<=1)
        mask_properties={key:doc.xref_get_key(mask,key) for key in ('Width','Height','ColorSpace','BitsPerComponent','Decode','Interpolate','Matte')} if mask else {}
        if mask and (doc.xref_get_key(mask,'Width')!=('int',str(width)) or doc.xref_get_key(mask,'Height')!=('int',str(height)) or not neutral_matte or doc.xref_get_key(mask,'ColorSpace')!=('name','/DeviceGray') or doc.xref_get_key(mask,'BitsPerComponent')!=('int','8') or len(alpha)!=width*height or doc.xref_get_key(mask,'Decode')[0]!='null'):
            raise FigureError('source_mixed_alpha','仅验证同像素尺寸8bit原SMask')
        records.append({'xref':xref,'width':width,'height':height,'bbox':list(info['bbox']),'transform':list(info['transform']),
                        'decoded_rgb_sha256':hashlib.sha256(rgb).hexdigest(),'smask_sha256':hashlib.sha256(alpha).hexdigest() if mask else None,
                        'smask_properties':mask_properties,'interpolate':values['Interpolate'],'bits_per_component':8,'colorspace':'DeviceRGB'})
    return records


def consume_images(expected:list[dict],actual:list[dict]) -> set[int]:
    used=set()
    exact=('width','height','decoded_rgb_sha256','smask_sha256','smask_properties','interpolate','bits_per_component','colorspace')
    for source in expected:
        index=next((i for i,target in enumerate(actual) if i not in used and all(source[key]==target[key] for key in exact)
                    and all(abs(a-b)<.0001 for key in ('bbox','transform') for a,b in zip(source[key],target[key],strict=True))),None)
        if index is None:raise FigureError('source_mixed_image_changed','原图像实例位置、矩阵、像素或SMask改变')
        used.add(index)
    return used


def prepare_mixed_body(source:Path,page_no:int,clip:list[float],*,text_replacements=None,outline_text_replacements=None,source_shape_replacements=None) -> PreparedIcon:
    with fitz.open(source) as original,fitz.open() as native:
        if isinstance(page_no,bool) or not isinstance(page_no,int) or not 0<=page_no<len(original):
            raise FigureError('source_mixed_page','混合图体须指定真实页')
        source_page=original[page_no]
        if list(source_page.rect)!=clip or source_page.rotation or source_page.cropbox_position!=fitz.Point(0,0):
            raise FigureError('source_mixed_full_page','当前混合能力仅验证未旋转零原点完整源页，不裁断原图像')
        replacements=validate_replacements(source_page,source_page.rect,text_replacements,allow_target_text=True)
        whitespace=[{'source_text':s['text'],'source_bbox':list(s['bbox'])} for b in source_page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans'] if s['text'] and not s['text'].strip()]
        source_images=image_records(original,source_page)
        if not source_images:raise FigureError('source_mixed_no_images','混合模式须包含真实原图像实例')
        outline_bound=[];shape_bound=[];removed=set()
        if outline_text_replacements or source_shape_replacements:
            from .source_registered_paints import remove_registered_paints
            selected,outline_bound,shape_bound,removed=remove_registered_paints(source,page_no,outline_text_replacements,source_shape_replacements)
            with fitz.open(stream=selected,filetype='pdf') as prepared:native.insert_pdf(prepared)
        else:native.insert_pdf(original,from_page=page_no,to_page=page_no)
        if set(row['target_text_id'] for row in replacements)&set(row['target_text_id'] for row in outline_bound):raise FigureError('source_outline_duplicate','原生字和转曲字目标不可重复')
        for shape in shape_bound:
            word=next((row for row in replacements if row['target_text_id']==shape['target_text_id']),None)
            if word is None or not fitz.Rect(shape['source_bbox']).contains(fitz.Rect(word['source_bbox'])):raise FigureError('source_shape_text','圆角框须互绑其内部已登记真实原字')
            shape['source_text']=word.get('target_text',word['source_text'])
        shape_masks=[]
        for shape in shape_bound:
            box=fitz.Rect(shape['source_bbox']);margin=shape['source_stroke_width']/2
            shape_masks.append({'source_bbox':[box.x0-margin,box.y0-margin,box.x1+margin,box.y1+margin]})
        source_paths=[path_record(row) for index,row in enumerate(source_page.get_drawings()) if index not in removed]
        page=native[0]
        for row in replacements+whitespace:page.add_redact_annot(fitz.Rect(row['source_bbox']),fill=False,cross_out=False)
        if replacements or whitespace:page.apply_redactions(images=0,graphics=0,text=0)
        page.clean_contents(sanitize=1)
        raw=native.tobytes(garbage=4,deflate=True,no_new_id=True)
        with fitz.open(stream=raw,filetype='pdf') as clean:
            page=clean[0]
            if page.get_fonts(full=True) or page.get_texttrace():raise FigureError('source_mixed_text_resources','清字后仍含原文字或字体')
            records=[path_record(row) for row in page.get_drawings()]
            consume_paths(source_paths,records);consume_paths(records,source_paths)
            clean_images=image_records(clean,page);consume_images(source_images,clean_images);consume_images(clean_images,source_images)
            for zoom in (4,8):
                compare_pixels(source_page.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False),page.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False),page.rect,replacements+outline_bound+shape_masks,zoom)
            image_proof=[]
            for xref in dict.fromkeys(row['xref'] for row in clean_images):
                pixels=clean.xref_stream(xref)
                gray=bytes(component for i in range(0,len(pixels),3) for component in [round(.299*pixels[i]+.587*pixels[i+1]+.114*pixels[i+2])]*3)
                clean.update_stream(xref,gray,compress=True)
                image_proof.append({'native_resource_xref':xref,'original_rgb_sha256':hashlib.sha256(pixels).hexdigest(),'gray_rgb_sha256':hashlib.sha256(gray).hexdigest(),'formula':'round(.299 R+.587 G+.114 B), replicated RGB','dimensions_unchanged':True,'smask_unchanged':True})
            data=clean.tobytes(garbage=4,deflate=True,no_new_id=True)
            with fitz.open(stream=data,filetype='pdf') as gray_saved:
                gray_images=image_records(gray_saved,gray_saved[0])
            for before,after in zip(clean_images,gray_images,strict=True):
                if before['smask_sha256']!=after['smask_sha256']:raise FigureError('source_mixed_alpha','灰度不得改变原SMask')
            data=clean.tobytes(garbage=4,deflate=True,no_new_id=True)
    from .source_native_gray import native_gray
    data,color_proof=native_gray(data,allow_image_xobjects=True)
    with fitz.open(stream=data,filetype='pdf') as final:
        page=final[0];actual_images=image_records(final,page)
        consume_images(gray_images,actual_images);consume_images(actual_images,gray_images)
        def protected(row):
            style=json.loads(row.style);style.pop('color',None);style.pop('fill',None)
            return replace(row,style=json.dumps(style,sort_keys=True))
        actual_paths=[path_record(row) for row in page.get_drawings()]
        consume_paths([protected(row) for row in source_paths],[protected(row) for row in actual_paths])
        consume_paths([protected(row) for row in actual_paths],[protected(row) for row in source_paths])
        if page.get_fonts(full=True) or page.get_texttrace():raise FigureError('source_mixed_text_resources','最终混合图体仍含原文字或字体')
        receipt={'mode':'source-mixed-body','source_path':str(source.resolve()),'source_sha256':digest_file(source),'source_page':page_no,'source_clip':clip,
                 'native_text_replacements':replacements,'outline_text_replacements':outline_text_replacements or [],'outline_text_bindings':outline_bound,'text_replacements':replacements+[{'source_text':row['source_text'],'source_bbox':row['source_bbox'],'target_text_id':row['target_text_id']} for row in outline_bound],'source_original_path_count':len(source_paths)+len(removed),'outline_removed_path_count':len(outline_bound),'source_shape_replacements':source_shape_replacements or [],'source_shape_bindings':shape_bound,'source_shape_removed_path_count':len(shape_bound),'whitespace_spans_removed':whitespace,'prepared_sha256':hashlib.sha256(data).hexdigest(),'path_count':len(actual_paths),
                 'image_resource_count':len(image_proof),'image_instance_count':len(actual_images),'original_smask_preserved':True,'original_image_placements_preserved':True,
                 'source_image_instances':source_images,'prepared_image_instances':actual_images,'image_grayscale':image_proof,'vector_color_conversion':color_proof,
                 'path_geometry_replayed':False,'noncolor_geometry_and_style_exact':True,'nontext_pixels_exact_before_gray_dpi':[288,576],
                 'source_text':'','source_text_character_count':0,'font_count':0,'source_text_scope':'native_pdf_text_only','embedded_image_text_not_removed':True,'embedded_image_semantic_review_required':True}
    return PreparedIcon(data,json.dumps(receipt,ensure_ascii=False))
