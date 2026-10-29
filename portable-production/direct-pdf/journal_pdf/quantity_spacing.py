"""Source-derived spacing for recognized quantity and unit tokens.

Case-sensitive, multi-character unit tokens only. Ambiguous single-character
symbols require separate semantic evidence. Literal/code/path runs are boundaries.
"""
from __future__ import annotations
import collections
import copy
import re
from typing import Final
from .axis_units import plain_content

QUANTITY_SPACING_RULE: Final = {
    'id':'quantity-spacing-20261029-v3',
    'scope':'recognized multi-character storage, frequency and SI unit tokens; case and values preserved',
}
LITERAL_ROLES: Final = frozenset({'literal','code','command','path'})
_UNITS: Final = r'(?:KiB|MiB|GiB|TiB|KB|kB|MB|GB|TB|kHz|MHz|GHz|Hz|mm|cm|km|µm|μm|nm|kg|mg|mL|ml|mV|kV|mA|kA|kW|mW|MW|kPa|MPa|GPa|dBm|dB|min|ms|µs|μs)'
_QUANTITY: Final = re.compile(
    r'(?<![A-Za-z0-9_./\\-])(?P<number>[+−-]?(?:\d+(?:\.\d+)?|\.\d+))'
    r'(?P<gap>[ \u00a0\u202f]*)(?P<unit>'+_UNITS+r')(?![A-Za-z0-9_./\\-])')


def quantity_matches(content, role='label'):
    """Return source quantity boundaries, protecting any intersecting literal run."""
    raw=plain_content(content)
    if role in LITERAL_ROLES:return []
    protected=[];offset=0
    if isinstance(content,list):
        for part in content:
            stop=offset+len(part['text'])
            if part.get('role') in LITERAL_ROLES:protected.append((offset,stop))
            offset=stop
    return [m for m in _QUANTITY.finditer(raw)
            if not any(a<m.end() and b>m.start() for a,b in protected)]


def normalize_quantity_spacing(content, role='label'):
    """Insert a space before the original unit, retaining rich-run styles exactly."""
    matches=quantity_matches(content,role)
    insertions={m.start('unit') for m in matches if not m['gap']}
    if isinstance(content,str):
        return ''.join((' ' if i in insertions else '')+c for i,c in enumerate(content))
    parts=copy.deepcopy(content);offset=0
    for part in parts:
        raw=part['text']
        part['text']=''.join((' ' if offset+i in insertions else '')+c for i,c in enumerate(raw))
        offset+=len(raw)
    return parts


def audit_quantity_spacing(scene, actual_text):
    """Independently derive required separators from ORIGINAL source quantities.

The actual PDF check retains spaces and verifies occurrence counts. Already spaced
literal quantities count as a baseline, preventing them from masking a missing gap
in an editable quantity elsewhere. This is a text-token audit, not dimensional or
physical-space measurement; PDFs with unusual extraction order need review.
"""
    required=collections.Counter();checks=[];issues=[]
    for item in scene.texts:
        source=item.get('source_content',item.get('content',''))
        raw=plain_content(source);role=item.get('role','label')
        matches=quantity_matches(source,role)
        wanted={m.start():m for m in matches}
        # Include already spaced literals in the document-level expected count.
        for m in _QUANTITY.finditer(raw):
            if m.start() in wanted or m['gap']:required[(m['number'],m['unit'])]+=1
        display=item['measurement']['text']
        expected=normalize_quantity_spacing(source,role)
        local_required=collections.Counter((m['number'],m['unit']) for m in matches)
        local_actual=collections.Counter((m['number'],m['unit']) for m in _QUANTITY.finditer(display) if m['gap'])
        if local_required:
            ok=all(local_actual[k]>=v for k,v in local_required.items())
            checks.append({'id':item['id'],'source':raw,'expected':plain_content(expected),
                           'scene_display':display,'scene_has_required_separators':ok})
            if not ok:issues.append({'code':'quantity_unit_spacing_violation','id':item['id'],'surface':'scene'})
    observed=collections.Counter((m['number'],m['unit']) for m in _QUANTITY.finditer(actual_text) if m['gap'])
    missing=required-observed
    if missing:issues.append({'code':'quantity_unit_spacing_violation','surface':'actual-pdf',
                             'missing_spaced_quantities':[{'number':n,'unit':u,'count':count} for (n,u),count in missing.items()]})
    return {'rule':QUANTITY_SPACING_RULE,'checks':checks,'issues':issues,'ok':not issues,
            'whitespace_ignored':False,'physical_character_gap_audited':False,
            'scope_note':'Confirmed storage and frequency tokens and occurrence counts; unknown units unchanged; not a general unit or formula audit.'}
