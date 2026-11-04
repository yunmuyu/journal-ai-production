import hashlib

from journal_pdf.assets import Assets
from journal_pdf.render import compile_figure


def test_two_panels_keep_both_original_curves_and_editable_labels(reg, tmp_path):
    source = tmp_path / 'panels.svg'
    source.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
      <g id="axes_1"><g id="curve1"><path d="M10 90 L90 10" stroke="black" fill="none"/></g></g>
      <g id="axes_2"><g id="curve2"><path d="M10 80 L90 20" stroke="black" fill="none"/></g></g>
      </svg>''', encoding='utf-8')
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    panels = []
    for index in (1, 2):
        panels.append({'kind': 'chart', 'source_kind': 'svg', 'source': 'panels.svg',
                       'axes_id': f'axes_{index}', 'legend_source_id': None,
                       'plot_clip': [0, 0, 100, 100], 'axis_frame_source': [0, 0, 100, 100],
                       'plot_width_pt': 150, 'tick_length_source_units': 3.5,
                       'x_title': 'Time(s)', 'y_title': 'SBP (mmHg)', 'plot_title': f'Panel {index}',
                       'x_ticks': [{'text': '0', 'position': 0}, {'text': '1', 'position': 100}],
                       'y_ticks': [{'text': '0', 'position': 100}, {'text': '1', 'position': 0}],
                       'series': [], 'series_source_groups': [f'curve{index}'],
                       'legend_review': {'present': False, 'source_sha256': sha, 'reason': 'No legend'}})
    spec = {'kind': 'chart', 'panels': panels, 'policy': {'column': 'double', 'design_font_size_pt': 8}}
    assets = Assets()
    try:
        scene = compile_figure(spec, reg, assets, tmp_path)
        assert scene.size == 8
        assert len(scene.layout_evidence['chart_panels']) == 2
        plots = [a for a in scene.assets if a['role'] == 'plot']
        assert len(plots) == 2
        assert all(a['asset'].audit['geometry_before'] == a['asset'].audit['geometry_after'] for a in plots)
        assert plots[0]['rect'][2] < plots[1]['rect'][0]
        assert len({t['id'] for t in scene.texts}) == len(scene.texts)
        assert {t['measurement']['text'] for t in scene.texts if t['id'].endswith('plot-title')} == {'Panel 1', 'Panel 2'}
    finally:
        assets.close()
