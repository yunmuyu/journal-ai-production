"""Verify Office-prepared simple shapes and source text without trusting PDF pixels."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}


def tree_signature(node: ET.Element) -> tuple:
    return node.tag,tuple(sorted(node.attrib.items())),node.text,tuple(tree_signature(c) for c in node)


def shapes(file: Path) -> dict[tuple[str,str],tuple]:
    output={}
    with ZipFile(file) as z:
        slides=sorted(n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n))
        for name in slides:
            root=ET.fromstring(z.read(name))
            if any(root.findall('.//p:'+tag,NS) for tag in ('grpSp','pic','graphicFrame')):
                raise ValueError('pptx_preparation_complex_objects: 分组、图片或嵌入图表需先单独核对')
            for obj in root.findall('.//p:sp',NS)+root.findall('.//p:cxnSp',NS):
                node=obj.find('./p:nvSpPr/p:cNvPr',NS)
                if node is None:node=obj.find('./p:nvCxnSpPr/p:cNvPr',NS)
                if node is None or not node.get('id'):raise ValueError('pptx_shape_identity')
                key=(name,node.get('id'))
                if key in output:raise ValueError('pptx_shape_duplicate_id')
                properties=obj.find('./p:spPr',NS)
                geometry=[] if properties is None else [tree_signature(c) for c in properties if c.tag.rsplit('}',1)[-1] in ('xfrm','prstGeom','custGeom')]
                text=''.join(x.text or '' for x in obj.findall('.//a:t',NS))
                output[key]=(tuple(geometry),text)
    if not output:raise ValueError('pptx_no_shapes')
    return output


def main() -> None:
    before=shapes(Path(sys.argv[1]));after=shapes(Path(sys.argv[2]))
    if before!=after:
        changed=[f'{key[0]}:{key[1]}' for key in before.keys()|after.keys() if before.get(key)!=after.get(key)]
        raise ValueError('pptx_preparation_geometry_changed: '+','.join(sorted(changed)[:30]))
    print(json.dumps({'unchanged':True,'shapeCount':len(before),'text_and_shape_geometry_exact':True}))


if __name__=='__main__':
    main()
