from pathlib import Path

from PIL import Image, ImageDraw
import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError, digest_file
from journal_pdf.original_asset_reference import audit_original_references


def test_chart_raster_region_is_compared_to_registered_original(tmp_path: Path):
    original = tmp_path / 'original.png'
    image = Image.new('RGB', (60, 40), 'white')
    ImageDraw.Draw(image).rectangle((10, 10, 40, 30), fill='black')
    image.save(original)
    bindings = [{'path': original.name, 'sha256': digest_file(original), 'role': 'original-artwork'}]
    spec = {'kind': 'chart', 'policy': {}, 'original_asset_references': {
        'plot': {'path': original.name, 'page': 0, 'clip': [0, 0, 60, 40]}}}
    assets = Assets()
    try:
        placement = [{'id': 'plot', 'asset': assets.raster(original, [0, 0, 60, 40])}]
        receipts = audit_original_references(spec, placement, assets, tmp_path, bindings)
        assert len(receipts) == 1 and receipts[0]['changed_fraction'] == 0
        changed = tmp_path / 'changed.png'
        Image.new('RGB', (60, 40), 'white').save(changed)
        placement[0]['asset'] = assets.raster(changed, [0, 0, 60, 40])
        with pytest.raises(FigureError, match='不一致'):
            audit_original_references(spec, placement, assets, tmp_path, bindings)
    finally:
        assets.close()


@pytest.mark.parametrize('change', ['missing', 'unknown', 'fractional', 'page', 'unbound'])
def test_chart_reference_cannot_skip_binding_or_use_invalid_coordinates(tmp_path: Path, change: str):
    source = tmp_path / 'original.png'
    Image.new('RGB', (40, 30), 'black').save(source)
    bindings = [{'path': source.name, 'sha256': digest_file(source), 'role': 'original-artwork'}]
    reference = {'path': source.name, 'page': 0, 'clip': [0, 0, 40, 30]}
    references = {'plot': reference}
    if change == 'missing': references.clear()
    if change == 'unknown': references['unknown'] = dict(reference)
    if change == 'fractional': reference['clip'] = [0, 0, 39.5, 30]
    if change == 'page': reference['page'] = 1
    if change == 'unbound': reference['path'] = 'other.png'
    assets = Assets()
    try:
        placement = [{'id': 'plot', 'asset': assets.raster(source, [0, 0, 40, 30])}]
        with pytest.raises(FigureError):
            audit_original_references({'kind':'chart', 'policy':{}, 'original_asset_references':references},
                                      placement, assets, tmp_path, bindings)
    finally:
        assets.close()
