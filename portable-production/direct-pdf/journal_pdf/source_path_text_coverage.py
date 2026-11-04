"""Complete, source-bound declarations for non-text chart/diagram strokes.

This does not recognize outlined letters. Every retained object needs an explicit
semantic binding; filled glyph silhouettes and image content remain unsupported.
"""
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import pymupdf as fitz
from .common import FigureError
from .source_icons import path_record


def path_fingerprint(row) -> str:
    return hashlib.sha256(json.dumps(asdict(path_record(row)), sort_keys=True).encode()).hexdigest()


def validate_nontext_paths(source: Path, page_number: int, clip, declarations: list) -> dict:
    if not isinstance(declarations,list):
        raise FigureError('source_path_text_binding','Non-text path bindings must be a list')
    with fitz.open(source) as doc:
        page=doc[page_number];viewport=fitz.Rect(clip)
        if any(viewport.intersects(fitz.Rect(image['bbox'])) for image in page.get_image_info()):
            raise FigureError('source_path_text_binding','Image typography is outside non-text path registration')
        paths={i:row for i,row in enumerate(page.get_drawings()) if viewport.intersects(row['rect']) or viewport.contains(row['rect'])}
        bound={}
        for item in declarations:
            if (not isinstance(item,dict) or set(item)!={'index','sha256','role','basis'}
                    or type(item['index']) is not int or item['index'] not in paths or item['index'] in bound
                    or item['role'] not in ('axis','tick','curve','diagram')
                    or not isinstance(item['basis'],str) or not item['basis'].strip()):
                raise FigureError('source_path_text_binding','Every retained path needs one reviewed role and basis')
            row=paths[item['index']]
            if row.get('fill') is not None or row.get('type')!='s':
                raise FigureError('source_path_text_binding','Filled/outlined glyph candidates require a text registration route')
            if item['sha256']!=path_fingerprint(row):
                raise FigureError('source_path_text_binding','Source geometry binding changed',index=item['index'])
            if not viewport.contains(row['rect']):
                raise FigureError('source_path_text_binding','Partially clipped compound paths require separate registration')
            bound[item['index']]=item
        if set(bound)!=set(paths):
            raise FigureError('source_path_text_binding','Non-text registration must cover all retained paths',missing=sorted(set(paths)-set(bound)))
    return {'status':'all-retained-paths-bound','source_path_count':len(paths),
            'bindings':[bound[i] for i in sorted(bound)],'scope':'Reviewed non-text stroke identities; not automatic outlined-text recognition'}
