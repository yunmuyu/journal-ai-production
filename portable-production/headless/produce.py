"""Folder in, PDF or JPG out. No november-data.js and no workbench."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from production_rules.load import load_rules
from production_rules.names import figure_stem
from production_rules.routing import route_dense_chart, route_source
from production_rules.width import column_tiers

from .intake import convert_to_pdf, discover


def _read_job(path: Path | None) -> dict:
    if path is None:
        return {'version': 1, 'figures': {}}
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    data.setdefault('version', 1)
    data.setdefault('figures', {})
    data.setdefault('unit_decisions', [])
    data.setdefault('owner_decisions', [])
    return data


def _column_mm(job, rules) -> float:
    mode = job.get('column') or 'auto'
    tiers = column_tiers(mode, {'policy': job, 'series': job.get('series') or []}, job.get('kind'))
    return float(tiers[0])


def _raster(source: Path, destination: Path, width_mm: float) -> dict:
    import sys
    portable = Path(__file__).resolve().parents[1]
    if str(portable) not in sys.path:
        sys.path.insert(0, str(portable))
    from PIL import Image
    from task_quality.storage import ref
    from raster import render
    with Image.open(source) as image:
        dpi = image.info.get('dpi') or (300, 300)
        physical = image.width / float(dpi[0]) * 25.4
    width = min(physical, width_mm)
    plan = {
        'version': 1,
        'inputs': [{**ref(source), 'crop': None}],
        'layout': {'mode': 'single', 'gap_px': 0},
        'output': str(destination),
        'width_mm': width,
        'quality': 95,
    }
    rules = load_rules()['normative']
    if physical > width_mm + 1e-6:
        plan['target_dpi'] = int(rules['raster_floor_dpi_when_resampled'])
    return render(plan)


def _deliver(source: Path, author: str, number: str, suffix: str, output_root: Path | None, input_root: Path) -> Path:
    stem = figure_stem(author, number)
    folder = output_root if output_root is not None else source.parent
    # Default is the author's own folder. An explicit --output replaces that.
    if output_root is None and source.parent.resolve() != input_root.resolve():
        folder = source.parent
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f'{stem}{suffix}'
    if destination.exists():
        raise FileExistsError(f'输出已存在，不覆盖：{destination}')
    if destination.resolve() == source.resolve():
        raise FileExistsError('不能覆盖来源文件')
    return destination


def produce(input_dir: Path, output_dir: Path | None = None, job_path: Path | None = None) -> dict:
    rules = load_rules()
    job = _read_job(job_path)
    figures = discover(input_dir, job)
    rows = []
    work = (output_dir or input_dir) / '.headless-work'
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    for figure in figures:
        figure_job = (job.get('figures') or {}).get(figure['id'], {})
        hint = figure_job.get('hint')
        decision = route_source(figure['path'], hint)
        if 'point_count' in figure_job or 'line_count' in figure_job or figure_job.get('bitmap_plot_vector_text') is True:
            if decision['route'] != 'raster-only':
                decision = route_dense_chart(
                    int(figure_job.get('point_count') or 0),
                    int(figure_job.get('line_count') or 0),
                    approved=figure_job.get('bitmap_plot_vector_text') is True,
                )
        row = {'id': figure['id'], 'source': figure['path'], 'route': decision, 'status': 'skipped'}
        source = Path(figure['path'])
        try:
            if decision['route'] == 'raster-only':
                destination = _deliver(source, figure['author'], figure['number'], '.jpg', output_dir, input_dir)
                staged = work / f"{figure['id']}.jpg"
                evidence = _raster(source, staged, _column_mm(job, rules))
                shutil.copyfile(staged, destination)
                row.update(status='delivered', output=str(destination), tool='public-raster',
                           automatic_qa=['format', 'size', 'grayscale'], text_legibility_check=False,
                           width_mm=evidence['output']['width_mm'])
            elif decision['route'] == 'screenshot-chart':
                row.update(status='needs-vector-redraw',
                           message='单独统计图截图要裁出图区并重做文字。本轮不凭空造数据。请在 job.json 给出图区。')
            elif decision['route'] == 'needs-owner-approval':
                row.update(status='needs-owner-approval', message=decision['reason'],
                           approval_field=decision.get('approval_field'))
            elif decision['route'] == 'bitmap-plot-vector-text':
                row.update(status='approved-bitmap-plot', message=decision['reason'])
            else:
                pdf = convert_to_pdf(source, work / figure['id'])
                row.update(status='converted', intermediate_pdf=str(pdf), message=decision['reason'])
            row['unit_decisions'] = job.get('unit_decisions') or []
        except Exception as error:
            row.update(status='blocked', error=str(error))
        rows.append(row)
    report = {
        'version': 1,
        'rules_version': rules.get('version'),
        'input': str(input_dir),
        'output': str(output_dir) if output_dir else 'author-folder',
        'workbench': False,
        'figures': rows,
        'open_questions': [item['id'] for item in rules.get('open_questions') or []],
    }
    report_path = (output_dir or input_dir) / 'produce-report.json'
    if output_dir is None and report_path.exists():
        report_path = input_dir / 'produce-report.json'
    # The report is not a source figure. Replace only this generated file.
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    report['report'] = str(report_path)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='无头生产：不启动工作台，不读 november-data.js')
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--job', type=Path)
    args = parser.parse_args(argv)
    report = produce(args.input.resolve(), args.output.resolve() if args.output else None, args.job.resolve() if args.job else None)
    print(json.dumps({key: report[key] for key in ('report', 'output', 'figures')}, ensure_ascii=False))
    blocked = [row for row in report['figures'] if row['status'] == 'blocked']
    return 1 if blocked and not any(row['status'] in ('delivered', 'converted', 'needs-vector-redraw') for row in report['figures']) else 0
