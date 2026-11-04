from PIL import Image, ImageChops
from journal_pdf.assets import Assets
from journal_pdf.render import render_one


def test_export_padding_survives_original_scene_boundary(tmp_path, reg):
    # Given visible glyphs close to the original scene edge and requested safe padding.
    source = tmp_path / 'source'
    source.mkdir()
    width = reg.measure('测试', 8)['width']
    spec = {'version': 1, 'id': 'edge', 'author': 'fixture', 'synthetic': True,
            'kind': 'scene', 'width_pt': 100, 'height_pt': 50,
            'texts': [{'id': 'edge', 'text': '测试', 'x': width/2+.3, 'y': 10}],
            'policy': {'column': 'single', 'export_crop_padding_pt': 4}}
    assets = Assets()
    try:
        result = render_one(spec, reg, assets, source, tmp_path/'output')
        with Image.open(tmp_path/'output'/result['preview']) as image:
            rgb = image.convert('RGB')
            box = ImageChops.difference(rgb, Image.new('RGB', rgb.size, 'white')).getbbox()
            # Then actual rendered ink, not just the requested policy, has four safe margins.
            margins = [box[0], box[1], rgb.width-box[2], rgb.height-box[3]]
            assert min(margins)*72/300 >= 2
    finally:
        assets.close()
