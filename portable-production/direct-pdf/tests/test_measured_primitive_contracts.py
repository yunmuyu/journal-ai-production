import pytest

from journal_pdf.common import digest_file
from journal_pdf.layouts import primitive
from journal_pdf.scene import Scene, audit_scene


def test_plain_primitive_box_cannot_silently_use_oversized_rect(reg):
    spec = {
        "width_pt": 100,
        "height_pt": 50,
        "nodes": [{"id": "sensor", "text": "传感器", "rect": [5, 5, 68, 31]}],
    }
    scene = primitive(spec, reg, 8)
    assert {issue["code"] for issue in audit_scene(scene)} >= {"primitive_box_measurement_mismatch"}


def test_plain_primitive_rect_matching_measured_tight_size_passes(reg):
    measured = reg.measure("传感器", 8)
    width, height = measured["width"] + 9, measured["height"] + 5.4
    spec = {"width_pt": 100, "height_pt": 50,
            "nodes": [{"id": "sensor", "text": "传感器", "rect": [5, 5, 5 + width, 5 + height]}]}
    scene = primitive(spec, reg, 8)
    assert not any(issue["code"].startswith("primitive_box_measurement") for issue in audit_scene(scene))


def test_custom_template_direct_shape_cannot_bypass_box_measurement(reg):
    scene = Scene(reg, 8);scene.template = "author-custom-rebuild"
    scene.shape("sensor", [5, 5, 68, 31])
    scene.text("sensor-text", "传感器", 36.5, 18, owner="sensor")
    scene.finish(100, 50)
    assert any(issue["code"] == "primitive_box_measurement_contract" for issue in audit_scene(scene))


@pytest.mark.parametrize("contract", [
    {"mode": "tight", "expected_wh": [85, 30]},
    {"mode": "measured-group", "group": "fake", "axis": "row", "expected_wh": [85, 30]},
    {"mode": "fixed", "fixed_size": {"purpose": "beautification", "evidence": {}}},
])
def test_forged_node_measurement_contract_cannot_bypass_audit(reg, contract):
    scene = Scene(reg, 8);scene.template = "arbitrary-template"
    node = scene.shape("sensor", [5, 5, 90, 35])
    scene.text("sensor-text", "传感器", 47.5, 20, owner="sensor")
    node["measurement_contract"] = contract
    scene.finish(100, 40)
    assert any(issue["code"].startswith("primitive_box_measurement") for issue in audit_scene(scene))


def test_source_bound_fixed_size_contract_is_revalidated_by_audit(reg, tmp_path):
    source = tmp_path / "source.svg";source.write_bytes(b"verified source bytes")
    digest = digest_file(source)
    scene = Scene(reg, 8);scene.template = "arbitrary-template";scene.source_root = tmp_path
    node = scene.shape("viewport", [5, 5, 90, 35]);node["role"] = "source-locked-viewport"
    scene.text("viewport-text", "源图视口", 47.5, 20, owner="viewport")
    node["measurement_contract"] = {"mode": "fixed", "fixed_size": {"purpose": "source-locked-viewport",
        "evidence": {"constraint": "source-artwork-bounds", "source_id": "source.svg", "source_sha256": digest}}}
    scene.finish(100, 40)
    assert not any(issue["code"].startswith("primitive_box_measurement") for issue in audit_scene(scene))
    source.write_bytes(b"changed source bytes")
    assert any(issue["code"] == "primitive_box_measurement_contract" for issue in audit_scene(scene))


def test_scene_self_reported_source_binding_is_not_trusted(reg):
    digest = "a" * 64
    scene = Scene(reg, 8);scene.source_bindings = {"does-not-exist.svg": digest}
    node = scene.shape("viewport", [5, 5, 90, 35]);node["role"] = "source-locked-viewport"
    scene.text("viewport-text", "源图视口", 47.5, 20, owner="viewport")
    node["measurement_contract"] = {"mode": "fixed", "fixed_size": {"purpose": "source-locked-viewport",
        "evidence": {"constraint": "source-artwork-bounds", "source_id": "does-not-exist.svg", "source_sha256": digest}}}
    scene.finish(100, 40)
    assert any(issue["code"] == "primitive_box_measurement_contract" for issue in audit_scene(scene))


@pytest.mark.parametrize("rotation", [90, 270])
def test_rotated_tight_box_uses_transformed_ink_dimensions(reg, rotation):
    probe = Scene(reg, 8)
    text = probe.text("probe", "QUERY", 50, 50, rotation=rotation)
    ink = text["position"]["bbox"]
    width, height = ink[2] - ink[0] + 9, ink[3] - ink[1] + 5.4
    scene = Scene(reg, 8);scene.template = "rotated-business-label"
    node = scene.shape("query", [5, 5, 5 + width, 5 + height]);node["padding_pt"] = [4.5, 2.7]
    node["measurement_contract"] = {"mode": "tight", "expected_wh": [999, 999]}
    scene.text("query-text", "QUERY", 5 + width / 2, 5 + height / 2, rotation=rotation, owner="query")
    scene.finish(120, 120)
    assert not any(issue["code"].startswith("primitive_box_measurement") for issue in audit_scene(scene))


def test_custom_template_business_arrow_still_requires_endpoint_semantics(reg):
    scene = Scene(reg, 8);scene.template = "author-custom-rebuild"
    scene.line("business", [[10, 20], [80, 20]], arrow=True)
    scene.finish(100, 50)
    assert any(issue["code"] == "arrow_endpoint_semantics_missing" for issue in audit_scene(scene))


def test_beautification_claim_is_not_a_fixed_size_escape(reg):
    spec = {
        "width_pt": 100,
        "height_pt": 50,
        "nodes": [{"id": "sensor", "text": "传感器", "rect": [5, 5, 68, 31],
                   "fixed_size": {"purpose": "beautification", "evidence": {"source": "manual", "constraint": "keep"}}}],
    }
    assert any(issue["code"] == "primitive_box_measurement_mismatch" for issue in audit_scene(primitive(spec, reg, 8)))


def test_measured_row_group_uses_ink_width_and_shared_measured_height(reg):
    spec = {
        "width_pt": 120,
        "height_pt": 50,
        "nodes": [
            {"id": "short", "text": "短"},
            {"id": "two_lines", "text": "第一行\n第二行"},
        ],
        "measured_groups": [
            {"id": "row", "axis": "row", "origin": [5, 5], "gap_pt": 9, "nodes": ["short", "two_lines"]}
        ],
    }
    scene = primitive(spec, reg, 8)
    short, two_lines = scene.nodes
    assert short["rect"][3] - short["rect"][1] == pytest.approx(two_lines["rect"][3] - two_lines["rect"][1])
    short_text = next(t for t in scene.texts if t["owner"] == "short")
    assert short["rect"][2] - short["rect"][0] == pytest.approx(short_text["measurement"]["width"] + 9)
    assert not audit_scene(scene)


def test_independent_opposite_collinear_connections_are_rejected(reg):
    scene = Scene(reg, 8).finish(120, 80)
    scene.line("power", [[20, 40], [80, 40]], arrow=True)
    scene.line("data", [[95, 40], [55, 40]], arrow=True)
    issues = audit_scene(scene)
    overlap = [issue for issue in issues if issue["code"] == "path_collinear_overlap"]
    assert overlap == [{"code": "path_collinear_overlap", "ids": ["power", "data"], "overlap_pt": pytest.approx(25)}]


def test_explicit_shared_net_allows_collinear_bus_segments(reg):
    scene = Scene(reg, 8).finish(120, 80)
    scene.line("bus", [[20, 40], [90, 40]], shared_net="control-bus", semantic_role="bus")
    scene.line("branch", [[50, 40], [80, 40]], shared_net="control-bus", semantic_role="branch")
    assert not any(issue["code"] == "path_collinear_overlap" for issue in audit_scene(scene))


def test_shared_net_does_not_hide_overlapping_arrow_edges(reg):
    scene = Scene(reg, 8).finish(120, 80)
    scene.line("forward", [[20, 40], [90, 40]], arrow=True, shared_net="control-bus", semantic_role="branch")
    scene.line("reverse", [[90, 40], [20, 40]], arrow=True, shared_net="control-bus", semantic_role="branch")
    assert any(issue["code"] == "path_collinear_overlap" for issue in audit_scene(scene))


def test_point_crossing_is_not_collinear_overlap(reg):
    scene = Scene(reg, 8).finish(120, 80)
    scene.line("horizontal", [[20, 40], [90, 40]])
    scene.line("vertical", [[55, 15], [55, 65]])
    assert not any(issue["code"] == "path_collinear_overlap" for issue in audit_scene(scene))


def test_container_owned_title_requires_normal_text_padding(reg):
    scene = Scene(reg, 8);scene.template = "primitive-scene"
    scene.shape("platform", [5, 5, 105, 55], container=True)
    scene.text("platform-title", "平台层", 5.4, 15, align="left", owner="platform", role="container-title")
    scene.finish(120, 70)
    assert any(issue["code"] == "container_title_padding" for issue in audit_scene(scene))
