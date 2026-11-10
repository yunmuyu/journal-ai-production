"""Normalize a PDF viewport origin without changing displayed artwork.

Public preparation coordinates always refer to the visible page, including
PDFs whose MediaBox/CropBox starts below zero. Never rewrite the source file.
"""
from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO

import pymupdf as fitz

from .common import FigureError


def normalize_page_origin(data: bytes, page_no: int):
    with fitz.open(stream=data,filetype='pdf') as source:
        if isinstance(page_no,bool) or not isinstance(page_no,int) or not 0<=page_no<len(source):return data,None
        page=source[page_no];media=page.mediabox;offset=page.cropbox_position
        if media.x0==0 and media.y0==0 and offset==fitz.Point(0,0):return data,None
        if page.rotation:
            raise FigureError('source_origin_rotation','非零原点页须先独立核对旋转，不能隐式变换')
        if page.annot_xrefs():
            raise FigureError('source_origin_annotations','带批注或表单的非零原点源页须独立处理')
        from pypdf import PdfReader,PdfWriter,Transformation
        from pypdf.generic import RectangleObject
        writer=PdfWriter(clone_from=PdfReader(BytesIO(data)));target=writer.pages[page_no]
        crop=target.cropbox
        translation=[-float(crop.left),-float(crop.bottom)]
        width,height=float(crop.width),float(crop.height)
        target.add_transformation(Transformation().translate(*translation))
        target.mediabox=RectangleObject([0,0,width,height])
        target.cropbox=RectangleObject([0,0,width,height])
        buffer=BytesIO();writer.write(buffer);normalized=buffer.getvalue()
        from .source_icons import path_record,consume_paths
        from .source_image_paints import close_values
        with fitz.open(stream=normalized,filetype='pdf') as saved:
            result=saved[page_no];normalized_rect=list(result.rect)
            if not close_values(list(page.rect),list(result.rect)) or result.cropbox_position!=fitz.Point(0,0):
                raise FigureError('source_origin_changed','原点归一化改变可见页尺寸')
            before=[path_record(row) for row in page.get_drawings()]
            after=[path_record(row) for row in result.get_drawings()]
            consume_paths(before,after);consume_paths(after,before)
            # Span text, direction and coordinates must survive unchanged, not
            # merely the extracted string or an OCR approximation.
            text=lambda p:[line for block in p.get_text('dict')['blocks'] if block['type']==0 for line in block['lines']]
            if not close_values(text(page),text(result)):
                raise FigureError('source_origin_changed','原点归一化改变原生文字或坐标')
            if page.get_image_info():
                from .source_mixed_body import image_records,consume_images
                images=image_records(source,page);actual=image_records(saved,result)
                consume_images(images,actual);consume_images(actual,images)
            for zoom in (1,2):
                a=page.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False)
                b=result.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False)
                if (a.width,a.height,a.samples)!=(b.width,b.height,b.samples):
                    raise FigureError('source_origin_changed','原点归一化改变可见源像素')
        proof={'source_mediabox':list(media),'source_cropbox':list(page.cropbox),
               'source_cropbox_position':list(offset),'pdf_translation_pt':translation,
               'normalized_page_rect':normalized_rect,'local_coordinates_preserved':True,
               'path_multiset_preserved':True,'native_text_preserved':True,
               'displayed_pixels_exact_dpi':[72,144],'source_file_unchanged':True}
        return normalized,proof


@contextmanager
def preparation_source(source,page_no):
    data,proof=normalize_page_origin(source.read_bytes(),page_no)
    with fitz.open(stream=data,filetype='pdf') as doc:yield doc,proof
