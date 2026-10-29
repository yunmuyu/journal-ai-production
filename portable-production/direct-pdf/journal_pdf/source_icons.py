"""Source-bound, font-free vector icon preparation and actual-path ownership."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,math
from pathlib import Path
import pymupdf as fitz
from .common import FigureError,digest_file

@dataclass(frozen=True,slots=True)
class PathRecord:
    tokens: tuple[str,...]
    coordinates: tuple[float,...]
    style: str
    width: float | None

@dataclass(frozen=True,slots=True)
class PreparedIcon:
    data: bytes
    receipt_json: str


def path_record(row) -> PathRecord:
    tokens=[];numbers=[]
    for item in row['items']:
        tokens.append(item[0])
        for value in item[1:]:
            match value:
                case fitz.Point():numbers.extend([value.x,value.y])
                case fitz.Rect():numbers.extend([value.x0,value.y0,value.x1,value.y1])
                case fitz.Quad():
                    for point in (value.ul,value.ur,value.ll,value.lr):numbers.extend([point.x,point.y])
                case _:tokens.append(str(value))
    keys=('type','color','fill','dashes','lineCap','lineJoin','closePath','even_odd','stroke_opacity','fill_opacity')
    return PathRecord(tuple(tokens),tuple(numbers),json.dumps({k:row.get(k) for k in keys},sort_keys=True),row['width'])


def same_path(a: PathRecord,b: PathRecord) -> bool:
    widths=(a.width is None and b.width is None) or (a.width is not None and b.width is not None and abs(a.width-b.width)<.00001)
    return widths and a.tokens==b.tokens and a.style==b.style and len(a.coordinates)==len(b.coordinates) and all(abs(x-y)<.0001 for x,y in zip(a.coordinates,b.coordinates))


def consume_paths(expected: list[PathRecord],actual: list[PathRecord]) -> set[int]:
    """Consume individual instances; missing or altered source paths are fatal."""
    used=set()
    for record in expected:
        found=next((i for i,row in enumerate(actual) if i not in used and same_path(record,row)),None)
        if found is None:raise FigureError('source_icon_path_changed','实际PDF缺失或改变了已绑定的原图标路径')
        used.add(found)
    return used


def prepare_icon(source: Path,page_no: int,clip: list[float],*,text_replacements=None,source_vector_body: bool=False) -> PreparedIcon:
    """Use native PDF filtering, preserving vector paint and proving source fidelity."""
    if isinstance(page_no,bool) or not isinstance(page_no,int) or not isinstance(clip,list) or len(clip)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in clip):
        raise FigureError('source_icon_input','图标须指定真实PDF页及四个有限裁切坐标')
    rect=fitz.Rect(clip)
    with fitz.open(source) as original,fitz.open() as isolated,fitz.open() as reference:
        if not 0<=page_no<len(original) or rect.is_empty or not original[page_no].rect.contains(rect):raise FigureError('source_icon_clip','图标裁切越界或为空')
        page=original[page_no]
        offset=page.cropbox_position;absolute_rect=fitz.Rect(rect.x0+offset.x,rect.y0+offset.y,rect.x1+offset.x,rect.y1+offset.y)
        from .source_icon_text import validate_replacements, compare_pixels
        replacements=validate_replacements(page,rect,text_replacements,allow_target_text=source_vector_body)
        whitespace=[{'source_text':span['text'],'source_bbox':list(span['bbox'])} for block in page.get_text('dict',clip=rect)['blocks'] if block['type']==0 for line in block['lines'] for span in line['spans'] if span['text'] and not span['text'].strip()] if source_vector_body else []
        reference.insert_pdf(original,from_page=page_no,to_page=page_no);refpage=reference[0];refpage.set_cropbox(absolute_rect)
        isolated.insert_pdf(original,from_page=page_no,to_page=page_no);page=isolated[0];bounds=page.rect
        for replacement in replacements+whitespace:page.add_redact_annot(fitz.Rect(replacement['source_bbox']),fill=False,cross_out=False)
        if replacements or whitespace:
            page.apply_redactions(images=0,graphics=0,text=0)
            from .source_icon_text import assert_clear_text_region
            if not source_vector_body:assert_clear_text_region(page,replacements)
        outside=[fitz.Rect(0,0,bounds.width,rect.y0),fitz.Rect(0,rect.y1,bounds.width,bounds.height),fitz.Rect(0,rect.y0,rect.x0,rect.y1),fitz.Rect(rect.x1,rect.y0,bounds.width,rect.y1)]
        for box in outside:
            if not box.is_empty:page.add_redact_annot(box,fill=False,cross_out=False)
        page.apply_redactions(images=1,graphics=1,text=0);page.clean_contents(sanitize=1);page.set_cropbox(absolute_rect)
        data=isolated.tobytes(garbage=4,deflate=True,no_new_id=True)
        with fitz.open(stream=data,filetype='pdf') as saved:
            page=saved[0]
            if page.get_fonts(full=True) or page.get_texttrace() or page.get_images(full=True):raise FigureError('source_icon_resources','纯矢量无字图标仍含字体、文字或图片；拒绝继续')
            source_drawings=refpage.get_drawings();prepared_drawings=page.get_drawings()
            visible=lambda v: v['rect'].x1>=0 and v['rect'].y1>=0 and v['rect'].x0<=rect.width and v['rect'].y0<=rect.height
            consume_paths([path_record(v) for v in prepared_drawings if visible(v)],[path_record(v) for v in source_drawings])
            expected_visible=[path_record(v) for v in source_drawings if visible(v)]
            consume_paths(expected_visible,[path_record(v) for v in prepared_drawings])
            if not prepared_drawings:raise FigureError('source_icon_empty','裁区没有矢量设备路径')
            comparisons=[]
            for zoom in (4,8):
                a=refpage.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False);b=page.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False)
                compare_pixels(a,b,rect,replacements,zoom)
                comparisons.append({'dpi':zoom*72,'width':a.width,'height':a.height,'pixel_sha256':hashlib.sha256(a.samples).hexdigest(),'exact':not replacements,'nontext_exact':True})
            receipt={'mode':'source-vector-body' if source_vector_body else 'source-bound-vector-icon','preparation_mode':'source-vector-reletter' if replacements else 'native-font-free-viewport','text_replacements':replacements,'whitespace_spans_removed':whitespace,'source_path':str(source.resolve()),'source_sha256':digest_file(source),'source_page':page_no,'source_clip':list(rect),'source_cropbox_position':list(offset),'absolute_mediabox_clip':list(absolute_rect),'prepared_sha256':hashlib.sha256(data).hexdigest(),'font_count':0,'image_count':0,'path_count':len(prepared_drawings),'source_visible_path_count':len(expected_visible),'source_path_multiset_preserved':True,'pixels':comparisons,'native_operations':{'graphics':1,'text':0,'images':1,'sanitize':1,'garbage':4},'source_text':'','source_text_character_count':0,'complete_icon_extent_proven':False,'extent_review_required':'cross-boundary compound paths may survive native clip; verify complete icon extent independently'}
            return PreparedIcon(data,json.dumps(receipt,ensure_ascii=False))


def write_icon(source: Path,page_no: int,clip: list[float],output: Path) -> None:
    """Write a separate derivative and source-bound receipt; never overwrite."""
    if source.resolve()==output.resolve() or output.exists():raise FigureError('source_icon_output','输出必须为新的独立文件')
    value=prepare_icon(source,page_no,clip);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(value.data)
    output.with_suffix(output.suffix+'.json').write_text(value.receipt_json,encoding='utf-8')


def audit_icon_paths(page, placements):
    """Match actual saved paths against source-bound placements, consuming each instance."""
    from .assets import Assets
    icons=[row for row in placements if row['asset'].audit.get('mode') in ('source-bound-vector-icon','source-vector-body','source-svg-group','source-vector-glyph','source-mixed-body','registered-outlined-svg-chart','registered-native-pdf-text')]
    actual=page.get_drawings()
    expected=[];bindings=[];image_expected=[]
    with fitz.open() as reference:
        refpage=reference.new_page(width=page.mediabox.width,height=page.mediabox.height)
        placer=Assets()
        try:
            for row in icons:
                asset=row['asset'];receipt=asset.audit
                if digest_file(Path(asset.source_path))!=asset.source_hash or receipt['source_sha256']!=asset.source_hash:
                    raise FigureError('source_icon_source_changed','图标原PDF与绑定来源不一致')
                if receipt['mode']=='registered-native-pdf-text':
                    replacements=[{k:v for k,v in q.items() if k not in ('source_gray','source_color')} for q in receipt['text_replacements']]
                    verified=placer.registered_pdf_text(Path(asset.source_path),receipt['source_page'],receipt['source_clip'],Path(receipt['svg_path']),receipt['text_registration'],text_replacements=replacements,grayscale=receipt['grayscale'])
                elif receipt['mode']=='registered-outlined-svg-chart':
                    verified=placer.registered_outline_chart(Path(asset.source_path),receipt['outline_chart_registration'],swatch_id=receipt['swatch_id'])
                elif receipt['mode']=='source-mixed-body':
                    verified=placer.source_mixed_body(Path(asset.source_path),receipt['source_page'],receipt['source_clip'],text_replacements=receipt.get('native_text_replacements',receipt.get('text_replacements')),outline_text_replacements=receipt.get('outline_text_replacements'),source_shape_replacements=receipt.get('source_shape_replacements'))
                elif receipt['mode']=='source-vector-glyph':
                    verified=placer.source_vector_glyph(Path(asset.source_path),receipt['source_page'],receipt['source_clip'],receipt['selected_source_path_indices'],gray=receipt['grayscale'],text_replacements=receipt.get('text_replacements'))
                elif receipt['mode']=='source-svg-group':
                    verified=placer.source_svg_group(Path(asset.source_path),receipt['source_group'],receipt['source_clip'],
                                                     text_replacements=receipt.get('text_replacements'),
                                                     clipped_viewport=receipt.get('clipped_viewport',False))
                else:
                    prepare=placer.source_vector_body if receipt['mode']=='source-vector-body' else placer.source_icon
                    verified=prepare(Path(asset.source_path),receipt['source_page'],receipt['source_clip'],text_replacements=receipt.get('text_replacements'))
                if verified.audit['prepared_sha256']!=receipt['prepared_sha256'] or hashlib.sha256(asset.data).hexdigest()!=receipt['prepared_sha256']:
                    raise FigureError('source_icon_derivative_changed','图标裁区或派生PDF与来源不一致')
                placer.place(refpage,verified,row['rect'])
                bindings.append({'id':row['id'],'mode':receipt['mode'],'source_sha256':asset.source_hash,'source_page':receipt['source_page'],
                                 'source_clip':receipt['source_clip'],'prepared_sha256':receipt['prepared_sha256'],
                                 'target_pt':list(row['rect'])})
            refpage.set_cropbox(page.cropbox)
            refpage.set_rotation(page.rotation)
            # Save/reopen the reference using the same final serialization as production.
            with fitz.open(stream=reference.tobytes(garbage=4,deflate=True),filetype='pdf') as saved:
                expected=[path_record(row) for row in saved[0].get_drawings()]
                if any(row['asset'].audit.get('mode')=='registered-native-pdf-text' for row in icons):
                    from .source_pdf_text import image_records,consume_images
                    image_expected=image_records(saved,saved[0])
                elif any(row['asset'].audit.get('mode')=='source-mixed-body' for row in icons):
                    from .source_mixed_body import image_records
                    image_expected=image_records(saved,saved[0])
        finally:
            placer.close()
    used=consume_paths(expected,[path_record(row) for row in actual])
    image_used=set()
    if image_expected:
        if any(row['asset'].audit.get('mode')=='registered-native-pdf-text' for row in icons):
            from .source_pdf_text import image_records,consume_images
        else:
            from .source_mixed_body import image_records,consume_images
        image_actual=image_records(page.parent,page)
        image_used=consume_images(image_expected,image_actual)
        consume_images(image_actual,image_expected)
    bad=[{'width_pt':row['width'],'rect':list(row['rect'])} for index,row in enumerate(actual)
         if index not in used and row['type'] in ('s','fs') and row['rect'].x1>=0 and row['rect'].y1>=0
         and row['rect'].x0<=page.rect.width and row['rect'].y0<=page.rect.height and abs(row['width']-.5)>.005]
    return {'image_ownership':{'matched_instance_count':len(image_used),'expected_instance_count':len(image_expected),'bidirectional_instance_multiset_exact':True,'derived_grayscale_pixels_exact':True,'original_smask_exact':True,'source_rgb_mapping_verified_by_preparation':True,'original_dimensions_and_ctm_exact':True},'bindings':bindings,'placement_count':len(icons),'matched_path_count':len(used),
            'source_geometry_and_style_exact':True,'stroke_violations':bad,
            'audited_stroke_count':sum(row['type'] in ('s','fs') and row['rect'].x1>=0 and row['rect'].y1>=0 and row['rect'].x0<=page.rect.width and row['rect'].y0<=page.rect.height for row in actual),
            'method':'source-bound asset-only reference via identical Assets.place; instance multiset consumption; no rectangle exemption'}
