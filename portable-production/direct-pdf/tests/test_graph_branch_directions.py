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
 nodes={node['id']:node for node in scene.nodes}
 if branch_kind=='fanout':
  for edge in edges:
   path=next(p for p in scene.paths if p['id']==edge['id'])
   assert path['points'][-1]==pytest.approx(port(nodes[edge['to']],target_port))
 else:
  outlet=next(p for p in scene.paths if p.get('semantic_role')=='outlet')
  assert outlet['points'][-1]==pytest.approx(port(nodes['c'],target_port))
