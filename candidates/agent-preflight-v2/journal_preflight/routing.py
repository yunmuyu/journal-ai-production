"""Agent-reviewed routing with conservative release gates; no PDF manufacture."""
from __future__ import annotations
import copy,hashlib,json
from pathlib import Path
from .probe import read_bytes,sha
BASELINE={'repository':'yunmuyu/journal-ai-production','commit':'ced82c85cb1a8490c52750e772a9415e6ac705f6',
 'release':'2026.10.14-r21-common-contract','rule_precedence':['current_user_instruction','verified_same_figure_correction','current_runtime_and_release','historical_example']}
ROUTES={'drawio_native_relayout':{'preflight_support':'implemented','production_support':'adapter_not_validated_for_this_topology'},
        'raster_panel_assembly':{'preflight_support':'implemented','production_support':'protected_assembly_requires_region_plan'},
        'raster_chart_preserve':{'preflight_support':'implemented','production_support':'requires_semantic_labels_and_safe_masks'},
        'manual_review':{'preflight_support':'review_packet','production_support':'not_auto_released'}}

def derive_gates(item):
    gates=[]
    def g(name,passed,reason):gates.append({'id':name,'status':'pass' if passed else 'pending','reason':reason})
    g('source_identity',item.get('identity',{}).get('verified') is True,'Word caption, current source hashes and Agent visual pairing are required.')
    g('export_scope',item.get('export',{}).get('scope_verified') is True,'Main figures, source pages, panel count and PDF export count are different.')
    blocked=[x['id'] for x in item.get('issues',[]) if x.get('blocks_publication') and x.get('status')!='resolved' and x.get('scope') in ('content','cross_figure')]
    g('content_consistency',not blocked,'Unresolved: '+','.join(blocked) if blocked else 'No unresolved content issue recorded; not a complete scientific review.')
    g('production_risk_review',not any(x.get('blocks_publication') and x.get('status')!='resolved' and x.get('scope') not in ('content','cross_figure') for x in item.get('issues',[])),'Quality, safe masking, native rich math and color strategy remain separate from content consistency.')
    g('column_capacity',item.get('layout',{}).get('capacity_verified') is True,'Suggested column or Word placement width is not a measured pass.')
    g('font_contract',False,'No production text/font rendering performed in this screening.')
    color=item.get('protection',{}).get('color',{})
    g('color_contract',color.get('actual_pdf_audit_passed') is True,'Protected color need does not grant source-color authorization.')
    g('actual_pdf_and_data_audit',False,'Screening evidence is not final-PDF/font/data audit.')
    g('local_cases_and_corrections',item.get('caseRetrieval',{}).get('local_context_verified') is True,'Production records, prior-artwork search and prepare-decisions required before formal dispatch.')
    return gates

def _live_snapshot(probe,manifest):
    if manifest is None:return {'status':'not_checked','reason':'Provide the input manifest for live source hash verification.'}
    rows=manifest['files']
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate live source IDs')
    actual={r['id']:sha(read_bytes(Path(r['path']))) for r in rows}
    expected={a['id']:a['sha256'] for a in probe['assets']}
    if actual!=expected:raise ValueError('Live source hash changed; reprobe and review affected evidence')
    return {'status':'verified','asset_count':len(actual),'snapshot':actual}

def _check_selector(assets,source):
    aid=source.get('asset_id')
    if aid not in assets:raise ValueError('Unknown source reference')
    p=assets[aid]['probe']
    if p.get('kind') in ('error','unsupported'):raise ValueError('Source probe is unsupported or failed')
    if 'member' in source:
        members={im['member'] for f in p.get('figures',[]) for im in f.get('images',[])}
        if source['member'] not in members:raise ValueError('Unknown Word media member')
    if 'page' in source:
        n=source['page'];page=next((v for v in p.get('pages',[]) if v['number']==n),None)
        if not isinstance(n,int) or isinstance(n,bool) or page is None:raise ValueError('Unknown source page')
        if 'image_object_index' in source:
            i=source['image_object_index']
            if not isinstance(i,int) or isinstance(i,bool) or not 1<=i<=len(page.get('images',[])):raise ValueError('Unknown image object index')
    if 'image_object_index' in source and 'page' not in source:raise ValueError('Image object requires a page')

def apply_review(probe:dict,review:dict,manifest:dict|None=None):
    assets={a['id']:a for a in probe['assets']}
    if len(assets)!=len(probe['assets']):raise ValueError('Duplicate probe asset IDs')
    live=_live_snapshot(probe,manifest)
    if review.get('snapshot')!={k:v['sha256'] for k,v in assets.items()}:
        raise ValueError('Review source snapshot mismatch; do not reuse stale identity/review decisions.')
    figures=[];ids=set()
    for raw in review['figures']:
        f=copy.deepcopy(raw)
        if f['id'] in ids:raise ValueError('Duplicate figure ID')
        ids.add(f['id'])
        if f['identity']['word_asset_id'] not in assets:raise ValueError('Unknown Word reference')
        word=assets[f['identity']['word_asset_id']]
        if word['probe']['kind']!='docx':raise ValueError('Word identity must refer to an actual DOCX')
        candidates=[x for x in word['probe']['figures'] if x['number']==f['identity']['word_number']]
        if len(candidates)>1:raise ValueError('Duplicate Word caption number; explicit disambiguation required')
        fig=candidates[0] if candidates else None
        if fig is None:raise ValueError('Figure number not present in parsed Word caption set')
        for source in f['sources']:
            _check_selector(assets,source)
            source['file_sha256']=assets[source['asset_id']]['sha256']
        if f['route'] not in ROUTES:raise ValueError('Unknown route')
        primary=f.get('selected_primary')
        if primary:
            _check_selector(assets,primary)
            if primary['asset_id'] not in {x['asset_id'] for x in f['sources']}:raise ValueError('Primary source not included in provenance')
            if f['route']=='drawio_native_relayout' and assets[primary['asset_id']]['probe'].get('kind')!='svg_drawio':raise ValueError('draw.io route requires actual native graph metadata')
        if f.get('layout',{}).get('locked') and f['layout'].get('confirmed_column')!=f['layout'].get('recommended_column'):
            raise ValueError('Cannot override confirmed locked column')
        if f.get('protection',{}).get('rebuild_data_curves') and not f['protection'].get('verified_raw_data'):
            raise ValueError('Cannot rebuild curves without verified raw data')
        f['identity'].update(word_sha256=word['sha256'],word_caption=fig['caption'])
        f['capability']=copy.deepcopy(ROUTES[f['route']])
        f['caseRetrieval']={'status':'pending_local_records','matches':[],'reason':'Local inventory, production-results and evidence were not provided; not reported as searched/no historical matches.','local_context_verified':False}
        f['gates']=derive_gates(f)
        f['gates'].append({'id':'live_source_snapshot','status':'pass' if live['status']=='verified' else 'pending','reason':'Saved review/probe matching is not proof the original files are still current.'})
        f['ready_for_publication']=False;f['automatic_grade_confirmed_by_user']=False
        f['preflight_state']='agent_reviewed_candidate'
        f['benchmark']={'cohort':review.get('benchmark_cohort','unclassified'),'include_in_blind_first_pass_benchmark':False,'reason':'No independent benchmark enrollment proof supplied; source probing and Agent review are measured separately.'}
        figures.append(f)
    return {'schema_version':'journal-preflight/2','version':'0.2.0','rule_baseline':BASELINE,
        'required_delivery_format':'pdf','ai_file_required':False,'publication_performed':False,
        'source_snapshot':copy.deepcopy(review['snapshot']),'live_source_verification':live,'figures':figures,
        'assessment_by':review.get('assessment_by','agent_review_received'),
        'screening_scope':{'asset_count':len(assets),'source':'provided_manifest_only','external_records_searched':False}}

def bridge_legacy(legacy,report):
    """Add a proposal, never mutate productionDecision, user corrections or acceptance.
    Only exact explicit figure IDs match. Unmatched items are not auto-created.
    """
    result=copy.deepcopy(legacy);mapf={f['id']:f for f in report['figures']}
    for f in result.get('figures',[]):
        if f.get('id') not in mapf:continue
        proposal=f.setdefault('aiProposal',{});incoming=copy.deepcopy(mapf[f['id']])
        prior=proposal.get('preflightV2')
        decision=f.get('productionDecision',{})
        constraints=decision.get('column') if isinstance(decision,dict) and decision.get('confirmed') is True else None
        conflict=constraints in ('single','double') and incoming.get('layout',{}).get('recommended_column')!=constraints
        incoming['legacy_constraint_check']={'status':'conflict' if conflict else 'requires_native_contract_review',
            'confirmed_column':constraints,'requires_reconciliation_before_dispatch':True}
        if conflict:
            incoming['gates'].append({'id':'legacy_confirmed_column','status':'pending','reason':'New proposal conflicts with confirmed legacy column; original decision remains authoritative.'})
        if prior and prior!=incoming:proposal.setdefault('preflightV2History',[]).append(copy.deepcopy(prior))
        proposal['preflightV2']=incoming
        # Do not overwrite source/Word IDs, original suggestions, confirmed column,
        # aiProposal.caseRetrieval, userCorrectionContext or productionDecision.
    return result
