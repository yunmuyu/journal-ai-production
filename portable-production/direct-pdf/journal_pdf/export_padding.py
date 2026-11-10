"""Uniform visible-ink padding without scaling PDF content."""
from pathlib import Path
import math
import os
import tempfile
import pymupdf as fitz
from PIL import Image, ImageChops, ImageStat
from .common import FigureError
DEFAULT_PADDING_PT = 0.25
MEASURE_DPI = 1200
# One measurement pixel plus float32 page-box rounding, not the full default.
MARGIN_TOLERANCE_PT = 72 / MEASURE_DPI + 0.005

def ink_rect(page):
    pix = page.get_pixmap(dpi=MEASURE_DPI, colorspace=fitz.csRGB, alpha=False)
    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    bounds = ImageChops.difference(image, Image.new('RGB', image.size, 'white')).getbbox()
    if bounds is None:
        raise FigureError('empty_pdf', '裁边前没有可见墨迹')
    return fitz.Rect(*(value * 72 / MEASURE_DPI for value in bounds)) & page.rect

def _normalize_pdf_padding(source: Path, destination: Path, padding=DEFAULT_PADDING_PT, corrections=None):
    """Stage and check page boxes, retaining original content and clipping."""
    if isinstance(padding, bool) or not isinstance(padding, (int, float)) or not math.isfinite(padding) or not 0 <= padding <= 12:
        raise FigureError('export_crop_padding_invalid', '导出留白须为0到12pt的有限数值')
    if source.resolve() == destination.resolve():
        raise FigureError('output_isolation', '先验证裁边副本，不能原位写入')
    pages = []
    with fitz.open(source) as document:
        for page_index,page in enumerate(document):
            if page.rotation:
                raise FigureError('export_rotation_unsupported', '旋转页面须先显式归一化')
            media, crop = fitz.Rect(page.mediabox), fitz.Rect(page.cropbox)
            bounds = ink_rect(page)
            correction=(corrections or {}).get(page_index,[0.,0.,0.,0.])
            wanted = bounds + (-padding-correction[0], -padding-correction[1], padding+correction[2], padding+correction[3])
            wanted = wanted + (crop.x0, crop.y0, crop.x0, crop.y0)
            expanded = fitz.Rect(min(media.x0, wanted.x0), min(media.y0, media.y1-wanted.y1), max(media.x1, wanted.x1), max(media.y1, media.y1-wanted.y0))
            shift_y = expanded.y1-media.y1
            # Preserve the old visible viewport. Expanding MediaBox alone
            # would otherwise reveal objects hidden by an earlier CropBox.
            if not crop.contains(wanted):
                page.wrap_contents()
                contents = page.get_contents()
                prefix, suffix = document.get_new_xref(), document.get_new_xref()
                for xref in (prefix, suffix): document.update_object(xref, '<<>>')
                clip = f'q {crop.x0:.8f} {media.y1-crop.y1:.8f} {crop.width:.8f} {crop.height:.8f} re W n\n'
                document.update_stream(prefix, clip.encode('ascii'))
                document.update_stream(suffix, b'\nQ\n')
                document.xref_set_key(page.xref, 'Contents', '['+' '.join(f'{n} 0 R' for n in [prefix,*contents,suffix])+']')
            page.set_mediabox(expanded)
            shift_y = page.mediabox.y1-media.y1
            # Write in PDF coordinates: converting through a float32 Rect
            # can put an edge a fraction of a point outside MediaBox.
            box = page.mediabox
            physical = (max(box.x0, wanted.x0), max(box.y0, media.y1-wanted.y1),
                        min(box.x1, wanted.x1), min(box.y1, media.y1-wanted.y0))
            document.xref_set_key(page.xref, 'CropBox', '['+' '.join(format(n, '.17g') for n in physical)+']')
            page = document.reload_page(page)
            pages.append({'source_media':list(media),'source_crop':list(crop),'source_ink':list(bounds),'crop_box':list(page.cropbox),'media_box':list(page.mediabox),'origin_shift_y_pt':shift_y,'protection_pt':padding,'measurement_adjustment_pt':correction,'rescaled':False})
        document.save(destination, garbage=0, deflate=True)
    mismatches=[]
    with fitz.open(source) as before, fitz.open(destination) as after:
        for index, receipt in enumerate(pages):
            page = after[index]
            actual = ink_rect(page)
            margins = [actual.x0,actual.y0,page.rect.width-actual.x1,page.rect.height-actual.y1]
            receipt['measured_margins_pt'] = margins
            if any(abs(value-padding) > MARGIN_TOLERANCE_PT for value in margins):
                mismatches.append({'actual':margins,'page_index':index})
                continue
            after.xref_set_key(page.xref,'MediaBox',before.xref_get_key(before[index].xref,'MediaBox')[1])
            after.xref_set_key(page.xref,'CropBox',before.xref_get_key(before[index].xref,'CropBox')[1])
            page=after.reload_page(page)
            a = before[index].get_pixmap(dpi=MEASURE_DPI, colorspace=fitz.csRGB, alpha=False)
            b = page.get_pixmap(dpi=MEASURE_DPI, colorspace=fitz.csRGB, alpha=False)
            if (a.width,a.height)!=(b.width,b.height):
                raise FigureError('export_content_changed', '原页面尺寸发生改变')
            first=Image.frombytes('RGB',(a.width,a.height),a.samples)
            second=Image.frombytes('RGB',(b.width,b.height),b.samples)
            difference=ImageChops.difference(first,second)
            inner=(2,2,a.width-2,a.height-2)
            if difference.crop(inner).getbbox():
                raise FigureError('export_content_changed', '裁边改变了原页面内部的实际渲染')
            receipt['source_view_pixels_identical'] = a.samples==b.samples
            receipt['viewport_edge_antialias_only'] = a.samples!=b.samples
            receipt['source_view_mean_pixel_difference'] = sum(ImageStat.Stat(difference).mean) / 3
    if mismatches:
        raise FigureError('export_padding_mismatch','保存后四边留白不符合目标',expected=padding,mismatches=mismatches)
    return {'method':'saved-PDF-1200dpi-visible-ink','measurement_dpi':MEASURE_DPI,
            'tolerance_pt':MARGIN_TOLERANCE_PT,'target_padding_pt':padding,
            'pages':pages,'rescaled':False}


def normalize_pdf_padding(source: Path, destination: Path, padding=DEFAULT_PADDING_PT):
    """Publish the copy only after verification; leave existing outputs untouched on failure."""
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve():
        raise FigureError('output_isolation','先验证裁边副本，不能原位写入')
    with tempfile.TemporaryDirectory(prefix='.padding-',dir=destination.parent) as folder:
        staged=Path(folder)/'verified.pdf'
        corrections={}
        # Re-render from the unchanged source after bounded per-edge correction.
        # Image interpolation can grow ink after shifting the raster origin.
        # Never relax the target tolerance or scale artwork to make it pass.
        for attempt in range(4):
            try:
                receipt=_normalize_pdf_padding(source,staged,padding,corrections)
            except FigureError as error:
                if error.code!='export_padding_mismatch' or attempt==3:raise
                for mismatch in error.details['mismatches']:
                    index=mismatch['page_index'];actual=mismatch['actual']
                    correction=corrections.setdefault(index,[0.,0.,0.,0.])
                    for edge,value in enumerate(actual):
                        if abs(value-padding)>MARGIN_TOLERANCE_PT:
                            correction[edge]=max(-padding,correction[edge]+padding-value)
                    if any(abs(value)>4*72/MEASURE_DPI+.005 for value in correction):raise
                staged.unlink(missing_ok=True)
                continue
            receipt['normalization_attempts']=attempt+1
            os.replace(staged,destination)
            return receipt
