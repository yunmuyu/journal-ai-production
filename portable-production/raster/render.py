"""Deterministic grayscale JPEG production, with explicit crops and composition."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageOps, TiffImagePlugin

from task_quality.storage import ref


class RasterError(ValueError):
    """A source, plan or output failed a declared production constraint."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RasterError(code)


def positive(value, code: str) -> float:
    require(type(value) in (int, float) and math.isfinite(value) and value > 0, code)
    return float(value)


def load_input(item: dict, grayscale_weights=None) -> tuple[Image.Image, dict]:
    require(type(item) is dict and set(item) == {'path', 'sha256', 'crop'}, 'invalid_schema: input')
    source = Path(item['path']).resolve()
    require(ref(source)['sha256'] == item['sha256'], 'source_hash')
    with Image.open(source) as original:
        require(original.format in ('PNG', 'JPEG', 'TIFF', 'BMP', 'WEBP', 'GIF'), 'source_format')
        require(getattr(original, 'n_frames', 1) == 1, 'multiple_frames_require_explicit_selection')
        source_size = list(original.size)
        orientation = original.getexif().get(274, 1)
        corrected = ImageOps.exif_transpose(original)
        oriented_size = list(corrected.size)
        crop = item['crop']
        if crop is not None:
            require(type(crop) is list and len(crop) == 4 and all(type(v) is int for v in crop), 'crop_bounds')
            x0, y0, x1, y1 = crop
            require(0 <= x0 < x1 <= corrected.width and 0 <= y0 < y1 <= corrected.height, 'crop_bounds')
            corrected = corrected.crop(tuple(crop))
        rgba = corrected.convert('RGBA')
        white = Image.new('RGBA', rgba.size, 'white')
        white.alpha_composite(rgba)
        rgb = white.convert('RGB')
        gray = rgb.convert('L') if grayscale_weights is None else rgb.convert('L', tuple(grayscale_weights) + (0,))
    require(ref(source)['sha256'] == item['sha256'], 'source_changed_during_read')
    return gray, dict(source=dict(item), native_pixels=source_size, oriented_pixels=oriented_size,
        exif_orientation=orientation, crop=crop, cropped_pixels=list(gray.size))


def compose(images: list[Image.Image], layout: dict) -> tuple[Image.Image, list[list[int]]]:
    require(type(layout) is dict, 'invalid_schema: layout')
    mode = layout.get('mode')
    require(mode in ('single', 'row', 'column', 'grid'), 'invalid_layout')
    require(set(layout) == ({'mode', 'gap_px', 'columns'} if mode == 'grid' else {'mode', 'gap_px'}), 'invalid_schema: layout')
    gap = layout['gap_px']
    require(type(gap) is int and 0 <= gap <= 10000, 'invalid_gap')
    if mode == 'single':
        require(len(images) == 1 and gap == 0, 'single_requires_one_input_and_zero_gap')
        return images[0], [[0, 0, images[0].width, images[0].height]]
    columns = len(images) if mode == 'row' else 1 if mode == 'column' else layout['columns']
    require(type(columns) is int and 1 <= columns <= len(images), 'invalid_columns')
    rows = math.ceil(len(images) / columns)
    cell_w, cell_h = max(i.width for i in images), max(i.height for i in images)
    size = (columns * cell_w + (columns - 1) * gap, rows * cell_h + (rows - 1) * gap)
    require(size[0] * size[1] <= Image.MAX_IMAGE_PIXELS, 'composition_too_large')
    result = Image.new('L', size, 255)
    placements = []
    for index, image in enumerate(images):
        x = (index % columns) * (cell_w + gap) + (cell_w - image.width) // 2
        y = (index // columns) * (cell_h + gap) + (cell_h - image.height) // 2
        result.paste(image, (x, y))
        placements.append([x, y, x + image.width, y + image.height])
    return result, placements


def render(plan: dict) -> dict:
    """Write a new JPEG/PNG pair; source files and existing outputs are never overwritten."""
    required = {'version', 'inputs', 'layout', 'output', 'width_mm'}
    require(type(plan) is dict and required <= set(plan) <= required | {'target_dpi', 'quality', 'grayscale_weights'}, 'invalid_schema: plan')
    require(type(plan['version']) is int and plan['version'] == 1, 'unsupported_version')
    require(type(plan['inputs']) is list and 1 <= len(plan['inputs']) <= 100, 'invalid_inputs')
    width = positive(plan['width_mm'], 'invalid_width')
    quality = plan.get('quality', 95)
    require(type(quality) is int and 90 <= quality <= 100, 'invalid_quality')
    weights = plan.get('grayscale_weights')
    if 'grayscale_weights' in plan:
        require(type(weights) is list and len(weights) == 3 and
            all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in weights) and
            math.isclose(sum(weights), 1, rel_tol=0, abs_tol=1e-9), 'invalid_grayscale_weights')
    target_dpi = plan.get('target_dpi')
    if target_dpi is not None:
        target_dpi = positive(target_dpi, 'invalid_dpi')
        require(target_dpi >= 300, 'target_dpi_below_300')
    output = Path(plan['output']).resolve()
    require(output.suffix.lower() in ('.jpg', '.jpeg'), 'output_format')
    preview = output.with_suffix('.png')
    report_path = output.with_suffix('.raster.json')
    source_paths = {Path(item['path']).resolve() for item in plan['inputs']}
    require(not source_paths.intersection({output, preview, report_path}), 'source_overwrite')
    require(not any(p.exists() for p in (output, preview, report_path)), 'output_exists_use_new_attempt')
    loaded = [load_input(item, weights) for item in plan['inputs']]
    images, evidence = [row[0] for row in loaded], [row[1] for row in loaded]
    canvas, placements = compose(images, plan['layout'])
    native_pixels = list(canvas.size)
    effective_source_dpi = canvas.width * 25.4 / width
    for row, placement in zip(evidence, placements):
        row['placement_before_resampling'] = placement
    resampled = target_dpi is not None
    if resampled:
        px = round(width / 25.4 * target_dpi)
        require(px > 0, 'invalid_target_pixels')
        canvas = canvas.resize((px, max(1, round(canvas.height * px / canvas.width))), Image.Resampling.LANCZOS)
    encoded_dpi = canvas.width * 25.4 / width
    exif = Image.Exif()
    exif[282] = TiffImagePlugin.IFDRational(encoded_dpi)
    exif[283] = TiffImagePlugin.IFDRational(encoded_dpi)
    exif[296] = 2
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        canvas.save(stream, format='JPEG', quality=quality, optimize=True, exif=exif)
    with Image.open(output) as actual:
        actual.load()
        require(actual.format == 'JPEG' and actual.mode == 'L', 'output_decode_mismatch')
        measured_dpi = [float(v) for v in actual.info['dpi']]
        actual_width = actual.width / measured_dpi[0] * 25.4
        require(abs(actual_width - width) <= .05, 'output_width_mismatch')
        actual.save(preview, format='PNG')
        output_ref = dict(**ref(output), format='jpg', pixels=list(actual.size), dpi=measured_dpi,
            width_mm=actual_width, nonneutral_pixels=0)
    for item in plan['inputs']:
        require(ref(Path(item['path']))['sha256'] == item['sha256'], 'source_changed_during_render')
    result = dict(version=1, tool='public-raster', inputs=evidence, layout=plan['layout'], grayscale_weights=weights,
        native_composite_pixels=native_pixels, resampled=resampled, requested_target_dpi=target_dpi,
        effective_source_dpi=effective_source_dpi, output=output_ref, preview=ref(preview),
        warnings=['effective_source_resolution_below_300ppi'] if effective_source_dpi < 300 else [],
        review_required=['source_content', 'readability', 'grayscale_semantics'],
        acceptance='candidate_only', no_ocr_font_measurement=True)
    import json
    with report_path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return result
