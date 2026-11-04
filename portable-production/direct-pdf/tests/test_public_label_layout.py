import pytest
import pymupdf as fitz

from journal_pdf.common import FigureError
from journal_pdf.fonts import draw_text
from journal_pdf.layouts import primitive
from journal_pdf.scene import Scene, audit_scene


def test_width_wrapping_preserves_words_and_source_at_generation(reg):
    # Given a real measured limit which fits one technical label.
    text = '数据采集模块VR系统'
    limit = max(reg.measure(v, 8)['width'] for v in ('数据采集模块', 'VR系统')) + .1
    scene = Scene(reg)
    # When the existing box generator receives a width constraint.
    node = scene.box('label', text, 10, 10, wrap_width_pt=limit)
    scene.finish(node['rect'][2] + 10, node['rect'][3] + 10)
    # Then no word, Latin token, or source character is lost.
    label = scene.texts[0]
    assert label['source_content'] == text
    assert label['content'].replace('\n', '') == text
    assert 'VR' in label['content']
    assert all(reg.measure(line, 8)['width'] <= limit for line in label['content'].splitlines())
    assert not audit_scene(scene)


def test_unbreakable_token_cannot_silently_overflow_or_shrink(reg):
    # Given a Latin token wider than the requested line.
    scene = Scene(reg)
    # When width wrapping is requested, then report the exact blocked token.
    with pytest.raises(FigureError) as error:
        scene.box('label', 'RL116B', 10, 10, wrap_width_pt=3)
    assert error.value.code == 'label_word_too_wide'
    assert error.value.details['token'] == 'RL116B'


def test_automatic_ellipse_contains_measured_ink(reg):
    # Given long text which fails inside an ordinary tight rectangle-sized ellipse.
    scene = Scene(reg)
    # When ellipse dimensions are omitted, size its curved boundary before drawing.
    node = scene.box('oval', '核心上下文领域模型', 10, 10, kind='ellipse')
    scene.finish(node['rect'][2] + 10, node['rect'][3] + 10)
    # Then all ink corners remain inside without reducing 8 pt.
    assert not audit_scene(scene)
    assert scene.texts[0]['measurement']['size'] == 8


def test_vertical_group_measures_and_draws_same_text(reg, tmp_path):
    # Given a public measured row of two native vertical labels.
    spec = {'nodes': [{'id': 'a', 'text': '基础信息配置', 'vertical_text': True},
                      {'id': 'b', 'text': '系统监控', 'vertical_text': True}],
            'measured_groups': [{'id': 'row', 'nodes': ['a', 'b'], 'axis': 'row',
                                 'origin': [10, 10], 'equal_width': True}],
            'width_pt': 100, 'height_pt': 150}
    # When the actual primitive generator lays out and renders it.
    scene = primitive(spec, reg, 8)
    reg.prepare_document_fonts(scene.texts)
    output = tmp_path / 'vertical.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=150)
        for label in scene.texts:
            draw_text(page, reg, label)
        doc.save(output)
    # Then tight measurements, ownership, and extracted glyphs remain intact.
    assert not audit_scene(scene)
    assert all(t['owner'] in {'a', 'b'} for t in scene.texts)
    assert all(g.get('rotation', 0) == 0 for t in scene.texts for g in t['measurement']['glyphs'])
    with fitz.open(output) as doc:
        text = ''.join(doc[0].get_text().split())
        assert all(ch in text for ch in '基础信息配置系统监控')


def test_primitive_width_wrap_and_row_reflow_use_same_measurement(reg):
    # Given constraints on text but no author-written rectangles.
    spec = {'nodes': [{'id': 'a', 'text': '数据采集模块', 'wrap_width_pt': 32},
                      {'id': 'b', 'text': '系统监控'}],
            'measured_groups': [{'id': 'row', 'nodes': ['a', 'b'], 'axis': 'row', 'origin': [10, 10]}],
            'width_pt': 150, 'height_pt': 100}
    # When the shared generation entry sizes and places the row.
    scene = primitive(spec, reg, 8)
    # Then it wraps before measurement and preserves the public 3 pt clear gap.
    assert '\n' in scene.texts[0]['content']
    assert scene.nodes[1]['rect'][0] - scene.nodes[0]['rect'][2] == pytest.approx(3.5)
    assert not audit_scene(scene)


def test_fixed_node_and_free_label_use_width_rule_consistently(reg):
    # Given fixed and free labels sharing a reliable width limit.
    from journal_pdf.label_layout import layout_label
    label = layout_label(reg, '数据采集模块', 8, wrap_width_pt=32)
    ink = reg.measure(label, 8)
    spec = {'nodes': [{'id': 'a', 'text': '数据采集模块', 'wrap_width_pt': 32,
                       'rect': [10, 10, 19 + ink['width'], 15.4 + ink['height']]}],
            'texts': [{'id': 'free', 'text': '数据采集模块', 'x': 85, 'y': 40,
                       'wrap_width_pt': 32}], 'width_pt': 150, 'height_pt': 100}
    # When both paths are compiled.
    scene = primitive(spec, reg, 8)
    # Then both receive identical measured wrapping, not merely matching checks.
    assert scene.texts[0]['content'] == scene.texts[1]['content'] == label
    assert not audit_scene(scene)


def test_conflicting_wrap_settings_are_rejected(reg):
    # Given two incompatible wrapping policies, when used together, then stop.
    with pytest.raises(FigureError) as error:
        Scene(reg).box('a', '系统监控', 10, 10, wrap_chars=3, wrap_width_pt=30)
    assert error.value.code == 'label_wrap_conflict'


def test_width_wrapping_preserves_newlines_and_whitespace(reg):
    # Given explicit lines and spaces, when width-wrapped, then preserve all text.
    from journal_pdf.label_layout import layout_label
    source = '系统 VR\n\n监控 模块'
    value = layout_label(reg, source, 8, wrap_width_pt=60, role='literal')
    assert value == source
