"""Measurements use actual PDF/JPG bytes; semantic coverage remains explicit."""
from __future__ import annotations

import math
from pathlib import Path

import fitz
from PIL import Image, UnidentifiedImageError

from .models import JSON, Contract, FileRef, GateError, Output, array, fields, text
from .storage import checked, child, ref, read, state


def preview(source: Path, target: Path) -> dict[str, JSON]:
    try:
        if source.suffix.lower() == '.pdf':
            with fitz.open(source) as doc:
                if len(doc) != 1:
                    raise GateError('page_count', str(source))
                doc[0].get_pixmap(dpi=150, alpha=False).save(target)
        else:
            with Image.open(source) as image:
                image.convert('RGB').save(target, format='PNG')
    except (RuntimeError, ValueError, OSError, UnidentifiedImageError) as exc:
        raise GateError('preview_failed', str(source)) from exc
    return ref(target)


def measure(output: Output, path: Path) -> dict[str, JSON]:
    try:
        if output.format == 'pdf':
            with fitz.open(path) as doc:
                if not doc.is_pdf or len(doc) != 1:
                    raise GateError('page_count', str(path))
                page = doc[0]
                width = page.rect.width * 25.4 / 72
                strokes = [float(item['width']) for item in page.get_drawings()
                           if item.get('color') is not None and item.get('stroke_opacity', 1) > 0
                           and item['rect'].intersects(page.rect)]
                if any(not math.isfinite(value) or value < 0 for value in strokes):
                    raise GateError('stroke_mismatch', f'{path}: invalid measured stroke')
                if output.stroke_pt is not None and (not strokes or any(
                        abs(value - output.stroke_pt) > .005 + 1e-8 for value in strokes)):
                    raise GateError('stroke_mismatch', f'{path}: measured {strokes}')
                measurement: dict[str, JSON] = dict(width_mm=width, vector_strokes_pt=strokes,
                    vector_scope='PyMuPDF visible intersecting paths; clipping/occlusion needs manual review')
        else:
            with Image.open(path) as image:
                if image.format != 'JPEG':
                    raise GateError('format_mismatch', str(path))
                dpi = image.info.get('dpi')
                if not dpi:
                    raise GateError('dpi_mismatch', str(path))
                dpi_values = [float(value) for value in dpi]
                if len(dpi_values) != 2 or any(
                        not math.isfinite(value) or value <= 0 or abs(value - output.dpi) > .5
                        for value in dpi_values):
                    raise GateError('dpi_mismatch', str(path))
                if tuple(image.size) != output.pixels:
                    raise GateError('pixels_mismatch', str(path))
                width = image.width / dpi_values[0] * 25.4
                measurement = dict(width_mm=width, pixels=list(image.size), dpi=dpi_values)
        if not math.isfinite(width) or width <= 0 or abs(width - output.width_mm) > .05:
            raise GateError('width_mismatch', f'{path}: {width} mm')
        return measurement
    except (RuntimeError, ValueError, OSError, UnidentifiedImageError) as exc:
        raise GateError('invalid_artifact', str(path)) from exc


def audit(contract: Contract, reference: FileRef) -> tuple[JSON, list[JSON]]:
    checked(reference)
    report = fields(read(reference.path), 'coverage source_geometry label_path_binding scene output_bindings')
    expected_bindings = {item.id: ref(child(contract.workspace, item.path))['sha256'] for item in contract.outputs}
    if report['output_bindings'] != expected_bindings:
        raise GateError('audit_binding_mismatch', 'Audit must bind every actual output ID and SHA256')
    rows = [fields(item, 'id status evidence') for item in array(report['coverage'])]
    if len({text(row['id']) for row in rows}) != len(rows):
        raise GateError('invalid_schema', 'Duplicate coverage IDs')
    if not set(contract.mechanical).issubset({text(row['id']) for row in rows}):
        raise GateError('coverage_missing', 'Required mechanical coverage missing')
    pending: list[JSON] = []
    for row in rows:
        status = row['status']
        if status not in ('checked', 'pending', 'not-applicable'):
            raise GateError('invalid_schema', 'Coverage status must be checked/pending/not-applicable')
        evidence = array(row['evidence'])
        if not evidence:
            raise GateError('coverage_evidence_missing', text(row['id']))
        for item in evidence:
            checked(FileRef.parse(item))
        if status == 'not-applicable' and row['id'] in contract.mechanical:
            permitted = (row['id'] == 'stroke' and all(item.stroke_pt is None for item in contract.outputs)) or (
                row['id'] in ('pixels', 'dpi') and all(item.format == 'pdf' for item in contract.outputs))
            if not permitted:
                raise GateError('coverage_not_applicable', text(row['id']))
        if status == 'pending':
            pending.append(text(row['id']))
    for name in ('source_geometry', 'label_path_binding'):
        claim = fields(report[name], 'status evidence observation')
        text(claim['observation'])
        evidence = array(claim['evidence'])
        if not evidence:
            raise GateError('coverage_evidence_missing', name)
        for item in evidence:
            checked(FileRef.parse(item))
        if claim['status'] not in ('checked', 'pending', 'not-applicable'):
            raise GateError('invalid_schema', name)
        if claim['status'] == 'pending':
            pending.append(name)
    scene_ref = report['scene']
    if scene_ref is not None:
        scene_file = FileRef.parse(scene_ref)
        checked(scene_file)
        scene = read(scene_file.path)
        if type(scene) is not dict or not {'nodes', 'texts', 'paths'}.issubset(scene):
            raise GateError('invalid_scene', str(scene_file.path))
        nodes = array(scene['nodes'])
        paths = array(scene['paths'])
        labels = array(scene['texts'])
        owners = {text(item['id']) for item in [*nodes, *paths] if type(item) is dict and 'id' in item}
        if contract.source.path.suffix.lower() == '.pdf':
            with fitz.open(contract.source.path) as source:
                if any(page.get_text().strip() for page in source) and not labels:
                    pending.append('label_path_binding')
                if any(page.get_drawings() for page in source) and not nodes:
                    pending.append('source_geometry')
        if contract.source.path.suffix.lower() != '.pdf' and contract.route in ('diagram', 'circuit'):
            pending.append('source_geometry')
        if any(type(item) is not dict or type(item.get('owner')) is not str or item.get('owner') not in owners for item in labels):
            pending.append('label_path_binding')
    elif contract.route in ('diagram', 'circuit'):
        pending.extend(('source_geometry', 'label_path_binding'))
    if contract.route in ('diagram', 'circuit') and any(
            fields(report[name], 'status evidence observation')['status'] == 'not-applicable'
            for name in ('source_geometry', 'label_path_binding')):
        pending.append('route_semantic_coverage')
    return report, pending


def check_artifact_set(contract: Contract) -> set[Path]:
    expected = {child(contract.workspace, item.path) for item in contract.outputs}
    found = {path.resolve() for path in contract.workspace.rglob('*')
             if path.suffix.lower() in ('.pdf', '.jpg', '.jpeg') and not path.is_relative_to(state(contract))}
    if found != expected:
        raise GateError('artifact_set', 'Actual artifact set must exactly match contract')
    return expected


def inspect(contract: Contract, submission: JSON) -> dict[str, JSON]:
    raw = fields(submission, 'artifacts audit')
    artifacts = tuple(FileRef.parse(item) for item in array(raw['artifacts']))
    expected = check_artifact_set(contract)
    actual = {item.path for item in artifacts}
    if actual != expected or len(actual) != len(artifacts):
        raise GateError('artifact_set', 'Actual artifact set must exactly match contract')
    references: list[JSON] = [checked(item) for item in artifacts]
    audit_ref = FileRef.parse(raw['audit'])
    if not audit_ref.path.is_relative_to(contract.workspace) or audit_ref.path in expected:
        raise GateError('unsafe_path', 'Audit must be a distinct file inside workspace')
    report, pending = audit(contract, audit_ref)
    references.append(checked(audit_ref))
    if type(report) is dict and report['scene'] is not None:
        references.append(checked(FileRef.parse(report['scene'])))
    report_fields = fields(report, 'coverage source_geometry label_path_binding scene output_bindings')
    evidence_rows = [fields(item, 'id status evidence') for item in array(report_fields['coverage'])]
    evidence_rows += [fields(report_fields[name], 'status evidence observation') for name in ('source_geometry', 'label_path_binding')]
    for row in evidence_rows:
        references.extend(checked(FileRef.parse(item)) for item in array(row['evidence']))
    measurements: list[JSON] = []
    previews: list[JSON] = []
    for output in contract.outputs:
        path = child(contract.workspace, output.path)
        measurements.append(dict(id=output.id, measured=measure(output, path)))
        previews.append(preview(path, child(state(contract), output.id + '.preview.png')))
    previews.append(preview(contract.source.path, state(contract) / 'source.preview.png'))
    references.extend(previews)
    return dict(status='candidate', manual_status='pending', coverage_pending=pending,
                measurements=measurements, references=references, previews=previews, audit=report)
