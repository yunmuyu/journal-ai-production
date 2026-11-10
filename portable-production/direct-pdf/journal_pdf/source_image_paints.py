"""Resolve image *paint instances*, never MuPDF's pixel-digest xref lookup.

Different XObjects may have identical color bytes but different dimensions or
SMasks. get_image_info(xrefs=True) cannot distinguish those resources reliably.
Walk the real Do operators, retaining Form transforms and clipping paths.
"""
from __future__ import annotations

from io import BytesIO

import pymupdf as fitz
from pypdf import PdfReader
from pypdf.generic import ContentStream

from .common import FigureError


def image_paints(doc, page) -> list[dict]:
    reader=PdfReader(BytesIO(doc.tobytes(no_new_id=True)))
    root=reader.pages[page.number]
    paints=[]
    to_page=page.transformation_matrix

    def walk(owner, resources, matrix, clips, ancestors=()):
        if len(ancestors)>32:
            raise FigureError('source_mixed_image_form','图像Form嵌套超过安全上限')
        stream=ContentStream(owner if owner.get('/Subtype')=='/Form' else owner.get_contents(),reader)
        stack=[];path=[];current=None;start=None;pending=None

        def point(x,y):
            return list(fitz.Point(float(x),float(y))*matrix*to_page)

        def rectangle(values):
            x,y,w,h=map(float,values)
            return [('m',point(x,y)),('l',point(x+w,y)),('l',point(x+w,y+h)),('l',point(x,y+h)),('h',)]

        def clipped(values, even_odd=False):
            item={'even_odd':even_odd,'path':values}
            return clips if item in clips else clips+[item]

        for args,op in stream.operations:
            if op==b'q':stack.append((matrix,clips))
            elif op==b'Q':
                if not stack:raise FigureError('source_mixed_image_state','图像图形状态栈不平衡')
                matrix,clips=stack.pop()
            elif op==b'cm':matrix=fitz.Matrix(*map(float,args))*matrix
            elif op==b'm':
                current=point(*args);start=current;path.append(('m',current))
            elif op==b'l':
                current=point(*args);path.append(('l',current))
            elif op==b'c':
                current=point(*args[4:]);path.append(('c',point(*args[:2]),point(*args[2:4]),current))
            elif op==b'v':
                if current is None:raise FigureError('source_mixed_image_clip','剪裁曲线缺失起点')
                end=point(*args[2:]);path.append(('c',current,point(*args[:2]),end));current=end
            elif op==b'y':
                end=point(*args[2:]);path.append(('c',point(*args[:2]),end,end));current=end
            elif op==b'h':path.append(('h',));current=start
            elif op==b're':
                path.extend(rectangle(args));current=point(*args[:2]);start=current
            elif op in (b'W',b'W*'):pending=op==b'W*'
            elif op in (b'n',b'S',b's',b'f',b'F',b'f*',b'B',b'B*',b'b',b'b*'):
                if pending is not None:
                    clips=clipped(path,pending);pending=None
                path=[];current=None;start=None
            elif op==b'Do':
                reference=resources.get('/XObject',{}).get(args[0])
                if reference is None:raise FigureError('source_mixed_image_paint','图像资源引用缺失')
                child=reference.get_object();xref=getattr(reference,'idnum',0)
                if child.get('/Subtype')=='/Image':
                    transform=fitz.Matrix(1,0,0,-1,0,1)*matrix*to_page
                    paints.append({'xref':xref,'transform':list(transform),'clip_paths':clips})
                elif child.get('/Subtype')=='/Form':
                    if xref in ancestors:raise FigureError('source_mixed_image_form','不接受循环Form资源')
                    child_matrix=fitz.Matrix(*map(float,child.get('/Matrix',[1,0,0,1,0,0])))*matrix
                    # A Form's BBox clips its content, independently of W/W*.
                    old=matrix;matrix=child_matrix
                    box=child.get('/BBox')
                    child_clips=clips
                    if box is not None:
                        x0,y0,x1,y1=map(float,box)
                        child_clips=clipped(rectangle([x0,y0,x1-x0,y1-y0]))
                    matrix=old
                    walk(child,child.get('/Resources',resources),child_matrix,child_clips,ancestors+(xref,))
                else:raise FigureError('source_mixed_image_form','未验证的XObject类型')
            elif op==b'INLINE IMAGE':raise FigureError('source_mixed_inline_image','未验证内联图像')
            elif op==b'Tr' and int(args[0])>=4:
                raise FigureError('source_mixed_image_clip','文字剪裁须独立验证，不能当作普通换字')
        if stack:raise FigureError('source_mixed_image_state','图像图形状态栈不平衡')

    walk(root,root.get('/Resources',{}),fitz.Matrix(1,1),[])
    return paints


def close_values(a,b, tolerance=.0001):
    if isinstance(a,bool) or isinstance(b,bool):return type(a) is type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        return abs(a-b)<tolerance
    if isinstance(a,dict) and isinstance(b,dict):
        return a.keys()==b.keys() and all(close_values(a[k],b[k],tolerance) for k in a)
    if isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)):
        return len(a)==len(b) and all(close_values(x,y,tolerance) for x,y in zip(a,b))
    return a==b


def paint_records(page, images, *, ignore_color=False):
    """Ordered non-text paint events, including each actual image's clip state."""
    from dataclasses import asdict
    from .source_icons import path_record
    paths={}
    for drawing in page.get_drawings():
        value=asdict(path_record(drawing))
        if ignore_color:
            import json
            style=json.loads(value['style']);style.pop('color',None);style.pop('fill',None)
            value['style']=json.dumps(style,sort_keys=True)
        paths[drawing['seqno']]=value
        if drawing['type']=='fs':paths[drawing['seqno']+1]=value
    records=[];cursor=0
    for index,(kind,bounds) in enumerate(page.get_bboxlog()):
        if kind.endswith('text'):continue
        value={'kind':kind,'bbox':list(bounds)}
        if kind=='fill-image':
            if cursor>=len(images) or not close_values(images[cursor]['bbox'],list(bounds),.001):
                raise FigureError('source_mixed_image_paint','图像绘制顺序与真实Do不一致')
            value['image']={key:item for key,item in images[cursor].items() if key!='xref'}
            cursor+=1
        elif kind in ('fill-path','stroke-path'):
            if index not in paths:raise FigureError('source_mixed_paint_order','实际路径未绑定绘制顺序')
            value['path']=paths[index]
        records.append(value)
    if cursor!=len(images):raise FigureError('source_mixed_image_paint','图像绘制顺序不完整')
    return records


def consume_paints(expected, actual, *, exact=False):
    """Keep source paint order; new scene paints may exist between source events."""
    cursor=0
    for source in expected:
        while cursor<len(actual) and not close_values(source,actual[cursor]):cursor+=1
        if cursor==len(actual):raise FigureError('source_mixed_paint_order','原矢量与图像绘制顺序或剪裁改变')
        cursor+=1
    if exact and len(expected)!=len(actual):
        raise FigureError('source_mixed_paint_order','原矢量与图像绘制操作数量改变')
