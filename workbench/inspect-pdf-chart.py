"""Read-only figure inventory. Candidates do not establish data semantics."""
import json
import re
import sys
from lxml import etree as ET
from pathlib import Path
from chart_object_candidates import propose_objects


def pdf_facts(source):
    import fitz
    pages=[]
    with fitz.open(source) as doc:
        for page in doc:
            blocks=page.get_text('dict')['blocks']
            spans=[s for block in blocks if block['type']==0 for line in block['lines'] for s in line['spans'] if s['text'].strip()]
            lines=[{'text':''.join(s['text'] for s in line['spans']),'bbox':list(line['bbox'])} for block in blocks if block['type']==0 for line in block['lines']]
            panel_candidates=[line for line in lines if re.search(r'(视图|视角|\b3D\b|\bpanel\b)',line['text'],re.I)]
            legend_candidates=[line for line in lines if re.search(r'(理想轨迹|实际跟踪|图例|true\s+|predicted\s+)',line['text'],re.I)]
            drawings=page.get_drawings();colors={};colored_paths=[]
            for index,drawing in enumerate(drawings):
                color=drawing.get('color')
                if color is not None:
                    key=','.join(str(round(v,4)) for v in color);colors[key]=colors.get(key,0)+1
                    if max(color)-min(color)>.01:
                        colored_paths.append({'id':f'path-{len(colored_paths)+1}','drawingIndex':index,'color':list(color),'bbox':list(drawing['rect']),'segments':len(drawing['items'])})
            objects=propose_objects(page.rect,drawings,spans,legend_candidates)
            pages.append({'pageWidth':page.rect.width,'pageHeight':page.rect.height,'textSpans':len(spans),'vectorPaths':len(drawings),'images':len(page.get_images()),'strokeColors':colors,'coloredPaths':colored_paths,'textObjects':[{'id':f'text-{i+1}','text':s['text'],'bbox':list(s['bbox'])} for i,s in enumerate(spans)],'legendCandidates':legend_candidates,'panelCandidates':panel_candidates,'objectCandidates':objects,'candidateWarning':'文字与几何均为候选，须核对对象及作用域','legendBinding':'unresolved','panelBinding':'unresolved'})
    return {'format':'pdf','pageCount':len(pages),'pages':pages,'textSpans':sum(p['textSpans'] for p in pages),'vectorPaths':sum(p['vectorPaths'] for p in pages),'images':sum(p['images'] for p in pages)}


def svg_facts(source):
    data=source.read_bytes()
    if len(data)>64*1024*1024 or b'<!ENTITY' in data.upper():raise ValueError('unsafe_svg_document')
    parser=ET.XMLParser(resolve_entities=False,no_network=True,load_dtd=False,huge_tree=False)
    root=ET.fromstring(data,parser=parser);elements=list(root.iter())
    if len(elements)>1000000:raise ValueError('svg_object_budget')
    tag=lambda e:e.tag.rsplit('}',1)[-1] if isinstance(e.tag,str) else ''
    paths=[e for e in elements if tag(e) in {'path','line','polyline','polygon','rect','circle','ellipse'}]
    texts=[e for e in elements if tag(e)=='text' and ''.join(e.itertext()).strip()]
    images=[e for e in elements if tag(e)=='image']
    panels=[{'id':e.get('id'),'text':e.get('id')} for e in elements if tag(e)=='g' and re.fullmatch(r'axes_\d+',e.get('id',''))]
    legends=[{'id':e.get('id'),'text':e.get('id')} for e in elements if tag(e)=='g' and re.fullmatch(r'legend_\d+',e.get('id',''))]
    colored=[]
    for i,e in enumerate(paths):
        paint=e.get('stroke') or e.get('fill') or ''
        if not paint and e.get('style'):
            match=re.search(r'(?:stroke|fill)\s*:\s*([^;]+)',e.get('style'));paint=match.group(1).strip() if match else ''
        if re.fullmatch(r'#[0-9a-fA-F]{6}',paint):
            channels=[int(paint[j:j+2],16) for j in (1,3,5)]
            if max(channels)-min(channels)>2:colored.append({'id':e.get('id') or f'path-{i+1}','color':paint,'geometry':'source-object-candidate'})
    view=root.get('viewBox','').replace(',',' ').split();width=height=None
    if len(view)==4:
        try:width,height=float(view[2]),float(view[3])
        except ValueError:pass
    if not width or not height:
        try:
            width=float(re.match(r'^\s*([0-9.]+)',root.get('width','')).group(1));height=float(re.match(r'^\s*([0-9.]+)',root.get('height','')).group(1))
        except (AttributeError,ValueError):width=height=None
    page={'pageWidth':width,'pageHeight':height,'textSpans':len(texts),'vectorPaths':len(paths),'images':len(images),'coloredPaths':colored,'textObjects':[{'id':e.get('id') or f'text-{i+1}','text':''.join(e.itertext())} for i,e in enumerate(texts)],'panelCandidates':panels,'legendCandidates':legends,'candidateWarning':'仅静态对象和名称候选；转曲文字、外部资源及对象语义须另核对','legendBinding':'unresolved','panelBinding':'unresolved'}
    return {'format':'svg','pageCount':1,'pages':[page],'textSpans':len(texts),'vectorPaths':len(paths),'images':len(images),'externalReferencesNotLoaded':True}


def raster_facts(source):
    from PIL import Image
    with Image.open(source) as image:
        width,height=image.size
        if width*height>100000000:raise ValueError('image_pixel_budget')
        sample=image.convert('RGB');sample.thumbnail((256,256))
        has_color=any(max(px)-min(px)>2 for px in sample.getdata())
        page={'pageWidth':width,'pageHeight':height,'textSpans':0,'vectorPaths':0,'images':1,'coloredPaths':[],'textObjects':[],'panelCandidates':[],'legendCandidates':[],'colorSample':has_color,'candidateWarning':'位图未OCR；未检出不代表不存在文字、曲线或图例','legendBinding':'unresolved','panelBinding':'unresolved'}
        return {'format':source.suffix.lower().lstrip('.'),'pageCount':1,'pages':[page],'textSpans':0,'vectorPaths':0,'images':1,'pixelTextRecognition':'not_performed'}

source=Path(sys.argv[1]);suffix=source.suffix.lower()
if suffix=='.pdf':result=pdf_facts(source)
elif suffix=='.svg':result=svg_facts(source)
elif suffix in ('.jpg','.jpeg','.png'):result=raster_facts(source)
else:raise ValueError('source_format_not_inspected')
print(json.dumps(result,ensure_ascii=False))
