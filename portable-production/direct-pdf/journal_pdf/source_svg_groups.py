
from __future__ import annotations

import copy
import hashlib
import json
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
    before = geometry_signature(root, [group_id])
    ancestors = list(reversed([node for node in selected.iterancestors() if node is not root]))
    inherited = [dict(node.attrib) for node in ancestors]
    all_defs(root)
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


def prepare_svg_group(source: Path, group_id: str, clip: list[float], *, text_replacements=None):

    from .assets import svg_pdf_bytes
    from .source_icons import PreparedIcon, prepare_icon

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
        if extent is None or not fitz.Rect(clip).contains(fitz.Rect(extent)):
            raise FigureError('source_svg_group_extent','裁区未完整包含所选原SVG对象及原描边',extent=extent,clip=clip)
        proof['complete_group_extent']=extent
        proof['complete_group_extent_proven']=True
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

