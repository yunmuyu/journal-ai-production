"""Place source-bound chart annotations only in measured, unoccupied space."""
import math
import pymupdf as fitz
from .common import FigureError
from .fonts import position_text
from .source_icons import prepare_icon


def fail(message):
    raise FigureError('chart_vector_annotation',message)


def content(value):
    if isinstance(value,str):return value
    if isinstance(value,list) and all(isinstance(part,dict) and isinstance(part.get('text'),str) for part in value):
        return ''.join(part['text'] for part in value)
    fail('标注文字格式无效')


def place_annotations(rows,texts,body,path,reg,size,clip,target,origin,xend,yend):
    scale=(target[2]-target[0])/(clip[2]-clip[0])
    bindings={r['target_text_id']:r for r in body['text_replacements']}
    prepared=prepare_icon(path,body.get('page',0),clip,text_replacements=body['text_replacements'],source_vector_body=True)
    annotation_ids={part['id'] for row in rows for part in row['parts']}
    occupied=[];evidence=[]
    for ident,item in texts.items():
        if ident in annotation_ids:continue
        if isinstance(item.get('x'),(int,float)) and isinstance(item.get('y'),(int,float)):
            measurement=reg.measure(item['text'],size)
            occupied.append(position_text(measurement,item['x'],item['y'],align=item.get('align','center'),rotation=item.get('rotation',0))['bbox'])
    with fitz.open(stream=prepared.data,filetype='pdf') as doc:
        page=doc[0]
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('parts'),list) or not row['parts'] or not str(row.get('evidence','')).strip():fail('标注须提供原文片段和图源依据')
            parts=row['parts'];anchors=[];metrics=[]
            for part in parts:
                ident=part.get('id');replacement=bindings.get(ident,{});source=replacement.get('source_text');box=replacement.get('source_bbox')
                if not isinstance(source,str) or not source.strip() or content(texts[ident]['text']).strip()!=source.strip():fail('标注文字与原图不一致')
                if not isinstance(box,list) or len(box)!=4 or any(not isinstance(n,(int,float)) or isinstance(n,bool) or not math.isfinite(n) for n in box):fail('标注缺少原文坐标')
                shift=part.get('offset_y_pt',0)
                if isinstance(shift,bool) or not isinstance(shift,(int,float)) or not math.isfinite(shift) or abs(shift)>size:fail('标注上下标偏移无效')
                anchors.append(box);metrics.append(reg.measure(texts[ident]['text'],size))
            # Anchor to the original text group. Alternatives are small displacements,
            # and the underlying vector body is measured after source text removal.
            ax=(min(b[0] for b in anchors)+max(b[2] for b in anchors))/2
            ay=(min(b[1] for b in anchors)+max(b[3] for b in anchors))/2
            width=sum(m['width'] for m in metrics)
            chosen=None
            for dx,dy in [(0,0),(0,-8),(0,8),(8,0),(-8,0),(8,-8),(-8,-8),(8,8),(-8,8)]:
                cx=target[0]+(ax-clip[0])*scale+dx;cy=target[1]+(ay-clip[1])*scale+dy
                cursor=cx-width/2;placements=[]
                for part,m in zip(parts,metrics):
                    x=cursor+m['width']/2;y=cy+part.get('offset_y_pt',0);box=position_text(m,x,y)['bbox'];placements.append((part['id'],x,y,box));cursor+=m['width']
                b=[min(p[3][0] for p in placements),min(p[3][1] for p in placements),max(p[3][2] for p in placements),max(p[3][3] for p in placements)]
                frame=[target[0]+(origin[0]-clip[0])*scale,target[1]+(yend[1]-clip[1])*scale,target[0]+(xend[0]-clip[0])*scale,target[1]+(origin[1]-clip[1])*scale]
                margin=1.5
                if b[0]-margin<frame[0] or b[1]-margin<frame[1] or b[2]+margin>frame[2] or b[3]+margin>frame[3]:continue
                if any(not (b[2]+margin<=o[0] or o[2]+margin<=b[0] or b[3]+margin<=o[1] or o[3]+margin<=b[1]) for o in occupied):continue
                source_box=fitz.Rect((b[0]-margin-target[0])/scale,(b[1]-margin-target[1])/scale,(b[2]+margin-target[0])/scale,(b[3]+margin-target[1])/scale)
                pix=page.get_pixmap(matrix=fitz.Matrix(4*scale,4*scale),clip=source_box,colorspace=fitz.csGRAY,alpha=False)
                if not pix.samples or min(pix.samples)<245:continue
                chosen=(placements,b,dx,dy);break
            if chosen is None:fail('原图附近没有可证明不遮挡曲线的标注空间')
            placements,box,dx,dy=chosen
            for ident,x,y,_ in placements:texts[ident].update(x=x,y=y,align='center',rotation=0)
            occupied.append(box);evidence.append({'ids':[p['id'] for p in parts],'source_anchor':[ax,ay],'offset_pt':[dx,dy],'bbox':box,'source_ink_clearance_pt':1.5})
    return evidence
