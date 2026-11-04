from copy import deepcopy

import pytest

from journal_pdf.common import FigureError
from journal_pdf.fonts import FontRegistry
from journal_pdf.graph_layout import graph
from journal_pdf.scene import audit_scene


def test_explicit_group_shares_width_across_ranks_but_keeps_individual_heights(reg: FontRegistry) -> None:
    # Given: three related processing modules, plus an unrelated decision and module.
    spec = {
        "direction": "TB",
        "nodes": [{"id": "a", "text": "Read"}, {"id": "b", "text": "Validate\npayload"},
                  {"id": "c", "text": "Dispatch results"}, {"id": "d", "text": "OK?", "shape": "diamond"},
                  {"id": "e", "text": "Log"}],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"},
                  {"from": "c", "to": "d"}, {"from": "d", "to": "e"}],
        "equal_width_groups": [{"id": "modules", "nodes": ["a", "b", "c"]}],
    }
    baseline = deepcopy(spec)
    baseline.pop("equal_width_groups")
    original = graph(baseline, reg, 8)

    # When: explicit semantic peers are laid out across topological ranks.
    scene = graph(spec, reg, 8)

    # Then: peers fit the widest text at unchanged size; other node dimensions stay independent.
    boxes = {node["id"]: node["rect"] for node in scene.nodes}
    originals = {node["id"]: node["rect"] for node in original.nodes}
    expected = max(reg.measure(node["text"], 8)["width"] for node in spec["nodes"][:3]) + 9
    assert [boxes[key][2] - boxes[key][0] for key in ("a", "b", "c")] == pytest.approx([expected] * 3)
    assert boxes["b"][3] - boxes["b"][1] > boxes["a"][3] - boxes["a"][1]
    assert [(boxes[key][0] + boxes[key][2]) / 2 for key in ("a", "b", "c")] == pytest.approx([scene.nodes[0]["rect"][0] + expected / 2] * 3)
    for key in ("d", "e"):
        assert [boxes[key][2] - boxes[key][0], boxes[key][3] - boxes[key][1]] == pytest.approx(
            [originals[key][2] - originals[key][0], originals[key][3] - originals[key][1]])
    assert all(text["measurement"]["size"] == 8 for text in scene.texts)
    assert not audit_scene(scene)


def test_group_audit_rejects_a_member_made_wider_after_layout(reg: FontRegistry) -> None:
    # Given: a declared group rendered by the public graph compiler.
    scene = graph({"nodes": [{"id": "a", "text": "Input"}, {"id": "b", "text": "Output"}],
                   "edges": [{"from": "a", "to": "b"}],
                   "equal_width_groups": [{"id": "modules", "nodes": ["a", "b"]}]}, reg, 8)
    # When: downstream code accidentally changes one frame width.
    scene.nodes[0]["rect"][2] += 2
    # Then: the existing measured-group audit independently detects the mismatch.
    assert any(issue["code"] == "primitive_box_measurement_mismatch" for issue in audit_scene(scene))


@pytest.mark.parametrize("groups", [
    [{"id": "g", "nodes": ["missing"]}],
    [{"id": "g", "nodes": ["a", "a"]}],
    [{"id": "g", "nodes": ["d"]}],
    [{"id": "g", "nodes": ["container"]}],
    [{"id": "g", "nodes": ["a"]}, {"id": "h", "nodes": ["a"]}],
    [{"id": "g", "nodes": ["a"]}, {"id": "g", "nodes": ["b"]}],
    [{"id": "g", "axis": "both", "nodes": ["a", "b"]}],
])
def test_invalid_semantic_group_is_rejected(reg: FontRegistry, groups) -> None:
    # Given: a group with ambiguous membership or unsupported shape/measurement intent.
    spec = {"nodes": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"},
                      {"id": "d", "text": "OK?", "shape": "diamond"},
                      {"id": "container", "text": "Container", "container": True}], "equal_width_groups": groups}
    # When / Then: invalid declarations never silently fall back to rank grouping.
    with pytest.raises(FigureError) as error:
        graph(spec, reg, 8)
    assert error.value.code == "measured_group_invalid"
