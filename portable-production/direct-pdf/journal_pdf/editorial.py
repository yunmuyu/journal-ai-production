"""Renderer-independent journal rules. Source snapshot is pinned, not a new style guide.
Normative overrides: 2026-10-13 fractional whole-artwork fitting; r21 final strokes.
Do not import the divergent root development diamond formula.
"""
from __future__ import annotations
import re, math, copy
from .common import FigureError, PT_PER_MM

RULESET = {
    'id': 'journal-editorial-20261016-r21-directpdf-bridge-4-unified-nodes',
    'repository': 'yunmuyu/journal-ai-production',
    'commit': 'ced82c85cb1a8490c52750e772a9415e6ac705f6',
    'profile': 'production-runtime/references/editorial-profile.md',
    'adapter': 'production-runtime/adobe/editorial-generator.jsx',
    'latest_override': 'release-notes/2026.10.14-r21.md',
}
PAD_X = 4.5
PAD_Y = 2.7
COMPACT_GAP = 3.0
ARROW_LENGTH = 3 * PT_PER_MM
ARROW_DEPTH = 4.4
ARROW_BOUNDARY_GAP = ARROW_LENGTH
LABEL_CLEARANCE = 3.0
TICK_CLEARANCE = 2.5
STROKE = 0.5
EXPORT_PAD = 0.25

# ASCII spaces match the provided reference samples. No float conversion: zeros,
# signs, precision, exponent spelling, and leading zeros must survive.
NUMERIC = re.compile(r'^([+\-−]?)([0-9][0-9 \u00a0\u202f]*)(?:\.([0-9][0-9 \u00a0\u202f]*))?([eE][+\-−]?[0-9]+)?$')
def group_number(value):
    raw = str(value)
    m = NUMERIC.fullmatch(raw)
    if not m:
        raise FigureError('numeric_label_not_number', '数值标签不是单一数值，不能按三位分组', text=raw)
    sign, integer, fraction, exponent = m.groups()
    integer = re.sub(r'[ \u00a0\u202f]', '', integer)
    integer = re.sub(r'(?<=\d)(?=(?:\d{3})+$)', ' ', integer)
    if fraction is not None:
        fraction = re.sub(r'[ \u00a0\u202f]', '', fraction)
        fraction = '.'.join(['', ' '.join(fraction[i:i+3] for i in range(0,len(fraction),3))])
    else: fraction = ''
    return sign + integer + fraction + (exponent or '')

_CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
_CJK_LINE = re.compile(r'^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+$')
_ASCII_PARENS = re.compile(r'[ \t]*\(([^()]*)\)')
_TECHNICAL_UNIT = re.compile(r'^(?:[A-Za-zµμΩ℃°‰%]+)(?:/[A-Za-zµμΩ℃°‰%]+)*$')
_RANGE_NUMBER = r'[+\-−]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)'
_NUMERIC_RANGE = re.compile(r'(?<![A-Za-z0-9_./\\])'+_RANGE_NUMBER+r'[ \t]*(?P<connector>[~〜～])[ \t]*'+_RANGE_NUMBER+r'(?![A-Za-z0-9_./\\])')
_RANGE_ROLES = {'label','edge-label','legend-label','title','axis-title','axis-category','axis-tick','numeric-value','number'}
_LITERAL_ROLES = {'code','command','path','literal'}

def normalize_numeric_range_connectors(content):
    parts=[{'text':content}] if isinstance(content,str) else copy.deepcopy(content)
    raw=''.join(part['text'] for part in parts)
    connectors={match.start('connector') for match in _NUMERIC_RANGE.finditer(raw)}
    offset=0
    for part in parts:
        text=part['text']
        part['text']=''.join('～' if offset+index in connectors else char for index,char in enumerate(text))
        offset+=len(text)
    return parts[0]['text'] if isinstance(content,str) else parts

def normalize_manual_line_breaks(value):
    lines = str(value).split('\n')
    for index in range(1, len(lines)):
        previous, current = lines[index - 1], lines[index]
        if len(current) != 1 or not (_CJK_LINE.fullmatch(previous) and _CJK_LINE.fullmatch(current)):
            continue
        combined = previous + current
        if len(combined) <= 3:
            lines[index - 1], lines[index] = combined, ''
        else:
            split = len(combined) // 2
            lines[index - 1], lines[index] = combined[:split], combined[split:]
    return '\n'.join(line for line in lines if line)

def wrap_text(value, max_chars):
    if not isinstance(max_chars, int) or max_chars < 2:
        raise FigureError('invalid_wrap_width', '换行宽度必须是不小于2的整数', max_chars=max_chars)
    output = []
    for paragraph in str(value).split('\n'):
        words = paragraph.split()
        line = ''
        for word in words:
            parts = []
            while len(word) > max_chars:
                parts.append(word[:max_chars - 1] + '-')
                word = word[max_chars - 1:]
            parts.append(word)
            for part in parts:
                candidate = part if not line else line + ' ' + part
                if len(candidate) <= max_chars:
                    line = candidate
                else:
                    if line: output.append(line)
                    line = part
        output.append(line)
    return '\n'.join(output)

def normalize_chinese_punctuation(value):
    text = str(value)
    if not _CJK.search(text):
        return text
    text = re.sub(r'\?(?=\s*(?:$|\n))', '？', text)

    def fullwidth(match):
        inner = match.group(1)
        before = text[:match.start()].rstrip()
        technical_call = (
            not _CJK.search(inner)
            and re.search(r'[A-Za-z_][A-Za-z0-9_./-]*$', before)
        )
        return match.group(0) if technical_call else '（' + inner + '）'

    return _ASCII_PARENS.sub(fullwidth, text)

def display_content(content, role='label'):
    if role in _LITERAL_ROLES:
        return copy.deepcopy(content)
    if role == 'axis-title':
        from .axis_units import normalize_axis_title
        return normalize_numeric_range_connectors(normalize_axis_title(content))
    if isinstance(content, str):
        content = content.replace('⮕','→')
        if role in _RANGE_ROLES:
            ranged=normalize_numeric_range_connectors(content)
            if _NUMERIC_RANGE.search(content) and role in ('axis-tick','numeric-value','number'):
                return ranged
            content=ranged
        if role in ('axis-tick','numeric-value','number'):
            return group_number(content)
        if role == 'label' and any(_TECHNICAL_UNIT.fullmatch(match.group(1).strip()) for match in _ASCII_PARENS.finditer(content)):
            return normalize_manual_line_breaks(content)
        if role in ('label','edge-label','legend-label','title'):
            return normalize_manual_line_breaks(normalize_chinese_punctuation(content))
        return content
    if isinstance(content, list):
        parts = normalize_numeric_range_connectors(content) if role in _RANGE_ROLES else copy.deepcopy(content)
        for p in parts:
            if p.get('role') in ('number','numeric-value'):
                p['text'] = group_number(p['text'])
        return parts
    return content

def diamond_size(width, height, font_size=8):
    """Exact formal-runtime adapter: calibrated base + ink containment correction.
    The documentary 1.7/1.6 + 4 base alone may fail for some font/line proportions.
    No ordinary rectangle padding is applied to the diamond.
    """
    scale=font_size/8
    a=width*.85+2*scale; b=height*.8+2*scale
    containment=max(1.,width/(2*(a-scale))+height/(2*(b-scale)))
    return 2*a*containment,2*b*containment,{
        'base_width_pt':2*a,'base_height_pt':2*b,
        'containment_scale':containment,'source':RULESET['adapter']}


def scale_scene(scene, factor):
    """Scale the WHOLE composed scene. Final path widths reset to r21's 0.5pt.
    Measurements are copied before editing, never mutating the shared font cache.
    """
    original_width=scene.width; original_size=scene.size
    if factor<=0 or factor>1+1e-9 or original_size*factor<6-1e-7:
        raise FigureError('layout_reflow_required','完整图件缩后低于6pt，必须重新布局',scale=factor)
    for n in scene.nodes:
        n['rect']=[v*factor for v in n['rect']]; n['width']=STROKE
        if 'dash' in n:n['dash']=[v*factor for v in n['dash']]
        if 'padding_pt' in n:n['padding_pt']=[v*factor for v in n['padding_pt']]
    for p in scene.paths:
        p['points']=[[v*factor for v in q] for q in p['points']]
        p['dash']=[v*factor for v in p['dash']];p['width']=STROKE;p['arrow_scale']=1
    for a in scene.assets:a['rect']=[v*factor for v in a['rect']]
    for t in scene.texts:
        m=copy.deepcopy(t['measurement'])
        for key in ('width','height','size'):m[key]*=factor
        m['ink']=[v*factor for v in m['ink']]
        for g in m['glyphs']:
            for key in ('size','x','y','advance'):g[key]*=factor
            g['ink']=[v*factor for v in g['ink']]
        t['measurement']=m;t['position']=copy.deepcopy(t['position'])
        for key in ('bbox','offset'):t['position'][key]=[v*factor for v in t['position'][key]]
        t['x']*=factor;t['y']*=factor
    scene.width*=factor;scene.height*=factor;scene.size*=factor
    scene.layout_evidence.update({
        'ruleset':RULESET,'design_font_size_pt':original_size,'design_width_pt':original_width,
        'whole_artwork_scale':factor,'final_font_size_pt':scene.size,
        'final_stroke_width_pt':STROKE,'fit_method':'whole-artwork-proportional-then-final-stroke-normalization',
    })
    return scene


from functools import lru_cache
@lru_cache(maxsize=1)
def engine_signature():
    """Hash source modules once per process; font files are NOT scanned/read here."""
    from pathlib import Path
    from .common import digest_file,digest_json
    folder=Path(__file__).resolve().parent
    return digest_json({'rules':RULESET,'modules':{p.name:digest_file(p) for p in sorted(folder.glob('*.py'))}})
