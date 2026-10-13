from __future__ import annotations
import re, zipfile, logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple, Optional
OOXML_NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','v':'urn:schemas-microsoft-com:vml'}
REL_NS = {'rel':'http://schemas.openxmlformats.org/package/2006/relationships'}
def normalize_digits(s: str) -> str:
    table = str.maketrans('０１２３４５６７８９', '0123456789')
    return s.translate(table)

def clean_line(line: str) -> str:
    line = line.replace('\u3000', ' ').replace('\xa0', ' ')
    line = re.sub(r'\s+', ' ', line).strip()
    return line

def _caption_segments_multi(text: str, photo_pair_anchored=False) -> List[dict]:
    """Parse one or more *caption* segments from one visual text line.

    Production manuscripts often put two side-by-side captions on the same line, e.g.::

        图3 模拟中风患者……    图4 健康人……

    Ordinary prose such as ``图7 和图8 所示。`` or ``图3 至图6……`` must not be
    mistaken for captions.  Besides the parsed text, character start/end offsets are returned
    so the PDF line rectangle can be split horizontally for left/right image matching.
    """
    text = clean_line(str(text or '').replace('\u200b', ''))
    if not re.match(r'^\s*图\s*[0-9０-９]+', text):
        return []
    hits = list(re.finditer(r'图\s*(4-1(?=$|[\s：:])|[0-9０-９]+)', text))
    if not hits:
        return []
    prose_starts = (
        '所示', '中', '可见', '展示', '显示', '给出', '说明', '表明', '为', '是',
        '采用', '包含', '包括', '反映', '描述', '对应', '代表了', '直观对比了'
    )
    connector_only = {'和', '与', '及', '至', '、', '，', ',', '或', '以及'}
    out: List[dict] = []
    for k, m in enumerate(hits):
        end = hits[k + 1].start() if k + 1 < len(hits) else len(text)
        raw = text[m.end():end]
        rest = clean_line(raw.lstrip('：:、.．-— '))
        # A genuine caption needs descriptive content.  Connectors between two figure
        # references (图7 和图8所示) are prose, not caption text.
        if not rest or rest in connector_only or len(rest) > 80 or rest.startswith(prose_starts) or (rest.startswith('用于') and (not re.match(r'^\s+|^[：:]', raw) or rest.endswith(('。', '；', ';')))):
            continue
        if len(rest) <= 2 and re.fullmatch(r'[和与及至、，,或]+', rest):
            continue
        # Long sentence-like endings are almost always narrative references.
        if rest.endswith(('所示。', '所示', '如下。', '如下')):
            continue
        if len(hits) == 1 and text.endswith(('。', '；', ';')) and len(text) > 24 and not (photo_pair_anchored and re.fullmatch(r'[（(]a[）)]\s*.+?照片。[（(]b[）)]\s*.+?照片。', rest)) and not (re.match(r'^\s+|^[：:]', raw) and re.search(r'[，,.。]\s*[（(]a[）)].+?[；;，,]\s*[（(]b[）)]', rest, re.I)):
            continue
        out.append({
            'no': normalize_digits(m.group(1)),
            'caption': rest,
            'start': m.start(),
            'end': end,
        })
    return out

def _paragraph_text_xml(p) -> str:
    return clean_line(''.join((t.text or '') for t in p.findall('.//w:t', OOXML_NS)).replace('\u200b', ''))

def _paragraph_media_targets(p, rels: dict) -> List[str]:
    targets = []
    for blip in p.findall('.//a:blip', OOXML_NS):
        rid = blip.attrib.get('{' + OOXML_NS['r'] + '}embed')
        target = rels.get(rid)
        if target and target.lower().startswith('media/'):
            targets.append(target)
    for im in p.findall('.//v:imagedata', OOXML_NS):
        rid = im.attrib.get('{' + OOXML_NS['r'] + '}id')
        target = rels.get(rid)
        if target and target.lower().startswith('media/'):
            targets.append(target)
    # Preserve order but remove duplicates.
    return list(dict.fromkeys(targets))

def _caption_parts_multi(text: str, photo_pair_anchored=False) -> List[Tuple[str, str]]:
    return [(x['no'], x['caption']) for x in _caption_segments_multi(text, photo_pair_anchored=photo_pair_anchored)]

def _is_subcaption_line(text: str) -> bool:
    """Return True for (a)/(b) style labels separating image rows from the main caption."""
    t = clean_line(text)
    if not t or len(t) > 220:
        return False
    return bool(re.match(r'^[（(]\s*[A-Za-z0-9一二三四五六七八九十]+\s*[）)]', t))

def _docx_caption_parts(paragraphs, index, rels):
    text = _paragraph_text_xml(paragraphs[index])
    targets = []
    for j in range(index, max(-1, index - 10), -1):
        q = paragraphs[j]
        refs = _paragraph_media_targets(q, rels)
        if refs:
            targets.extend(refs)
            continue
        qtext = _paragraph_text_xml(q)
        if j == index or not qtext or _is_subcaption_line(qtext):
            continue
        break
    return _caption_parts_multi(text, photo_pair_anchored=len(set(targets)) >= 2)

def find_docx_caption_media(docx_path: Path) -> List[dict]:
    """Locate Word media immediately associated with each figure caption.

    Besides ordinary one-image figures, this recognizes two important production patterns:
    1) one logical figure assembled from several pictures plus (a)/(b) labels; and
    2) two side-by-side figures whose captions share one Word paragraph.

    Multi-image *single-caption* figures are marked as composites so process_one_word can crop
    the complete rendered group from the Word-generated PDF instead of extracting only one raw
    media file.  Multi-caption paragraphs intentionally fall back to PDF geometry, because that
    preserves Word's crop/recolor/layout and lets horizontal caption alignment choose the correct
    left/right picture.
    """
    if not docx_path.exists():
        return []
    try:
        with zipfile.ZipFile(docx_path) as z:
            root = ET.fromstring(z.read('word/document.xml'))
            relroot = ET.fromstring(z.read('word/_rels/document.xml.rels'))
            rels = {
                rel.attrib.get('Id'): rel.attrib.get('Target', '')
                for rel in relroot.findall('.//rel:Relationship', REL_NS)
            }
            paragraphs = root.findall('.//w:body//w:p', OOXML_NS)
            results = []
            for i, p in enumerate(paragraphs):
                caps = _docx_caption_parts(paragraphs, i, rels)
                if not caps:
                    continue

                # Collect media across a short block immediately above the caption.  Allow
                # (a)/(b) label paragraphs between rows, but stop at prose/table captions.
                refs_with_pos = []
                for j in range(i, max(-1, i - 10), -1):
                    q = paragraphs[j]
                    refs = _paragraph_media_targets(q, rels)
                    qtext = _paragraph_text_xml(q)
                    if refs:
                        for order, target in enumerate(refs):
                            member = 'word/' + target.lstrip('/')
                            try:
                                size = z.getinfo(member).file_size
                            except KeyError:
                                size = 0
                            refs_with_pos.append((j, order, size, target, member))
                        continue
                    if j == i or not qtext:
                        continue
                    if _is_subcaption_line(qtext):
                        continue
                    break

                if not refs_with_pos:
                    continue
                refs_with_pos.sort(key=lambda x: (x[0], x[1]))
                members = [
                    {
                        'target': target,
                        'member': member,
                        'ext': Path(target).suffix.lower(),
                        'size': size,
                        'object_paragraph_index': j,
                    }
                    for j, order, size, target, member in refs_with_pos
                ]

                # Two captions + two pictures in the same Word paragraph are best recovered
                # from the rendered PDF, not raw media, because Word may apply crop/grayscale.
                if len(caps) > 1:
                    # Returning no direct-media candidate forces the PDF path.  The improved
                    # horizontal ranking in _nearby_raster_bbox maps left caption -> left image,
                    # right caption -> right image.
                    continue

                no, caption = caps[0]
                first = members[0]
                results.append({
                    'figure_no': no,
                    'caption': caption,
                    'target': first['target'],
                    'member': first['member'],
                    'ext': first['ext'],
                    'paragraph_index': i,
                    'object_paragraph_index': first['object_paragraph_index'],
                    'members': members,
                    'member_count': len(members),
                    'composite': len(members) > 1,
                })
            return results
    except Exception:
        logging.exception('解析 DOCX 图对象关系失败: %s', docx_path)
        return []
