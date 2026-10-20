from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
from pathlib import Path
import math

import pymupdf as fitz

from .common import FigureError,digest_file,digest_json
from .source_icons import consume_paths,path_record


def rounded_rectangle(drawing) -> bool:
    items=drawing['items'];box=drawing['rect'];eps=.0001
    if drawing['type']!='s' or [row[0] for row in items] not in (['c','l']*4,['l','c']*4):return False
    for row,next_row in zip(items,items[1:]+items[:1]):
        if abs(row[-1]-next_row[1])>eps:return False
        if row[0]=='l':
            a,b=row[1:]
            if not ((abs(a.x-b.x)<eps and min(abs(a.x-box.x0),abs(a.x-box.x1))<eps) or (abs(a.y-b.y)<eps and min(abs(a.y-box.y0),abs(a.y-box.y1))<eps)):return False
        elif any(not (box.x0-eps<=p.x<=box.x1+eps and box.y0-eps<=p.y<=box.y1+eps) for p in row[1:]):return False
    return True


def remove_registered_paints(source:Path,page_no:int,outline_rows=None,shape_rows=None):
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import ContentStream
    base={'source_sha256','source_page','source_path_index','source_path_sha256','source_paint_operation_index'}
    schemas={'outline':base|{'source_text','target_text_id'},'shape':base|{'source_paint_operator','source_bbox','target_node_id','target_text_id','horizontal_inset_pt','purpose'}}
    tagged=[]
    for kind,rows in (('outline',outline_rows),('shape',shape_rows)):
        if rows is None:continue
        if not isinstance(rows,list):raise FigureError('source_'+kind+'_registration','原paint登记须为列表')
        tagged.extend((kind,row) for row in rows)
    mapping_prefix='source_shape' if shape_rows else 'source_outline'
    reader=PdfReader(source);writer=PdfWriter();writer.add_page(reader.pages[page_no]);stream=ContentStream(writer.pages[0].get_contents(),writer)
    counts={b'S':1,b's':1,b'f':1,b'F':1,b'f*':1,b'B':2,b'B*':2,b'b':2,b'b*':2}
    with fitz.open(source) as doc:
        page=doc[page_no];drawings=page.get_drawings()
        if page.get_xobjects():raise FigureError(mapping_prefix+'_form','不猜测Form内部paint索引')
        events=[i for i,row in enumerate(page.get_bboxlog()) if row[0] in ('fill-path','stroke-path','fill-shade')]
        mapping={};cursor=0
        for position,(args,op) in enumerate(stream.operations):
            if op==b'sh':raise FigureError(mapping_prefix+'_paint','不猜测直接shading的paint映射')
            if op not in counts:continue
            group=events[cursor:cursor+counts[op]];cursor+=counts[op]
            if len(group)!=counts[op]:raise FigureError(mapping_prefix+'_paint','源paint与实际绘制序列不一致')
            for seqno in group:mapping[seqno]=(position,op,group)
        if cursor!=len(events):raise FigureError(mapping_prefix+'_paint','源paint映射不完整')
        removed=set();positions=set();targets=set();node_targets=set();bound={'outline':[],'shape':[]}
        for kind,row in tagged:
            prefix='source_'+kind
            if not isinstance(row,dict) or set(row)!=schemas[kind]:raise FigureError(prefix+'_registration','原paint登记字段不完整或含未知字段')
            if row['source_sha256']!=digest_file(source) or row['source_page']!=page_no or isinstance(row['source_page'],bool) or not isinstance(row['source_page'],int):raise FigureError(prefix+'_source','源hash或页不匹配')
            index=row['source_path_index'];position=row['source_paint_operation_index']
            if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in (index,position)) or index>=len(drawings):raise FigureError(prefix+'_index','原路径或paint索引无效')
            drawing=drawings[index]
            if row['source_path_sha256']!=digest_json(asdict(path_record(drawing))):raise FigureError(prefix+'_path_hash','原路径hash不匹配')
            actual_position,op,group=mapping[drawing['seqno']]
            if position!=actual_position or len(group)!=1 or op not in ((b'f',b'F',b'f*') if kind=='outline' else (b'S',)):raise FigureError(prefix+'_paint','只能移除完整登记的独立原paint')
            if not isinstance(row['target_text_id'],str) or not row['target_text_id']:raise FigureError(prefix+'_text','须明确目标文字ID')
            if index in removed or position in positions or row['target_text_id'] in targets:raise FigureError(prefix+'_duplicate','原paint或目标重复登记')
            if kind=='outline':
                if not isinstance(row['source_text'],str) or not row['source_text'].strip():raise FigureError(prefix+'_text','须明确经源图核对的原文')
            else:
                bbox=row['source_bbox'];inset=row['horizontal_inset_pt'];node=row['target_node_id']
                if row['source_paint_operator']!='S' or not rounded_rectangle(drawing):raise FigureError(prefix+'_geometry','仅接受真实独立描边圆角矩形')
                if not isinstance(bbox,list) or len(bbox)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in bbox) or any(abs(a-b)>.01 for a,b in zip(bbox,drawing['rect'])):raise FigureError(prefix+'_bbox','源bbox与真实圆角框不匹配')
                if isinstance(inset,bool) or not isinstance(inset,(int,float)) or not math.isfinite(inset) or abs(inset-.15)>1e-9 or row['purpose']!='source-bound-narrow-panel':raise FigureError(prefix+'_contract','仅接受左右各内收0.15pt的源绑定窄竖panel')
                if not isinstance(node,str) or not node or node in node_targets:raise FigureError(prefix+'_duplicate','目标矩形ID无效或重复')
                node_targets.add(node)
            removed.add(index);positions.add(position);targets.add(row['target_text_id'])
            bound[kind].append(dict(row,source_bbox=list(drawing['rect']),source_primitive_count=len(drawing['items']),source_paint_operator=op.decode(),source_stroke_width=drawing['width']))
        expected=[path_record(row) for i,row in enumerate(drawings) if i not in removed]
    stream.operations=[([],b'n') if i in positions else (args,op) for i,(args,op) in enumerate(stream.operations)]
    writer.pages[0].replace_contents(stream);buffer=BytesIO();writer.write(buffer);data=buffer.getvalue()
    with fitz.open(stream=data,filetype='pdf') as selected:
        actual=[path_record(row) for row in selected[0].get_drawings()]
        consume_paths(expected,actual);consume_paths(actual,expected)
    return data,bound['outline'],bound['shape'],removed
