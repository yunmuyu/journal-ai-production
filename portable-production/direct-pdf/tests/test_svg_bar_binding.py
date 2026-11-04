import pytest
from journal_pdf.ingest_native import svg_pages
from journal_pdf.agent_spec import _svg, svg_tick as svg_x_tick
from journal_pdf.charts import tick_content
from journal_pdf.common import FigureError


def fixture(tmp_path, *, ambiguous=False):
    color = '#ff0000' if ambiguous else '#0000ff'
    source = tmp_path / 'bars.svg'
    source.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <defs><clipPath id="clip"><rect width="100" height="100"/></clipPath></defs>
      <g id="axes_1">
        <g id="patch_1"><path d="M0 0 L100 0 L100 100 L0 100 Z" fill="white"/></g>
        <g id="patch_2"><path d="M10 20 L20 20 L20 90 L10 90 Z" fill="#ff0000" clip-path="url(#clip)"/></g>
        <g id="patch_3"><path d="M30 40 L40 40 L40 90 L30 90 Z" fill="{color}" clip-path="url(#clip)"/></g>
        <g id="line2d_1"><path d="M50 0 L50 100" stroke="black"/></g>
        <g id="text_1"><!-- 70 --><text x="10" y="18">70</text></g>
        <g id="text_2"><!-- 50 --><text x="30" y="38">50</text></g>
        <g id="legend_1">
          <g id="patch_4"><path d="M60 0 L65 0 L65 5 L60 5 Z" fill="#ff0000"/></g>
          <g id="text_3"><!-- Before --><text x="66" y="5">Before</text></g>
          <g id="patch_5"><path d="M60 10 L65 10 L65 15 L60 15 Z" fill="{color}"/></g>
          <g id="text_4"><!-- After --><text x="66" y="15">After</text></g>
        </g>
      </g></svg>''', encoding='utf-8')
    return svg_pages(source, tmp_path)[0]


def test_rectangles_bind_to_two_legends_not_divider(tmp_path):
    chart = fixture(tmp_path)['chart_candidates'][0]
    assert chart['series_group_members'] == {'patch_4':['patch_2'], 'patch_5':['patch_3']}
    assert 'line2d_1' not in chart['series_groups']
    assert chart['data_label_groups'] == ['text_1','text_2']
    assert not chart['unresolved_patch_series']


def test_ambiguous_fill_rejects_instead_of_losing_bars(tmp_path):
    page = fixture(tmp_path, ambiguous=True)
    assert page['chart_candidates'][0]['unresolved_patch_series']
    with pytest.raises(FigureError) as error:
        _svg({'chart_ref':'axes_1'}, {}, page, {})
    assert error.value.code == 'svg_bar_binding'


@pytest.mark.parametrize('label', ['A', 'Layer 2'])
def test_categorical_labels_are_source_text(label):
    assert tick_content(svg_x_tick({'text_hint':label,'position':10})) == label


def test_numeric_ticks_still_receive_grouping():
    assert tick_content(svg_x_tick({'text_hint':'1000','position':10})) == '1 000'
