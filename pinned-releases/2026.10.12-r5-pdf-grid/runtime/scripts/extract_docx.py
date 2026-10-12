import hashlib
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from legacy_caption import OOXML_NS, REL_NS, find_docx_caption_media, _docx_caption_parts, _paragraph_text_xml


def extract(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    candidates = find_docx_caption_media(source)
    with zipfile.ZipFile(source) as z:
        root = ET.fromstring(z.read('word/document.xml'))
        relroot = ET.fromstring(z.read('word/_rels/document.xml.rels'))
        rels = {r.get('Id'): r.get('Target', '') for r in relroot.findall('rel:Relationship', REL_NS) if r.get('TargetMode') != 'External'}
        paragraphs = root.findall('.//w:body//w:p', OOXML_NS)
        captions = [{'paragraph': i, 'parts': _docx_caption_parts(paragraphs, i, rels)} for i, p in enumerate(paragraphs)]
        captions = [c for c in captions if c['parts']]
        items, used, issues = [], set(), []
        for c in candidates:
            members = []
            for m in c['members']:
                member = m['member']
                if not member.startswith('word/media/') or '..' in Path(member).parts:
                    issues.append({'type': 'unsafe_media_target', 'member': member})
                    continue
                data = z.read(member)
                digest = hashlib.sha256(data).hexdigest()
                target = output / (digest + Path(member).suffix.lower())
                if not target.exists():
                    target.write_bytes(data)
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    raise ValueError('Extracted source hash mismatch')
                p = paragraphs[m['object_paragraph_index']]
                crops = []
                for picture in p.findall('.//a:blip', OOXML_NS):
                    rid = picture.get('{' + OOXML_NS['r'] + '}embed')
                    if 'word/' + rels.get(rid, '') != member:
                        continue
                    for parent in p.iter():
                        if picture in list(parent):
                            rect = parent.find('a:srcRect', OOXML_NS)
                            crops.append([int(rect.get(k, '0')) / 100000 for k in ['l', 't', 'r', 'b']] if rect is not None else [0, 0, 0, 0])
                crop = crops[0] if len(crops) == 1 else [0, 0, 0, 0]
                if len(crops) > 1:
                    issues.append({'type': 'repeated_media_occurrence', 'paragraph': m['object_paragraph_index'], 'member': member})
                members.append({**m, 'source': str(target), 'sha256': digest, 'crop': crop, 'cropOccurrenceCount': len(crops)})
                used.add(member)
            item = {'number': c['figure_no'], 'caption': c['caption'], 'paragraph': c['paragraph_index'], 'members': members, 'status': 'ready' if len(members) == 1 and members[0]['cropOccurrenceCount'] <= 1 else 'needs_layout_review'}
            items.append(item)
        mapped = {c['paragraph'] for c in items}
        for c in captions:
            if c['paragraph'] not in mapped:
                issues.append({'type': 'caption_without_unique_media', **c})
        numbers = {}
        for item in items:
            numbers.setdefault(item['number'], []).append(item['paragraph'])
        for number, positions in numbers.items():
            if len(positions) > 1:
                issues.append({'type': 'duplicate_figure_number', 'number': number, 'paragraphs': positions})
        unassigned = [n for n in z.namelist() if n.startswith('word/media/') and not n.endswith('/') and n not in used]
    return {'version': 1, 'article': str(source), 'articleHash': source_hash, 'figures': items, 'issues': issues, 'unassignedMedia': unassigned}


if __name__ == '__main__':
    result = extract(sys.argv[1], sys.argv[2])
    Path(sys.argv[3]).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
