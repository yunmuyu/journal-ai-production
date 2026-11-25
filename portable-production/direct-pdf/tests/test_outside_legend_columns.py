from journal_pdf.legend_grid import pack_legend_columns
from journal_pdf.assets import Assets
from journal_pdf.render import compile_figure


def test_six_labels_fit_two_per_row_using_actual_measured_widths():
    grid = pack_legend_columns([80, 90, 90, 90, 90, 90], 208, gap=6)
    assert grid.columns == 2
    assert grid.rows == 3
    assert grid.width == 186
    assert grid.offsets == (0, 96)


def test_short_labels_use_three_columns_when_they_fit():
    grid = pack_legend_columns([55] * 6, 180, gap=6)
    assert grid.columns == 3
    assert grid.rows == 2
    assert grid.width == 177


def test_long_labels_keep_one_column_without_reducing_font_size():
    grid = pack_legend_columns([100, 100, 100], 190, gap=6)
    assert grid.columns == 1
    assert grid.rows == 3


def test_safe_inside_legend_takes_priority_over_fewer_outside_rows(reg, tmp_path):
    label_width = reg.measure('Series A label', 8)['width']
    plot_width = 2 * (label_width + 13) + 6 - 15
    source = tmp_path / 'chart.svg'
    source.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
    <g id="axes_1"><g id="curve"><path d="M0 100 L100 100" fill="none" stroke="black"/></g>
    <g id="legend_1"><g id="sample"><path d="M0 0 L10 0" stroke="black"/></g></g></g></svg>''', encoding='utf-8')
    spec = {'kind': 'chart', 'source_kind': 'svg', 'source': 'chart.svg',
            'axes_id': 'axes_1', 'legend_source_id': 'legend_1',
            'plot_clip': [0, 0, 100, 100], 'axis_frame_source': [0, 0, 100, 100],
            'plot_width_pt': plot_width, 'tick_length_source_units': 0,
            'x_ticks': [{'text': '0', 'position': 0}, {'text': '1', 'position': 100}],
            'y_ticks': [{'text': '0', 'position': 100}, {'text': '1', 'position': 0}],
            'x_title': 'Time(s)', 'y_title': 'Value(V)', 'legend_placement': 'auto-inside',
            'legend_frame': False, 'protected_path_points': [[[0, 100], [100, 100]]],
            'series': [{'id': f'curve-{i}', 'label': f'Series {letter} label', 'source_group': 'curve',
                        'swatch_group': 'sample', 'swatch_clip': [0, -1, 10, 1]}
                       for i, letter in enumerate('ABCD')]}
    assets = Assets()
    try:
        scene = compile_figure(spec, reg, assets, tmp_path)
        assert scene.layout_evidence['legend_columns'] == 1
        assert scene.layout_evidence['legend_rows'] == 4
        assert scene.layout_evidence['legend_placement'] == 'auto-inside'
    finally:
        assets.close()
