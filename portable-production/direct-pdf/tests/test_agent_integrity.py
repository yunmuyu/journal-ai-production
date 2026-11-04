"""Negative cases: report integrity, dropped inputs, unresolved exceptions, retries."""
from pathlib import Path
import copy
import pytest
from journal_pdf.common import FigureError, read_json, atomic_json
from journal_pdf.agent_entry import prepare, complete, review
from test_ingest_v020 import source_pdf, reply_for_job


def finish(tmp_path, profile, exceptions=None):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job);rep=reply_for_job(job)
    if exceptions is not None:rep['exceptions']=exceptions
    return job,rep,complete(job,rep,profile,cache=tmp_path/'cache')


def visual_items(report):
    return [{'id':r['id'],'author':r['author'],'passed':True,
             'evidence':'attempt-01/output/'+r['preview'],
             'notes':'Synthetic output test, not user acceptance'} for r in report['results']]


@pytest.mark.parametrize('figures',[None,'invalid',[None],[0],[{'id':3}],[{'id':'a','author':4}]])
def test_bad_figure_envelope_does_not_create_attempt(tmp_path,profile,figures):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job);rep=reply_for_job(job);rep['figures']=figures
    with pytest.raises(FigureError):complete(job,rep,profile)
    assert not list(job.glob('attempt-*'))


def test_missing_profile_does_not_leave_running_state(tmp_path,profile):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job)
    with pytest.raises(FigureError) as exc:complete(job,reply_for_job(job),tmp_path/'missing.json')
    assert exc.value.code=='font_profile_missing'
    assert read_json(job/'job.json')['status']=='awaiting-agent' and not list(job.glob('attempt-*'))


@pytest.mark.parametrize('rows',[{},[None],[{'source_id':'fake','reason':'x'}],
    [{'source_id':'source-1','reason':''}], [{'source_id':'source-1','reason':'x','command':'bad'}],
    [{'source_id':'source-1','reason':'x','disposition':'accepted'}]])
def test_exception_schema_is_data_only(tmp_path,profile,rows):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job);rep=reply_for_job(job);rep['exceptions']=rows
    with pytest.raises(FigureError):complete(job,rep,profile)
    assert not list(job.glob('attempt-*'))


def test_unresolved_exception_does_not_pass_as_whole_task(tmp_path,profile):
    job,rep,r=finish(tmp_path,profile,[{'source_id':'source-1','reason':'A separate ambiguous item remains'}])
    assert r['status']=='partial-or-blocked' and r['unresolved_exceptions']
    review(job,reviewer='unit test',items=visual_items(r))
    assert read_json(job/'job.json')['status']=='partial-reviewed'


def test_declared_scope_exclusion_stays_visible(tmp_path,profile):
    job,rep,r=finish(tmp_path,profile,[{'source_id':'source-1','reason':'Unused source material explicitly excluded','disposition':'excluded'}])
    assert r['status']=='awaiting-visual-review' and len(r['declared_exclusions'])==1
    rr=review(job,reviewer='unit test',items=visual_items(r))
    assert rr['declared_exclusions'] and not rr['ready_for_publication']


def test_input_cannot_disappear_without_explanation(tmp_path,profile):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job);rep=reply_for_job(job);rep['figures']=[]
    r=complete(job,rep,profile);assert r['failures'][0]['error']['code']=='source_unaccounted'
    with pytest.raises(FigureError) as exc:review(job,reviewer='test',items=[])
    assert exc.value.code=='review_empty'


def test_review_not_possible_before_output(tmp_path):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job)
    with pytest.raises(FigureError) as exc:review(job,reviewer='test',items=[])
    assert exc.value.code=='review_before_output'


@pytest.mark.parametrize('target,code',[('report','review_report_changed'),('summary','review_summary_changed'),('single','review_pdf_changed')])
def test_actual_results_bound_for_visual_review(tmp_path,profile,target,code):
    job,rep,r=finish(tmp_path,profile)
    if target=='report':path=job/'attempt-01/report.json'
    elif target=='summary':path=job/'attempt-01/output'/r['summary_pdf']
    else:path=job/'attempt-01/output'/r['results'][0]['output_pdf']
    with path.open('ab') as f:f.write(b'\n ')
    with pytest.raises(FigureError) as exc:review(job,reviewer='unit test',items=visual_items(r))
    assert exc.value.code==code


def test_reused_figure_report_marks_reuse_and_spec_is_fresh(tmp_path,profile):
    job,rep,first=finish(tmp_path,profile)
    p=job/'attempt-01/output'/first['results'][0]['output_pdf'];(p.parent/'figure.spec.json').write_text('{"bad":true}')
    second=complete(job,rep,profile,cache=tmp_path/'cache')
    p=job/'attempt-02/output'/second['results'][0]['output_pdf']
    rr=read_json(p.parent/'report.json');spec=read_json(p.parent/'figure.spec.json')
    assert rr['reused_from_previous_attempt'] and 'bad' not in spec and spec['id']=='native-flow'


def test_summary_identity_contains_author(tmp_path,profile):
    import pymupdf as fitz
    job,rep,r=finish(tmp_path,profile)
    with fitz.open(job/'attempt-01/output'/r['summary_pdf']) as d:
        assert 'Synthetic' in d[0].get_text() and 'native-flow' in d[0].get_text()


@pytest.mark.parametrize('head,tail,edge,ok',[
    ('none','triangle',{'from':'a','to':'b'},True),
    ('none','triangle',{'from':'b','to':'a'},False),
    ('triangle','none',{'from':'b','to':'a'},True),
    ('triangle','none',{'from':'a','to':'b'},False),
    ('triangle','triangle',{'from':'a','to':'b','both':True},True),
    ('triangle','triangle',{'from':'a','to':'b'},False),
    ('none','none',{'from':'a','to':'b','arrow':False},True),
    ('none','none',{'from':'a','to':'b'},False),
])
def test_bound_native_arrow_direction_preserved(head,tail,edge,ok):
    from journal_pdf.agent_spec import compile_reply_figure
    source={'id':'source-1','snapshot':'x.pptx','sha256':'a'*64}
    page={'id':'slide-1','kind':'pptx','objects':[
        {'id':'source-a','text':'A'},{'id':'source-b','text':'B'},
        {'id':'connector','kind':'native-connector','from_ref':'source-a','to_ref':'source-b','head':head,'tail':tail}]}
    rep={'id':'x','kind':'diagram','review':{'source_checked':True,'labels_checked':True,'topology_checked':True},
         'nodes':[{'id':'a','ref':'source-a'},{'id':'b','ref':'source-b'}],'edges':[dict(edge,ref='connector')]}
    if ok:
        assert compile_reply_figure(rep,source,page)['edges']
    else:
        with pytest.raises(FigureError) as exc:compile_reply_figure(rep,source,page)
        assert exc.value.code=='native_arrow_direction_mismatch'


def test_native_edge_label_cannot_be_taken_from_outside_scope():
    from journal_pdf.agent_spec import compile_reply_figure
    source={'id':'source-1','snapshot':'x.pdf','sha256':'a'*64}
    page={'id':'page-1','kind':'pdf','objects':[{'id':'A','text':'A'},{'id':'B','text':'B'},{'id':'Other','text':'Other figure'}]}
    rep={'id':'x','kind':'diagram','review':{'source_checked':True,'labels_checked':True,'topology_checked':True},
         'scope_refs':['A','B'],'scope_reason':'Only left figure','nodes':[{'id':'a','ref':'A'},{'id':'b','ref':'B'}],
         'edges':[{'from':'a','to':'b','label_ref':'Other'}]}
    with pytest.raises(FigureError) as exc:compile_reply_figure(rep,source,page)
    assert exc.value.code=='used_outside_scope'


def test_labelled_tick_cannot_be_silently_omitted():
    from journal_pdf.agent_spec import compile_reply_figure
    source={'id':'source-1','snapshot':'x.png','sha256':'a'*64}
    ticks=[{'id':'x0','position':0,'label_candidate':True},{'id':'x1','position':100,'label_candidate':True}]
    page={'id':'image-1','kind':'raster','geometry':{'axes':[{'id':'axis','frame':[0,0,200,200],
          'plot_clip':[0,0,200,200],'x_ticks':ticks,'y_ticks':[{'id':'y0','position':100,'label_candidate':True}]}],
          'legend_rows':[{'id':'legend','rect':[20,20,70,40],'swatch_clip':[20,20,30,30]}]}}
    rep={'id':'x','kind':'raster-chart','review':{'source_checked':True,'labels_checked':True,'inward_ticks_confirmed':True},
         'axis_ref':'axis','x_ticks':[{'ref':'x0','text':'0'}],'y_ticks':[{'ref':'y0','text':'0'}],
         'x_title':'Time(s)','y_title':'Value(V)',
         'legend_rows':[{'ref':'legend','series_id':'one','label':'One'}],
         'mask_review':{'approved_empty_background':True,'reason':'Test blank background'}}
    with pytest.raises(FigureError) as exc:compile_reply_figure(rep,source,page)
    assert exc.value.code=='unaccounted_tick_candidates'
    rep['ignored_ticks']=[{'ref':'x1','reason':'In this synthetic evidence it is a false-positive label candidate'}]
    assert compile_reply_figure(rep,source,page)['kind']=='chart'


def test_raster_no_legend_requires_explicit_review_and_accounts_for_candidates():
    from journal_pdf.agent_spec import compile_reply_figure
    source={'id':'source-1','snapshot':'x.png','sha256':'a'*64}
    axis={'id':'axis','frame':[0,0,200,200],'plot_clip':[0,0,200,200],
          'x_ticks':[{'id':'x0','position':0,'label_candidate':True}],
          'y_ticks':[{'id':'y0','position':100,'label_candidate':True}]}
    page={'id':'image-1','kind':'raster','geometry':{'axes':[axis],'legend_rows':[]}}
    rep={'id':'x','kind':'raster-chart','review':{'source_checked':True,'labels_checked':True,'inward_ticks_confirmed':True},
         'axis_ref':'axis','x_ticks':[{'ref':'x0','text':'0'}],'y_ticks':[{'ref':'y0','text':'0'}],
         'x_title':'x','y_title':'z','legend_rows':[]}
    # Given: omitting legend data is not itself proof of a legend-free source.
    with pytest.raises(FigureError):compile_reply_figure(rep,source,page)
    rep.update(no_legend=True)
    with pytest.raises(FigureError) as error:compile_reply_figure(rep,source,page)
    assert error.value.code=='legend_absence_review'
    rep['review']['legend_absence_reason']='Synthetic scalar field has axes and no series legend.'
    # When / Then: explicit review produces a mask-free, legend-free chart.
    spec=compile_reply_figure(rep,source,page)
    assert spec['series']==[] and spec['legend_placement']=='none'
    assert not spec.get('masks') and not spec.get('approved_empty_regions')
    rep['legend_rows']=[{'ref':'conflicting-legend'}]
    with pytest.raises(FigureError) as error:compile_reply_figure(rep,source,page)
    assert error.value.code=='legend_absence_review'
    rep['legend_rows']=[]
    # A detected candidate must be accounted for; the flag cannot erase it silently.
    page['geometry']['legend_rows']=[{'id':'false-legend'}]
    with pytest.raises(FigureError) as error:compile_reply_figure(rep,source,page)
    assert error.value.code=='unaccounted_legend_candidates'
    rep['ignored_legends']=[{'ref':'false-legend','reason':'Candidate is an interior data mark, not a legend.'}]
    assert compile_reply_figure(rep,source,page)['series']==[]


def test_review_crop_keeps_overlapping_leading_digit_piece():
    from journal_pdf.ingest_geometry import extend_label_left
    pieces=[{'rect':[10,5,29,25]},{'rect':[28,5,42,25]}]
    assert extend_label_left([28,5,42,25],pieces,15,20)==[10,5,42,25]


def test_review_crop_does_not_join_other_line_or_far_text():
    from journal_pdf.ingest_geometry import extend_label_left
    pieces=[{'rect':[10,45,29,65]},{'rect':[1,5,5,25]},{'rect':[28,5,42,25]}]
    assert extend_label_left([28,5,42,25],pieces,15,20)==[28,5,42,25]


def test_raster_structured_tree_compiles_without_manual_coordinates():
    from journal_pdf.agent_spec import compile_reply_figure
    source={'id':'source-1','snapshot':'x.png','sha256':'a'*64}
    page={'id':'image-1','kind':'raster','geometry':{'shapes':[{'id':'box1'},{'id':'box2'},{'id':'box3'}],'regions':[]}}
    rep={'id':'tree','kind':'diagram','model':'tree','review':{'source_checked':True,'labels_checked':True,'topology_checked':True},
         'structure':{'root':{'ref':'box1','text':'Root'},'branches':[{'text':{'ref':'box2','text':'Branch'},'children':[{'ref':'box3','text':'Leaf'}]}]}}
    spec=compile_reply_figure(rep,source,page)
    assert spec['kind']=='tree' and spec['root']=='Root' and spec['branches'][0]['children']==['Leaf']
    rep['structure']['root']={'ref':'box1'}
    with pytest.raises(FigureError) as exc:compile_reply_figure(rep,source,page)
    assert exc.value.code=='raster_transcription_required'


def test_failed_compilation_time_is_still_recorded(tmp_path,profile):
    job=tmp_path/'job';prepare([source_pdf(tmp_path)],job);rep=reply_for_job(job);rep['figures'][0]['nodes'][0]['ref']='absent'
    r=complete(job,rep,profile)
    assert r['failures'] and r['timings']['semantic_compile_ms']>0
