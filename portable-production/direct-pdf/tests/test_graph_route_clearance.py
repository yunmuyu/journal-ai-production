import pytest

from journal_pdf.common import FigureError
from journal_pdf.graph_layout import graph
from journal_pdf.scene import audit_scene


def offset_rank_spec():
 return {
  'nodes':[{'id':'start','text':'开始'},
           {'id':'choice','text':'继续？','shape':'diamond'},
           {'id':'side','text':'短分支'},
           {'id':'main','text':'较宽的主要处理框，包含多项处理内容与状态比较'},
           {'id':'next','text':'后续居中处理'},
           {'id':'end','text':'结束'}],
  'edges':[{'id':'start-choice','from':'start','to':'choice'},
           {'id':'choice-side','from':'choice','to':'side'},
           {'id':'choice-main','from':'choice','to':'main'},
           {'id':'main-next','from':'main','to':'next'},
           {'id':'side-return','from':'side','to':'choice','return_edge':True},
           {'id':'next-end','from':'next','to':'end'}]}


def test_offset_adjacent_rank_reserves_room_for_orthogonal_stubs(reg):
 scene=graph(offset_rank_spec(),reg,8)
 assert not audit_scene(scene)
 assert next(p for p in scene.paths if p['id']=='main-next')['points'][0]!=next(
  p for p in scene.paths if p['id']=='main-next')['points'][-1]


def test_route_blocked_reports_edge_ports_and_constraints(reg,monkeypatch):
 def blocked(*_args,**_kwargs):
  raise FigureError('graph_route_blocked','无避开节点的正交连线方案')
 monkeypatch.setattr('journal_pdf.graph_layout._route',blocked)
 with pytest.raises(FigureError) as caught:
  graph(offset_rank_spec(),reg,8)
 assert caught.value.code=='graph_route_blocked'
 assert caught.value.details['edge']=='main-next'
 assert caught.value.details['from']=='main'
 assert caught.value.details['to']=='next'
 assert caught.value.details['from_port']=='bottom'
 assert caught.value.details['to_port']=='top'
 assert caught.value.details['source_stub_pt']>0
 assert caught.value.details['target_stub_pt']>0
 assert caught.value.details['obstacle_count']==len(offset_rank_spec()['nodes'])
