import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, TiffImagePlugin

from case_helpers import candidate, make_case
from task_quality.gate import precheck
from task_quality.storage import ref


def test_exif_rational_dpi_jpeg_postcheck_cli_emits_serializable_numbers(tmp_path):
    contract = make_case(tmp_path)
    contract['route'] = 'raster'
    output = contract['outputs'][0]
    output.update(path='fig1.jpg', format='jpg', pixels=[1200, 600], width_mm=101.6, stroke_pt=None,
                  delivery_target=str(tmp_path / 'authors' / 'fig1.jpg'))
    precheck(contract)
    submission = candidate(contract)
    jpeg = Path(contract['workspace']) / 'fig1.jpg'
    exif = Image.Exif()
    exif[282] = TiffImagePlugin.IFDRational(300, 1)
    exif[283] = TiffImagePlugin.IFDRational(300, 1)
    exif[296] = 2
    Image.new('RGB', (1200, 600), 'white').save(jpeg, exif=exif)
    with Image.open(jpeg) as actual:
        assert all(isinstance(value, TiffImagePlugin.IFDRational) for value in actual.info['dpi'])
    submission['artifacts'] = [ref(jpeg)]
    report_path = Path(submission['audit']['path'])
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report['output_bindings']['fig1'] = ref(jpeg)['sha256']
    report_path.write_text(json.dumps(report), encoding='utf-8')
    submission['audit'] = ref(report_path)
    contract_path = tmp_path / 'contract.json'
    submission_path = tmp_path / 'submission.json'
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    submission_path.write_text(json.dumps(submission), encoding='utf-8')
    process = subprocess.run([sys.executable, '-m', 'task_quality', 'postcheck',
        str(contract_path), str(submission_path)], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=False)
    assert process.returncode == 0, process.stderr + process.stdout
    assert json.loads(process.stdout)['result']['status'] == 'candidate'
    sealed = json.loads((Path(contract['workspace']) / '.task-quality' / 'candidate.json').read_text(encoding='utf-8'))
    measured = sealed['measurements'][0]['measured']
    assert measured['dpi'] == [300.0, 300.0]
    assert all(type(value) is float for value in measured['dpi'])
    assert measured['width_mm'] == 101.6
    assert measured['pixels'] == [1200, 600]
