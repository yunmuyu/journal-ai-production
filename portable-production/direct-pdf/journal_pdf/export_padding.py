"""Uniform visible-ink padding without scaling PDF content."""
from pathlib import Path
import math
import pymupdf as fitz
from PIL import Image, ImageChops, ImageStat
from .common import FigureError
DEFAULT_PADDING_PT = 2.0
MEASURE_DPI = 600

def ink_rect(page):
    pix = page.get_pixmap(dpi=MEASURE_DPI, colorspace=fitz.csRGB, alpha=False)
    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    bounds = ImageChops.difference(image, Image.new('RGB', image.size, 'white')).getbbox()
    if bounds is None:
        raise FigureError('empty_pdf', '裁边前没有可见墨迹')
    return fitz.Rect(*(value * 72 / MEASURE_DPI for value in bounds)) & page.rect

def normalize_pdf_padding(source: Path, destination: Path, padding=DEFAULT_PADDING_PT):
    """Stage and check page boxes, retaining original content and clipping."""
    if isinstance(padding, bool) or not isinstance(padding, (int, float)) or not math.isfinite(padding) or not 0 <= padding <= 12:
        raise FigureError('export_crop_padding_invalid', '导出留白须为0到12pt的有限数值')
    if source.resolve() == destination.resolve():
        raise FigureError('output_isolation', '先验证裁边副本，不能原位写入')
    pages = []
    with fitz.open(source) as document:
        for page in document:
            if page.rotation:
                raise FigureError('export_rotation_unsupported', '旋转页面须先显式归一化')
            media, crop = fitz.Rect(page.mediabox), fitz.Rect(page.cropbox)
            bounds = ink_rect(page)
            wanted = bounds + (-padding, -padding, padding, padding)
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
            pages.append({'source_media':list(media),'source_crop':list(crop),'source_ink':list(bounds),'crop_box':list(page.cropbox),'media_box':list(page.mediabox),'origin_shift_y_pt':shift_y,'protection_pt':padding,'rescaled':False})
        document.save(destination, garbage=0, deflate=True)
    with fitz.open(source) as before, fitz.open(destination) as after:
        for index, receipt in enumerate(pages):
            page = after[index]
            actual = ink_rect(page)
            margins = [actual.x0,actual.y0,page.rect.width-actual.x1,page.rect.height-actual.y1]
            receipt['measured_margins_pt'] = margins
            if any(abs(value-padding) > .25 for value in margins):
                raise FigureError('export_padding_mismatch', '保存后四边留白不符合目标', actual=margins, expected=padding)
            after.xref_set_key(page.xref,'MediaBox',before.xref_get_key(before[index].xref,'MediaBox')[1])
            after.xref_set_key(page.xref,'CropBox',before.xref_get_key(before[index].xref,'CropBox')[1])
            page=after.reload_page(page)
            a = before[index].get_pixmap(dpi=300, colorspace=fitz.csRGB, alpha=False)
            b = page.get_pixmap(dpi=300, colorspace=fitz.csRGB, alpha=False)
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
    return {'method':'saved-PDF-600dpi-visible-ink','pages':pages,'rescaled':False}
