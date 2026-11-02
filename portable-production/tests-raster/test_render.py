import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from task_quality.storage import ref
from raster import render, RasterError


def plan(tmp_path, image=None):
    source = tmp_path / 'source.png'
    (image or Image.new('RGB', (1200, 600), (200, 20, 40))).save(source)
    return dict(version=1, inputs=[dict(**ref(source), crop=None)],
        layout=dict(mode='single', gap_px=0), output=str(tmp_path / 'candidate.jpg'),
        width_mm=80, target_dpi=None, quality=95)


def test_single_image_preserves_pixels_and_exact_width_without_adobe(tmp_path):
    spec = plan(tmp_path)
    result = render(spec)
    assert result['output']['pixels'] == [1200, 600]
    assert result['output']['width_mm'] == pytest.approx(80, abs=.001)
    assert not result['resampled']
    assert result['output']['nonneutral_pixels'] == 0
    assert result['inputs'][0]['source'] == spec['inputs'][0]
    with Image.open(spec['output']) as actual:
        assert actual.format == 'JPEG'
        assert actual.info['dpi'][0] == pytest.approx(381)


def test_transparency_flattens_to_white_before_grayscale(tmp_path):
    result = render(plan(tmp_path, Image.new('RGBA', (100, 100), (255, 0, 0, 0))))
    with Image.open(result['preview']['path']) as preview:
        assert preview.convert('RGB').getpixel((1, 1)) == (255, 255, 255)
    assert result['warnings'] == ['effective_source_resolution_below_300ppi']


def test_crop_is_explicit_and_reported(tmp_path):
    spec = plan(tmp_path)
    spec['inputs'][0]['crop'] = [10, 20, 1110, 520]
    result = render(spec)
    assert result['output']['pixels'] == [1100, 500]
    assert result['inputs'][0]['crop'] == [10, 20, 1110, 520]


@pytest.mark.parametrize('crop', [[-1, 0, 5, 5], [0, 0, 1201, 600], [5, 5, 4, 4]])
def test_invalid_crop_fails_before_output(tmp_path, crop):
    spec = plan(tmp_path)
    spec['inputs'][0]['crop'] = crop
    with pytest.raises(RasterError, match='crop_bounds'):
        render(spec)
    assert not Path(spec['output']).exists()


def test_exif_orientation_applied_before_crop(tmp_path):
    spec = plan(tmp_path)
    source = tmp_path / 'oriented.jpg'
    image = Image.new('RGB', (40, 20), 'white')
    exif = Image.Exif()
    exif[274] = 6
    image.save(source, exif=exif)
    spec['inputs'] = [dict(**ref(source), crop=None)]
    result = render(spec)
    assert result['output']['pixels'] == [20, 40]
    assert result['inputs'][0]['exif_orientation'] == 6


@pytest.mark.parametrize('mode,columns,expected', [('row', None, [42, 10]), ('column', None, [20, 22]), ('grid', 2, [42, 10])])
def test_combination_preserves_input_order(tmp_path, mode, columns, expected):
    spec = plan(tmp_path, Image.new('RGB', (20, 10), 'black'))
    second = tmp_path / 'second.png'
    Image.new('RGB', (20, 10), 'white').save(second)
    spec['inputs'].append(dict(**ref(second), crop=None))
    spec['layout'] = dict(mode=mode, gap_px=2)
    if columns is not None:
        spec['layout']['columns'] = columns
    result = render(spec)
    assert result['output']['pixels'] == expected
    assert [row['source']['path'] for row in result['inputs']] == [row['path'] for row in spec['inputs']]
    with Image.open(result['preview']['path']) as image:
        assert image.getpixel((0, 0)) == 0
        assert image.getpixel((0, 12) if mode == 'column' else (22, 0)) == 255


def test_explicit_resampling_records_original_effective_resolution(tmp_path):
    spec = plan(tmp_path, Image.new('RGB', (100, 50), 'white'))
    spec['target_dpi'] = 300
    result = render(spec)
    assert result['resampled']
    assert result['output']['pixels'][0] == 945
    assert result['effective_source_dpi'] == pytest.approx(31.75)
    assert 'effective_source_resolution_below_300ppi' in result['warnings']


@pytest.mark.parametrize('mutation,error', [('hash', 'source_hash'), ('pdf', 'output_format'), ('source', 'source_overwrite'), ('font', 'invalid_schema')])
def test_conflicting_or_unsafe_plan_is_rejected(tmp_path, mutation, error):
    spec = plan(tmp_path)
    if mutation == 'hash':
        spec['inputs'][0]['sha256'] = '0' * 64
    elif mutation == 'pdf':
        spec['output'] = str(tmp_path / 'candidate.pdf')
    elif mutation == 'source':
        source = tmp_path / 'original.jpg'
        Image.new('RGB', (100, 50), 'white').save(source)
        spec['inputs'] = [dict(**ref(source), crop=None)]
        spec['output'] = str(source)
    else:
        spec['font_size'] = 6
    with pytest.raises(RasterError, match=error):
        render(spec)


def test_cli_renders_real_jpg_and_report(tmp_path):
    spec = plan(tmp_path)
    filename = tmp_path / 'plan.json'
    filename.write_text(json.dumps(spec), encoding='utf-8')
    run = subprocess.run([sys.executable, '-m', 'raster', 'render', str(filename)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)
    assert result['ok']
    assert Path(result['report']['path']).is_file()
    assert Path(spec['output']).is_file()


def test_existing_candidate_is_not_overwritten(tmp_path):
    spec = plan(tmp_path)
    render(spec)
    previous = ref(Path(spec['output']))
    with pytest.raises(RasterError, match='output_exists_use_new_attempt'):
        render(spec)
    assert ref(Path(spec['output'])) == previous


def test_multiframe_input_cannot_silently_drop_frames(tmp_path):
    spec = plan(tmp_path)
    source = tmp_path / 'multi.tiff'
    image = Image.new('RGB', (100, 50), 'white')
    image.save(source, save_all=True, append_images=[Image.new('RGB', (100, 50), 'black')])
    spec['inputs'] = [dict(**ref(source), crop=None)]
    with pytest.raises(RasterError, match='multiple_frames'):
        render(spec)
