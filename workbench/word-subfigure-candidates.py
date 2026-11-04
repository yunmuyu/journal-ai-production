"""Propose Word subfigure numbers; never treat textual proximity as source binding."""
import hashlib
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MARKER = re.compile(r'[（(]([a-zA-Z])[）)]')


def discover(word: Path, number: str) -> dict:
    data = word.read_bytes()
    with ZipFile(word) as archive:
        if sum(item.file_size for item in archive.infolist()) > 128 * 1024 * 1024:
            raise RuntimeError('word_uncompressed_size_limit')
        root = ET.fromstring(archive.read('word/document.xml'))
    body = root.find('.//' + W + 'body')
    if body is None:
        raise RuntimeError('word_body_missing')
    paragraphs = list(body.iter(W + 'p'))
    texts = [''.join(t.text or '' for t in p.iter(W + 't')).strip() for p in paragraphs]
    caption = re.compile(r'^图\s*' + re.escape(number) + r'(?![\d.．\-－])')
    candidates = []
    for index, text in enumerate(texts):
        if not caption.match(text) or index == 0:
            continue
        previous = texts[index - 1]
        markers = list(MARKER.finditer(previous))
        if len(markers) < 2 or previous[:markers[0].start()].strip():
            continue
        labels = [m.group(1).lower() for m in markers]
        if labels != [chr(ord('a') + n) for n in range(len(labels))]:
            continue
        titles = [previous[m.end():markers[i + 1].start() if i + 1 < len(markers) else len(previous)].strip() for i, m in enumerate(markers)]
        if any(not title for title in titles):
            continue
        candidates.append({'caption': text, 'paragraph': index, 'labelsParagraph': index - 1,
                           'outputs': [{'number': f'{number}.{i + 1}', 'marker': f'({label})', 'title': titles[i]} for i, label in enumerate(labels)]})
    return {'wordSha256': hashlib.sha256(data).hexdigest(), 'figureNumber': number,
            'status': 'candidate' if len(candidates) == 1 else 'ambiguous' if candidates else 'not_detected',
            'candidates': candidates, 'warning': '子图题仅为候选；来源区域和语义须另行绑定'}


if __name__ == '__main__':
    print(json.dumps(discover(Path(sys.argv[1]), sys.argv[2]), ensure_ascii=False))
