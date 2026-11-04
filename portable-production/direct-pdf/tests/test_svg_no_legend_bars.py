from journal_pdf.ingest_native import svg_pages
import pytest
from journal_pdf.agent_spec import _svg, svg_tick
from journal_pdf.charts import tick_content
from journal_pdf.common import FigureError


def test_no_legend_bars_remain_source_series(tmp_path):
    source = tmp_path / 'bars.svg'
    source.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <defs><clipPath id="c"><rect width="100" height="100"/></clipPath></defs>
    <g id="axes_1"><g id="patch_1"><path d="M0 0 L100 0 L100 100 L0 100 Z"/></g>
    <g id="patch_2"><path d="M0 10 L80 10 L80 20 L0 20 Z" clip-path="url(#c)"/></g>
    <g id="patch_3"><path d="M0 30 L60 30 L60 40 L0 40 Z" clip-path="url(#c)"/></g>
    </g></svg>''', encoding='utf-8')
    chart = svg_pages(source, tmp_path)[0]['chart_candidates'][0]
    assert chart['series_groups'] == ['patch_2', 'patch_3']
    assert len(chart['protected_path_points']) == 2


def test_category_and_numeric_ticks_preserve_original_text():
    assert tick_content(svg_tick({'text_hint':'crest_factor','position':1})) == 'crest_factor'
    assert tick_content(svg_tick({'text_hint':'1000','position':2})) == '1 000'


def test_unbound_plot_text_cannot_be_silently_removed():
    page={'kind':'svg','chart_candidates':[{'id':'axes_1','unhandled_plot_text':[{'id':'text_1','text':'Title'}]}]}
    with pytest.raises(FigureError) as exc:
        _svg({'chart_ref':'axes_1'}, {}, page, {})
    assert exc.value.code == 'svg_plot_text_unbound'
