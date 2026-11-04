"""Validate reflowed source text without introducing a painted dummy asset.

These receipts cover text identity only. They neither remove source graphics nor
prove that a caller's selected source viewports contain every data object.
"""
from pathlib import Path
import pymupdf as fitz
from .common import FigureError, resolve_source, digest_file
from .source_icon_text import validate_replacements
from .source_pdf_text import validate_registration


def bind_source_text(scene, declarations, root: Path) -> set[str]:
    """Bind exact registered source spans to editable scene text; draw nothing."""
    if not isinstance(declarations,list):
        raise FigureError('source_text_bindings','Text bindings must be a list')
    targets={t['id']:t for t in scene.texts}
    records=[];ids=set();used_targets=set();white=set()
    for declaration in declarations:
        ident=declaration.get('id')
        if not isinstance(ident,str) or not ident or ident in ids:
            raise FigureError('source_text_bindings','Unique nonempty binding ID required')
        ids.add(ident)
        source=resolve_source(root,declaration['path'])
        registration=declaration['text_registration']
        svg=resolve_source(root,registration['svg_path'])
        page_no=declaration.get('page',0)
        with fitz.open(source) as doc:
            if type(page_no) is not int or not 0<=page_no<len(doc):
                raise FigureError('source_text_bindings','Invalid source page')
            page=doc[page_no];clip=fitz.Rect(declaration['clip'])
            if clip.is_empty or clip.is_infinite or not page.rect.contains(clip):
                raise FigureError('source_text_bindings','Invalid source text viewport')
            spans=validate_registration(source,page,svg,registration)
            rows=validate_replacements(page,clip,declaration.get('text_replacements'))
            if not rows:
                raise FigureError('source_text_bindings','A text binding must identify source text')
            for row in rows:
                tid=row['target_text_id'];target=targets.get(tid)
                from .quantity_spacing import normalize_quantity_spacing
                allowed={row['source_text'],normalize_quantity_spacing(row['source_text'],target.get('role','label') if target else 'label')}
                if tid in used_targets or target is None or ''.join(target['measurement']['text'].splitlines()) not in allowed:
                    raise FigureError('source_text_binding_target','Bound source text must have one matching editable target')
                original=next(s for s in spans if s['text']==row['source_text'] and all(abs(a-b)<.01 for a,b in zip(s['bbox'],row['source_bbox'])))
                gray=original['registered_gray']
                if target.get('gray',0)!=gray:
                    raise FigureError('source_text_color','Bound text must preserve source black/white contrast')
                if gray:white.add(tid)
                used_targets.add(tid)
        records.append({'id':ident,'source_sha256':digest_file(source),'svg_sha256':digest_file(svg),
                        'source_page':page_no,'source_clip':list(clip),'text_replacements':rows,
                        'target_text_ids':[r['target_text_id'] for r in rows],
                        'draws_source_geometry':False,'scope':'text identity only; not source graphic coverage'})
    scene.layout_evidence['source_text_bindings']=records
    return white
