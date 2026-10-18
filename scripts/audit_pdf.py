"""Render the PDF itself and detect image loss relative to the native preview."""
from pathlib import Path
import json
import sys
import math
from pypdf.generic import ContentStream
from PIL import Image, ImageChops, ImageFilter
from pypdf import PdfReader
import pypdfium2 as pdfium

STROKE_TARGET_PT = 0.5
STROKE_TOLERANCE_PT = 0.005  # PDF width/transform operands are commonly rounded to 3 decimals.
STROKE_PAINT = {b'S', b's', b'B', b'B*', b'b', b'b*'}

def stroke_audit(reader: PdfReader, target_pt: float = STROKE_TARGET_PT) -> dict[str, object]:
    """Measure painted path strokes in final page coordinates, including nested Forms."""
    if not math.isfinite(target_pt) or target_pt<=0:raise ValueError('Invalid physical stroke target')
    dash_patterns=[];unverified_dashes=0
    widths: list[float] = []
    issues: list[dict[str, float | int]] = []
    filled_only_paths = 0
    nonuniform_curves_sampled = 0

    def dash_state(value):
        if not isinstance(value,(list,tuple))or len(value)!=2 or not isinstance(value[0],(list,tuple)):raise ValueError('Invalid PDF dash state')
        pattern,phase=value
        if any(not isinstance(v,(int,float))or not math.isfinite(v)or v<0 for v in pattern)or pattern and not any(pattern)or not isinstance(phase,(int,float))or not math.isfinite(phase)or phase<0:raise ValueError('Invalid PDF dash pattern or phase')
        return tuple(map(float,pattern)),float(phase)

    def multiply(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float, ...]:
        a,b,c,d,e,f = left
        g,h,i,j,k,l = right
        return (a*g+c*h,b*g+d*h,a*i+c*j,b*i+d*j,a*k+c*l+e,b*k+d*l+f)

    def walk(stream: object, resources: object, initial: tuple[float, ...], page_number: int,
             initial_width: float = 1.0,
             active: frozenset[int] = frozenset(), initial_dash: tuple = (), initial_phase: float = 0) -> None:
        nonlocal filled_only_paths, nonuniform_curves_sampled, unverified_dashes
        ctm = initial
        width = initial_width;dash=initial_dash;phase=initial_phase
        stack: list[tuple[tuple[float, ...], float]] = []
        tangents: list[tuple[float, float]] = []
        curves_in_path = 0
        point: tuple[float, float] | None = None
        start: tuple[float, float] | None = None
        local = resources.get_object()
        for args, op in ContentStream(stream, reader).operations:
            if op == b'q':
                stack.append((ctm, width,dash,phase))
            elif op == b'Q':
                if not stack:
                    raise ValueError('PDF graphics state stack underflow')
                ctm, width,dash,phase = stack.pop()
            elif op == b'cm':
                ctm = multiply(ctm, tuple(map(float, args)))
            elif op == b'd':
                dash,phase=dash_state(args)
            elif op == b'w':
                width = float(args[0])
            elif op == b'gs':
                state_ref = local.get('/ExtGState',{}).get(args[0])
                if state_ref is None:
                    raise ValueError('PDF graphics state missing from resources')
                state = state_ref.get_object()
                width = float(state.get('/LW',width))
                if '/D' in state:dash,phase=dash_state(state['/D'])
            elif op == b'm':
                point = start = (float(args[0]), float(args[1]))
            elif op == b'l':
                end = (float(args[0]), float(args[1]))
                if point is not None:
                    tangents.append((end[0]-point[0], end[1]-point[1]))
                point = end
            elif op in (b'c', b'v', b'y'):
                curves_in_path += 1
                end = (float(args[-2]), float(args[-1]))
                if point is not None:
                    if op == b'c':
                        p1 = (float(args[0]),float(args[1])); p2 = (float(args[2]),float(args[3]))
                    elif op == b'v':
                        p1 = point; p2 = (float(args[0]),float(args[1]))
                    else:
                        p1 = (float(args[0]),float(args[1])); p2 = end
                    for t in (0, .25, .5, .75, 1):
                        u = 1-t
                        tangents.append((u*u*(p1[0]-point[0])+2*u*t*(p2[0]-p1[0])+t*t*(end[0]-p2[0]),
                                         u*u*(p1[1]-point[1])+2*u*t*(p2[1]-p1[1])+t*t*(end[1]-p2[1])))
                point = end
            elif op == b're':
                x,y,w,h = map(float,args)
                tangents.extend(((w,0),(0,h),(-w,0),(0,-h)))
                point = start = (x,y)
            elif op in (b'h', b's', b'b', b'b*'):
                if point is not None and start is not None:
                    tangents.append((start[0]-point[0],start[1]-point[1]))
                point = start
            if op in STROKE_PAINT:
                a,b,c,d,_,_ = ctm
                if curves_in_path and (abs(a*a+b*b-c*c-d*d)>1e-9 or abs(a*c+b*d)>1e-9):
                    nonuniform_curves_sampled += curves_in_path
                if dash and tangents:
                    if abs(a*a+b*b-c*c-d*d)>1e-9 or abs(a*c+b*d)>1e-9:unverified_dashes+=1
                    else:
                        scale=math.hypot(a,b);dash_patterns.append({'page':page_number,'lengthsPt':[round(v*scale,6)for v in dash],'phasePt':round(phase*scale,6)})
                determinant = abs(a*d-b*c)
                for dx,dy in tangents:
                    source_length = math.hypot(dx,dy)
                    transformed_length = math.hypot(a*dx+c*dy,b*dx+d*dy)
                    if source_length == 0:
                        continue
                    effective = width*determinant*source_length/transformed_length if transformed_length else 0
                    widths.append(effective)
                    if not math.isfinite(effective) or abs(effective-target_pt)>STROKE_TOLERANCE_PT:
                        issues.append({'page':page_number,'widthPt':round(effective,6),'declaredWidthPt':width})
            if op in (b'f',b'f*') and tangents:
                filled_only_paths += 1
            if op in STROKE_PAINT or op in (b'f',b'f*',b'n'):
                tangents = []
                curves_in_path = 0
                point = start = None
            if op == b'Do':
                xobjects = local.get('/XObject', {})
                child_ref = xobjects.get(args[0])
                if child_ref is None:
                    raise ValueError('PDF XObject missing from resources')
                child = child_ref.get_object()
                if child.get('/Subtype') == '/Form':
                    identity = id(child)
                    if identity in active:
                        raise ValueError('Recursive PDF Form')
                    form_matrix = tuple(map(float, child.get('/Matrix',[1,0,0,1,0,0])))
                    walk(child, child.get('/Resources',local), multiply(ctm,form_matrix),page_number,
                         width,active|{identity},dash,phase)

    for number, page in enumerate(reader.pages, 1):
        unit = float(page.get('/UserUnit',1))
        walk(page.get_contents(),page['/Resources'],(unit,0,0,unit,0,0),number)
    return {'ok':not issues and nonuniform_curves_sampled == 0 and unverified_dashes == 0,
            'dashPatterns':dash_patterns,'unverifiedDashPaths':unverified_dashes,'targetPt':target_pt,'tolerancePt':STROKE_TOLERANCE_PT,
            'scope':'Painted path strokes only; filled outlines, filled markers, text glyphs and raster ink have no stroke-width verdict.',
            'nonUniformCurvePolicy':'Five tangent samples are reported but cannot prove every point; reject these curves pending a complete geometry check.',
            'strokeSegments':len(widths),'minWidthPt':min(widths) if widths else None,
            'maxWidthPt':max(widths) if widths else None,'filledOnlyPaths':filled_only_paths,
            'nonUniformCurvesSampled':nonuniform_curves_sampled,
            'issueCount':len(issues),'issues':issues[:20]}

def native_grid(rendered: Image.Image, expected_size: tuple[int, int]) -> Image.Image:
    """Keep 300-dpi pixels intact when page-edge rounding differs by at most three pixels."""
    if all(abs(actual - expected) <= 3 for actual, expected in zip(rendered.size, expected_size, strict=True)):
        aligned = Image.new('L', expected_size, 255)
        aligned.paste(rendered, (0, 0))
        return aligned
    return rendered.resize(expected_size)

def audit(pdf_path: str, native_path: str, preview_path: str, route: str = 'vector-reletter', expected_stroke_pt: float = STROKE_TARGET_PT) -> dict[str, int | float | bool | str]:
    reader = PdfReader(pdf_path)
    invisible = 0
    images = reader.pages[0].images
    for image in images:
        alpha = image.image.getchannel('A') if 'A' in image.image.getbands() else None
        if alpha is not None and alpha.getextrema()[1] == 0:
            invisible += 1
    pdf = pdfium.PdfDocument(pdf_path)
    page = pdf[0]
    rendered = page.render(scale=300 / 72).to_pil().convert('RGB')
    rendered.save(preview_path)
    with Image.open(native_path) as native:
        expected = native.convert('L')
    actual = native_grid(rendered.convert('L'), expected.size)
    expected_ink = expected.point(lambda value: 255 if value < 160 else 0)
    actual_ink = actual.point(lambda value: 255 if value < 160 else 0)
    covered = ImageChops.multiply(expected_ink, actual_ink.filter(ImageFilter.MaxFilter(5)))
    total = sum(expected_ink.histogram()[1:])
    matched = sum(covered.histogram()[1:])
    recall = matched / total if total else 1.0
    page.close()
    pdf.close()
    strokes=None if route=='image'else stroke_audit(reader,float(expected_stroke_pt))
    return {'ok': invisible == 0 and recall >= 0.94 and(strokes is None or strokes['ok']), 'invisibleImages': invisible,
            'nativeInkRecall': recall, 'pdfPreview': preview_path, 'imageCount': len(images),'strokeAudit':strokes}

if __name__ == '__main__':
    result = audit(*sys.argv[1:6])
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result['ok'] else 2)
