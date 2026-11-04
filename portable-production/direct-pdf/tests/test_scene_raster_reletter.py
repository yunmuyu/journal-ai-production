import pytest
from PIL import Image, ImageDraw
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import compile_figure


def fixture(tmp_path):
    source = tmp_path / 'source.png'
    image = Image.new('RGB', (600, 400), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 40, 140, 80), fill='black')
    draw.line((30, 220, 560, 220), fill='black', width=3)
    image.save(source)
    replacement = {'source_text': 'R1', 'source_bbox': [60, 40, 141, 81], 'target_text_id': 'label'}
    return {'id': 'raster', 'kind': 'scene', 'width_pt': 210, 'height_pt': 150,
            'texts': [{'id': 'label', 'text': 'R1', 'x': 40, 'y': 30}],
            'assets': [{'id': 'body', 'path': str(source), 'source_kind': 'raster',
                        'clip': [0, 0, 600, 400], 'target': [5, 5, 205, 138],
                        'masks': [[60, 40, 141, 81]], 'approved_empty_regions': [[50, 30, 150, 90]],
                        'text_replacements': [replacement]}]}


def test_scene_raster_executes_registered_masks_and_editable_replacement(tmp_path, reg):
    spec = fixture(tmp_path)
    assets = Assets()
    try:
        scene = compile_figure(spec, reg, assets, tmp_path)
        body = scene.assets[0]['asset']
        assert body.audit['masks'] == [[60, 40, 141, 81]]
        assert body.audit['text_replacements'][0]['target_text_id'] == 'label'
        assert body.audit['protected_pixels_unchanged_before_color_conversion'] is True
    finally:
        assets.close()


@pytest.mark.parametrize('mutation', ['missing-target', 'missing-mask', 'unregistered-mask', 'unsafe-mask'])
def test_scene_raster_rejects_incomplete_relettering(tmp_path, reg, mutation):
    spec = fixture(tmp_path)
    item = spec['assets'][0]
    if mutation == 'missing-target':
        spec['texts'] = []
    elif mutation == 'missing-mask':
        item['masks'] = []
    elif mutation == 'unregistered-mask':
        item['text_replacements'] = []
    else:
        item['approved_empty_regions'] = []
    assets = Assets()
    try:
        with pytest.raises(FigureError):
            compile_figure(spec, reg, assets, tmp_path)
    finally:
        assets.close()
