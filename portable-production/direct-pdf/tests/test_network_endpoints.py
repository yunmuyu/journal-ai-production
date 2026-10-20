import math

import pytest

from journal_pdf.editorial import ARROW_LENGTH
from journal_pdf.layouts import network
from journal_pdf.scene import audit_scene


def test_network_edges_bind_nodes_and_keep_exact_arrow_terminal(reg):
    spec={
        'width_pt':150,
        'height_pt':100,
        'nodes':[
            {'id':'a','text':'N1','x':25,'y':50},
            {'id':'b','text':'N2','x':75,'y':20},
        ],
        'edges':[{'from':'a','to':'b','arrow':True}],
    }

    scene=network(spec,reg,8)

    edge=scene.paths[0]
    assert edge['endpoint_nodes']==['a','b']
    assert edge['exact_terminal'] is True
    assert math.dist(edge['points'][-2],edge['points'][-1])==pytest.approx(ARROW_LENGTH)
    assert audit_scene(scene)==[]
