"""Remove explicitly tagged Visio text shadows, keeping the matching real text."""
from pathlib import Path
import hashlib
import json
import sys
import re
import base64
from lxml import etree as ET

SVG = 'http://www.w3.org/2000/svg'
VISIO = 'http://schemas.microsoft.com/visio/2003/SVGExtensions/'


def remove_text_shadows(root):
    removed = []
    styles={name:dict(part.strip().split(':',1) for part in body.split(';') if ':' in part) for node in root.iter('{'+SVG+'}style') for name,body in re.findall(r'\.([\w-]+)\s*\{([^}]+)\}',node.text or '')}
    def invisible(node):
        values={}
        for name in node.get('class','').split():values.update(styles.get(name,{}))
        values.update({k:v for k,v in node.attrib.items() if k in ('fill','stroke')})
        values.update(dict(part.strip().split(':',1) for part in node.get('style','').split(';') if ':' in part))
        return values.get('fill','').strip()=='none' and values.get('stroke','').strip()=='none'
    for group in list(root.iter('{'+SVG+'}g')):
        if group.get('{'+VISIO+'}groupContext') != 'shadow':
            continue
        shadow = group.findall('.//{'+SVG+'}text')
        if not shadow:
            continue
        parent = group.getparent()
        text = [''.join(node.itertext()).strip() for node in shadow]
        real = [''.join(node.itertext()).strip() for node in parent.findall('{'+SVG+'}text')]
        graphics = [node for node in group.iter() if node.tag in {'{'+SVG+'}'+name for name in ('path','rect','ellipse','circle','line','polyline','polygon','image','use')}]
        if any(not invisible(node) for node in graphics) or text != real or not all(text):
            raise ValueError('Visio文字阴影未能与同组原字完整绑定：'+str(group.get('id')))
        removed.append({'group':group.get('id'),'text':text,'basis':'Visio shadow group with identical sibling native text'})
        parent.remove(group)
    return removed


def prepare(source: Path, output: Path, replaced_images=None):
    if source.resolve()==output.resolve() or output.exists():
        raise ValueError('必须使用新的派生输出路径')
    parser=ET.XMLParser(resolve_entities=False,no_network=True,load_dtd=False)
    root=ET.parse(str(source),parser).getroot()
    if root.tag!='{'+SVG+'}svg':
        raise ValueError('输入必须为SVG')
    removed=remove_text_shadows(root)
    image_records=[]
    for request in replaced_images or []:
        if set(request)!={'source_sha256','replacement','basis'} or not request['replacement'] or not request['basis']:
            raise ValueError('重排图片必须登记原始哈希、替换内容及依据')
        matches=[]
        for image in root.iter('{'+SVG+'}image'):
            href=image.get('{http://www.w3.org/1999/xlink}href','')
            if href.startswith('data:image/png;base64,'):
                pixels=base64.b64decode(''.join(href.split(',',1)[1].split()),validate=True)
                if hashlib.sha256(pixels).hexdigest()==request['source_sha256']:matches.append(image)
        if len(matches)!=1:raise ValueError('待换排图片未唯一绑定源SVG')
        image_records.append(request)
        matches[0].getparent().remove(matches[0])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(ET.tostring(root,xml_declaration=True,encoding='UTF-8'))
    report={'source':str(source.resolve()),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output':str(output.resolve()),'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'removed_text_shadows':removed,'replaced_images':image_records}
    output.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    print(json.dumps(prepare(Path(sys.argv[1]),Path(sys.argv[2])),ensure_ascii=False))
