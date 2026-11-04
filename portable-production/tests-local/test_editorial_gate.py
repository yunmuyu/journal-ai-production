"""Synthetic source-bound publication-gate tests; no customer assets."""
import copy
from pathlib import Path
import pytest
from localflow.core import Config,FlowError,hash_file,hash_json,write_json
import localflow.editorial_gate as gate
from journal_preflight.editorial_route import COMMON_CHECKS,ROUTE_CHECKS


def fixture(tmp_path,monkeypatch,route='structural_redraw',source_name='source.txt'):
    src=tmp_path/'sources';src.mkdir();file=src/source_name;file.write_text('synthetic source')
    if source_name.endswith('.pdf'):
        import fitz
        with fitz.open() as document:
            page=document.new_page(width=200,height=100)
            page.insert_text((20,40),'Node A -> Node B')
            document.save(file)
    digest=hash_file(file);cid='a'*32;pid='b'*64
    config=Config(tmp_path/'delivery',tmp_path/'state',tmp_path/'unused-fonts',tmp_path/'cache')
    figure={'id':'figure-1','sources':[{'id':'source','sha256':digest}],
      'decision':{'proposed':{'route':route,'column':'single'},'route':route,'column':'single','reason':'Synthetic source-based route decision.','overrides':[]},
      'evidence':[{'id':'e1','source_id':'source','source_sha256':digest,'method':'synthetic test','location':'whole source','observation':'Source checked only for test routing.'}],
      'checks':{name:{'status':'recorded_satisfied','evidence_ids':['e1']} for name in COMMON_CHECKS+ROUTE_CHECKS[route]},'author_issues':[]}
    figure['text_review']={'requirement':'preserve_native','categories':['other'],
        'reason':'Synthetic source text is preserved verbatim for this routing test.','evidence_ids':['e1']}
    if route=='plot_reletter': figure['text_review']['requirement']='replace'
    figure['source_review']={'source_snapshot':{'source':digest},
        'structure':{'structural_redraw':'node_link','plot_reletter':'plot','raster_grayscale_single_column':'ui','unresolved':'unknown'}[route],
        'text_requirement':figure['text_review']['requirement'],
        'data_preservation':'not_applicable' if route=='structural_redraw' else 'required',
        'topology':'reconstructable' if route=='structural_redraw' else 'not_applicable',
        'evidence':[{'source_id':'source','source_sha256':digest,'location':'whole synthetic fixture','observation':'Recorded test structure and text needs.'}]}
    constraints={'confirmed':{'column':'single','editorial_route_contract':{'schema_version':'editorial-route/1','figures':[figure]},'editorial_figure_id':'figure-1','editorial_targets':[{'id':'figure-1','author_rel':'editor/author','figure_number':'1'}]}}
    folder=config.state_root/'candidates'/cid
    write_json(folder/'constraints.json',constraints);write_json(folder/'spec.json',{'author_rel':'editor/author','figure_number':'1'})
    write_json(config.state_root/'probes'/pid/'evidence'/'probe.json',{'assets':[]})
    seal={'source_root':str(src),'sources':{source_name:digest},'identity':{'source':source_name}}
    monkeypatch.setattr(gate,'check_snapshot',lambda *_:seal)
    candidate={'candidate_id':cid,'probe_id':pid,'constraints_sha256':hash_json(constraints)}
    report={'source_bindings':[{'path':source_name,'sha256':digest}]}
    def save():
        write_json(folder/'constraints.json',constraints);candidate['constraints_sha256']=hash_json(constraints)
    return config,candidate,report,constraints,save,file


@pytest.mark.parametrize('route,fmt',[('structural_redraw','pdf'),('plot_reletter','pdf'),('raster_grayscale_single_column','jpg')])
def test_live_source_complete_contract_passes_but_never_accepts(tmp_path,monkeypatch,route,fmt):
    c,k,r,_,_,_=fixture(tmp_path,monkeypatch,route)
    result=gate.check_editorial_gate(c,k,r,fmt)
    assert result['status']=='editorial-contract-passed'
    assert result['acceptance']=='not_recorded' and result['ready_for_publication'] is False


def test_old_candidate_without_contract_blocks_publication(tmp_path,monkeypatch):
    c,k,r,d,save,_=fixture(tmp_path,monkeypatch);d['confirmed'].clear();save()
    with pytest.raises(FlowError,match='发布必须'):gate.check_editorial_gate(c,k,r)


def test_contract_cannot_change_without_constraints_hash(tmp_path,monkeypatch):
    c,k,r,d,save,_=fixture(tmp_path,monkeypatch);d['confirmed'].clear();write_json(c.state_root/'candidates'/k['candidate_id']/'constraints.json',d)
    with pytest.raises(FlowError,match='哈希'):gate.check_editorial_gate(c,k,r)


def test_unresolved_route_blocks(tmp_path,monkeypatch):
    c,k,r,_,_,_=fixture(tmp_path,monkeypatch,'unresolved')
    with pytest.raises(FlowError,match='尚未解决'):gate.check_editorial_gate(c,k,r)


def test_live_source_changes_block(tmp_path,monkeypatch):
    c,k,r,_,_,file=fixture(tmp_path,monkeypatch);file.write_text('changed')
    with pytest.raises(FlowError,match='尚未解决'):gate.check_editorial_gate(c,k,r)


@pytest.mark.parametrize('fmt',['jpg','jpeg','tiff'])
def test_wrong_artifact_route_blocks(tmp_path,monkeypatch,fmt):
    c,k,r,_,_,_=fixture(tmp_path,monkeypatch)
    with pytest.raises(FlowError,match='格式'):gate.check_editorial_gate(c,k,r,fmt)


@pytest.mark.parametrize('change',['missing','duplicate','target','extra'])
def test_target_inventory_fail_closed(tmp_path,monkeypatch,change):
    c,k,r,d,save,_=fixture(tmp_path,monkeypatch);a=d['confirmed']['editorial_targets']
    if change=='missing':a[0]['id']='other'
    elif change=='duplicate':a.append(copy.deepcopy(a[0]))
    elif change=='target':a[0]['figure_number']='2'
    else:a[0]['unknown']=True
    save()
    with pytest.raises(FlowError):gate.check_editorial_gate(c,k,r)


def test_candidate_source_set_must_match_selected_figure(tmp_path,monkeypatch):
    c,k,r,_,_,_=fixture(tmp_path,monkeypatch);r['source_bindings']=[]
    with pytest.raises(FlowError,match='来源集合'):gate.check_editorial_gate(c,k,r)


def test_unextracted_docx_caption_still_blocks_incomplete_inventory(tmp_path,monkeypatch):
    c,k,r,_,_,_=fixture(tmp_path,monkeypatch)
    write_json(c.state_root/'probes'/k['probe_id']/'evidence'/'probe.json',{'assets':[{'id':'source','probe':{'kind':'docx','figures':[{'number':'1'}],'unmapped_figure_captions':[{'number':'2'}]}}]})
    with pytest.raises(FlowError,match='完整解释'):gate.check_editorial_gate(c,k,r)


def test_duplicate_caption_requires_inventory_resolution(tmp_path,monkeypatch):
    c,k,r,_,_,_=fixture(tmp_path,monkeypatch)
    write_json(c.state_root/'probes'/k['probe_id']/'evidence'/'probe.json',{'assets':[{'id':'source','probe':{'kind':'docx','figures':[{'number':'1'},{'number':'1'}]}}]})
    with pytest.raises(FlowError,match='重复'):gate.check_editorial_gate(c,k,r)


def test_route_column_cannot_disagree_with_confirmed_output(tmp_path,monkeypatch):
    c,k,r,d,save,_=fixture(tmp_path,monkeypatch);d['confirmed']['column']='double';save()
    with pytest.raises(FlowError,match='栏宽'):gate.check_editorial_gate(c,k,r)

@pytest.mark.parametrize('requirement', ['missing', 'unknown', 'replace'])
def test_text_treatment_blocks_actual_publication_gate(tmp_path, monkeypatch, requirement):
    c,k,r,d,save,_=fixture(tmp_path,monkeypatch,'raster_grayscale_single_column')
    figure=d['confirmed']['editorial_route_contract']['figures'][0]
    del figure['source_review']
    if requirement=='missing': del figure['text_review']
    else: figure['text_review'].update(requirement=requirement,categories=['tick_label'])
    save()
    with pytest.raises(FlowError,match='尚未解决'):
        gate.check_editorial_gate(c,k,r,'jpg')

@pytest.mark.parametrize('structure', ['missing', 'plot', 'node_link'])
def test_real_gate_rejects_missing_or_conflicting_structure_for_gray(tmp_path, monkeypatch, structure):
    c,k,r,d,save,_=fixture(tmp_path,monkeypatch,'raster_grayscale_single_column')
    figure=d['confirmed']['editorial_route_contract']['figures'][0]
    del figure['source_review']
    if structure != 'missing':
        figure['source_review']={'source_snapshot':{s['id']:s['sha256'] for s in figure['sources']},
            'structure':structure,'text_requirement':'replace',
            'data_preservation':'required' if structure=='plot' else 'not_applicable',
            'topology':'not_applicable' if structure=='plot' else 'reconstructable',
            'evidence':[{'source_id':'source','source_sha256':figure['sources'][0]['sha256'],
                         'location':'synthetic source','observation':'Recorded source structure, independent of extension.'}]}
        figure['text_review']['requirement']='replace'
    save()
    with pytest.raises(FlowError):
        gate.check_editorial_gate(c,k,r,'jpg')


def test_real_publication_gate_keeps_pdf_node_link_structural(tmp_path, monkeypatch):
    # Given: an actual generated PDF source whose recorded semantics are node-link.
    c,k,r,d,save,file=fixture(tmp_path,monkeypatch,'structural_redraw',source_name='source.pdf')
    assert file.read_bytes().startswith(b'%PDF')
    # When: checking the ordinary localflow publication gate.
    result=gate.check_editorial_gate(c,k,r,'pdf')
    # Then: PDF source does not imply raster; the explicit structural route passes.
    assert result['status']=='editorial-contract-passed'


def test_native_text_preservation_does_not_justify_grayscaling_node_link(tmp_path, monkeypatch):
    c,k,r,d,save,_=fixture(tmp_path,monkeypatch,'raster_grayscale_single_column',source_name='source.pdf')
    figure=d['confirmed']['editorial_route_contract']['figures'][0]
    figure['source_review'].update(structure='node_link',data_preservation='not_applicable',topology='reconstructable')
    save()
    with pytest.raises(FlowError,match='尚未解决'):
        gate.check_editorial_gate(c,k,r,'jpg')
