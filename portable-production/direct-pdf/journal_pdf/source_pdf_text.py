"""Explicit complete native-PDF text registration against companion SVG text groups."""
from __future__ import annotations
import collections, hashlib, json, re
from pathlib import Path
import pymupdf as fitz
from .common import FigureError, digest_file
from .source_icons import PreparedIcon, consume_paths, path_record
from .source_icon_text import validate_replacements


def need(ok, message):
    if not ok: raise FigureError('pdf_text_registration', message)


def pdf_white_text(source,page_no):
    """Independently decode PDF text with its native fill graphics state."""
    from pypdf import PdfReader
    color=(0.,);stack=[];white=[];paint=[]
    def operand(op,args,cm,tm):
        nonlocal color
        if op==b'q':stack.append(color)
        elif op==b'Q':
            need(bool(stack),'Unbalanced PDF graphics state');color=stack.pop()
        elif op in (b'g',b'rg'):color=tuple(map(float,args))
        elif op in (b'k',b'cs',b'sc',b'scn'):color=None
        if op in (b'Tj',b'TJ',b"'",b'"'):paint.append(color)
    def text(value,cm,tm,font,size):
        if value.strip():
            need(paint and all(q==paint[0] for q in paint),'Mixed or ambiguous PDF text paint')
            if paint[0] and all(abs(v-1)<1e-8 for v in paint[0]):white.append(value.strip())
        paint.clear()
    PdfReader(str(source)).pages[page_no].extract_text(visitor_operand_before=operand,visitor_text=text)
    return collections.Counter(white)


def svg_white(node):
    fill='black'
    for q in [*reversed(list(node.iterancestors())),node]:
        fill=q.get('fill',fill)
        for term in q.get('style','').split(';'):
            if ':' in term:
                key,value=term.split(':',1)
                if key.strip()=='fill':fill=value.strip()
    return fill.lower().replace(' ','') in ('white','#fff','#ffffff','rgb(255,255,255)')


def svg_text_content(node):
    # Matplotlib math text uses explicitly positioned tspans. Indentation
    # outside those spans is not a glyph in the positioned expression.
    children=list(node)
    preserve=any(q.get('{http://www.w3.org/XML/1998/namespace}space')=='preserve' for q in [node,*node.iterancestors()])
    if (children and not preserve and not (node.text or '').strip()
            and all(isinstance(q.tag,str) and q.tag.endswith('}tspan') and q.get('x') is not None and not (q.tail or '').strip() for q in children)):
        return ''.join(''.join(q.itertext()) for q in children)
    return ''.join(node.itertext())


def image_records(doc, page):
    rows=[]
    for info in page.get_image_info(xrefs=True):
        xref=info['xref'];need(xref, 'Inline images are not supported by this registration')
        pix=fitz.Pixmap(doc,xref)
        mask=doc.xref_get_key(xref,'SMask')
        alpha=doc.xref_stream(int(mask[1].split()[0])) if mask[0]=='xref' else b''
        rows.append({'bbox':list(info['bbox']),'transform':list(info['transform']),
                     'width':pix.width,'height':pix.height,'n':pix.n,
                     'pixels':hashlib.sha256(pix.samples).hexdigest(),
                     'alpha':hashlib.sha256(alpha).hexdigest(),
                     'decode':doc.xref_get_key(xref,'Decode'),'interpolate':doc.xref_get_key(xref,'Interpolate')})
    return rows


def consume_images(expected,actual):
    remaining=list(actual)
    for row in expected:
        match=next((i for i,q in enumerate(remaining) if all(q[k]==row[k] for k in row if k not in ('bbox','transform'))
                    and all(abs(a-b)<.0001 for k in ('bbox','transform') for a,b in zip(q[k],row[k],strict=True))),None)
        need(match is not None,'Source image pixels, alpha or placement changed')
        remaining.pop(match)
    need(not remaining,'Unexpected image instance')
    return set(range(len(actual)))


def validate_registration(source, page, svg_path, registration):
    from lxml import etree as ET
    need(isinstance(registration,dict),'Explicit registration is required')
    need(registration.get('pdf_sha256')==digest_file(source) and registration.get('svg_sha256')==digest_file(svg_path),'Source hash changed')
    root=ET.parse(str(svg_path),ET.XMLParser(resolve_entities=False,no_network=True,load_dtd=False)).getroot()
    need(root.tag=='{http://www.w3.org/2000/svg}svg' and not any(isinstance(q,ET._Entity) for q in root.iter()),'Unsafe SVG document')
    backgrounds=registration.get('nontext_svg_groups',[])
    need(all(isinstance(q,dict) and q.get('role')=='label-background' for q in backgrounds),'Unsupported nontext declaration')
    background_ids={q['id'] for q in backgrounds}
    groups={q.get('id'):q for q in root.findall('.//{*}g') if re.fullmatch(r'text_\d+',q.get('id',''))}
    need(groups,'Companion SVG has no text_N groups')
    leaves={}
    for gid,g in groups.items():
        need(all(q.tag.rsplit('}',1)[-1] in ('g','text','tspan') or (q.tag.rsplit('}',1)[-1] in ('path','rect') and any(a.get('id') in background_ids for a in q.iterancestors())) for q in g.iter() if isinstance(q.tag,str)), 'Outlined or undeclared paint inside text groups is unsupported')
        leaves[gid]=g.findall('.//{*}text')
    need(sum(map(len,leaves.values()))==len(root.findall('.//{*}text')),'SVG has unregistered text outside text_N groups')
    spans=[s for b in page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans'] if s['text'].strip()]
    used=set();seen=set();seen_groups=set();white_text=[]
    for row in registration.get('groups',[]):
        gid=row.get('svg_group_id');need(gid in groups and gid not in seen_groups,'Missing or duplicate SVG group');seen_groups.add(gid)
        for entry in row.get('entries',[]):
            i=entry.get('svg_text_index');ids=entry.get('pdf_span_indices')
            need(type(i) is int and 0<=i<len(leaves[gid]) and (gid,i) not in seen,'Invalid or duplicate SVG text');seen.add((gid,i))
            need(isinstance(ids,list) and ids and all(type(j) is int and 0<=j<len(spans) and j not in used for j in ids) and len(set(ids))==len(ids),'Invalid or duplicate PDF span')
            pdf_text=''.join(spans[j]['text'] for j in ids);svg_text=svg_text_content(leaves[gid][i])
            whitespace_equivalent=(entry.get('layout_whitespace_equivalent') is True and ''.join(pdf_text.split())==''.join(svg_text.split()))
            need(pdf_text==svg_text or whitespace_equivalent,'PDF and SVG text differ')
            white=svg_white(leaves[gid][i])
            if white:white_text.append(svg_text.strip())
            for j in ids:spans[j]['registered_gray']=int(white)
            used.update(ids)
    need(seen_groups==set(groups) and len(seen)==sum(map(len,leaves.values())) and len(used)==len(spans),'Incomplete whole-page text registration')
    need(collections.Counter(white_text)==pdf_white_text(source,page.number),'SVG white labels and PDF text paint disagree')
    return spans


def prepare_registered_text(source:Path,page_no:int,clip,svg_path:Path,registration,*,text_replacements=None,grayscale=False):
    need(type(grayscale) is bool,'grayscale must be an explicit boolean')
    with fitz.open(source) as original,fitz.open() as work:
        need(type(page_no) is int and 0<=page_no<len(original),'Invalid PDF page')
        page=original[page_no];rect=fitz.Rect(clip)
        need(not page.rotation and page.cropbox_position==fitz.Point(0,0) and not rect.is_empty and page.rect.contains(rect),'Unsupported crop or rotation')
        spans=validate_registration(source,page,svg_path,registration)
        # A clip cannot split an existing label: registration must stay exact.
        need(all(rect.contains(fitz.Rect(s['bbox'])) or not rect.intersects(fitz.Rect(s['bbox'])) for s in spans),'Clip cuts a source text span')
        replacements=validate_replacements(page,rect,text_replacements,allow_target_text=True)
        for row in replacements:
            original_span=next(s for s in spans if s['text']==row['source_text'] and all(abs(a-b)<.01 for a,b in zip(s['bbox'],row['source_bbox'])))
            row['source_color']=original_span['color']
            row['source_gray']=original_span['registered_gray']
        paths=[path_record(q) for q in page.get_drawings()];images=image_records(original,page)
        # Type3 glyph programs also appear in get_drawings. Remove only native
        # text-show operators, preserving every nontext operation and resource.
        from io import BytesIO
        from pypdf import PdfReader,PdfWriter
        from pypdf.generic import ContentStream
        writer=PdfWriter();writer.add_page(PdfReader(str(source)).pages[page_no])
        stream=ContentStream(writer.pages[0].get_contents(),writer)
        removed=sum(op in (b'Tj',b'TJ',b"'",b'"') for args,op in stream.operations)
        need(not any(op==b'Tr' and int(args[0])>=4 for args,op in stream.operations),'Text clipping modes are unsupported')
        text_ops={b'BT',b'ET',b'Tj',b'TJ',b"'",b'"',b'Tf',b'Tm',b'Td',b'TD',b'T*',b'Tc',b'Tw',b'Tz',b'TL',b'Tr',b'Ts'}
        stream.operations=[(args,op) for args,op in stream.operations if op not in text_ops]
        writer.pages[0]['/Resources'].pop('/Font',None)
        writer.pages[0].replace_contents(stream);buffer=BytesIO();writer.write(buffer)
        with fitz.open(stream=buffer.getvalue(),filetype='pdf') as stripped:work.insert_pdf(stripped)
        out=work[0];paths=[path_record(q) for q in out.get_drawings()]
        out.clean_contents(sanitize=1)
        consume_paths(paths,[path_record(q) for q in out.get_drawings()]);need(len(paths)==len(out.get_drawings()),'Unexpected source paths')
        consume_images(images,image_records(work,out))
        need(not out.get_text().strip(),'Residual native text after removal')
        out.set_cropbox(rect)
        data=work.tobytes(garbage=4,deflate=True,no_new_id=True)
        gray_proof=[]
        if grayscale:
            from .source_native_gray import native_gray,grayscale_rgb_bytes,replace_rgb_image_pixels
            # Resolve palette pixels explicitly; retain dimensions, placement and SMask.
            with fitz.open(stream=data,filetype='pdf') as mapped:
                for xref in {q[0] for q in mapped[0].get_images()}:
                    need(mapped.xref_get_key(xref,'Decode')[0]=='null','Image Decode transform is unsupported')
                    pix=fitz.Pixmap(mapped,xref);rgb=fitz.Pixmap(fitz.csRGB,pix) if pix.colorspace.n!=3 else pix
                    pixels=rgb.samples
                    gray=grayscale_rgb_bytes(pixels)
                    replace_rgb_image_pixels(mapped,xref,gray)
                    gray_proof.append({'original_rgb_sha256':hashlib.sha256(pixels).hexdigest(),'gray_rgb_sha256':hashlib.sha256(gray).hexdigest(),'formula':'round(.299 R+.587 G+.114 B), replicated RGB','dimensions_and_smask_unchanged':True})
                data=mapped.tobytes(garbage=4,deflate=True,no_new_id=True)
            data,vector_proof=native_gray(data,allow_image_xobjects=True)
            with fitz.open(stream=data,filetype='pdf') as verified_gray:
                decoded={hashlib.sha256(fitz.Pixmap(verified_gray,q[0]).samples).hexdigest() for q in verified_gray[0].get_images()}
                need(decoded=={q['gray_rgb_sha256'] for q in gray_proof},'Serialized gray image pixels differ from the declared mapping')
            for proof in gray_proof:proof['serialized_decoded_pixels_exact']=True
            gray_proof.extend(vector_proof)
        receipt={'mode':'registered-native-pdf-text','source_path':str(source.resolve()),'source_sha256':digest_file(source),
                 'source_page':page_no,'source_clip':list(rect),'prepared_sha256':hashlib.sha256(data).hexdigest(),
                 'svg_path':str(svg_path.resolve()),'text_registration':registration,'text_replacements':replacements,
                 'source_text':'','registered_native_span_count':len(spans),'companion_svg_all_text_registered':True,
                 'source_nontext_operators_preserved':True,'removed_native_text_show_operations':removed,'prepared_path_multiset_preserved_before_gray':True,'source_image_pixels_preserved':not grayscale,
                 'grayscale':grayscale,'grayscale_proof':gray_proof,
                 'coverage_scope':'All native PDF spans and all companion SVG text_N text elements; not automatic outlined-text detection.'}
        return PreparedIcon(data,json.dumps(receipt,ensure_ascii=False))
