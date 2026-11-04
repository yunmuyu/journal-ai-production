"""Actual subprocess coverage for synthetic photo and multi-input raster plans."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from task_quality.storage import ref


def test_cli_photo_and_three_input_grid_preserve_order_and_source_hashes(tmp_path):
    # Three independently bound, photographic-like continuous-tone fixtures.
    sources = []
    for index, base in enumerate((20, 90, 160)):
        image = Image.new('RGB', (240, 160))
        image.putdata([(base + x // 8, base + y // 8, base + (x + y) // 16)
                       for y in range(160) for x in range(240)])
        source = tmp_path / f'photo-{index}.png'
        image.save(source)
        sources.append(dict(**ref(source), crop=None))
    original_hashes = [source['sha256'] for source in sources]
    root = Path(__file__).resolve().parents[1]
    for name, inputs, layout, dimensions in (
        ('photo', sources[:1], dict(mode='single', gap_px=0), [240, 160]),
        ('composite', sources, dict(mode='grid', gap_px=8, columns=2), [488, 328]),
    ):
        output = tmp_path / name / 'figure.jpg'
        plan = dict(version=1, inputs=inputs, layout=layout, output=str(output), width_mm=80)
        plan_path = tmp_path / f'{name}.json'
        plan_path.write_text(json.dumps(plan), encoding='utf-8')
        run = subprocess.run([sys.executable, '-m', 'raster', 'render', str(plan_path)],
                             cwd=root, capture_output=True, text=True, check=False)
        assert run.returncode == 0, run.stdout + run.stderr
        response = json.loads(run.stdout)
        assert response['status'] == 'candidate'
        report = json.loads(Path(response['report']['path']).read_text(encoding='utf-8'))
        assert report['output']['pixels'] == dimensions
        assert report['output']['width_mm'] == pytest.approx(80, abs=.05)
        assert not report['resampled']
        assert report['no_ocr_font_measurement']
        assert report['acceptance'] == 'candidate_only'
        assert [item['source']['sha256'] for item in report['inputs']] == original_hashes[:len(inputs)]
        assert ref(output)['sha256'] == report['output']['sha256']
        with Image.open(output) as actual:
            assert actual.format == 'JPEG'
            assert actual.mode == 'L'
            if name == 'composite':
                # Independent decode verifies left→right then next-row placement.
                assert actual.getpixel((40, 40)) < actual.getpixel((288, 40)) < actual.getpixel((40, 208))
                assert actual.getpixel((300, 220)) == 255  # Unused fourth cell.
                assert actual.getpixel((244, 80)) == 255  # Declared white gutter.
                assert [item['placement_before_resampling'] for item in report['inputs']] == [
                    [0, 0, 240, 160], [248, 0, 488, 160], [0, 168, 240, 328]]
        assert [ref(Path(item['path']))['sha256'] for item in sources] == original_hashes
