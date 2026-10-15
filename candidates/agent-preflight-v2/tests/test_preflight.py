import base64,copy,io,json,urllib.parse,zlib
from pathlib import Path
from zipfile import ZipFile
import pytest
from PIL import Image
import pymupdf as fitz
from journal_preflight.probe import xml,sha,ProbeError,probe_svg,probe_pdf,document_images,scan,candidate_matches,safe_zip_member
from journal_preflight.routing import apply_review,bridge_legacy

MODEL='<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="a" vertex="1" value="A" parent="1"><mxGeometry x="1" y="2" width="40" height="20"/></mxCell><mxCell id="b" vertex="1" value="B" parent="1"/><mxCell id="e" edge="1" source="a" target="b"/></root></mxGraphModel>'
def svg_file(tmp_path,compressed=False,extra=''):
 import html
 if compressed:
  obj=zlib.compressobj(wbits=-15);payload=base64.b64encode(obj.compress(urllib.parse.quote(MODEL).encode())+obj.flush()).decode()
  content='<mxfile><diagram name="Diagram">'+payload+'</diagram></mxfile>'
 else:content='<mxfile><diagram name="Diagram">'+MODEL+'</diagram></mxfile>'
 s='<svg xmlns="http://www.w3.org/2000/svg" width="400px" height="300px" viewBox="0 0 400 300" content="'+html.escape(content,quote=True)+'"><switch><foreignObject><div xmlns="http://www.w3.org/1999/xhtml">A<sub>1</sub></div></foreignObject><image href="data:image/png;base64,eA=="/></switch>'+extra+'</svg>'
 p=tmp_path/'source.svg';p.write_text(s);return p
@pytest.mark.parametrize('compressed',[False,True])
def test_drawio_metadata_without_ocr(tmp_path,compressed):
 o=tmp_path/'out';o.mkdir();r=probe_svg(svg_file(tmp_path,compressed),o)
 assert r['kind']=='svg_drawio'
 assert r['drawio_pages'][0]['vertex_count']==2 and r['drawio_pages'][0]['edge_object_count']==1
 assert r['drawio_pages'][0]['bound_edge_count']==1
 assert not r['drawio_pages'][0]['semantic_topology_verified']
 assert r['image_count']==1 and r['text_fallback_image_count']==1 and r['scientific_raster_images_not_in_text_fallback']==0

def test_svg_active_content_and_external_not_auto_rendered(tmp_path):
 o=tmp_path/'out';o.mkdir();r=probe_svg(svg_file(tmp_path,extra='<script>bad()</script><image href="https://example.invalid/a.png"/>'),o)
 assert r['requires_sandbox_render'] and r['active_content_present'] and r['external_reference_count']==1

def test_unknown_terminal_not_repaired(tmp_path):
 p=svg_file(tmp_path);s=p.read_text().replace('target=&quot;b&quot;','target=&quot;unknown&quot;');p.write_text(s)
 o=tmp_path/'out';o.mkdir();r=probe_svg(p,o)
 assert r['drawio_pages'][0]['dangling_edges']==['e']

@pytest.mark.parametrize('data',[b'<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>',b'<!ENTITY bomb "xx"><r/>'])
def test_entities_rejected(data):
 with pytest.raises(ProbeError):xml(data)

def test_unsafe_zip_member_rejected(tmp_path):
 p=tmp_path/'x.zip'
 with ZipFile(p,'w') as z:z.writestr('../secret','a')
 with ZipFile(p) as z:
  with pytest.raises(ProbeError):safe_zip_member(z,'../secret')

def make_docx(tmp_path):
 a=io.BytesIO();Image.new('RGB',(400,300),'white').save(a,format='PNG')
 ns='xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
 body='<w:p><w:r><w:t>图9展示了其他信息</w:t></w:r></w:p><w:p><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p><w:p><w:r><w:t>图4-1 实验结果</w:t></w:r></w:p><w:p><w:r><w:object><a:blip r:embed="rId2"/></w:object></w:r></w:p><w:p><w:r><w:t>图5仅为正文引用</w:t></w:r></w:p>'
 p=tmp_path/'document.docx'
 with ZipFile(p,'w') as z:
  z.writestr('word/document.xml',f'<w:document {ns}><w:body>{body}</w:body></w:document>')
  z.writestr('word/_rels/document.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="media/a.png"/><Relationship Id="rId2" Target="media/b.png"/></Relationships>')
  z.writestr('word/media/a.png',a.getvalue());z.writestr('word/media/b.png',a.getvalue())
 return p

def test_caption_identity_not_filename_or_prose_or_formula(tmp_path):
 o=tmp_path/'out';o.mkdir();r=document_images(make_docx(tmp_path),o)
 assert [f['number'] for f in r['figures']]==['4-1'] and r['media_member_count']==2

def test_pdf_with_native_caption_not_native_chart(tmp_path):
 p=tmp_path/'chart.pdf';img=io.BytesIO();Image.new('RGB',(400,300),'white').save(img,format='PNG')
 d=fitz.open();pg=d.new_page();pg.insert_image(fitz.Rect(20,30,300,240),stream=img.getvalue());pg.insert_text((20,260),'Figure 3');d.save(p);d.close()
 o=tmp_path/'out';o.mkdir();r=probe_pdf(p,o)
 assert r['pages'][0]['content_kind']=='mixed_text_raster' and r['pages'][0]['vector_path_count']==0

def fixture_route():
 s={'assets':[{'id':'w','sha256':'a'*64,'probe':{'kind':'docx','figures':[{'number':'4-1','caption':'图4-1 测试'}]}},{'id':'s','sha256':'b'*64,'probe':{'kind':'pdf'}}]}
 f={'id':'item','identity':{'word_asset_id':'w','word_number':'4-1','verified':True},'sources':[{'asset_id':'s'}],
    'route':'raster_chart_preserve','layout':{'recommended_column':'single','confirmed_column':None,'locked':False,'capacity_verified':False},
    'export':{'scope_verified':True},'protection':{'rebuild_data_curves':False},'issues':[]}
 return s,{'snapshot':{'w':'a'*64,'s':'b'*64},'figures':[f]}

def test_candidate_never_publication():
 s,r=fixture_route();out=apply_review(s,r)
 assert not out['publication_performed'] and not out['figures'][0]['ready_for_publication'] and not out['ai_file_required']
 assert out['figures'][0]['caseRetrieval']['status']=='pending_local_records'
 assert not out['figures'][0]['benchmark']['include_in_blind_first_pass_benchmark']

@pytest.mark.parametrize('mutation', ['hash','number','unknown-source','route','locked','data'])
def test_reject_invalid_decisions(mutation):
 s,r=fixture_route();f=r['figures'][0]
 if mutation=='hash':r['snapshot']['s']='c'*64
 elif mutation=='number':f['identity']['word_number']='1'
 elif mutation=='unknown-source':f['sources'][0]['asset_id']='lost'
 elif mutation=='route':f['route']='invented'
 elif mutation=='locked':f['layout'].update(locked=True,confirmed_column='double')
 elif mutation=='data':f['protection']['rebuild_data_curves']=True
 with pytest.raises(ValueError):apply_review(s,r)

def test_confirmed_columns_remain_hard_constraints():
 s,r=fixture_route();r['figures'][0]['layout'].update(locked=True,confirmed_column='single')
 out=apply_review(s,r);assert out['figures'][0]['layout']['locked']

def test_legacy_bridge_is_additive_and_history_safe():
 s,r=fixture_route();report=apply_review(s,r)
 old={'figures':[{'id':'item','productionDecision':{'confirmed':True,'column':'double'},'aiProposal':{'caseRetrieval':{'matches':['old']},'userCorrectionContext':{'column':'double'}}},{'id':'other','productionDecision':{'accepted':True}}]}
 before=copy.deepcopy(old);new=bridge_legacy(old,report)
 assert old==before
 assert new['figures'][0]['productionDecision']==before['figures'][0]['productionDecision']
 assert new['figures'][0]['aiProposal']['caseRetrieval']==before['figures'][0]['aiProposal']['caseRetrieval']
 assert new['figures'][0]['aiProposal']['userCorrectionContext']==before['figures'][0]['aiProposal']['userCorrectionContext']
 assert new['figures'][1]==before['figures'][1]
 assert 'preflightV2' in new['figures'][0]['aiProposal']

def test_content_issue_does_not_modify_source():
 s,r=fixture_route();r['figures'][0]['issues']=[{'id':'mismatch','scope':'content','status':'unresolved','blocks_publication':True}]
 before=copy.deepcopy(r);out=apply_review(s,r)
 assert r==before
 assert next(g for g in out['figures'][0]['gates'] if g['id']=='content_consistency')['status']=='pending'

def test_dimension_match_is_not_verified_identity(tmp_path):
 o=tmp_path/'out';d=make_docx(tmp_path);v=svg_file(tmp_path)
 report=scan({'files':[{'id':'doc','path':str(d)},{'id':'svg','path':str(v)}]},o)
 match=report['matching_candidates'][0]
 assert match['decision']=='needs_agent_visual_review'
 assert not match['candidates'][0]['identity_verified']
 assert report['ocr_calls']==0 and report['font_directory_scans']==0

def test_duplicate_ids_rejected(tmp_path):
 p=svg_file(tmp_path)
 with pytest.raises(ProbeError):scan({'files':[{'id':'x','path':str(p)},{'id':'x','path':str(p)}]},tmp_path/'out')


def test_live_hash_checks_the_actual_file_not_two_stale_jsons(tmp_path):
 from journal_preflight.probe import sha
 s,r=fixture_route();w=tmp_path/'w';q=tmp_path/'s';w.write_bytes(b'w');q.write_bytes(b's')
 s['assets'][0]['sha256']=sha(b'w');s['assets'][1]['sha256']=sha(b's')
 r['snapshot']={a['id']:a['sha256'] for a in s['assets']}
 m={'files':[{'id':'w','path':str(w)},{'id':'s','path':str(q)}]}
 assert apply_review(s,r,m)['live_source_verification']['status']=='verified'
 q.write_bytes(b'changed')
 with pytest.raises(ValueError,match='Live source hash'):apply_review(s,r,m)


def test_no_live_manifest_is_explicitly_pending():
 s,r=fixture_route();out=apply_review(s,r)
 assert next(g for g in out['figures'][0]['gates'] if g['id']=='live_source_snapshot')['status']=='pending'
 assert out['screening_scope']['asset_count']==2
 assert out['figures'][0]['benchmark']['cohort']=='unclassified'


@pytest.mark.parametrize('selector',[{'member':'word/media/fake.png'},{'page':17},{'image_object_index':1}])
def test_unseen_media_page_or_image_reference_rejected(selector):
 s,r=fixture_route();r['figures'][0]['sources'][0].update(selector)
 with pytest.raises(ValueError):apply_review(s,r)


def test_pdf_cannot_claim_native_graph_route():
 s,r=fixture_route();f=r['figures'][0];f['selected_primary']={'asset_id':'s'};f['route']='drawio_native_relayout'
 with pytest.raises(ValueError,match='native graph'):apply_review(s,r)


def test_primary_must_be_in_provenance():
 s,r=fixture_route();r['figures'][0]['selected_primary']={'asset_id':'w'}
 with pytest.raises(ValueError,match='provenance'):apply_review(s,r)


def test_duplicate_caption_needs_disambiguation():
 s,r=fixture_route();s['assets'][0]['probe']['figures'].append({'number':'4-1','caption':'Duplicate'})
 with pytest.raises(ValueError,match='Duplicate Word'):apply_review(s,r)


def test_bridge_records_conflict_and_keeps_old_proposal_history():
 s,r=fixture_route();out=apply_review(s,r)
 old={'figures':[{'id':'item','productionDecision':{'confirmed':True,'column':'double'},'aiProposal':{'preflightV2':{'id':'old-proposal'}}}]}
 new=bridge_legacy(old,out)['figures'][0]
 assert new['aiProposal']['preflightV2']['legacy_constraint_check']['status']=='conflict'
 assert new['aiProposal']['preflightV2History']==[{'id':'old-proposal'}]
 assert new['productionDecision']==old['figures'][0]['productionDecision']


def test_standalone_raster_probed_and_never_ocrd(tmp_path):
 p=tmp_path/'raster.png';Image.new('RGB',(400,300),'white').save(p)
 result=scan({'files':[{'id':'r','path':str(p)}]},tmp_path/'out')
 assert result['assets'][0]['probe']['kind']=='raster'
 assert not result['assets'][0]['probe']['semantic_text_extracted']
 assert result['font_directory_scans']==0 and result['ocr_calls']==0
 with pytest.raises(ProbeError,match='fresh evidence'):scan({'files':[{'id':'r','path':str(p)}]},tmp_path/'out')


def test_same_bridge_twice_is_idempotent():
 s,r=fixture_route();report=apply_review(s,r)
 old={'figures':[{'id':'item','productionDecision':{'confirmed':True,'column':'double'},'aiProposal':{}}]}
 once=bridge_legacy(old,report)
 assert bridge_legacy(once,report)==once


def test_svg_without_viewbox_is_not_guessed_or_crashed(tmp_path):
 p=tmp_path/'plain.svg';p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><text x="1" y="20">A</text></svg>')
 r=scan({'files':[{'id':'s','path':str(p)}]},tmp_path/'out')
 assert r['assets'][0]['probe']['kind']=='svg' and r['matching_candidates']==[]
