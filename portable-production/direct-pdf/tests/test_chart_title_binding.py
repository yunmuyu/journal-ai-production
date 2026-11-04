import copy

import pytest

from journal_pdf.agent_spec import compile_reply_figure
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import compile_figure
from test_no_legend_chart import no_legend_spec


def title_input():
    chart = {
        'id': 'axes_1', 'axes_id': 'axes_1',
        'x_ticks': [{'text_hint': '1', 'position': 0}],
        'y_ticks': [{'text_hint': '2', 'position': 100}],
        'titles': {'x': {'text_hint': 'Time(s)'}, 'y': {'text_hint': 'Value(V)'}},
        'legend_rows': [], 'legend_id': None, 'series_groups': ['line_1'],
        'plot_clip': [0, 0, 200, 200], 'frame': [0, 0, 200, 200],
        'protected_path_points': [], 'tick_length': 1,
        'unhandled_plot_text': [{'id': 'text_9', 'text': 'Original chart title'}],
    }
    page = {'id': 'p', 'kind': 'svg', 'chart_candidates': [chart]}
    reply = {'id': 'fig', 'kind': 'svg-chart', 'title_ref': 'text_9',
             'review': {'source_checked': True, 'labels_checked': True, 'no_legend_reason': 'No legend in source'},
             'chart_ref': 'axes_1', 'accept_source_text_hints': True, 'series_pairs': []}
    source = {'id': 's', 'snapshot': 'x.svg', 'sha256': 'a' * 64}
    return reply, source, page


def test_explicit_original_title_is_bound_without_deleting_other_text():
    reply, source, page = title_input()
    spec = compile_reply_figure(reply, source, page)
    assert spec['plot_title'] == 'Original chart title'
    assert spec['ingest_provenance']['plot_title_ref'] == 'text_9'
    changed = copy.deepcopy(page)
    changed['chart_candidates'][0]['unhandled_plot_text'].append({'id': 'text_10', 'text': 'Data note'})
    with pytest.raises(FigureError, match='图内标题或数据文字'):
        compile_reply_figure(reply, source, changed)


def test_title_is_not_invented_from_an_unknown_reference():
    reply, source, page = title_input()
    reply['title_ref'] = 'missing'
    with pytest.raises(FigureError):
        compile_reply_figure(reply, source, page)


def test_title_layout_keeps_original_plot_geometry_and_measured_clearance(reg, tmp_path):
    spec = no_legend_spec(tmp_path)
    assets = Assets()
    try:
        original = compile_figure(spec, reg, assets, tmp_path)
        spec['plot_title'] = 'Original chart title'
        titled = compile_figure(spec, reg, assets, tmp_path)
        title = next(t for t in titled.texts if t['id'] == 'plot-title')
        rest = [t for t in titled.texts if t['id'] != 'plot-title']
        assert title['measurement']['size'] == rest[0]['measurement']['size']
        assert min(t['position']['bbox'][1] for t in rest) - title['position']['bbox'][3] >= 3
        assert titled.assets[0]['asset'].audit == original.assets[0]['asset'].audit
        a, b = original.assets[0]['rect'], titled.assets[0]['rect']
        assert b[2] - b[0] == pytest.approx(a[2] - a[0])
        assert b[3] - b[1] == pytest.approx(a[3] - a[1])
    finally:
        assets.close()
