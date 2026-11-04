import sys
from pathlib import Path

import pytest
from PIL import Image, TiffImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from raster import render, RasterError
from task_quality.storage import ref


def spec(tmp_path):
    source = tmp_path / 'rgb.png'
    image = Image.new('RGB', (300, 100))
    image.paste((255, 0, 0), (0, 0, 100, 100))
    image.paste((0, 130, 0), (100, 0, 200, 100))
    image.paste((0, 0, 255), (200, 0, 300, 100))
    image.save(source)
    return dict(version=1, inputs=[dict(**ref(source), crop=None)],
        layout=dict(mode='single', gap_px=0), output=str(tmp_path / 'new.jpg'), width_mm=80)


def test_channel_mix_changes_only_gray_mapping_and_records_weights(tmp_path):
    plan = spec(tmp_path)
    plan['grayscale_weights'] = [1, 0, 0]
    report = render(plan)
    assert report['grayscale_weights'] == [1, 0, 0]
    assert report['output']['pixels'] == [300, 100]
    assert ref(Path(plan['inputs'][0]['path']))['sha256'] == plan['inputs'][0]['sha256']
    with Image.open(report['preview']['path']) as actual:
        assert actual.getpixel((50, 50)) == 255
        assert actual.getpixel((150, 50)) == 0
        assert actual.getpixel((250, 50)) == 0
    assert 'grayscale_semantics' in report['review_required']


def test_default_jpeg_bytes_match_prior_standard_grayscale_encoder(tmp_path):
    plan = spec(tmp_path)
    legacy = tmp_path / 'legacy.jpg'
    with Image.open(plan['inputs'][0]['path']) as original:
        gray = original.convert('RGBA').convert('RGB').convert('L')
        exif = Image.Exif()
        exif[282] = exif[283] = TiffImagePlugin.IFDRational(300 * 25.4 / 80)
        exif[296] = 2
        gray.save(legacy, format='JPEG', quality=95, optimize=True, exif=exif)
    report = render(plan)
    assert report['output']['sha256'] == ref(legacy)['sha256']
    assert report['grayscale_weights'] is None


@pytest.mark.parametrize('weights', [[-1, 1, 1], [1, 1, 1], [0, 0, 0],
    [float('nan'), 0, 1], [float('inf'), 0, 0], [True, 0, 0], [1, 0], 'red', None])
def test_invalid_mix_rejected_before_any_candidate(tmp_path, weights):
    plan = spec(tmp_path)
    plan['grayscale_weights'] = weights
    with pytest.raises(RasterError, match='invalid_grayscale_weights'):
        render(plan)
    assert not Path(plan['output']).exists()
