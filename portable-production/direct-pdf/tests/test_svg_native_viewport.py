import pytest
from journal_pdf.agent_entry import prepare
from journal_pdf.common import read_json
from journal_pdf.ingest_native import svg_pages
from journal_pdf.agent_spec import compile_reply_figure

def test_absolute_pixel_viewport_without_viewbox(tmp_path):
    source = tmp_path / 'source.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><path d="M0 0L200 100"/></svg>', encoding='utf-8')
    result = prepare([str(source)], tmp_path / 'job')
    evidence = read_json(tmp_path / 'job' / 'evidence' / 'source-1' / 'evidence.json')
    assert evidence['status'] != 'blocked'
    assert len(evidence['pages']) == 1

def test_relative_viewport_remains_blocked(tmp_path):
    source = tmp_path / 'source.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"/>', encoding='utf-8')
    prepare([str(source)], tmp_path / 'job')
    evidence = read_json(tmp_path / 'job' / 'evidence' / 'source-1' / 'evidence.json')
    assert evidence['error']['code'] == 'svg_viewbox_required'

def test_generic_svg_exposes_native_text_and_shapes_without_inventing_links(tmp_path):
    source = tmp_path / 'source.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><g transform="translate(10 20)"><path d="M0 0L20 0"/><text x="4" y="8">Hello<tspan> world</tspan></text><text x="4" y="30">Hello</text></g></svg>', encoding='utf-8')
    page = svg_pages(source, tmp_path)[0]
    objects = page['objects']
    assert [o['text'] for o in objects if o.get('text')] == ['Hello world', 'Hello']
    assert len({o['id'] for o in objects}) == len(objects)
    assert all(o.get('from_ref') is None and o.get('to_ref') is None for o in objects)
    assert any(o['kind'] == 'svg-geometry' for o in objects)
    assert all('translate(10 20)' in o['transform'] for o in objects)

def test_svg_text_objects_bind_existing_diagram_compiler(tmp_path):
    source = tmp_path / 'source.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><text x="4" y="8">Start</text><text x="4" y="30">End</text></svg>', encoding='utf-8')
    page = svg_pages(source, tmp_path)[0]
    texts = [o for o in page['objects'] if o.get('text')]
    reply = {'id':'sample','author':'test','kind':'diagram','review':{'source_checked':True,'labels_checked':True,'topology_checked':True},'nodes':[{'id':'a','ref':texts[0]['id']},{'id':'b','ref':texts[1]['id']}],'edges':[{'from':'a','to':'b'}]}
    result = compile_reply_figure(reply, {'id':'s','snapshot':str(source),'sha256':'a'*64}, page)
    assert [n['text'] for n in result['nodes']] == ['Start','End']
