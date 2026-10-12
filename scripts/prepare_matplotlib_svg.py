from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final, TypedDict

SVG: Final = 'http://www.w3.org/2000/svg'
XLINK: Final = 'http://www.w3.org/1999/xlink'
ET.register_namespace('', SVG)
ET.register_namespace('xlink', XLINK)


class Label(TypedDict):
    text: str
    role: str
    x: float
    y: float
    rotation: float


def glyph_text(group: ET.Element) -> str:
    chars: list[str] = []
    for node in group:
        if node.tag != f'{{{SVG}}}use':
            continue
        reference = node.get(f'{{{XLINK}}}href', node.get('href', ''))
        match = re.fullmatch(r'#[\w-]+-([0-9a-fA-F]{2,6})', reference)
        if match is None:
            raise ValueError(f'Unrecognized text glyph: {reference}')
        chars.append(chr(int(match[1], 16)))
    return ''.join(chars).replace('−', '-')


def translate(group: ET.Element) -> tuple[float, float, float]:
    transform = group.get('transform', '')
    match = re.search(r'translate\(([-\d.]+)[ ,]+([-\d.]+)\)', transform)
    if match is None:
        raise ValueError(f'Unsupported text anchor: {transform}')
    angle = re.search(r'rotate\(([-\d.]+)\)', transform)
    return float(match[1]), float(match[2]), float(angle[1]) if angle else 0.0


def prepare(source: Path, directory: Path) -> None:
    root = ET.fromstring(source.read_bytes())
    if root.findall(f'.//{{{SVG}}}image'):
        raise ValueError('Raster SVG is outside the verified vector route')
    if root.findall(f'.//{{{SVG}}}text'):
        raise ValueError('Use native SVG text route for editable SVG text')
    axes = [e for e in root.iter() if re.fullmatch(r'axes_\d+', e.get('id', ''))]
    if not axes:
        raise ValueError('No Cartesian Matplotlib axes found')
    original_paths = [(e.get('id'), e.get('d')) for e in root.iter(f'{{{SVG}}}path')]
    path_definitions = {e.get('id'): e for e in root.iter(f'{{{SVG}}}path') if e.get('id')}
    panels: list[dict] = []
    directory.mkdir(parents=True, exist_ok=True)
    for index, original in enumerate(axes):
        axis = copy.deepcopy(original)
        patch = axis.find(f'{{{SVG}}}g/{{{SVG}}}path')
        if patch is None:
            raise ValueError('Plot boundary missing')
        values = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', patch.get('d', ''))]
        if len(values) != 8:
            raise ValueError('Nonrectangular plot requires another route')
        left, top, right, bottom = min(values[::2]), min(values[1::2]), max(values[::2]), max(values[1::2])
        scale = (62 * 72 / 25.4) / (right - left)
        target_left, target_top = 36.0, 14.0
        height = (bottom - top) * scale
        page_width, page_height = 250.0, height + 56.0
        labels: list[Label] = []
        parents = {child: parent for parent in axis.iter() for child in parent}
        text_nodes = [e for e in axis.iter() if re.fullmatch(r'text_\d+', e.get('id', ''))]
        for outer in text_nodes:
            parent = parents[outer]
            ancestry: list[str] = []
            node = parent
            while node is not axis:
                ancestry.append(node.get('id', ''))
                node = parents[node]
            role = 'annotation'
            if any(n.startswith('legend_') for n in ancestry):
                role = 'legend'
            elif any(n.startswith('xtick_') for n in ancestry):
                role = 'x-tick'
            elif any(n.startswith('ytick_') for n in ancestry):
                role = 'y-tick'
            elif parent.get('id', '').startswith('matplotlib.axis_'):
                role = 'axis-title'
            for group in list(outer.iter(f'{{{SVG}}}g')):
                if not any(e.tag == f'{{{SVG}}}use' for e in group):
                    continue
                text = glyph_text(group)
                x, y, rotation = translate(group)
                actual_role = role
                if role == 'axis-title':
                    actual_role = 'y-title' if abs(rotation) == 90 else 'x-title'
                if role == 'annotation' and y < top:
                    actual_role = 'panel-title'
                if role.endswith('tick'):
                    marker = next((e for e in parent.iter(f'{{{SVG}}}use') if e.get(f'{{{XLINK}}}href', '').startswith('#m') and 'x' in e.attrib and 'y' in e.attrib), None)
                    if marker is None:
                        raise ValueError('Tick lacks a real marker anchor')
                    x, y = float(marker.attrib['x']), float(marker.attrib['y'])
                labels.append({'text': text, 'role': actual_role, 'x': target_left + (x-left)*scale, 'y': target_top + (y-top)*scale, 'rotation': rotation})
            parent.remove(outer)
        for legend in [e for e in axis.iter() if e.get('id', '').startswith('legend_')]:
            samples = [e for e in legend if not e.get('id', '').startswith('patch_')]
            rows = [r for r in labels if r['role'] == 'legend']
            if len(samples) != len(rows):
                raise ValueError('Legend sample/text count mismatch')
            lower = sum(r['y'] for r in rows)/len(rows) > target_top + height/2
            first_y = target_top + height - 7 - 9.6*(len(rows)-1) if lower else target_top + 8
            for row_index, (sample, label) in enumerate(zip(samples, rows, strict=True)):
                coordinates = [e for e in sample.iter(f'{{{SVG}}}use') if 'x' in e.attrib and 'y' in e.attrib]
                path_nodes = [e for e in sample if e.tag == f'{{{SVG}}}path']
                if coordinates:
                    sx = sum(float(e.attrib['x']) for e in coordinates)/len(coordinates)
                    sy = float(coordinates[0].attrib['y'])
                    marker = path_definitions.get(coordinates[0].get(f'{{{XLINK}}}href', '').removeprefix('#'))
                    marker_points = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', marker.get('d', ''))] if marker is not None else []
                    half_width = max(abs(n) for n in marker_points[::2]) if marker_points else 0.0
                elif path_nodes:
                    points = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', path_nodes[0].get('d', ''))]
                    sx, sy = (points[0]+points[-2])/2, points[1]
                    half_width = abs(points[-2]-points[0])/2
                else:
                    raise ValueError('Unknown legend sample geometry')
                if path_nodes:
                    line_points = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', path_nodes[0].get('d', ''))]
                    half_width = max(half_width, abs(line_points[-2]-line_points[0])/2)
                sample_right = target_left + (right-left)*scale - 72
                sample_x = sample_right-half_width*scale-0.25
                sample_y = first_y + row_index*9.6
                sample.set('transform', f'translate({(sample_x-target_left)/scale+left-sx} {(sample_y-target_top)/scale+top-sy})')
                label['x'], label['y'] = sample_right+3, sample_y
            for frame in [e for e in legend if e.get('id', '').startswith('patch_')]:
                legend.remove(frame)
        panel = ET.Element(f'{{{SVG}}}svg', {'width':f'{page_width}pt','height':f'{page_height}pt','viewBox':f'0 0 {page_width} {page_height}'})
        shared_definitions = root.iter(f'{{{SVG}}}defs')
        for definitions in shared_definitions:
            panel.append(copy.deepcopy(definitions))
        geometry = ET.SubElement(panel, f'{{{SVG}}}g', {'transform':f'translate({target_left-left*scale} {target_top-top*scale}) scale({scale})'})
        geometry.append(axis)
        output = directory / f'panel-{index+1}.svg'
        ET.ElementTree(panel).write(output, encoding='utf-8', xml_declaration=True)
        remaining = [(e.get('id'),e.get('d')) for e in axis.iter(f'{{{SVG}}}path')]
        if any(item not in original_paths for item in remaining):
            raise ValueError('Original path geometry changed')
        panels.append({'svg':str(output.resolve()),'labels':labels,'pageSizePt':[page_width,page_height],'plotBoundsPt':[target_left,target_top,target_left+62*72/25.4,target_top+height],'plotWidthMm':62,'plotHeightMm':height*25.4/72,'sourceAxis':original.get('id'),'retainedPaths':len(remaining),'sourceScale':scale})
    report = {'source':str(source.resolve()),'sourceHash':hashlib.sha256(source.read_bytes()).hexdigest(),'panels':panels,'curveGeometryPreserved':True,'scope':'Outlined Unicode Cartesian SVG only; no inferred data or OCR'}
    (directory/'prepared.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
