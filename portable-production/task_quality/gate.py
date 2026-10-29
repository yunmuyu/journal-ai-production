"""Four optional phases: freeze inputs, inspect candidates, review, reverify."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .checks import check_artifact_set, inspect
from .models import JSON, Contract, FileRef, GateError, array, fields, text
from .storage import checked, encoded, exclusive, inputs, prepare, read, ref, state, target_states, task_lock, verify_refs


def digest(raw: JSON) -> str:
    return hashlib.sha256(encoded(raw)).hexdigest()


def envelope(contract: Contract, raw: JSON) -> dict[str, JSON]:
    path = state(contract) / 'envelope.json'
    row = fields(read(path), 'schema_version contract inputs targets limitation')
    if row['contract'] != raw:
        raise GateError('contract_changed', str(path))
    owner = fields(read(contract.workspace / '.task-quality-owner.json'), 'id contract')
    if owner['contract'] != raw or owner['id'] != contract.id:
        raise GateError('workspace_conflict', str(contract.workspace))
    if target_states(contract) != row['targets']:
        raise GateError('delivery_target_changed', 'Delivery target changed since precheck')
    verify_refs(row['inputs'])
    if inputs(contract) != row['inputs']:
        raise GateError('inputs_changed', 'Frozen inputs differ from envelope')
    return row


def precheck(raw: JSON) -> dict[str, JSON]:
    contract = Contract.parse(raw)
    prepare(contract, raw)
    by_stem: dict[tuple[str, str], list[str]] = {}
    for output in contract.outputs:
        target = output.delivery_target
        if target.suffix.lower() in {'.pdf', '.jpg', '.jpeg'}:
            by_stem.setdefault((str(target.parent).casefold(), target.stem.casefold()), []).append(str(target))
    warnings = [dict(code='multiple_figure_formats', targets=targets,
                     message='Confirm the requested formats; matching names may be intentional.')
                for targets in by_stem.values() if len(targets) > 1]
    return dict(status='prechecked', envelope=ref(state(contract) / 'envelope.json'), warnings=warnings)


def postcheck(raw: JSON, submission: JSON) -> dict[str, JSON]:
    contract = Contract.parse(raw)
    with task_lock(contract):
        envelope(contract, raw)
        candidate = inspect(contract, submission)
        envelope(contract, raw)
        verify_refs(candidate['references'])
        candidate['envelope'] = ref(state(contract) / 'envelope.json')
        path = state(contract) / 'candidate.json'
        exclusive(path, candidate)
        return dict(status='candidate', manual_status='pending', candidate_sha256=ref(path)['sha256'],
                    coverage_pending=candidate['coverage_pending'], previews=candidate['previews'])


def candidate_record(contract: Contract) -> dict[str, JSON]:
    check_artifact_set(contract)
    candidate = fields(read(state(contract) / 'candidate.json'),
        'status manual_status coverage_pending measurements references previews audit envelope')
    checked(FileRef.parse(candidate['envelope']))
    verify_refs(candidate['references'])
    return candidate


def finalize(raw: JSON, review: JSON) -> dict[str, JSON]:
    contract = Contract.parse(raw)
    with task_lock(contract):
        envelope(contract, raw)
        candidate = candidate_record(contract)
        review_fields = fields(review, 'reviewer candidate_sha256 items')
        reviewer = text(review_fields['reviewer'])
        if reviewer.casefold().strip() == contract.producer.casefold().strip():
            raise GateError('independent_review_required', 'Producer cannot review own output')
        path = state(contract) / 'candidate.json'
        candidate_sha = ref(path)['sha256']
        if review_fields['candidate_sha256'] != candidate_sha:
            raise GateError('review_binding_mismatch', str(path))
        pending = [text(item) for item in array(candidate['coverage_pending'])]
        if set(pending).intersection(contract.mechanical):
            raise GateError('mechanical_pending', 'Required mechanical coverage cannot be waived')
        items = [fields(item, 'id decision observation evidence') for item in array(review_fields['items'])]
        if len(items) != len(contract.manual_review) or {text(row['id']) for row in items} != set(contract.manual_review):
            raise GateError('manual_items_missing', 'Every manual item requires a distinct review entry')
        known = {candidate_sha, FileRef.parse(candidate['envelope']).sha256}
        known.update(FileRef.parse(item).sha256 for item in array(candidate['references']))
        known.update(FileRef.parse(item).sha256 for item in inputs(contract))
        preview_hashes = {FileRef.parse(item).sha256 for item in array(candidate['previews'])}
        reviewed_hashes: set[str] = set()
        for row in items:
            if row['decision'] != 'approved':
                raise GateError('manual_pending_or_rejected', text(row['id']))
            text(row['observation'])
            evidence = array(row['evidence'])
            if not evidence or any(text(item) not in known for item in evidence):
                raise GateError('review_evidence_missing', text(row['id']))
            reviewed_hashes.update(text(item) for item in evidence)
        if not preview_hashes.issubset(reviewed_hashes):
            raise GateError('review_evidence_missing', 'Review must reference both source and artifact preview hashes')
        resolutions: list[JSON] = []
        semantic_items = {'source_geometry': 'source_content',
                          'label_path_binding': 'label_ownership' if contract.route in ('diagram', 'circuit') else 'source_content',
                          'route_semantic_coverage': 'topology'}
        for issue in sorted(set(pending)):
            required = semantic_items.get(issue, issue)
            matches = [item for item in items if item['id'] == required]
            if not matches or not (preview_hashes | {contract.source.sha256}).issubset({text(value) for value in array(matches[0]['evidence'])}):
                raise GateError('manual_resolution_missing', f'{issue} requires {required} with both previews')
            resolutions.append(dict(automatic_pending=issue, manual_item=matches[0]))
        receipt: dict[str, JSON] = dict(status='reviewed', producer=contract.producer, reviewer=reviewer,
            automatic_coverage_pending=candidate['coverage_pending'], manual_resolutions=resolutions,
            contract_sha256=digest(raw), envelope=ref(state(contract) / 'envelope.json'),
            candidate=ref(path), inputs=inputs(contract), references=candidate['references'], review=review,
            limitation='Auditable reviewer declaration; no cryptographic identity or visual truth guarantee')
        exclusive(state(contract) / 'receipt.json', receipt)
        return receipt


def verify(raw: JSON) -> dict[str, JSON]:
    contract = Contract.parse(raw)
    envelope(contract, raw)
    candidate_record(contract)
    path = state(contract) / 'receipt.json'
    receipt = fields(read(path), 'status producer reviewer automatic_coverage_pending manual_resolutions contract_sha256 envelope candidate inputs references review limitation')
    if receipt['contract_sha256'] != digest(raw) or receipt['status'] != 'reviewed':
        raise GateError('receipt_binding_mismatch', str(path))
    checked(FileRef.parse(receipt['candidate']))
    checked(FileRef.parse(receipt['envelope']))
    verify_refs(receipt['inputs'])
    verify_refs(receipt['references'])
    finalized = finalize(raw, receipt['review'])
    if finalized != receipt:
        raise GateError('receipt_binding_mismatch', str(path))
    return dict(status='verified', receipt=ref(path), publication='Use existing localflow review/publish protections')
