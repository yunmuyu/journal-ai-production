"""Inspect saved PDF paint, not just object declarations or content streams."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Final

import pymupdf as fitz
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .original_asset_reference import PIXEL_DELTA, MAX_CHANGED_FRACTION

ZOOM: Final = 300 / 72
PIXEL_ROUNDING_EPSILON: Final = 0.01  # PDF decimal serialization near an integer pixel boundary.


def _image(page: fitz.Page, rect: fitz.Rect, *, alpha: bool = False) -> Image.Image:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=rect, colorspace=fitz.csGRAY, alpha=alpha)
    return Image.frombytes('LA' if alpha else 'L', (pixmap.width, pixmap.height), pixmap.samples)


def _asset_coverage(page: fitz.Page, rect: fitz.Rect, expected: Image.Image) -> Image.Image:
    """Protect visible ink and enclosed white details, not external paper padding."""
    alpha = _image(page, rect, alpha=True).getchannel('A')
    painted = ImageChops.multiply(alpha.point(lambda value: 255 if value else 0),
                                  expected.point(lambda value: 255 if value < 255 else 0))
    padded = Image.new('L', (alpha.width+2, alpha.height+2), 0)
    padded.paste(painted, (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128)
    return padded.crop((1, 1, alpha.width+1, alpha.height+1)).point(lambda value: 0 if value == 128 else 255)


def _boundary_contacts(scene, declarations):
    """Only declared exterior stroke contacts are composited, never interior overlaps."""
    from .common import FigureError
    if not isinstance(declarations, list):
        raise FigureError('final_visibility_contact', '图元接框声明须为列表')
    assets = {row['id']: row for row in scene.assets}
    nodes = {row['id']: row for row in scene.nodes}
    contacts = {}
    for item in declarations:
        if (not isinstance(item, dict) or set(item) != {'asset_id', 'node_id'}
                or not isinstance(item['asset_id'], str) or item['asset_id'] not in assets
                or not isinstance(item['node_id'], str) or item['node_id'] not in nodes):
            raise FigureError('final_visibility_contact', '接框声明必须引用真实图元和节点')
        a = fitz.Rect(assets[item['asset_id']]['rect']); node = nodes[item['node_id']]
        b = fitz.Rect(node['rect']); cx, cy = (a.x0+a.x1)/2, (a.y0+a.y1)/2
        reach = (node.get('width') or 0)/2 + .001
        vertical = (abs(a.x0-b.x1) <= reach or abs(a.x1-b.x0) <= reach) and b.y0 <= cy <= b.y1
        horizontal = (abs(a.y0-b.y1) <= reach or abs(a.y1-b.y0) <= reach) and b.x0 <= cx <= b.x1
        if node['kind'] == 'ellipse':
            vertical = vertical and abs(cy-(b.y0+b.y1)/2) < .001
            horizontal = horizontal and abs(cx-(b.x0+b.x1)/2) < .001
        if node['kind'] not in ('rectangle', 'ellipse') or (a & b).get_area() > 1e-6 or not (vertical or horizontal):
            raise FigureError('final_visibility_contact', '仅支持矩形外缘或椭圆轴端描边接触；不得掩盖内部遮挡')
        contacts.setdefault(item['asset_id'], {})[item['node_id']] = node
    return contacts


def _compare(expected: Image.Image, actual: Image.Image, *, full_region: bool, ident: str, halo_exclusions=None, coverage=None, stroke_context=None):
    from .common import FigureError
    if expected.size != actual.size:
        raise FigureError('final_visibility_geometry', '最终检查区域尺寸不一致', id=ident)
    difference = ImageChops.difference(expected, actual) if full_region else ImageChops.subtract(actual, expected)
    changed = difference.point(lambda value: 255 if value > PIXEL_DELTA else 0)
    if full_region:
        if coverage is None:
            count = expected.width * expected.height
        else:
            count = coverage.histogram()[255]
            changed = ImageChops.multiply(changed, coverage)
    else:
        ink = expected.point(lambda value: 255 if value < 245 else 0)
        count = ink.histogram()[255]
        changed = ImageChops.multiply(changed, ink)
        if halo_exclusions is not None:
            # A black panel can preserve dark pixels while swallowing a line
            # or glyph silhouette. Inspect a one-pixel halo around that ink.
            halo = ImageChops.subtract(ink.filter(ImageFilter.MaxFilter(3)), ink)
            draw = ImageDraw.Draw(halo)
            for x, y in halo_exclusions:
                radius = 2 * ZOOM
                draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=0)
            extra = ImageChops.multiply(halo, actual.point(lambda value: 255 if value < 32 else 0))
            if stroke_context is not None:
                extra = ImageChops.multiply(extra, stroke_context.point(lambda value: 255 if value >= 32 else 0))
            changed = ImageChops.lighter(changed, extra)
    if not count:
        raise FigureError('final_visibility_empty_reference', '保护对象没有可验证的可见墨迹', id=ident)
    fraction = changed.histogram()[255] / count
    if fraction > MAX_CHANGED_FRACTION:
        raise FigureError('final_visibility_changed', '最终PDF中受保护对象被遮挡或改变', id=ident,
                          changed_fraction=fraction, pixel_bbox=changed.getbbox(),
                          pixel_delta=PIXEL_DELTA, maximum_changed_fraction=MAX_CHANGED_FRACTION)
    return {'id': ident, 'changed_fraction': fraction, 'full_region': full_region,
            'protected_pixels': count, 'blank_exterior_excluded': coverage is not None}


def audit_final_visibility(pdf: Path, scene, registry, assets, original_receipts, structure, *, required: bool = False, asset_contacts=None):
    """Reopen final bytes, account for CropBox, and check original assets and locked structure."""
    from .common import FigureError
    from .fonts import draw_text
    from .render import draw_node, draw_path
    from .source_structure_contract import node_has_visible_ink
    if not isinstance(required, bool):
        raise FigureError('final_visibility_policy', '最终可见性开关必须为布尔值')
    contacts = _boundary_contacts(scene, [] if asset_contacts is None else asset_contacts)
    if contacts and not required:
        raise FigureError('final_visibility_contact', '声明图元接框必须启用完整最终可见性检查')
    asset_ids = {row['id'] for row in scene.assets} if required else {row['asset_id'] for row in original_receipts}
    structure_checked = structure['status'] == 'checked'
    if not required and not asset_ids and not structure_checked:
        return {'status': 'not-checked', 'checked_assets': [], 'checked_paths': [], 'checked_nodes': [], 'checked_texts': []}
    receipts = []
    checked = {'assets': [], 'paths': [], 'nodes': [], 'texts': []}
    with fitz.open(pdf) as actual_doc, fitz.open() as stroke_doc:
        actual_page = actual_doc[0]
        visible_crop = fitz.Rect(actual_page.cropbox)
        actual_page.set_cropbox(actual_page.mediabox)
        width, height = actual_page.rect.width, actual_page.rect.height
        stroke_page = stroke_doc.new_page(width=width, height=height)
        for path in scene.paths:
            if not path.get('closed') and path.get('fill') is None:
                draw_path(stroke_page, path)
        for node in scene.nodes:
            if node.get('width') and not node.get('invisible'):
                draw_node(stroke_page, {key: value for key, value in node.items() if key != 'fill'})
        objects = [('assets', row) for row in scene.assets if row['id'] in asset_ids]
        if structure_checked or required:
            objects += [('paths', row) for row in scene.paths]
            # Reuse the already verified visible-ink inventory, including white backgrounds.
            visible_node_ids = set(structure['visible_node_ids']) if structure_checked else {
                row['id'] for row in scene.nodes if node_has_visible_ink(row)}
            objects += [('nodes', row) for row in scene.nodes if row['id'] in visible_node_ids]
        objects += [('texts', row) for row in scene.texts]
        for kind, row in objects:
            with fitz.open() as reference_doc:
                reference = reference_doc.new_page(width=width, height=height)
                match kind:
                    case 'assets':
                        assets.place(reference, row['asset'], row['rect'])
                        for node in contacts.get(row['id'], {}).values():
                            draw_node(reference, node)
                        bounds = fitz.Rect(row['rect'])
                    case 'paths':
                        draw_path(reference, row)
                        points = row['points']
                        bounds = fitz.Rect(min(p[0] for p in points)-4, min(p[1] for p in points)-4,
                                           max(p[0] for p in points)+4, max(p[1] for p in points)+4)
                    case 'nodes':
                        draw_node(reference, row)
                        bounds = fitz.Rect(row['rect']) + (-1, -1, 1, 1)
                    case 'texts':
                        if row.get('gray', 0) != 0:
                            raise FigureError('final_visibility_scope', '白字的最终对比度需独立背景证明，不能冒报通过', id=row['id'])
                        draw_text(reference, registry, row)
                        bounds = fitz.Rect(row['position']['bbox']) + (-1, -1, 1, 1)
                bounds &= actual_page.rect
                if bounds.is_empty:
                    raise FigureError('final_visibility_geometry', '保护对象完全在页面之外', id=row['id'])
                expected = _image(reference, bounds)
                actual = _image(actual_page, bounds)
                # Restoring CropBox coordinates must not restore paint hidden by the exported crop.
                origin_x, origin_y = math.floor(bounds.x0*ZOOM), math.floor(bounds.y0*ZOOM)
                visible = Image.new('L', actual.size, 0)
                ImageDraw.Draw(visible).rectangle((math.ceil(visible_crop.x0*ZOOM-PIXEL_ROUNDING_EPSILON)-origin_x,
                    math.ceil(visible_crop.y0*ZOOM-PIXEL_ROUNDING_EPSILON)-origin_y,
                    math.floor(visible_crop.x1*ZOOM+PIXEL_ROUNDING_EPSILON)-origin_x-1,
                    math.floor(visible_crop.y1*ZOOM+PIXEL_ROUNDING_EPSILON)-origin_y-1), fill=255)
                actual = Image.composite(actual, Image.new('L', actual.size, 255), visible)
                coverage = _asset_coverage(reference, bounds, expected) if kind == 'assets' else None
                halo_exclusions = [(p[0]*ZOOM-origin_x, p[1]*ZOOM-origin_y)
                             for p in (row['points'][0], row['points'][-1])] if kind == 'paths' else [] if kind == 'texts' else None
                context = _image(stroke_page, bounds) if kind == 'paths' else None
                receipts.append(_compare(expected, actual, full_region=kind == 'assets', ident=row['id'],
                    halo_exclusions=halo_exclusions, coverage=coverage, stroke_context=context))
                checked[kind].append(row['id'])
    return {'status': 'checked', **{'checked_'+key: value for key, value in checked.items()},
            'activation': 'explicit-full-scene' if required else 'source-bound-objects',
            'source_topology_checked': structure_checked,
            'asset_boundary_contacts': {key: sorted(value) for key, value in contacts.items()},
            'measurements': receipts, 'dpi': 300,
            'scope': 'selected assets visible ink and enclosed white details, excluding external blank padding; selected node/path and native black text ink loss; text/path black-overpaint halo excluding 2pt path endpoint junctions; visually identical overpaint is indistinguishable'}
