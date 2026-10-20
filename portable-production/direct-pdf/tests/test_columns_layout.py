from copy import deepcopy

import pytest

from journal_pdf.columns import columns
from journal_pdf.graph_layout import graph
from journal_pdf.scene import Scene, audit_scene


def _two_flows():
    return {
        "columns": [
            {
                "id": "main",
                "title": "主程序",
                "nodes": [{"id": "start", "text": "开始"}, {"id": "work", "text": "处理"}],
                "edges": [
                    {"id": "next", "from": "start", "to": "work"},
                    {"id": "again", "from": "work", "to": "start", "return_edge": True},
                ],
            },
            {
                "id": "irq",
                "title": "中断程序",
                "nodes": [{"id": "start", "text": "开始"}, {"id": "work", "text": "处理"}],
                "edges": [{"id": "next", "from": "start", "to": "work"}],
            },
        ],
        "relations": [
            {
                "id": "interrupt",
                "type": "asynchronous-event-response",
                "from": "main.work",
                "to": "irq.start",
                "note": "可响应中断，不是顺序流程边。",
            }
        ],
    }


def test_columns_namespace_independent_graphs_without_cross_column_path(reg):
    # Given: two independent flows reuse local node and edge IDs.
    spec = _two_flows()

    # When: the flows are composed as columns.
    scene = columns(spec, reg, 8)

    # Then: every object reference is namespaced and the relation remains a note.
    object_ids = [item["id"] for group in (scene.nodes, scene.texts, scene.paths) for item in group]
    assert len(object_ids) == len(set(object_ids))
    assert {node["id"] for node in scene.nodes} == {"main:start", "main:work", "irq:start", "irq:work"}
    assert all(text["owner"] is None or ":" in text["owner"] for text in scene.texts)
    assert all(path["endpoint_nodes"] is None or all(":" in node for node in path["endpoint_nodes"]) for path in scene.paths)
    assert not any(path["id"] == "interrupt" for path in scene.paths)
    assert scene.notes == spec["relations"]
    assert not audit_scene(scene)


def test_columns_top_align_and_translate_ports_from_each_graph(reg):
    # Given: the expected standalone geometry for each flow.
    spec = _two_flows()
    standalone = [graph(column, reg, 8) for column in spec["columns"]]

    # When: both graphs are composed.
    scene = columns(spec, reg, 8)

    # Then: graph origins share a top edge and every path point has one column offset.
    starts = {node["id"]: node for node in scene.nodes if node["id"].endswith(":start")}
    assert starts["main:start"]["rect"][1] == pytest.approx(starts["irq:start"]["rect"][1])
    for index, prefix in enumerate(("main", "irq")):
        source_path = next(path for path in standalone[index].paths if path["id"] == "next")
        composed_path = next(path for path in scene.paths if path["id"] == f"{prefix}:next")
        dx = starts[f"{prefix}:start"]["rect"][0] - standalone[index].nodes[0]["rect"][0]
        dy = starts[f"{prefix}:start"]["rect"][1] - standalone[index].nodes[0]["rect"][1]
        expected = [[x + dx, y + dy] for x, y in source_path["points"]]
        assert all(actual == pytest.approx(wanted) for actual, wanted in zip(composed_path["points"], expected))


def test_columns_translate_assets_and_text_render_positions(monkeypatch, reg):
    # Given: a child Scene containing all coordinate-bearing object classes.
    marker = type("Marker", (), {"key": "asset", "audit": {}})()

    def child(_spec, registry, size):
        scene = Scene(registry, size)
        scene.shape("node", [1, 2, 11, 12])
        scene.text("label", "A", 6, 7, owner="node")
        scene.line("path", [[11, 7], [21, 7]], endpoint_nodes=[None, "node"])
        scene.embed("asset", marker, [2, 3, 8, 9])
        return scene.finish(22, 14)

    monkeypatch.setattr("journal_pdf.columns.graph", child)

    # When: the child is placed in the second column.
    scene = columns({"columns": [{"id": "a", "nodes": [{}]}, {"id": "b", "nodes": [{}]}]}, reg, 8)
    node = next(item for item in scene.nodes if item["id"] == "b:node")
    text = next(item for item in scene.texts if item["id"] == "b:label")
    path = next(item for item in scene.paths if item["id"] == "b:path")
    asset = next(item for item in scene.assets if item["id"] == "b:asset")
    dx, dy = node["rect"][0] - 1, node["rect"][1] - 2

    # Then: draw anchors, ink bbox, path points, and asset rect move together.
    assert [text["x"], text["y"]] == pytest.approx([6 + dx, 7 + dy])
    assert text["position"]["bbox"] == pytest.approx([value + (dx if index % 2 == 0 else dy) for index, value in enumerate(child({}, reg, 8).texts[0]["position"]["bbox"])])
    assert text["position"]["offset"] == pytest.approx([value + delta for value, delta in zip(child({}, reg, 8).texts[0]["position"]["offset"], (dx, dy))])
    assert all(actual == pytest.approx(wanted) for actual, wanted in zip(path["points"], [[11 + dx, 7 + dy], [21 + dx, 7 + dy]]))
    assert path["endpoint_nodes"] == [None, "b:node"]
    assert asset["rect"] == pytest.approx([2 + dx, 3 + dy, 8 + dx, 9 + dy])


def test_columns_does_not_mutate_or_change_standalone_graph(reg):
    # Given: a standalone graph and an untouched semantic spec.
    column = _two_flows()["columns"][0]
    original = deepcopy(column)
    before = graph(column, reg, 8).export()

    # When: the same spec is used through the column compositor.
    columns({"columns": [column]}, reg, 8)
    after = graph(column, reg, 8).export()

    # Then: graph input and standalone output remain unchanged.
    assert column == original
    assert after == before


def test_columns_support_vertical_packing_from_child_bounds(reg):
    # Given: two independent flows requested as a vertical stack.
    spec = _two_flows() | {"direction": "TB"}

    # When: the public compositor packs their measured child scenes.
    scene = columns(spec, reg, 8)
    main = [node for node in scene.nodes if node["id"].startswith("main:")]
    irq = [node for node in scene.nodes if node["id"].startswith("irq:")]

    # Then: the second flow begins below the first flow's actual bounds.
    assert min(node["rect"][1] for node in irq) > max(node["rect"][3] for node in main)
    assert scene.layout_evidence["direction"] == "TB"
