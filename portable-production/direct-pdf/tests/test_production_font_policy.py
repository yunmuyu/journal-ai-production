"""Production semantic entry starts at 8pt; low-level previews remain legitimate."""
import pytest
from journal_pdf.agent_spec import compile_reply_figure
from journal_pdf.agent_entry import prepare,complete
from journal_pdf.common import FigureError,digest_json,read_json
from journal_pdf.render import compile_figure
from journal_pdf.rules_registry import rule_evidence
from test_ingest_v020 import source_pdf,reply_for_job


@pytest.fixture
def semantic():
    source={'id':'source-1','snapshot':'source.pdf','sha256':'a'*64}
    page={'id':'page-1','kind':'pdf','objects':[{'id':'text-a','text':'A'}]}
    reply={'id':'figure','author':'Synthetic','source_id':source['id'],'page_id':page['id'],
           'kind':'diagram','review':{'source_checked':True,'labels_checked':True,'topology_checked':True},
           'nodes':[{'id':'a','ref':'text-a','shape':'rectangle'}],'edges':[]}
    return reply,source,page


def policy_exception(reply,source):
    return {'reply_sha256':digest_json(reply),'source_sha256':source['sha256'],
            'design_font_size_pt':reply['policy']['design_font_size_pt'],
            'reason':'Synthetic test of a separately authorized production exception',
            'evidence_ref':'test-approval-record:font-size-exception'}


def font_rule_states(spec,scene):
    audit={'axis_unit_notation':{'ok':True},'numeric_grouping_in_actual_pdf':True,
           'effective_path_strokes_05pt':True,'editable_text_pure_black':True,
           'all_fonts_embedded':True,'neutral_rgb_300dpi':True}
    result={'layout':scene.export(),'pdf_audit':audit}
    return {r['id']:r['status'] for r in rule_evidence(spec,result)['rules']}


@pytest.mark.parametrize('size',[6,6.4,7,7.99])
def test_semantic_reply_cannot_choose_smaller_start(semantic,size):
    reply,source,page=semantic;reply['policy']={'design_font_size_pt':size}
    with pytest.raises(FigureError) as error:compile_reply_figure(reply,source,page)
    assert error.value.code=='production_font_policy_required'


def test_default_and_explicit_eight_continue(semantic):
    reply,source,page=semantic
    for policy in ({},{'design_font_size_pt':8}):
        reply['policy']=policy;spec=compile_reply_figure(reply,source,page)
        assert spec['policy']['design_font_size_pt']==8
        assert spec['ingest_provenance']['production_font_policy']=={'design_font_size_pt':8,'basis':'default-8pt'}


@pytest.mark.parametrize('size',[6,6.4,7.99])
def test_separate_bound_exception_allows_lower_design_size(semantic,size):
    reply,source,page=semantic;reply['policy']={'design_font_size_pt':size}
    exception=policy_exception(reply,source)
    spec=compile_reply_figure(reply,source,page,production_policy_exception=exception)
    assert spec['policy']['design_font_size_pt']==size
    recorded=spec['ingest_provenance']['production_font_policy']
    assert recorded['basis']=='explicit-production-policy-exception' and recorded['exception']==exception
    exception['reason']='changed after compilation'
    assert recorded['exception']['reason']!='changed after compilation'


@pytest.mark.parametrize('field,value',[
    ('source_sha256','b'*64),('reply_sha256','b'*64),('design_font_size_pt',7),
    ('reason',''),('evidence_ref',''),('source_sha256',None),('design_font_size_pt',True),
])
def test_exception_must_bind_current_source_reply_size_and_evidence(semantic,field,value):
    reply,source,page=semantic;reply['policy']={'design_font_size_pt':6}
    exception=policy_exception(reply,source);exception[field]=value
    with pytest.raises(FigureError):compile_reply_figure(reply,source,page,production_policy_exception=exception)


@pytest.mark.parametrize('location',['figure','policy'])
def test_reply_cannot_self_authorize_exception(semantic,location):
    reply,source,page=semantic;reply['policy']={'design_font_size_pt':6}
    target=reply if location=='figure' else reply['policy']
    target['production_policy_exception']=policy_exception(reply,source)
    with pytest.raises(FigureError) as error:compile_reply_figure(reply,source,page)
    assert error.value.code in ('semantic_unknown_fields','policy_unknown')


@pytest.mark.parametrize('coordinate',['x','rect','row_gap_pt'])
def test_bound_exception_does_not_allow_manual_node_geometry(semantic,coordinate):
    reply,source,page=semantic;reply['policy']={'design_font_size_pt':6}
    reply['nodes'][0][coordinate]=70
    with pytest.raises(FigureError) as error:
        compile_reply_figure(reply,source,page,production_policy_exception=policy_exception(reply,source))
    assert error.value.code=='diagram_node_schema'


def test_unsupported_native_shape_still_blocks(semantic):
    reply,source,page=semantic;reply['nodes'][0]['shape']='unsupported-special-symbol'
    with pytest.raises(FigureError) as error:compile_reply_figure(reply,source,page)
    assert error.value.code=='shape_not_supported'


@pytest.mark.parametrize('size',[6,6.5,8])
def test_low_level_preview_keeps_explicit_size_and_truthful_ledger(reg,tmp_path,size):
    spec={'kind':'graph','nodes':[{'id':'a','text':'A'}],'edges':[],
          'policy':{'design_font_size_pt':size}}
    scene=compile_figure(spec,reg,None,tmp_path);evidence=scene.layout_evidence
    assert evidence['initial_design_font_size_pt']==size
    assert evidence['fit_attempts'][0]['design_font_size_pt']==size
    assert evidence['final_font_size_pt']==size
    states=font_rule_states(spec,scene)
    assert states['whole-artwork-default8-min6']==('checked' if size==8 else 'pending')
    if size<8:
        assert 'default-8pt-first' not in evidence['priority']
        assert states['explicit-design-size-policy-exception']=='pending'


def test_measured_whole_artwork_scaling_from_eight_still_passes(reg,tmp_path):
    spec={'kind':'scene','width_pt':260,'height_pt':40,
          'texts':[{'id':'a','text':'A','x':20,'y':20}]}
    scene=compile_figure(spec,reg,None,tmp_path);evidence=scene.layout_evidence
    assert evidence['initial_design_font_size_pt']==8 and evidence['initial_design_width_pt']==260
    assert 6<evidence['final_font_size_pt']<8 and evidence['whole_artwork_scale']<1
    assert font_rule_states(spec,scene)['whole-artwork-default8-min6']=='checked'


@pytest.mark.parametrize('tamper',['tag-only','missing-initial','attempt','scale','declared'])
def test_ledger_does_not_trust_priority_or_final_range(reg,tmp_path,tamper):
    spec={'kind':'graph','nodes':[{'id':'a','text':'A'}],'edges':[],
          'policy':{'design_font_size_pt':6 if tamper=='tag-only' else 8}}
    scene=compile_figure(spec,reg,None,tmp_path);evidence=scene.layout_evidence
    if tamper=='tag-only':evidence['priority']='default-8pt-first'
    elif tamper=='missing-initial':del evidence['initial_design_font_size_pt']
    elif tamper=='attempt':evidence['fit_attempts'][0]['design_font_size_pt']=6
    elif tamper=='scale':evidence['whole_artwork_scale']=.8
    elif tamper=='declared':spec['policy']['design_font_size_pt']=6
    assert font_rule_states(spec,scene)['whole-artwork-default8-min6']=='pending'


def test_exception_has_distinct_ledger_not_false_eight_first(semantic,reg,tmp_path):
    reply,source,page=semantic;reply['policy']={'design_font_size_pt':6}
    spec=compile_reply_figure(reply,source,page,production_policy_exception=policy_exception(reply,source))
    scene=compile_figure(spec,reg,None,tmp_path);states=font_rule_states(spec,scene)
    assert states['whole-artwork-default8-min6']=='pending'
    assert states['explicit-design-size-policy-exception']=='checked'
    spec['ingest_provenance']['production_font_policy']['exception']['source_sha256']='b'*64
    assert font_rule_states(spec,scene)['explicit-design-size-policy-exception']=='pending'


def test_complete_blocks_manual_six_then_records_separate_exception(tmp_path,profile):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job);reply=reply_for_job(job)
    figure=reply['figures'][0];figure['policy']={'design_font_size_pt':6}
    blocked=complete(job,reply,profile,cache=tmp_path/'cache')
    assert blocked['rendered']==0
    assert blocked['failures'][0]['error']['code']=='production_font_policy_required'
    source=read_json(job/'job.json')['sources'][0];exception=policy_exception(figure,source)
    accepted=complete(job,reply,profile,cache=tmp_path/'cache',production_policy_exceptions=[exception])
    assert accepted['rendered']==1 and not accepted['failures']
    assert accepted['production_policy_exceptions']==[exception]
    assert read_json(job/'attempt-02/production-policy-exceptions.json')==[exception]
    state=read_json(job/'job.json')
    assert state['attempts'][-1]['production_policy_exceptions_sha256']==accepted['production_policy_exceptions_sha256']
    result=accepted['results'][0];spec=read_json(job/'attempt-02/specs/1.json')
    assert spec['ingest_provenance']['production_font_policy']['exception']==exception
    assert result['layout']['layout_evidence']['initial_design_font_size_pt']==6
    states={r['id']:r['status'] for r in result['rule_evidence']['rules']}
    assert states['whole-artwork-default8-min6']=='pending' and states['explicit-design-size-policy-exception']=='checked'
    assert not accepted['ready_for_publication']
    third=complete(job,reply,profile,cache=tmp_path/'cache')
    assert third['rendered']==0 and third['failures'][0]['error']['code']=='production_font_policy_required'


def test_unused_or_duplicate_exception_rejected_before_attempt(tmp_path,profile):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job);reply=reply_for_job(job)
    figure=reply['figures'][0];figure['policy']={'design_font_size_pt':6}
    source=read_json(job/'job.json')['sources'][0];exception=policy_exception(figure,source)
    for rows in ([dict(exception,reply_sha256='b'*64)],[exception,exception]):
        with pytest.raises(FigureError) as error:complete(job,reply,profile,production_policy_exceptions=rows)
        assert error.value.code=='production_policy_exception_binding'
        assert not list(job.glob('attempt-*'))


def test_recorded_policy_evidence_cannot_change_before_retry(tmp_path,profile):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job);reply=reply_for_job(job)
    reply['figures'][0]['policy']={'design_font_size_pt':6}
    complete(job,reply,profile)
    (job/'attempt-01/production-policy-exceptions.json').write_text('[{}]')
    with pytest.raises(FigureError) as error:complete(job,reply,profile)
    assert error.value.code=='production_policy_exception_changed'


def test_run_with_agent_forwards_separate_caller_records(tmp_path,monkeypatch):
    from journal_pdf import agent_entry
    from journal_pdf.common import atomic_json
    brief=tmp_path/'brief.json';atomic_json(brief,{'protocol':'synthetic'})
    monkeypatch.setattr(agent_entry,'prepare',lambda *a,**kw:{'brief':str(brief)})
    received={}
    def capture(job,reply,profile,**kwargs):received.update(kwargs);return {'reply':reply}
    monkeypatch.setattr(agent_entry,'complete',capture)
    records=[{'external':'caller-owned-test-record'}]
    result=agent_entry.run_with_agent([],tmp_path/'job',tmp_path/'font.json',lambda request:{'figures':[]},
                                      production_policy_exceptions=records)
    assert result['reply']=={'figures':[]} and received['production_policy_exceptions']==records


def test_cli_reads_exception_file_separately(tmp_path,monkeypatch,capsys):
    from journal_pdf import agent_entry
    from journal_pdf.cli import main
    from journal_pdf.common import atomic_json
    reply=tmp_path/'reply.json';approval=tmp_path/'approval.json'
    atomic_json(reply,{'figures':[]});atomic_json(approval,[{'external':'separate-test-record'}])
    received={}
    def capture(job,reply,profile,**kwargs):
        received.update(kwargs)
        return {'status':'partial-or-blocked','attempt':1,'rendered':0,'failures':[],
                'unresolved_exceptions':[],'declared_exclusions':[],'timings':{},'reused_unaffected_figures':0}
    monkeypatch.setattr(agent_entry,'complete',capture)
    assert main(['agent','complete','--job',str(tmp_path/'job'),'--reply',str(reply),
                 '--profile',str(tmp_path/'font.json'),'--production-policy-exceptions',str(approval)])==0
    assert received['production_policy_exceptions']==[{'external':'separate-test-record'}]


def test_copied_consistent_exception_is_not_bound_to_current_spec_sources(semantic, reg, tmp_path):
    reply, source, page = semantic
    reply['policy'] = {'design_font_size_pt': 6}
    spec = compile_reply_figure(reply, source, page, production_policy_exception=policy_exception(reply, source))
    scene = compile_figure(spec, reg, None, tmp_path)
    assert font_rule_states(spec, scene)['explicit-design-size-policy-exception'] == 'checked'
    # Both copied fields agree, but neither identifies this candidate's source.
    spec['ingest_provenance']['source_file_sha256'] = 'b' * 64
    spec['ingest_provenance']['production_font_policy']['exception']['source_sha256'] = 'b' * 64
    assert font_rule_states(spec, scene)['explicit-design-size-policy-exception'] == 'pending'
