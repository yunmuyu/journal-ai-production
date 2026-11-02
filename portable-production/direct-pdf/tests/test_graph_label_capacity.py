from journal_pdf.common import PT_PER_MM
from journal_pdf.fonts import FontRegistry
from journal_pdf.graph_layout import graph
from journal_pdf.scene import audit_scene


def test_vertical_chain_reserves_space_for_long_edge_labels(reg: FontRegistry) -> None:
    # Given: narrow nodes and a label that cannot fit in the node-only canvas.
    spec = {
        "direction": "TB",
        "nodes": [{"id": "a", "text": "Input"}, {"id": "b", "text": "Output"}],
        "edges": [{"id": "ab", "from": "a", "to": "b", "label": "Normalized event payload"}],
    }

    # When: laying out at the intended publication font size.
    scene = graph(spec, reg, 8)

    # Then: the complete label fits one column without scaling or collisions.
    label = next(text for text in scene.texts if text["id"] == "ab:label")
    assert label["measurement"]["size"] == 8
    assert label["position"]["bbox"][2] < scene.width
    assert scene.width < 80 * PT_PER_MM
    assert not audit_scene(scene)
