"""First-route proposals from recorded semantic facts and locally paired cases.

No OCR, file-type classifier, production writer, or independent evidence verifier.
"""
from __future__ import annotations

import copy

from .editorial_route import (
    ROUTES, _choice, _object, _provenance, _require, _rows, _sha, _text,
)

STRUCTURES = ('node_link', 'plot', 'photo', 'ui', 'mixed', 'unknown')


def _source_review(review):
    _object(review, ('source_snapshot', 'structure', 'text_requirement', 'data_preservation',
                     'topology', 'evidence'), optional=('source_graphics',), where='source_review')
    snapshot = review['source_snapshot']
    _require(isinstance(snapshot, dict) and bool(snapshot), 'source_review: source snapshot required')
    for key, digest in snapshot.items():
        _text(key, 'source id')
        _sha(digest, 'source hash')
    _choice(review['structure'], STRUCTURES, 'structure')
    _choice(review['text_requirement'], ('none', 'preserve_native', 'replace', 'unknown'), 'text_requirement')
    _choice(review['data_preservation'], ('required', 'not_applicable', 'unknown'), 'data_preservation')
    _choice(review['topology'], ('reconstructable', 'not_reconstructable', 'not_applicable', 'unknown'), 'topology')
    seen = set()
    for evidence in _rows(review['evidence'], 'source evidence', nonempty=True):
        _object(evidence, ('source_id', 'source_sha256', 'location', 'observation'), where='source evidence')
        _text(evidence['source_id'], 'source evidence id')
        _require(snapshot.get(evidence['source_id']) == evidence['source_sha256'], 'source evidence: stale hash')
        for key in ('location', 'observation'):
            _text(evidence[key], key)
        seen.add(evidence['source_id'])
    _require(seen == set(snapshot), 'source evidence: every source needs review')
    graphics = review.get('source_graphics', {'status':'unknown', 'objects':[]})
    _object(graphics, ('status','objects'), where='source_graphics')
    _choice(graphics['status'], ('unknown','none','identified'), 'source graphics status')
    objects = _rows(graphics['objects'], 'source graphics')
    _require(bool(objects) == (graphics['status'] == 'identified'), 'source graphics: objects disagree with status')
    identities = set()
    for obj in objects:
        _object(obj, ('source_id','source_sha256','object_id','kind'), where='source graphic')
        _text(obj['source_id'], 'source graphic source id')
        _text(obj['object_id'], 'source graphic object id')
        _choice(obj['kind'], ('symbol','data'), 'source graphic kind')
        _require(snapshot.get(obj['source_id']) == obj['source_sha256'], 'source graphic: stale hash')
        identity = (obj['source_id'], obj['object_id'])
        _require(identity not in identities, 'source graphic: duplicate object')
        identities.add(identity)


def _cases(cases, review, route):
    refs, seen = [], set()
    for case in _rows(cases, 'cases'):
        _object(case, ('id', 'paired', 'hashes', 'structure', 'observed_method', 'method_basis',
                       'scope', 'observation_evidence'), where='case')
        _text(case['id'], 'case id')
        _require(case['id'] not in seen, 'case: duplicate id')
        seen.add(case['id'])
        _require(case['paired'] is True, 'case: local source/Word/final pairing must be recorded')
        _object(case['hashes'], ('source', 'word', 'final'), where='case hashes')
        for digest in case['hashes'].values():
            _sha(digest, 'case hash')
        _choice(case['structure'], STRUCTURES, 'case structure')
        _choice(case['observed_method'], ROUTES - {'unresolved'}, 'case method')
        _choice(case['method_basis'], ('observed_difference', 'historical_record'), 'case method basis')
        _text(case['scope'], 'case scope')
        for observation in _rows(case['observation_evidence'], 'case observations', nonempty=True):
            _text(observation, 'case observation')
        differences = []
        if case['structure'] != review['structure']:
            differences.append('structure differs from current source')
        if case['observed_method'] != route:
            differences.append('recorded treatment differs from proposed route')
        refs.append({**copy.deepcopy(case), 'differences': differences,
                     'applicability': 'review_candidate' if not differences else 'contrast_only',
                     'limit': 'Observed differences do not prove historical workflow; recorded workflow is not independently authenticated. Never copy dimensions, data or acceptance.'})
    return refs


def suggest_route(source_review, cases, *, user_override=None):
    """Propose from explicit joint facts; never return a satisfied review or dispatch approval."""
    _source_review(source_review)
    structure = source_review['structure']
    text = source_review['text_requirement']
    data = source_review['data_preservation']
    topology = source_review['topology']
    route = 'unresolved'
    basis, blocking = [], []
    if structure == 'node_link' and topology == 'reconstructable' and data == 'not_applicable' and text != 'unknown':
        route = 'structural_redraw'
        basis.append('Recorded reconstructable topology without original quantitative geometry to preserve.')
    elif structure == 'plot' and data == 'required' and topology == 'not_applicable' and text == 'replace':
        route = 'plot_reletter'
        basis.append('Recorded original data geometry must remain while reviewed text is replaced.')
    elif structure in ('photo', 'ui') and data == 'required' and topology == 'not_applicable' and (
            text == 'none' or structure == 'ui' and text == 'preserve_native'):
        route = 'raster_grayscale_single_column'
        basis.append('Recorded full-image preservation with no replacement lettering; grayscale suitability and legibility still need review.')
    else:
        blocking.append('Joint structure/text/data/topology facts are unknown, mixed or outside supported suggestions; inspect or split panels explicitly.')
    refs = _cases(cases, source_review, route)
    graphics = copy.deepcopy(source_review.get('source_graphics', {'status':'unknown', 'objects':[]}))
    if structure == 'node_link' and graphics['status'] == 'unknown':
        blocking.append('Source graphic symbols have not been reviewed; inspect them before choosing substitutes.')
    elif graphics['status'] == 'identified':
        blocking.append('Identified source graphics require preservation mapping and explicit review before delivery.')
    if not any(ref['applicability'] == 'review_candidate' for ref in refs):
        blocking.append('No paired case supports this candidate structure and treatment; comparative review remains outstanding.')
    proposed = route
    if user_override is not None:
        _object(user_override, ('route', 'provenance'), where='user_override')
        _choice(user_override['route'], ROUTES, 'user override route')
        _provenance(user_override['provenance'], source_review['source_snapshot'], 'user_override.provenance')
        route = user_override['route']
        if route != proposed:
            blocking.append('User route retained; its difference from the fact-based suggestion needs explicit reconciliation.')
        if route == 'raster_grayscale_single_column' and text == 'replace':
            blocking.append('Grayscale-only treatment cannot fulfill recorded lettering replacement needs.')
    return {'schema_version': 'route-suggestion/1', 'proposed_route': proposed, 'candidate_route': route,
            'basis': basis, 'blocking': blocking, 'case_refs': refs,
            'source_graphics': graphics,
            'source_review': copy.deepcopy(source_review), 'user_override': copy.deepcopy(user_override),
            'ready_for_processing': False, 'ready_for_publication': False,
            'semantics_independently_verified': False,
            'validation_scope': 'recorded-facts-and-paired-case-proposal-only'}
