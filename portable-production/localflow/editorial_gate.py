"""Mandatory source-bound editorial decision gate for candidate publication.

This checks recorded evidence and completeness, not editorial truth or user identity.
A passing gate never grants final human acceptance.
"""
from __future__ import annotations
import sys
from pathlib import Path
from .core import Config, FlowError, hash_json, json_file, safe_child
from .probing import check_snapshot


def check_editorial_gate(config: Config, candidate: dict, report: dict, artifact_format: str = 'pdf') -> dict:
    cid = candidate.get('candidate_id')
    if not isinstance(cid, str) or not cid or any(c not in '0123456789abcdef' for c in cid):
        raise FlowError('candidate_id', '候选 ID 无效')
    folder = config.state_root / 'candidates' / cid
    constraints = json_file(folder / 'constraints.json')
    if hash_json(constraints) != candidate.get('constraints_sha256'):
        raise FlowError('editorial_constraints_changed', '编辑决策约束哈希不匹配')
    confirmed = constraints.get('confirmed', {})
    contract = confirmed.get('editorial_route_contract')
    selected_id = confirmed.get('editorial_figure_id')
    targets = confirmed.get('editorial_targets')
    if not isinstance(contract, dict) or not isinstance(selected_id, str) or not isinstance(targets, list) or not targets:
        raise FlowError('editorial_contract_required', '发布必须绑定编辑路由契约、图件ID和完整目标清单；旧候选须重新生成约束')
    seal = check_snapshot(config, candidate['probe_id'])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'preflight'))
    from journal_preflight.editorial_route import validate_manifest, ContractError
    try:
        declared = {row['id']: row['sha256'] for figure in contract.get('figures', []) for row in figure['sources']}
        files = []
        for source_id, digest in declared.items():
            rel = seal['identity'].get(source_id)
            if rel is None or seal['sources'].get(rel) != digest:
                raise FlowError('editorial_source_binding', '路由来源不属于本候选预检快照')
            files.append({'id': source_id, 'path': str(safe_child(Path(seal['source_root']), rel))})
        validation = validate_manifest(contract, {'files': files})
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        raise FlowError('editorial_contract_invalid', f'编辑路由契约无效：{exc}') from exc
    if validation['ready_for_processing'] is not True:
        raise FlowError('editorial_route_blocked', '路由、来源、核对证据或作者问题尚未解决，禁止发布')
    figures = {row['id']: row['record'] for row in validation['figures']}
    target_by_id = {}
    pairs = set()
    for row in targets:
        if not isinstance(row, dict) or set(row) != {'id', 'author_rel', 'figure_number'} or any(not isinstance(v, str) or not v.strip() for v in row.values()):
            raise FlowError('editorial_targets', '完整编辑目标须含id、author_rel、figure_number且不含未知字段')
        pair = (row['author_rel'], row['figure_number'])
        if row['id'] in target_by_id or pair in pairs:
            raise FlowError('editorial_targets', '编辑目标图件ID或交付身份重复')
        target_by_id[row['id']] = row; pairs.add(pair)
    if set(target_by_id) != set(figures) or selected_id not in figures:
        raise FlowError('editorial_inventory', '编辑目标清单必须覆盖且只覆盖全部决策图件')
    selected = figures[selected_id]
    spec = json_file(folder / 'spec.json')
    target = target_by_id[selected_id]
    if (target['author_rel'], target['figure_number']) != (spec.get('author_rel'), spec.get('figure_number')):
        raise FlowError('editorial_target_binding', '编辑决策目标与候选制作说明不同')
    if artifact_format not in ('pdf', 'jpg', 'jpeg'):
        raise FlowError('editorial_output_format', '未支持的编辑交付格式')
    if selected['decision']['column'] != confirmed.get('column'):
        raise FlowError('editorial_column_binding', '编辑路由栏宽与已确认交付栏宽不一致')
    route = selected['decision']['route']
    if (artifact_format in ('jpg', 'jpeg')) != (route == 'raster_grayscale_single_column'):
        raise FlowError('editorial_output_format', '编辑路由与实际候选格式不一致')
    selected_sources = {(seal['identity'][s['id']], s['sha256']) for s in selected['sources']}
    actual_sources = {(s['path'], s['sha256']) for s in report.get('source_bindings', [])}
    if actual_sources != selected_sources:
        raise FlowError('editorial_source_binding', '候选来源集合必须与选定编辑图件完全一致')
    # Caption candidates are not certified figures: require explicit resolution of all,
    # rather than silently equating only successfully extracted drawings with the job.
    probe = json_file(config.state_root / 'probes' / candidate['probe_id'] / 'evidence' / 'probe.json')
    for asset in probe.get('assets', []):
        info = asset.get('probe', {})
        if info.get('kind') != 'docx': continue
        rows = info.get('figures', []) + info.get('unmapped_figure_captions', [])
        numbers = [str(row['number']) for row in rows]
        if len(numbers) != len(set(numbers)):
            raise FlowError('editorial_inventory_ambiguous', 'Word图题候选号码重复，需要先核实清单')
        associated = {target_by_id[fid]['figure_number'] for fid, fig in figures.items() if any(s['id'] == asset['id'] for s in fig['sources'])}
        if set(numbers) != associated:
            raise FlowError('editorial_inventory_incomplete', 'Word图题候选未在来源绑定的编辑目标中完整解释')
    return {'status': 'editorial-contract-passed', 'figure_id': selected_id,
            'contract_sha256': hash_json(contract), 'route': route,
            'ready_for_publication': False, 'acceptance': 'not_recorded',
            'validation_scope': 'recorded-decisions-and-live-source-completeness',
            'semantics_independently_verified': False}
