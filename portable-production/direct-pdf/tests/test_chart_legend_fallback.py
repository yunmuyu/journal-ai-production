from journal_pdf.assets import Assets
from journal_pdf.render import compile_figure


def test_full_inside_legend_uses_existing_outside_layout_without_covering_data(reg, tmp_path):
    source = tmp_path / 'chart.svg'
    source.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
    <g id="axes_1"><g id="curve"><path d="M0 0 L100 0 L100 100 L0 100 Z" fill="none" stroke="black"/></g>
    <g id="legend_1"><g id="sample"><path d="M0 0 L10 0" stroke="black"/></g></g></g></svg>''', encoding='utf-8')
    spec = {'kind': 'chart', 'source_kind': 'svg', 'source': 'chart.svg',
            'axes_id': 'axes_1', 'legend_source_id': 'legend_1',
            'plot_clip': [0, 0, 100, 100], 'axis_frame_source': [0, 0, 100, 100],
            'plot_width_pt': 40, 'tick_length_source_units': 0,
            'x_ticks': [{'text': '0', 'position': 0}, {'text': '1', 'position': 100}],
            'y_ticks': [{'text': '0', 'position': 100}, {'text': '1', 'position': 0}],
            'x_title': 'Time(s)', 'y_title': 'Value(V)', 'legend_placement': 'auto-inside',
            'legend_frame': False, 'plot_title': 'Original title',
            'protected_path_points': [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]],
            'series': [{'id': 'curve', 'label': 'Original curve label', 'source_group': 'curve',
                        'swatch_group': 'sample', 'swatch_clip': [0, -1, 10, 1]}]}
    assets = Assets()
    try:
        scene = compile_figure(spec, reg, assets, tmp_path)
        assert scene.layout_evidence['legend_placement'] == 'outside-top'
        plot = next(a for a in scene.assets if a['role'] == 'plot')
        legend = next(t for t in scene.texts if t['role'] == 'legend-label')
        title = next(t for t in scene.texts if t['id'] == 'plot-title')
        assert title['position']['bbox'][3] < legend['position']['bbox'][1]
        assert legend['position']['bbox'][3] < plot['rect'][1]
        assert plot['asset'].audit['geometry_before'] == plot['asset'].audit['geometry_after']
    finally:
        assets.close()
