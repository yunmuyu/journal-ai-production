import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from production_rules.load import load_rules
from production_rules.margin import margin_tolerance_pt
from production_rules.names import FigureNameError, figure_stem, validate_figure_stem
from production_rules.routing import route_dense_chart, route_source
from production_rules.width import column_tiers
from journal_pdf.editorial import EXPORT_PAD, STROKE, COMPACT_GAP, PAD_X, PAD_Y
from journal_pdf.scene import Scene


def test_migrated_numbers_match_the_code_constants():
    rules = load_rules()['normative']
    assert rules['scale_floor_pt'] == 6
    assert rules['body_pt'] == 8
    assert rules['margin_pt'] == 0.25
    assert EXPORT_PAD == 0.25
    assert STROKE == 0.5
    assert COMPACT_GAP == 3
    assert (PAD_X, PAD_Y) == (4.5, 2.7)
    assert rules['single_column_mm'] == 80
    assert rules['double_column_mm'] == 160


def test_font_roles_match_the_existing_statement():
    roles = load_rules()['normative']['font_role_labels']
    assert roles == {
        'cn': '宋体 Regular',
        'punct': '汉仪中宋简 regular',
        'latin': 'Times New Roman Regular',
        'latin_italic': 'Times New Roman Italic',
    }
    assert load_rules()['normative']['heading_font'] == 'none'
    assert load_rules()['normative']['emphasis_font'] == 'none'


def test_quarter_point_tolerance_rejects_a_missing_margin():
    slack = margin_tolerance_pt()
    margin = load_rules()['normative']['margin_pt']
    assert slack < margin
    assert abs(0 - margin) > slack


def test_names_accept_decimal_subfigures_and_reject_letters():
    assert figure_stem('张三', '1.2') == '张三-图1.2'
    validate_figure_stem('张三-图1')
    for bad in ('张三-图1.A', '张三-图1a', '张三-图1A', '张三-图A', '张三-图18（a）', '张三-图2 3'):
        try:
            validate_figure_stem(bad)
        except FigureNameError:
            continue
        raise AssertionError(bad)


def test_explicit_single_does_not_include_the_double_tier():
    assert column_tiers('single', {'policy': {}}, 'scene') == [80]
    assert column_tiers('auto', {'policy': {}}, 'scene') == [80, 160]
    assert column_tiers('single', {'policy': {'simple_chart': True}}, 'chart') == [60, 80]
    assert column_tiers('auto', {'policy': {'simple_chart': True}}, 'chart') == [60, 80, 160]


def test_screenshot_routing_does_not_redraw_web_pages():
    assert route_source('页面.png', '网页截图')['route'] == 'raster-only'
    assert route_source('map.png', 'citespace')['redraw'] is False
    chart = route_source('仅此一张.png', 'standalone-chart')
    assert chart['route'] == 'screenshot-chart' and chart['redraw'] is True
    assert route_source('photo.jpg')['redraw'] is False
    assert route_dense_chart(10, 2, approved=False)['route'] == 'vector-chart'
    assert route_dense_chart(800, 2, approved=False)['route'] == 'needs-owner-approval'
    assert route_dense_chart(800, 2, approved=True)['route'] == 'bitmap-plot-vector-text'
    script = load_rules()['normative']
    assert script['scientific_exponent_scale'] == 0.7
    assert script['scientific_baseline_shift_ratio'] == -0.4
    assert script['summary_bus_edge_mm'] == 2
    assert script['summary_bus_trunk_mm'] == 2
    assert script['direct_connector_mm'] == 3
    assert script['short_connector_mm'] == 2
    assert script['graph_branch_bus_leg_pt'] == 6


def test_actor_and_frame_are_scene_primitives():
    scene = Scene(registry=None, size=8)
    scene.shape('person', [0, 0, 20, 40], 'actor')
    scene.shape('group', [0, 0, 80, 60], 'frame')
    assert scene.nodes[0]['kind'] == 'actor'
    assert scene.nodes[1]['kind'] == 'frame' and scene.nodes[1]['container'] is True
