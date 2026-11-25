"""Axis-only, style-preserving application of the 2026-10-09 slash rule.
No numerical scale conversion, translation, variable rewriting or global regex.
Recognized terminal unit expressions are automatic; unknown expressions are
left for semantic review. No unit conversion or spelling correction occurs.
"""
from __future__ import annotations
import contextvars
import copy
import re
from .common import FigureError

_DECISIONS = contextvars.ContextVar('unit_decisions', default=None)

AXIS_UNIT_RULE = {
    "id": "axis-quantity-slash-unit-20261009-v1",
    "source": "production-runtime/references/editorial-profile.md",
    "source_blob": "d588e694daf7a9e601fe9614da581755197e498a",
    "scope": "axis-title, recognized terminal single and compound units",
}
# Case-sensitive: do not silently repair spelling or change a scale.
_SIMPLE = {"%", "‰", "°", "°C", "℃", "dB", "dBm", "rad", "sr", "min", "h", "L", "l", "t"}
_BASE = {"m", "g", "s", "A", "K", "mol", "cd", "Hz", "N", "Pa", "J", "W", "C", "V", "F", "Ω", "S", "Wb", "T", "H", "Bq", "Gy", "Sv", "kat"}
_PREFIX = ("da", "Y", "Z", "E", "P", "T", "G", "M", "k", "h", "d", "c", "m", "µ", "μ", "n", "p", "f", "a", "z", "y")
_TERMINAL = re.compile(r"(?P<open>\(|（)(?P<unit>[^()（）]+)(?P<close>\)|）)\s*$")
# U+00B2/00B3/00B9 sit outside the superscript block but appear in m²/m³.
_ATOM = re.compile(r'^(?P<base>[^\s\^⁰¹²³⁴⁵⁶⁷⁸⁹⁻\u00b2\u00b3\u00b9]+)(?:\^-?\d+|[⁻⁰¹²³⁴⁵⁶⁷⁸⁹\u00b2\u00b3\u00b9]+)?$')


def _lexicon():
    from .journal_rules import load_rules
    return set(load_rules().get('units', {}).get('lexicon') or [])


def plain_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list) and all(isinstance(v, dict) and isinstance(v.get('text'), str) for v in content):
        return ''.join(v['text'] for v in content)
    raise FigureError('axis_title_content', '轴题必须为字符串或带text的样式片段')


def is_known_single_unit(value: str) -> bool:
    if value in _lexicon() or value in _SIMPLE or value in _BASE:
        return True
    return any(value.startswith(p) and value[len(p):] in _BASE for p in _PREFIX)


def _atom_known(atom: str) -> bool:
    if is_known_single_unit(atom) or atom in {'次', '秒', '分钟', '小时'}:
        return True
    match = _ATOM.fullmatch(atom)
    return bool(match and (is_known_single_unit(match.group('base')) or match.group('base') in {'次', '秒', '分钟', '小时'}))


def is_known_compound_unit(value: str) -> bool:
    # Parse only explicit multiplication/division of known unit atoms. An
    # unknown term remains a review item rather than a guess at its meaning.
    parts = re.split(r'\s*([/·*])\s*', value)
    if len(parts) < 3 or len(parts) % 2 == 0:
        return False
    return all(_atom_known(atom) for atom in parts[::2])


def _recorded_decision(unit, raw, decisions):
    """Job-file hook. None means no recorded decision; do not guess."""
    if not decisions:
        return None
    for item in decisions:
        if not isinstance(item, dict):
            continue
        if item.get('fragment') == unit or item.get('source') == raw:
            if 'is_unit' not in item:
                return None
            return bool(item.get('is_unit'))
    return None


def _rewrite_plan(raw, decisions=None):
    match = _TERMINAL.search(raw)
    if not match:
        return None
    if (match['open'], match['close']) not in (('(', ')'), ('（', '）')):
        return None
    unit = match['unit'].strip()
    qend = match.start()
    while qend and raw[qend-1].isspace(): qend -= 1
    quantity = raw[:qend]
    # A/(Hz) is already slash-separated. Function arguments / equations are not
    # identified as quantity names by this conservative fallback parser.
    if not quantity or quantity.endswith('/') or any(c in quantity for c in '=()（）\n'):
        return None
    compound = is_known_compound_unit(unit)
    if not compound and not is_known_single_unit(unit):
        decision = _recorded_decision(unit, raw, decisions)
        if decision is not True:
            return None
        compound = bool(re.search(r'[/·*]', unit))
    ustart = match.start('unit') + len(match['unit']) - len(match['unit'].lstrip())
    uend = match.end('unit') - len(match['unit']) + len(match['unit'].rstrip())
    formatted_unit = '次 / 分钟' if re.fullmatch(r'次\s*/\s*分钟', unit) else unit
    normalized = quantity + ('/（' + formatted_unit + '）' if compound else '/' + unit)
    return qend, ustart, uend, normalized, compound


def _slice_parts(parts, start, end):
    selected=[]; offset=0
    for part in parts:
        stop=offset+len(part['text'])
        a,b=max(start,offset),min(end,stop)
        if a<b:
            p=copy.deepcopy(part);p['text']=p['text'][a-offset:b-offset];selected.append(p)
        offset=stop
    return selected


def normalize_axis_title(content, role='axis-title', decisions=None):
    # Legend and prose parentheses stay. See open question legend-parentheses.
    if role != 'axis-title':
        return copy.deepcopy(content)
    if decisions is None:
        decisions = _DECISIONS.get()
    raw=plain_content(content);plan=_rewrite_plan(raw, decisions)
    if plan is None:
        return copy.deepcopy(content)
    qend,ustart,uend,normalized,compound=plan
    if isinstance(content,str): return normalized
    # Preserve variable italics, subscripts, and the existing unit's style. The
    # inserted separator alone uses ordinary baseline and upright Roman type.
    if compound and re.fullmatch(r'次\s*/\s*分钟',raw[ustart:uend]):
        minute=raw.index('分钟',ustart,uend)
        return (_slice_parts(content,0,qend) + [{'text':'/（','style':'regular'}]
                + _slice_parts(content,ustart,ustart+1) + [{'text':' / ','style':'regular'}]
                + _slice_parts(content,minute,minute+2) + [{'text':'）','style':'regular'}])
    if compound:
        return (_slice_parts(content,0,qend) + [{'text':'/（','style':'regular'}]
                + _slice_parts(content,ustart,uend) + [{'text':'）','style':'regular'}])
    return _slice_parts(content,0,qend) + [{'text':'/','style':'regular'}] + _slice_parts(content,ustart,uend)


def axis_title_evidence(content, decisions=None):
    from .editorial import normalize_numeric_range_connectors
    source=plain_content(content);normalized=plain_content(normalize_numeric_range_connectors(normalize_axis_title(content, decisions=decisions)))
    tail=_TERMINAL.search(source)
    unresolved=source==normalized and tail is not None and not source[:tail.start()].rstrip().endswith('/')
    return {'source':source, 'display':normalized, 'changed':source!=normalized,
            'rule_id':AXIS_UNIT_RULE['id'],
            'status':'normalized' if source!=normalized else 'semantic_review_needed' if unresolved else 'unchanged',
            'numeric_scale_changed':False, 'quantity_name_changed':False}


def audit_axis_titles(scene, actual_text):
    """Re-derive from ORIGINAL source content, not from the renderer's output.
    This catches a bypassed normalizer even when a wrong scene matches its PDF.
    """
    compact=lambda text:re.sub(r'\s+','',text)
    actual=compact(actual_text);checks=[];issues=[]
    for item in scene.texts:
        if item.get('role')!='axis-title': continue
        ev=axis_title_evidence(item.get('source_content',item['content']))
        expected=compact(ev['display']);scene_display=compact(item['measurement']['text'])
        ok=expected in actual and scene_display==expected
        checks.append({'id':item['id'],**ev,'actual_pdf_contains_expected':expected in actual,'scene_matches_rule':scene_display==expected})
        if not ok: issues.append({'code':'axis_unit_rule_violation','id':item['id'],'expected':ev['display'],'scene_display':item['measurement']['text']})
    return {'rule':AXIS_UNIT_RULE,'checks':checks,'issues':issues,'ok':not issues,
            'scope_note':'Recognized explicit unit expressions only; not a global dimensional-consistency audit.'}
