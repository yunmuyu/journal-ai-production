"""Synthetic source-bound publication-gate tests; no customer assets."""
import copy
from pathlib import Path
import pytest
from localflow.core import Config,FlowError,hash_file,hash_json,write_json
import localflow.editorial_gate as gate
from journal_preflight.editorial_route import COMMON_CHECKS,ROUTE_CHECKS


def fixture(tmp_path,monkeypatch,route='structural_redraw'):
    src=tmp_path/'sources';src.mkdir();file=src/'source.txt';file.write_text('synthetic source')
    digest=hash_file(file);cid='a'*32;pid='b'*64
    config=Config(tmp_path/'delivery',tmp_path/'state',tmp_path/'unused-fonts',tmp_path/'cache')
    figure={'id':'figure-1','sources':[{'id':'source','sha256':digest}],
      'decision':{'proposed':{'route':route,'column':'single'},'route':route,'column':'single','reason':'Synthetic source-based route decision.','overrides':[]},
      'evidence':[{'id':'e1','source_id':'source','source_sha256':digest,'method':'synthetic test','location':'whole source','observation':'Source checked only for test routing.'}],
      'checks':{name:{'status':'recorded_satisfied','evidence_ids':['e1']} for name in COMMON_CHECKS+ROUTE_CHECKS[route]},'author_issues':[]}
    constraints={'confirmed':{'column':'single','editorial_route_contract':{'schema_version':'editorial-route/1','figures':[figure]},'editorial_figure_id':'figure-1','editorial_targets':[{'id':'figure-1','author_rel':'editor/author','figure_number':'1'}]}}
    folder=config.state_root/'candidates'/cid
    write_json(folder/'constraints.json',constraints);write_json(folder/'spec.json',{'author_rel':'editor/author','figure_number':'1'})
    write_json(config.state_root/'probes'/pid/'evidence'/'probe.json',{'assets':[]})
    seal={'source_root':str(src),'sources':{'source.txt':digest},'identity':{'source':'source.txt'}}
    monkeypatch.setattr(gate,'check_snapshot',lambda *_:seal)
    candidate={'candidate_id':cid,'probe_id':pid,'constraints_sha256':hash_json(constraints)}
    report={'source_bindings':[{'path':'source.txt','sha256':digest}]}
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
