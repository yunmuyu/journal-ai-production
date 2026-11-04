import hashlib
import json
import re
import sys
import posixpath
from zipfile import ZipFile
from xml.etree import ElementTree as ET


word_path, evidence_path = sys.argv[1:3]
expected = json.load(open(evidence_path, encoding='utf-8'))
word_sha = hashlib.sha256(open(word_path, 'rb').read()).hexdigest()
if word_sha != expected.get('word', {}).get('sha256'):
    raise ValueError('当前Word文件SHA与输出集合不一致')
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
WP = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
V = '{urn:schemas-microsoft-com:vml}'
caption_re = re.compile(r'^图\s*([0-9]+(?:[.．\-－][0-9]+)*)\s*(.*)$')
marker_re = re.compile(r'[（(]([a-zA-Z])[）)]\s*([^（）()]*?)(?=\s*[（(][a-zA-Z][）)]|$)')

with ZipFile(word_path) as z:
    if sum(item.file_size for item in z.infolist()) > 128 * 1024 * 1024:
        raise ValueError('Word解压尺寸超限')
    root = ET.fromstring(z.read('word/document.xml'))
    relroot = ET.fromstring(z.read('word/_rels/document.xml.rels'))
    rels = {item.get('Id'): item for item in relroot}
    body = root.find('.//' + W + 'body')
    if body is None:
        raise ValueError('Word正文缺失')
    tokens = []
    paragraph_id = 0
    for block_index, block in enumerate(list(body)):
        paragraphs = [block] if block.tag == W + 'p' else block.findall('.//' + W + 'p')
        for paragraph in paragraphs:
            text = ''.join(t.text or '' for t in paragraph.iter(W + 't')).strip()
            rids = list(dict.fromkeys(b.get(R + 'embed') for b in paragraph.iter(A + 'blip') if b.get(R + 'embed')))
            inline_rids = [b.get(R + 'embed') for inline in paragraph.iter(WP + 'inline') for b in inline.iter(A + 'blip') if b.get(R + 'embed')]
            for shape in paragraph.iter(V + 'shape'):
                for image in shape.iter(V + 'imagedata'):
                    rid=image.get(R + 'id')
                    if rid and rid not in rids:
                        rids.append(rid)
                        if 'position:absolute' not in shape.get('style','').replace(' ','').lower():
                            inline_rids.append(rid)
            images = []
            for rid in rids:
                rel = rels.get(rid)
                if rel is None or rel.get('TargetMode') == 'External':
                    raise ValueError('Word图像关系缺失或外链')
                member = posixpath.normpath(posixpath.join('word', rel.get('Target', '')))
                if not member.startswith('word/media/') or member not in z.namelist():
                    raise ValueError('Word图像未绑定实际media')
                images.append({'member': member, 'sha256': hashlib.sha256(z.read(member)).hexdigest(), 'paragraph': paragraph_id, 'block': block_index, 'inline': inline_rids.count(rid) == 1})
            tokens.append({'text': text, 'images': images, 'paragraph': paragraph_id, 'block': block_index})
            paragraph_id += 1

    figures = []
    pending_images = []
    pending_labels = []
    pending_paragraphs = set()
    pending_groups = []
    active_group = None
    group_error = False
    unlabelled_continuation = False
    for token in tokens:
        text = token['text']
        caption = caption_re.match(text)
        if caption:
            caption_marker_matches = list(marker_re.finditer(caption.group(2)))
            caption_labels = [m.groups() for m in caption_marker_matches]
            if caption_labels and ''.join(m.group(0) for m in caption_marker_matches).replace(' ', '') != caption.group(2).replace(' ', ''):
                group_error = True
            if caption_labels:
                if len(pending_groups) != 1:
                    group_error = True
                elif len(caption_labels) != len(pending_groups[0]['images']):
                    group_error = True
                else:
                    group = pending_groups[0]
                    if pending_labels:
                        suffix = caption_labels[-len(pending_labels):]
                        body_markers_match = all(
                            body[0] == full[0] and (not body[1] or body[1].casefold() == full[1].casefold())
                            for body, full in zip(pending_labels, suffix)
                        )
                        if (not body_markers_match or group['lastLabelParagraph'] != token['paragraph'] - 1):
                            group_error = True
                    elif token['paragraph'] - group['lastParagraph'] > 2:
                        group_error = True
                    group['labels'] = caption_labels
                    pending_labels = caption_labels
            figures.append({'number': caption.group(1), 'caption': text, 'images': pending_images,
                            'labels': pending_labels, 'paragraphs': pending_paragraphs, 'captionParagraph': token['paragraph'],
                            'groups': pending_groups, 'groupError': group_error, 'unlabelledContinuation': unlabelled_continuation})
            pending_images, pending_labels, pending_paragraphs = [], [], set()
            pending_groups, active_group, group_error = [], None, False
            unlabelled_continuation = False
            continue
        if token['images']:
            if text:
                pending_images, pending_labels, pending_paragraphs = [], [], set()
                pending_groups, active_group, group_error = [], None, False
                unlabelled_continuation = False
                continue
            if active_group is not None:
                if not active_group['labels']:
                    unlabelled_continuation = True
                else:
                    active_group = None
            if active_group is None:
                active_group = {'images': [], 'labels': [], 'lastParagraph': token['paragraph'], 'lastLabelParagraph': None}
                pending_groups.append(active_group)
            active_group['lastParagraph'] = token['paragraph']
            active_group['images'].extend(token['images'])
            pending_images.extend(token['images'])
            pending_paragraphs.add(token['paragraph'])
            continue
        if not text:
            continue
        found = list(marker_re.finditer(text))
        if found and ''.join(m.group(0) for m in found).replace(' ', '') == text.replace(' ', '') and active_group is not None:
            prior = active_group['lastLabelParagraph']
            expected_paragraph = active_group['lastParagraph'] + 1 if prior is None else prior + 1
            if token['paragraph'] != expected_paragraph:
                group_error = True
            active_group['lastLabelParagraph'] = token['paragraph']
            labels_here = [m.groups() for m in found]
            active_group['labels'].extend(labels_here)
            pending_labels.extend(labels_here)
            pending_paragraphs.add(token['paragraph'])
        else:
            pending_images, pending_labels, pending_paragraphs = [], [], set()
            pending_groups, active_group, group_error = [], None, False
            unlabelled_continuation = False

matches = [figure for figure in figures if figure['number'] == str(expected.get('figureNumber')) and figure['images']]
if len(matches) != 1:
    raise ValueError('当前Word未能唯一提取目标图号题注')
figure = matches[0]
if expected.get('caption') != figure['caption']:
    raise ValueError('输出集合题注与当前Word不一致')
outputs = expected.get('outputs', [])
grouped = expected.get('grouping') in ('word-inline-columns','word-labelled-segments')
if not outputs or (not grouped and expected.get('grouping')!='word-media-regions' and len(figure['images']) != len(outputs)):
    raise ValueError('Word目标题注关联图件数量与输出集合不一致')
number_suffixes = []
for wanted in outputs:
    suffix = re.fullmatch(re.escape(str(expected['figureNumber'])) + r'[.\-]([0-9]+)', str(wanted.get('number', '')))
    if not suffix:
        raise ValueError('输出集合数字后缀不属于当前图号')
    number_suffixes.append(int(suffix.group(1)))
if number_suffixes != list(range(1, len(outputs) + 1)):
    raise ValueError('输出集合子图序号必须完整且连续')

labels = figure['labels']
if expected.get('grouping') == 'word-media-regions':
    import math
    if len(figure['images'])!=1 or not figure['images'][0]['inline'] or len(labels)!=len(outputs) or figure['groupError']:
        raise ValueError('裁区分图须有单一行内媒体及完整无歧义子图题')
    regions=[];actual=figure['images'][0]
    for wanted,label in zip(outputs,labels):
        region=wanted.get('wordRegion');marker=wanted.get('captionMarker','').translate(str.maketrans({'（':'(', '）':')'}))
        if wanted.get('wordMedia')!=actual['member'] or wanted.get('wordMediaSha256')!=actual['sha256'] or marker!=f'({label[0]})' or not wanted.get('subcaption') or wanted['subcaption'].casefold() not in label[1].casefold():
            raise ValueError('裁区子图媒体、哈希或题注不匹配')
        if not isinstance(region,list) or len(region)!=4 or any(type(v) not in (float,int) or not math.isfinite(v) or not 0<=v<=1 for v in region) or not region[0]<region[2] or not region[1]<region[3]:
            raise ValueError('裁区须为有效归一化矩形')
        if any(max(region[0],r[0])<min(region[2],r[2]) and max(region[1],r[1])<min(region[3],r[3]) for r in regions):
            raise ValueError('子图裁区重叠')
        regions.append(region)
        source=wanted.get('source',{})
        if not source.get('path') or hashlib.sha256(open(source['path'],'rb').read()).hexdigest()!=source.get('sha256'):
            raise ValueError('子图源文件哈希不符')
    print(json.dumps({'ok':True,'grouping':'word-media-regions','figureNumber':figure['number'],'completeOutputNumbers':[o['number'] for o in outputs]},ensure_ascii=False))
    sys.exit(0)
if expected.get('grouping') == 'word-labelled-segments':
    if figure['groupError'] or figure['unlabelledContinuation'] or len(labels)!=len(outputs):
        raise ValueError('分段子图须有完整且无歧义的Word子图题')
    assignments=[]
    for group in figure['groups']:
        count=len(group['labels'])
        if not count or not group['images'] or len(group['images'])%count or len({i['paragraph'] for i in group['images']})!=1 or not all(i['inline'] for i in group['images']):
            raise ValueError('分段子图仅支持明确单行图片及紧邻对应子图题')
        size=len(group['images'])//count
        assignments.extend((label,group['images'][i*size:(i+1)*size]) for i,label in enumerate(group['labels']))
    if len(assignments)!=len(outputs):raise ValueError('完整子图集合未覆盖全部Word图组')
    seen=set()
    for wanted,(label,images) in zip(outputs,assignments):
        marker=wanted.get('captionMarker','').translate(str.maketrans({'（':'(', '）':')'}))
        members=wanted.get('members');caption=wanted.get('subcaption')
        if marker!=f'({label[0]})' or not isinstance(caption,str) or not caption.strip() or caption.casefold() not in label[1].casefold() or not isinstance(members,list) or len(members)!=len(images):
            raise ValueError('分段子图题或组成媒体数量不匹配')
        for actual,part in zip(images,members):
            source=part.get('source',{});source_path=source.get('path')
            if actual['member']!=part.get('wordMedia') or actual['sha256']!=part.get('wordMediaSha256') or actual['member'] in seen:
                raise ValueError('分段子图媒体顺序、哈希或唯一性不符')
            if not source_path or hashlib.sha256(open(source_path,'rb').read()).hexdigest()!=source.get('sha256') or source.get('sha256')!=actual['sha256']:
                raise ValueError('分段子图须采用Word原媒体及有效哈希')
            seen.add(actual['member'])
    published=expected.get('publishNumbers')
    numbers=[o['number'] for o in outputs]
    if published is not None and (not isinstance(published,list) or not published or len(set(published))!=len(published) or published!=[n for n in numbers if n in published]):
        raise ValueError('分次回传范围不属于完整Word子图集合或顺序不符')
    print(json.dumps({'ok':True,'figureNumber':figure['number'],'completeOutputNumbers':numbers,'publishNumbers':published or numbers,'grouping':expected['grouping']},ensure_ascii=False))
    sys.exit(0)
if grouped:
    if len(outputs)<2 or not labels or len(labels)!=len(outputs) or figure['groupError'] or len(figure['groups'])!=1:
        raise ValueError('多媒体子图须有完整Word子图题及单一明确图组')
    rows = []
    for image in figure['images']:
        if not image['inline']:
            raise ValueError('多媒体子图仅支持Word行内图片，浮动图片位置不明确')
        if not rows or rows[-1][0]['paragraph'] != image['paragraph']:
            rows.append([])
        rows[-1].append(image)
    if len(rows)<2 or any(len(row)!=len(outputs) for row in rows) or any(rows[i+1][0]['paragraph']!=rows[i][0]['paragraph']+1 for i in range(len(rows)-1)):
        raise ValueError('Word图片须为连续且列数一致的行内网格')
    seen_sources=set()
    for col,(label,wanted) in enumerate(zip(labels,outputs)):
        marker=wanted.get('captionMarker','')
        if not isinstance(marker,str):raise ValueError('Word子图标记格式无效')
        marker=marker.translate(str.maketrans({'（':'(', '）':')'}))
        subcaption=wanted.get('subcaption')
        members=wanted.get('members')
        if marker!=f'({label[0]})' or not isinstance(subcaption,str) or not subcaption.strip() or subcaption.casefold() not in label[1].casefold() or not isinstance(members,list) or len(members)!=len(rows):
            raise ValueError('Word子图题与多媒体输出不匹配')
        for row,part in zip(rows,members):
            actual=row[col];source=part.get('source',{});source_path=source.get('path')
            if actual['member']!=part.get('wordMedia') or actual['sha256']!=part.get('wordMediaSha256'):
                raise ValueError('Word图像行列或媒体哈希与映射不一致')
            if not source_path or hashlib.sha256(open(source_path,'rb').read()).hexdigest()!=source.get('sha256'):
                raise ValueError('多媒体子图来源文件哈希不符')
            origin=part.get('originPdf')
            if origin is not None:
                import fitz
                origin_path=origin.get('path')
                if not origin_path or hashlib.sha256(open(origin_path,'rb').read()).hexdigest()!=origin.get('sha256'):
                    raise ValueError('原始PDF哈希不符')
                with fitz.open(origin_path) as doc:
                    if len(doc)!=1:raise ValueError('原始PDF须为单页图像')
                    page=doc[0];images=page.get_images(full=True)
                    if len(images)!=1 or images[0][1] or page.get_drawings() or page.get_text().strip():
                        raise ValueError('原始PDF并非单一无蒙版图像，不能按位图提取')
                    rects=page.get_image_rects(images[0][0]);bounds=page.rect
                    if len(rects)!=1 or any(abs(a-b)>1 for a,b in zip(rects[0],bounds)):
                        raise ValueError('原始PDF图片未覆盖完整页面')
                    if hashlib.sha256(doc.extract_image(images[0][0])['image']).hexdigest()!=source.get('sha256'):
                        raise ValueError('候选图像不是原始PDF图像的无损提取')
            identity=(source_path,source.get('sha256'))
            if identity in seen_sources:raise ValueError('多媒体子图重复使用来源')
            seen_sources.add(identity)
    print(json.dumps({'ok':True,'figureNumber':figure['number'],'caption':figure['caption'],'media':[i['member'] for i in figure['images']],'grouping':expected['grouping']},ensure_ascii=False))
    sys.exit(0)
if labels:
    if figure['groupError'] or figure['unlabelledContinuation'] or any(len(group['images']) != len(group['labels']) for group in figure['groups']) or len(labels) != len(outputs):
        raise ValueError('Word子图标记数量与输出集合不一致')
    grouped_images = [image for group in figure['groups'] for image in group['images']]
    if grouped_images != figure['images']:
        raise ValueError('Word媒体分组与图块顺序不一致')
    for label, wanted in zip(labels, outputs):
        marker = wanted.get('captionMarker')
        if isinstance(marker, str):
            marker = marker.translate(str.maketrans({'（': '(', '）': ')'}))
        subcaption = wanted.get('subcaption')
        if marker != f'({label[0]})' or not isinstance(subcaption, str) or subcaption.casefold() not in label[1].casefold():
            raise ValueError('Word子图标记/名称顺序与输出集合不一致')
elif any(not isinstance(w.get('source'), dict) for w in outputs):
    raise ValueError('无Word子图标记时必须逐项绑定来源SHA')
elif len({image['paragraph'] for image in figure['images']}) != 1 or figure['captionParagraph'] - figure['images'][-1]['paragraph'] > 2:
    raise ValueError('无Word子图标记时必须来自同一Word段并紧邻题注')

for actual, wanted in zip(figure['images'], outputs):
    source = wanted.get('source', {})
    source_path = source.get('path')
    source_hash = hashlib.sha256(open(source_path, 'rb').read()).hexdigest() if source_path else None
    if actual['member'] != wanted.get('wordMedia') or actual['sha256'] != wanted.get('wordMediaSha256'):
        raise ValueError('Word实际media字节/顺序与输出集合映射不一致')
    if source_hash != source.get('sha256'):
        raise ValueError('来源文件SHA与输出集合不一致')
    if not labels and source_hash != actual['sha256']:
        raise ValueError('Word无子图标记且来源字节不一致，不能安全绑定')

print(json.dumps({'ok': True, 'figureNumber': figure['number'], 'caption': figure['caption'], 'media': [i['member'] for i in figure['images']]}, ensure_ascii=False))
