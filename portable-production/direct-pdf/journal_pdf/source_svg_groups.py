
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

from lxml import etree as ET
import pymupdf as fitz

from .common import FigureError, digest_file


def isolate_svg_group(source: Path, group_id: str, *, gray: bool = True):

    from .assets import all_defs, element, geometry_signature, grayscale_svg, svg_root

    root = svg_root(source)
    selected = element(root, group_id)
    if ET.QName(selected).localname != 'g':
        raise FigureError('source_svg_group_kind', '原SVG对象必须为明确的组')
    ancestors = list(reversed([node for node in selected.iterancestors() if node is not root]))
    inherited = [dict(node.attrib) for node in ancestors]
    all_defs(root)
    before = geometry_signature(root, [group_id])
    isolated = ET.Element(root.tag, nsmap=root.nsmap, attrib=dict(root.attrib))
    for child in root:
        if isinstance(child.tag, str) and ET.QName(child).localname in ('defs', 'style'):
            isolated.append(copy.deepcopy(child))
    parent = isolated
    for ancestor in ancestors:
        child = ET.Element(ancestor.tag, attrib=dict(ancestor.attrib))
        parent.append(child)
        parent = child
    parent.append(copy.deepcopy(selected))
    ids = set(isolated.xpath('//*[@id]/@id'))
    for node in isolated.iter():
        if not isinstance(node.tag, str):
            continue
        for key, value in node.attrib.items():
            references = re.findall(r'url\(#([^)]*)\)', value)
            if ET.QName(key).localname == 'href' and value.startswith('#'):
                references.append(value[1:])
            if any(reference not in ids for reference in references):
                raise FigureError('source_svg_group_reference', '选定组依赖未隔离的外部同级对象')
    after = geometry_signature(isolated, [group_id])
    if before != after:
        raise FigureError('source_svg_group_geometry', '隔离改变了原组路径或描边属性')
    operations = grayscale_svg(isolated) if gray else 0
    return isolated, {'source_group': group_id, 'ancestor_attributes': inherited,
                      'geometry_before': before, 'geometry_after': after,
                      'geometry_unchanged': True, 'grayscale_operations': operations,
                      'siblings_included': False, 'source_root_attributes': dict(root.attrib)}


def _rect_clipped_group(root, group_id, clip, page):
    """Prove a restricted source clip, without assuming a path's raw bbox is ink."""
    from .assets import element

    if root.get('transform') or 'transform' in root.get('style', ''):
        raise FigureError('source_svg_clip_unproven', 'SVG根节点的变换无法证明裁切范围')
    for sheet in root.xpath('//*[local-name()="style"]'):
        css = (sheet.text or '').strip()
        match = re.fullmatch(r'\*\s*\{([^{}]*)\}', css)
        if not match:
            raise FigureError('source_svg_clip_unproven', 'SVG样式表可能改变裁切语义')
        for declaration in match.group(1).split(';'):
            if not declaration.strip():
                continue
            pair = declaration.split(':', 1)
            if len(pair) != 2 or pair[0].strip() not in ('stroke-linejoin', 'stroke-linecap'):
                raise FigureError('source_svg_clip_unproven', 'SVG样式表包含未验证属性')

    view = root.get('viewBox', '').replace(',', ' ').split()
    if len(view) != 4:
        raise FigureError('source_svg_clip_unproven', '需要明确且无变换的SVG viewBox')
    try:
        x, y, width, height = map(float, view)
    except ValueError as error:
        raise FigureError('source_svg_clip_unproven', 'SVG viewBox无法解析') from error
    if (not all(math.isfinite(v) for v in (x, y, width, height)) or x != 0 or y != 0
            or abs(page.rect.width-width) > 1e-4 or abs(page.rect.height-height) > 1e-4):
        raise FigureError('source_svg_clip_unproven', '仅支持源坐标与PDF坐标一一对应')
    selected = element(root, group_id)
    wanted = fitz.Rect(clip)
    if wanted.is_empty or not page.rect.contains(wanted):
        raise FigureError('source_svg_clip_unproven', '裁区无效或越过页面')
    allowed = {'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon'}
    graphics = []
    for node in selected.iter():
        if not isinstance(node.tag, str):
            continue
        local = ET.QName(node).localname
        if local in ('defs', 'clipPath') or any(
                isinstance(parent.tag, str) and ET.QName(parent).localname in ('defs', 'clipPath')
                for parent in node.iterancestors() if parent is not root):
            continue
        if local == 'g':
            continue
        if local not in allowed:
            raise FigureError('source_svg_clip_unproven', '受裁切组含未验证的对象', kind=local)
        graphics.append(node)
    if not graphics:
        raise FigureError('source_svg_clip_unproven', '受裁切组没有图形')
    rectangles = []
    for node in graphics:
        chain = [node, *node.iterancestors()]
        if any(item.get('transform') for item in chain if item is not root):
            raise FigureError('source_svg_clip_unproven', '受裁切组含未验证的变换')
        if any(re.search(r'(?:^|;)\s*(?:clip-path|clip|transform|mask|filter|all)\s*:', item.get('style', ''), re.I)
               for item in chain):
            raise FigureError('source_svg_clip_unproven', '内联样式可能改变裁切语义')
        references = [item.get('clip-path') for item in chain if item.get('clip-path')]
        if len(references) != 1:
            raise FigureError('source_svg_clip_unproven', '每个图形必须具有唯一源裁切')
        match = re.fullmatch(r'url\(#([^\s)]+)\)', references[0])
        if not match:
            raise FigureError('source_svg_clip_unproven', '源裁切引用无法解析')
        mask = element(root, match.group(1))
        children = [item for item in mask if isinstance(item.tag, str)]
        if (ET.QName(mask).localname != 'clipPath' or mask.get('transform')
                or mask.get('clipPathUnits', 'userSpaceOnUse') != 'userSpaceOnUse'
                or len(children) != 1 or ET.QName(children[0]).localname != 'rect'
                or children[0].get('transform') or children[0].get('style') or children[0].get('class')):
            raise FigureError('source_svg_clip_unproven', '仅支持单个无变换的矩形裁切')
        try:
            rx, ry = float(children[0].get('x', '0')), float(children[0].get('y', '0'))
            rw, rh = float(children[0].get('width')), float(children[0].get('height'))
        except (TypeError, ValueError) as error:
            raise FigureError('source_svg_clip_unproven', '源裁切尺寸无法解析') from error
        if not all(math.isfinite(v) for v in (rx, ry, rw, rh)) or rw <= 0 or rh <= 0:
            raise FigureError('source_svg_clip_unproven', '源裁切尺寸无效')
        original = fitz.Rect(rx, ry, rx+rw, ry+rh)
        if not wanted.contains(original):
            raise FigureError('source_svg_clip_unproven', '目标裁区截断源图形的原始裁切区域')
        rectangles.append(list(original))
    if page.get_fonts(full=True) or page.get_texttrace() or page.get_images(full=True):
        raise FigureError('source_svg_clip_unproven', '受裁切组仅支持无字、无位图的矢量图形')
    return rectangles


def prepare_svg_group(source: Path, group_id: str, clip: list[float], *, text_replacements=None,
                      clipped_viewport: bool = False):

    from .assets import svg_pdf_bytes
    from .source_icons import PreparedIcon, prepare_icon

    if not isinstance(clipped_viewport, bool):
        raise FigureError('source_svg_clip_unproven', 'clipped_viewport必须是布尔值')

    isolated, proof = isolate_svg_group(source, group_id)
    pdf = svg_pdf_bytes(isolated)
    with fitz.open(stream=pdf,filetype='pdf') as document:
        page=document[0]
        bounds=[]
        for drawing in page.get_drawings():
            box=drawing['rect'];margin=(drawing.get('width') or 0)/2
            bounds.append([box.x0-margin,box.y0-margin,box.x1+margin,box.y1+margin])
        for block in page.get_text('dict')['blocks']:
            if block['type']==0:
                bounds.extend(list(span['bbox']) for line in block['lines'] for span in line['spans'])
        extent=[min(box[0] for box in bounds),min(box[1] for box in bounds),max(box[2] for box in bounds),max(box[3] for box in bounds)] if bounds else None
        if extent is None:
            raise FigureError('source_svg_group_extent','源组没有矢量图形',extent=extent,clip=clip)
        if not fitz.Rect(clip).contains(fitz.Rect(extent)):
            if not clipped_viewport or text_replacements:
                raise FigureError('source_svg_group_extent','裁区未完整包含所选原SVG对象及原描边',extent=extent,clip=clip)
            rectangles = _rect_clipped_group(isolated, group_id, clip, page)
            content_before = [document.xref_stream(xref) for xref in page.get_contents()]
            page.set_cropbox(fitz.Rect(clip))
            data = document.tobytes(garbage=4, deflate=True, no_new_id=True)
            with fitz.open(stream=data, filetype='pdf') as check:
                if [check.xref_stream(xref) for xref in check[0].get_contents()] != content_before:
                    raise FigureError('source_svg_clip_changed', '裁切改变了原矢量内容流')
                path_count = len(check[0].get_drawings())
            proof.update(complete_group_extent=extent, complete_group_extent_proven=False,
                         source_clip_path_contained=True, original_clip_rectangles=rectangles,
                         clipped_viewport=True)
            proof.update(mode='source-svg-group', source_path=str(source.resolve()),
                         source_sha256=digest_file(source), source_page=0, source_clip=clip,
                         text_replacements=[], path_count=path_count, font_count=0, image_count=0,
                         source_text='', source_text_character_count=0,
                         prepared_sha256=hashlib.sha256(data).hexdigest(),
                         isolated_svg_sha256=hashlib.sha256(ET.tostring(isolated)).hexdigest(),
                         isolated_pdf_sha256=hashlib.sha256(pdf).hexdigest())
            return PreparedIcon(data, json.dumps(proof, ensure_ascii=False))
        proof['complete_group_extent']=extent
        proof['complete_group_extent_proven']=True
        proof['clipped_viewport']=False
    with tempfile.TemporaryDirectory(prefix='source-svg-group-') as temporary:
        converted = Path(temporary) / 'source-group.pdf'
        converted.write_bytes(pdf)
        prepared = prepare_icon(converted, 0, clip, text_replacements=text_replacements,
                                source_vector_body=True)
    receipt = json.loads(prepared.receipt_json)
    receipt.pop('complete_icon_extent_proven',None)
    receipt.pop('extent_review_required',None)
    receipt.update(proof)
    receipt.update(mode='source-svg-group', source_path=str(source.resolve()),
                   source_sha256=digest_file(source),
                   isolated_svg_sha256=hashlib.sha256(ET.tostring(isolated)).hexdigest(),
                   isolated_pdf_sha256=hashlib.sha256(pdf).hexdigest())
    return PreparedIcon(prepared.data, json.dumps(receipt, ensure_ascii=False))
