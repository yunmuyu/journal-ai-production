"""Compare prepared assets with an independently bound original PDF region.

This checks appearance inside the declared source region, not whether that
region was semantically selected correctly or whether final overlays hide it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Final

import pymupdf as fitz
from PIL import Image, ImageChops

from .assets import Asset, Assets
from .common import FigureError, digest_file, finite, resolve_source

PIXEL_DELTA: Final = 8
MAX_CHANGED_FRACTION: Final = 0.001
SAMPLE_LONG_SIDE: Final = 600


@dataclass(frozen=True, slots=True)
class ReferenceReceipt:
    asset_id: str
    source_path: str
    source_sha256: str
    source_page: int
    source_clip: tuple[float, float, float, float]
    prepared_sha256: str
    changed_fraction: float
    pixel_delta: int = PIXEL_DELTA
    maximum_changed_fraction: float = MAX_CHANGED_FRACTION
    scope: str = 'declared-original-region-before-final-composition'


def _pixels(assets: Assets, asset: Asset, width: float, height: float) -> Image.Image:
    """Use the same placement backend on a normalized white reference canvas."""
    with fitz.open() as document:
        page = document.new_page(width=width, height=height)
        assets.place(page, asset, [0, 0, width, height])
        pixmap = page.get_pixmap(colorspace=fitz.csGRAY, alpha=False)
        return Image.frombytes('L', (pixmap.width, pixmap.height), pixmap.samples)


def compare_original(assets: Assets, asset: Asset, source: Path, page: int,
                     clip: tuple[float, float, float, float], asset_id: str) -> ReferenceReceipt:
    """Reject missing white components, added paint, and altered crop geometry."""
    if source.suffix.lower() == '.pdf':
        original = assets.pdf(source, page, list(clip))
    elif source.suffix.lower() in ('.png', '.jpg', '.jpeg'):
        if page != 0 or any(int(value) != value for value in clip):
            raise FigureError('original_asset_reference_input', '位图原件仅支持第0页和整数像素裁区')
        original = assets.raster(source, [int(value) for value in clip])
    else:
        raise FigureError('original_asset_reference_scope', '原始区域比较仅支持PDF或PNG/JPG位图')
    box = fitz.Rect(clip)
    prepared_box = fitz.Rect(asset.rect)
    if abs(box.width / box.height - prepared_box.width / prepared_box.height) > 1e-4:
        raise FigureError('original_asset_pixels_changed', '准备素材改变了原始区域的宽高比', asset=asset_id)
    scale = SAMPLE_LONG_SIDE / max(box.width, box.height)
    width, height = box.width * scale, box.height * scale
    if min(width, height) < 1:
        raise FigureError('original_asset_reference_input', '原始区域过窄，无法可靠比较', asset=asset_id)
    expected = _pixels(assets, original, width, height)
    actual = _pixels(assets, asset, width, height)
    histogram = ImageChops.difference(expected, actual).histogram()
    fraction = sum(histogram[PIXEL_DELTA + 1:]) / (expected.width * expected.height)
    if fraction > MAX_CHANGED_FRACTION:
        raise FigureError('original_asset_pixels_changed', '准备素材与登记原图区域不一致',
                          asset=asset_id, changed_fraction=fraction,
                          maximum_changed_fraction=MAX_CHANGED_FRACTION, pixel_delta=PIXEL_DELTA)
    return ReferenceReceipt(asset_id, str(source), digest_file(source), page, clip,
                            hashlib.sha256(asset.data).hexdigest(), fraction)


def audit_original_references(spec, scene_assets, assets: Assets, root: Path, bindings):
    """Public render gate; receipts are per placement, never cached as source truth."""
    required = spec.get('policy', {}).get('require_original_asset_reference', False)
    if not isinstance(required, bool):
        raise FigureError('original_asset_reference_input', '原图引用门禁开关必须为布尔值')
    # A declared original activates the gate even if a caller tries to disable
    # the policy. Legacy jobs without original-artwork remain explicitly legacy.
    required = required or any(b['role'] == 'original-artwork' for b in bindings)
    declarations = spec.get('assets', [])
    chart_references = spec.get('original_asset_references', {})
    if not isinstance(chart_references, dict):
        raise FigureError('original_asset_reference_input', '图表原图引用须按素材ID登记')
    has_reference = any('original_reference' in item for item in declarations) or bool(chart_references)
    if not required and not has_reference:
        return []
    if not scene_assets and not has_reference:
        return []  # Pure rebuilt graphs have no prepared assets to compare.
    if spec.get('kind') not in ('scene', 'chart'):
        raise FigureError('original_asset_reference_scope', '原图区域门禁当前仅支持scene或chart素材')
    if spec.get('kind') == 'chart' and set(chart_references) != {row['id'] for row in scene_assets}:
        raise FigureError('original_asset_reference_missing', '图表每个素材均须绑定独立原图区域')
    originals = {b['path']: b['sha256'] for b in bindings if b['role'] == 'original-artwork'}
    by_id = {item['id']: item for item in declarations}
    receipts = []
    for row in scene_assets:
        reference = chart_references.get(row['id']) if spec.get('kind') == 'chart' else by_id.get(row['id'], {}).get('original_reference')
        if reference is None:
            if required:
                raise FigureError('original_asset_reference_missing', '素材缺少独立原图区域引用', asset=row['id'])
            continue
        if not isinstance(reference, dict) or set(reference) != {'path', 'page', 'clip'}:
            raise FigureError('original_asset_reference_input', '原图引用须包含path/page/clip，不接受忽略区域或自定阈值')
        path, page, clip = reference['path'], reference['page'], reference['clip']
        if not isinstance(path, str) or path not in originals:
            raise FigureError('original_asset_reference_unbound', '引用必须绑定original-artwork原件，不能只绑定中间文件')
        if (isinstance(page, bool) or not isinstance(page, int) or page < 0
                or not isinstance(clip, list) or len(clip) != 4 or not finite(clip)
                or clip[2] <= clip[0] or clip[3] <= clip[1]):
            raise FigureError('original_asset_reference_input', '原图页号和裁区无效')
        source = resolve_source(root, path)
        if digest_file(source) != originals[path]:
            raise FigureError('source_hash_mismatch', '原图在准备期间发生变化')
        receipt = compare_original(assets, row['asset'], source, page, tuple(clip), row['id'])
        receipts.append(asdict(receipt))
    return receipts
