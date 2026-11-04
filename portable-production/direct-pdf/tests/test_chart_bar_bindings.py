from pathlib import Path

import pytest

from journal_pdf.chart_bar_bindings import bind_bar_labels
from journal_pdf.charts import place_bar_top_labels
from journal_pdf.common import FigureError


def sample(tmp_path: Path):
    source=tmp_path/'chart.svg'
    source.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g id="axes_1">
      <g id="bar"><path d="M 10 80 L 20 80 L 20 48 L 10 48 z"/></g>
      <g id="text_1"><!-- 64 --><g transform="translate(12 43) scale(.1 -.1)"><path d="M 0 0 L 1 1"/></g></g>
      <g id="text_2"><!-- Group --><g transform="translate(10 20) scale(.1 -.1)"><path d="M 0 0 L 1 1"/></g></g>
    </g></svg>''',encoding='utf8')
    return {'source_kind':'svg','source':'chart.svg','axes_id':'axes_1','series':[{'source_groups':['bar']}],
      'y_ticks':[{'text':'0','position':80},{'text':'100','position':30}],
      'bar_labels':[{'id':'label','text_group':'text_1','bar_group':'bar'}],
      'section_labels':[{'id':'section-label','text_group':'text_2'}]}


def test_bar_text_is_bound_to_source_geometry_and_axis(tmp_path):
    spec=sample(tmp_path);rows,sections=bind_bar_labels(spec,tmp_path)
    assert rows[0].text=='64' and rows[0].rect==(10,48,20,80)
    assert sections[0][1]=='Group'
    spec['y_ticks'][1]['text']='90'
    with pytest.raises(FigureError,match='数值'):bind_bar_labels(spec,tmp_path)


def test_bar_binding_refuses_duplicate_or_unregistered_source(tmp_path):
    spec=sample(tmp_path);spec['bar_labels'].append(dict(spec['bar_labels'][0],id='other'))
    with pytest.raises(FigureError,match='唯一'):bind_bar_labels(spec,tmp_path)
    spec=sample(tmp_path);spec['series'][0]['source_groups']=['another']
    with pytest.raises(FigureError,match='已绑定系列'):bind_bar_labels(spec,tmp_path)
    spec=sample(tmp_path);spec['section_labels']=[]
    with pytest.raises(FigureError,match='完整绑定'):bind_bar_labels(spec,tmp_path)
    spec=sample(tmp_path);spec['bar_labels']=[]
    with pytest.raises(FigureError,match='完整绑定'):bind_bar_labels(spec,tmp_path)


def test_dense_bar_labels_can_rotate_without_reducing_font_or_touching():
    values=[[{'rect':[2,30,8,70],'runs':'1'},{'rect':[10,30,16,70],'runs':'2'}]]
    measure=lambda text:{'ink':[0,0,10,5]}
    with pytest.raises(FigureError,match='净距不足'):place_bar_top_labels(values,measure,ink_gap_pt=2,plot_rect=[0,0,50,80])
    rows,proof=place_bar_top_labels(values,measure,ink_gap_pt=2,plot_rect=[0,0,50,80],rotation=90)
    assert len(rows)==2 and proof['minimum_horizontal_gap_pt']>=2
