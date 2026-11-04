import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest


CHECKER = Path(__file__).with_name('verify-word-output-set.py')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'


@pytest.fixture
def grouped(tmp_path):
    word=tmp_path/'source.docx'
    blobs=[b'picture-one',b'picture-two',b'picture-three',b'picture-four']
    paragraphs=[]
    for row in ((1,2),(3,4)):
        drawings=''.join(f'<w:r><w:drawing><wp:inline><a:graphic><a:blip r:embed="rId{i}"/></a:graphic></wp:inline></w:drawing></w:r>' for i in row)
        paragraphs.append('<w:p>'+drawings+'</w:p>')
    paragraphs += ['<w:p><w:r><w:t>(a) Foo (b) Bar</w:t></w:r></w:p>','<w:p><w:r><w:t>图5 Example</w:t></w:r></w:p>']
    document=f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="{A}" xmlns:wp="{WP}"><w:body>{"".join(paragraphs)}</w:body></w:document>'
    relationships='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Target="media/image{i}.png"/>' for i in range(1,5))+'</Relationships>'
    with ZipFile(word,'w') as z:
        z.writestr('word/document.xml',document);z.writestr('word/_rels/document.xml.rels',relationships)
        for i,b in enumerate(blobs,1):z.writestr(f'word/media/image{i}.png',b)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    parts=[]
    for i,b in enumerate(blobs,1):
        p=tmp_path/f'source{i}.png';p.write_bytes(b)
        parts.append({'wordMedia':f'word/media/image{i}.png','wordMediaSha256':sha(b),'source':{'path':str(p),'sha256':sha(b)}})
    outputs=[{'number':'5.1','captionMarker':'(a)','subcaption':'Foo','basis':'visual row-column mapping','members':[parts[0],parts[2]]},
             {'number':'5.2','captionMarker':'(b)','subcaption':'Bar','basis':'visual row-column mapping','members':[parts[1],parts[3]]}]
    evidence={'version':1,'articleId':'A','figureNumber':'5','caption':'图5 Example','word':{'path':str(word),'sha256':sha(word.read_bytes())},'grouping':'word-inline-columns','outputs':outputs}
    return word,evidence,tmp_path/'evidence.json'


def run(grouped):
    word,evidence,path=grouped;path.write_text(json.dumps(evidence),encoding='utf8')
    return subprocess.run([sys.executable,str(CHECKER),str(word),str(path)],capture_output=True,text=True)


def test_two_subfigures_can_bind_multiple_word_images(grouped):
    assert run(grouped).returncode == 0


def test_swapped_or_missing_media_is_rejected(grouped):
    grouped[1]['outputs'][0]['members'].reverse()
    assert run(grouped).returncode != 0


def test_duplicate_or_changed_source_is_rejected(grouped):
    grouped[1]['outputs'][0]['members'][1]['source']['sha256']='0'*64
    assert run(grouped).returncode != 0
