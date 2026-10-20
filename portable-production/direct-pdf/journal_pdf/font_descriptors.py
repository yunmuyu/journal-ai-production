#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pymupdf", "fonttools"]
# ///
# ─── How to run ───
# Run: uv run font_safe.py INPUT.pdf OUTPUT.pdf
# Or use the verified existing release Python; no installation required here.
# Produces a separate PDF and JSON; never overwrites an existing output.
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
import math
from pathlib import Path
import re
from typing import Final

import pymupdf as fitz
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from .pdf_fonts import normalize_type0_font_names

@dataclass(frozen=True, slots=True)
class FontSafetyError(Exception):
    code: str
    xref: int
    def __str__(self) -> str:
        return f'{self.code} (xref={self.xref})'

@dataclass(frozen=True, slots=True)
class FontRef:
    font: int
    descendant: int
    descriptor: int
    subtype: str

@dataclass(frozen=True, slots=True)
class Metric:
    cap_height: float
    metric_source: str
    postscript_name: str
    embedded_sha256: str

@dataclass(frozen=True, slots=True)
class FontEvidence:
    font_xref: int
    descriptor_xref: int
    subtype: str
    postscript_name: str
    cap_height: float
    metric_source: str
    embedded_sha256: str

@dataclass(frozen=True, slots=True)
class AuditReport:
    fonts: tuple[FontEvidence,...]
    passed: bool
    requires_indesign_placement: bool = True

def reference(doc: fitz.Document, xref: int, key: str) -> int:
    """Require an actual indirect object reference."""
    kind,value=doc.xref_get_key(xref,key)
    if kind!='xref':
        raise FontSafetyError(f'font_reference_missing:{key}',xref)
    return int(value.split()[0])

def fonts(doc: fitz.Document) -> tuple[FontRef,...]:
    """Follow page and Form XObject resources, preserving font subtype rules."""
    refs=[]
    seen=set()
    for page in doc:
        for row in page.get_fonts(full=True):
            xref=row[0]
            if xref in seen:
                continue
            seen.add(xref)
            subtype=row[2]
            descendant=xref
            if subtype=='Type0':
                kind,value=doc.xref_get_key(xref,'DescendantFonts')
                targets=re.findall(r'(\d+)\s+\d+\s+R',value) if kind=='array' else []
                if len(targets)!=1:
                    raise FontSafetyError('type0_descendant_invalid',xref)
                descendant=int(targets[0])
                subtype=doc.xref_get_key(descendant,'Subtype')[1].lstrip('/')
            if subtype not in {'TrueType','Type1','CIDFontType2','CIDFontType0'}:
                raise FontSafetyError(f'font_subtype_unsupported:{subtype}',xref)
            refs.append(FontRef(xref,descendant,reference(doc,descendant,'FontDescriptor'),subtype))
    return tuple(refs)

def metric(doc: fitz.Document, ref: FontRef) -> Metric:
    """Use embedded sfnt cap metrics or an actual H outline; never ascent guesses."""
    streams=[reference(doc,ref.descriptor,k) for k in ('FontFile','FontFile2','FontFile3') if doc.xref_get_key(ref.descriptor,k)[0]=='xref']
    if len(streams)!=1:
        raise FontSafetyError('embedded_font_stream_invalid',ref.descriptor)
    data=doc.xref_stream(streams[0])
    if data[:4] not in (b'\x00\x01\x00\x00',b'OTTO',b'true'):
        raise FontSafetyError('embedded_font_format_unsupported',ref.descriptor)
    with TTFont(io.BytesIO(data)) as font:
        units=font['head'].unitsPerEm
        cap=getattr(font['OS/2'],'sCapHeight',0) if 'OS/2' in font else 0
        source='embedded:OS/2.sCapHeight'
        if cap<=0:
            name=(font.getBestCmap() or {}).get(ord('H'))
            if not name:
                raise FontSafetyError('cap_height_unproven',ref.descriptor)
            glyphs=font.getGlyphSet()
            pen=BoundsPen(glyphs)
            glyphs[name].draw(pen)
            if pen.bounds is None or pen.bounds[3]<=0:
                raise FontSafetyError('cap_height_unproven',ref.descriptor)
            cap=pen.bounds[3]
            source='embedded:H-outline-yMax'
        names=[n.toUnicode() for n in font['name'].names if n.nameID==6]
        if not names or len(set(names))!=1:
            raise FontSafetyError('postscript_name_unproven',ref.descriptor)
        name=names[0]
        if not name or re.search(r'[\s()<>\[\]{}/%]',name):
            raise FontSafetyError('postscript_name_invalid',ref.descriptor)
        return Metric(cap*1000/units,source,name,hashlib.sha256(data).hexdigest())

def check_fields(doc: fitz.Document, ref: FontRef) -> None:
    """Check required descriptor keys for the supported embedded font families."""
    required={'FontName':{'name'},'Flags':{'int'},'FontBBox':{'array'},'ItalicAngle':{'int','float'},'Ascent':{'int','float'},'Descent':{'int','float'},'CapHeight':{'int','float'},'StemV':{'int','float'}}
    for key,kinds in required.items():
        kind,value=doc.xref_get_key(ref.descriptor,key)
        if kind=='null':
            raise FontSafetyError(f'descriptor_field_missing:{key}',ref.descriptor)
        if kind not in kinds:
            raise FontSafetyError(f'descriptor_field_type:{key}',ref.descriptor)
        if kind in {'int','float'} and not math.isfinite(float(value)):
            raise FontSafetyError(f'descriptor_field_nonfinite:{key}',ref.descriptor)
    if doc.xref_get_key(ref.descriptor,'Type')!=('name','/FontDescriptor'):
        raise FontSafetyError('descriptor_type_invalid',ref.descriptor)
    bbox=doc.xref_get_key(ref.descriptor,'FontBBox')[1]
    values=re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)',bbox)
    if len(values)!=4 or not all(math.isfinite(float(v)) for v in values) or float(values[0])>float(values[2]) or float(values[1])>float(values[3]):
        raise FontSafetyError('descriptor_bbox_invalid',ref.descriptor)

def audit_document(doc: fitz.Document) -> AuditReport:
    """Audit saved-byte descriptors independently of rendering success."""
    evidence=[]
    for ref in fonts(doc):
        check_fields(doc,ref)
        actual=metric(doc,ref)
        cap=float(doc.xref_get_key(ref.descriptor,'CapHeight')[1])
        if abs(cap-actual.cap_height)>.01:
            raise FontSafetyError('cap_height_metric_mismatch',ref.descriptor)
        for xref,key in ((ref.font,'BaseFont'),(ref.descendant,'BaseFont'),(ref.descriptor,'FontName')):
            if doc.xref_get_key(xref,key)!=('name','/'+actual.postscript_name):
                raise FontSafetyError(f'postscript_name_mismatch:{key}',xref)
        evidence.append(FontEvidence(ref.font,ref.descriptor,ref.subtype,actual.postscript_name,cap,actual.metric_source,actual.embedded_sha256))
    return AuditReport(tuple(evidence),True)

def complete_descriptors(doc: fitz.Document) -> None:
    """Minimal pre-save mutation: CapHeight and proven PostScript name only."""
    measured=[(ref,metric(doc,ref)) for ref in fonts(doc)]
    for ref,value in measured:
        if doc.xref_get_key(ref.descriptor,'Type')[0]=='null':
            doc.xref_set_key(ref.descriptor,'Type','/FontDescriptor')
        kind=doc.xref_get_key(ref.descriptor,'CapHeight')[0]
        if kind=='null':
            doc.xref_set_key(ref.descriptor,'CapHeight',format(value.cap_height,'.12g'))
        doc.xref_set_key(ref.descendant,'BaseFont','/'+value.postscript_name)
        if ref.font==ref.descendant:
            doc.xref_set_key(ref.descriptor,'FontName','/'+value.postscript_name)
    normalize_type0_font_names(doc)
    audit_document(doc)

def finalize_pdf(source: Path, output: Path) -> AuditReport:
    """Write a new isolated PDF, then reopen and audit the exact saved bytes."""
    if source.resolve()==output.resolve() or output.exists():
        raise FontSafetyError('output_must_be_new_path',0)
    with fitz.open(source) as doc:
        complete_descriptors(doc)
        doc.save(output,garbage=0,deflate=False)
    with fitz.open(output) as saved:
        return audit_document(saved)
