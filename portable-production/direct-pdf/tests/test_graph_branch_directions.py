import math

import pytest

from journal_pdf.graph_layout import graph
from journal_pdf.scene import audit_scene, port


@pytest.mark.parametrize('direction',['TB','LR'])
@pytest.mark.parametrize('branch_kind',['fanout','merge'])
def test_branch_bus_uses_flow_direction_without_crossing_nodes(reg,direction,branch_kind):
 # Given an ordinary split or join with two parallel branches.
 edges=([{'id':'ab','from':'a','to':'b'},{'id':'ac','from':'a','to':'c'}]
        if branch_kind=='fanout' else
        [{'id':'ac','from':'a','to':'c'},{'id':'bc','from':'b','to':'c'}])
 spec={'direction':direction,'nodes':[{'id':name,'text':name.upper()} for name in ['a','b','c']],
       'edges':edges}
 # When the measured graph places its shared bus.
 scene=graph(spec,reg,8)
 # Then it must retain the complete topology and all geometry audits.
 assert not audit_scene(scene)
 source_port,target_port=('bottom','top') if direction=='TB' else ('right','left')
 for binding in scene.layout_evidence['edge_bindings']:
  assert binding['from_port']==source_port
  assert binding['to_port']==target_port
 assert {(b['from'],b['to']) for b in scene.layout_evidence['edge_bindings']}=={
  (edge['from'],edge['to']) for edge in edges}
 if branch_kind=='merge':
  legs=[p for p in scene.paths if p.get('semantic_role')=='merge-leg']
  from journal_pdf.common import PT_PER_MM
  from journal_pdf.journal_rules import load_rules
  leg=float(load_rules()['normative']['summary_bus_edge_mm'])*PT_PER_MM
  assert legs and all(math.dist(*p['points'])==pytest.approx(leg) for p in legs)
 nodes={node['id']:node for node in scene.nodes}
 from journal_pdf.editorial import ARROW_DEPTH, STROKE
 from journal_pdf.scene import arrow_vertices
 if branch_kind=='fanout':
  arrows=[next(p for p in scene.paths if p['id']==edge['id']) for edge in edges]
  for edge in edges:
   path=next(p for p in scene.paths if p['id']==edge['id'])
   assert path['points'][-1]==pytest.approx(port(nodes[edge['to']],target_port))
 else:
  outlet=next(p for p in scene.paths if p.get('semantic_role')=='outlet')
  assert outlet['points'][-1]==pytest.approx(port(nodes['c'],target_port))
  arrows=[outlet]
 for path in arrows:
  bus_pt, tip = path['points'][-2], path['points'][-1]
  leg = math.dist(bus_pt, tip)
  axis = 0 if abs(tip[0] - bus_pt[0]) >= abs(tip[1] - bus_pt[1]) else 1
  direction_sign = 1 if tip[axis] > bus_pt[axis] else -1
  vertices = arrow_vertices(path['points'], scale=path['arrow_scale'])
  along = [(v[axis] - bus_pt[axis]) * direction_sign for v in vertices]
  assert min(along) > STROKE / 2
  assert max(along) == pytest.approx(leg)
  assert ARROW_DEPTH * path['arrow_scale'] + STROKE / 2 < leg
  target = nodes[path['endpoint_nodes'][1]]
  assert not any(target['rect'][0] < v[0] < target['rect'][2] and target['rect'][1] < v[1] < target['rect'][3] for v in vertices)
