"""Measurements use actual PDF/JPG bytes; semantic coverage remains explicit."""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz
from lxml import etree
from PIL import Image, ImageChops, UnidentifiedImageError

from .models import JSON, Contract, FileRef, GateError, Output, array, fields, text
from .storage import checked, child, ref, read, state
from .typography import audit_typography


def _flatten_html_text_svg(root) -> bool:
    """Drop draw.io HTML label duplicates when a native <text> fallback exists.

    draw.io writes every HTML label twice: a <foreignObject> copy inside a
    <switch> plus a native <text> sibling. The preflight probe already treats
    the native text as a fallback. Require equivalent wording before using it.
    Only that duplicate is removed, and only when *every*
    foreignObject sits in a switch that carries a text fallback, so a preview
    can never lose a label. Anything else stays rejected as before.
    """
    def local(element):
        return etree.QName(element).localname if isinstance(element.tag, str) else ''

    foreign = [element for element in root.iter() if local(element) == 'foreignObject']
    if not foreign:
        return False
    switches = []
    for element in foreign:
        parent = element.getparent()
        if parent is None or local(parent) != 'switch':
            return False
        fallback = [child for child in parent if local(child) == 'text']
        if len(fallback) != 1 or sum(local(child) == 'foreignObject' for child in parent) != 1:
            return False
        if any(local(child) not in ('foreignObject', 'text') for child in parent):
            return False
        native = ' '.join(''.join(fallback[0].itertext()).split())
        html = ' '.join(''.join(element.itertext()).split())
        if not native or native != html:
            raise GateError('preview_svg_fallback_mismatch', 'HTML标签与原生回退文字不一致；不能使用截断预览')
        switches.append(parent)
    for element in foreign:
        element.getparent().remove(element)
    for element in switches:
        # Retain switch-level transform/style/clip attributes after resolving its
        # duplicate branches; unwrapping children would silently change geometry.
        element.tag = '{http://www.w3.org/2000/svg}g'
    # draw.io also wraps the whole diagram in a click-through link to its export
    # FAQ. Drop only that link target: the <a> keeps its transform and children,
    # so geometry is untouched and no external resource can be followed.
    for element in [row for row in root.iter() if local(row) == 'a']:
        href = element.get('{http://www.w3.org/1999/xlink}href') or element.get('href') or ''
        if re.match(r'^https?://(www\.)?drawio\.com/', href):
            for key in [key for key in element.attrib if etree.QName(key).localname in ('href', 'target')]:
                del element.attrib[key]
    return True


def preview(source: Path, target: Path) -> dict[str, JSON]:
    try:
        if source.suffix.lower() == '.pptx':
            # Render the actual source slides with Office; a geometry-only thumbnail
            # cannot represent embedded pictures, connectors or grouped shapes.
            script = r'''$ErrorActionPreference='Stop'
$owned=$false; $presentation=$null; $app=$null
try {
  $owned=-not [bool](Get-Process -Name POWERPNT -ErrorAction SilentlyContinue)
  $app=New-Object -ComObject PowerPoint.Application
  $presentation=$app.Presentations.Open($env:JFW_PREVIEW_SOURCE,-1,0,0)
  $presentation.SaveAs($env:JFW_PREVIEW_PDF,32)
} finally {
  if($presentation){$presentation.Close();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)}
  if($app){if($owned){$app.Quit()};[void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)}
}'''
            with tempfile.TemporaryDirectory(prefix='jfw-pptx-preview-') as directory:
                pdf = Path(directory) / 'slides.pdf'
                env = os.environ | {'JFW_PREVIEW_SOURCE':str(source),'JFW_PREVIEW_PDF':str(pdf)}
                shell=shutil.which('pwsh') or 'powershell.exe'
                result = subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',script],
                                        env=env,capture_output=True,timeout=90,check=False)
                if result.returncode != 0 or not pdf.is_file():
                    raise GateError('preview_pptx_failed',result.stderr.decode(errors='replace')[-1000:])
                with fitz.open(pdf) as doc:
                    if not 1 <= len(doc) <= 50:raise GateError('preview_pptx_pages',str(len(doc)))
                    slides=[]
                    for page in doc:
                        pix=page.get_pixmap(dpi=100,alpha=False)
                        slides.append(Image.frombytes('RGB',(pix.width,pix.height),pix.samples))
                    canvas=Image.new('RGB',(max(image.width for image in slides),sum(image.height for image in slides)+12*(len(slides)-1)),'white')
                    y=0
                    for slide in slides:
                        canvas.paste(slide,(0,y));y+=slide.height+12
                    canvas.save(target,format='PNG')
        elif source.suffix.lower() == '.svg':
            parser=etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False,huge_tree=False)
            root=etree.parse(str(source),parser).getroot()
            if root.tag!='{http://www.w3.org/2000/svg}svg':raise GateError('preview_svg_invalid',str(source))
            flattened=_flatten_html_text_svg(root)
            for element in root.iter():
                if not isinstance(element.tag,str):continue
                name=etree.QName(element).localname
                if name in ('script','foreignObject','filter','animate','set'):
                    raise GateError('preview_svg_unsupported',name)
                if name=='style' and element.text and ('@import' in element.text or re.search(r'url\(\s*[\'\"]?(?!#)',element.text)):
                    raise GateError('preview_svg_external',str(source))
                for key,value in element.attrib.items():
                    if key.startswith('on') or (etree.QName(key).localname=='href' and not value.startswith('#')) or ('url(' in value and re.search(r'url\(\s*[\'\"]?(?!#)',value)):
                        raise GateError('preview_svg_external',str(source))
            document=fitz.open(stream=etree.tostring(root,xml_declaration=True,encoding='UTF-8'),filetype='svg') if flattened else fitz.open(source)
            with document as doc:
                if len(doc)!=1:raise GateError('page_count',str(source))
                doc[0].get_pixmap(dpi=150,alpha=False).save(target)
        elif source.suffix.lower() == '.pdf':
            with fitz.open(source) as doc:
                if len(doc) != 1:
                    raise GateError('page_count', str(source))
                doc[0].get_pixmap(dpi=150, alpha=False).save(target)
        else:
            with Image.open(source) as image:
                image.convert('RGB').save(target, format='PNG')
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired, UnidentifiedImageError, etree.XMLSyntaxError) as exc:
        raise GateError('preview_failed', str(source)) from exc
    return ref(target)


def _neutrality(image: Image.Image, path: Path) -> tuple[int, int]:
    r, g, b = image.convert('RGB').split()
    differences = ImageChops.lighter(ImageChops.difference(r, g),
        ImageChops.lighter(ImageChops.difference(r, b), ImageChops.difference(g, b)))
    histogram = differences.histogram()
    off = sum(histogram[3:])
    if off:
        raise GateError('nonneutral_pixels', f'{path}: {off} pixels exceed channel difference 2')
    return off, max(i for i, count in enumerate(histogram) if count)


def measure(output: Output, path: Path) -> dict[str, JSON]:
    try:
        if output.format == 'pdf':
            with fitz.open(path) as doc:
                if not doc.is_pdf or len(doc) != 1:
                    raise GateError('page_count', str(path))
                page = doc[0]
                width = page.rect.width * 25.4 / 72
                if abs(width - output.width_mm) > .05:
                    raise GateError('width_mismatch', f'{path}: {width} mm')
                strokes = [float(item['width']) for item in page.get_drawings()
                           if item.get('color') is not None and item.get('stroke_opacity', 1) > 0
                           and item['rect'].intersects(page.rect)]
                if any(not math.isfinite(value) or value < 0 for value in strokes):
                    raise GateError('stroke_mismatch', f'{path}: invalid measured stroke')
                if output.stroke_pt is not None and (not strokes or any(
                        abs(value - output.stroke_pt) > .005 + 1e-8 for value in strokes)):
                    raise GateError('stroke_mismatch', f'{path}: measured {strokes}')
                pixels = page.get_pixmap(dpi=300, colorspace=fitz.csRGB, alpha=False)
                with Image.frombytes('RGB', (pixels.width, pixels.height), pixels.samples) as image:
                    off, difference = _neutrality(image, path)
                measurement: dict[str, JSON] = dict(width_mm=width, vector_strokes_pt=strokes,
                    nonneutral_pixels=off, max_channel_difference=difference, color_audit_dpi=300,
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
                off, difference = _neutrality(image, path)
                measurement = dict(width_mm=width, pixels=list(image.size), dpi=dpi_values,
                    nonneutral_pixels=off, max_channel_difference=difference)
        if not math.isfinite(width) or width <= 0 or abs(width - output.width_mm) > .05:
            raise GateError('width_mismatch', f'{path}: {width} mm')
        return measurement
    except (RuntimeError, ValueError, OSError, UnidentifiedImageError) as exc:
        raise GateError('invalid_artifact', str(path)) from exc


def audit(contract: Contract, reference: FileRef) -> tuple[JSON, list[JSON]]:
    checked(reference)
    raw_report = read(reference.path)
    keys = 'coverage source_geometry label_path_binding scene output_bindings'
    report = fields(raw_report, keys + (' text_roles' if type(raw_report) is dict and 'text_roles' in raw_report else ''))
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
    report_fields = fields(report, 'coverage source_geometry label_path_binding scene output_bindings' +
        (' text_roles' if type(report) is dict and 'text_roles' in report else ''))
    evidence_rows = [fields(item, 'id status evidence') for item in array(report_fields['coverage'])]
    evidence_rows += [fields(report_fields[name], 'status evidence observation') for name in ('source_geometry', 'label_path_binding')]
    for row in evidence_rows:
        references.extend(checked(FileRef.parse(item)) for item in array(row['evidence']))
    measurements: list[JSON] = []
    previews: list[JSON] = []
    for output in contract.outputs:
        path = child(contract.workspace, output.path)
        measured = measure(output, path)
        if output.format == 'pdf':
            typography, unresolved = audit_typography(path, output.id, report_fields.get('text_roles'))
            measured['typography'] = typography
            pending.extend(unresolved)
        measurements.append(dict(id=output.id, measured=measured))
        previews.append(preview(path, child(state(contract), output.id + '.preview.png')))
    previews.append(preview(contract.source.path, state(contract) / 'source.preview.png'))
    references.extend(previews)
    return dict(status='candidate', manual_status='pending', coverage_pending=pending,
                measurements=measurements, references=references, previews=previews, audit=report)
