import hashlib

import pymupdf as fitz
import pytest
from lxml import etree as ET

from journal_pdf.chart_annotations import source_annotations
from journal_pdf.common import FigureError
from journal_pdf.assets import Assets
from journal_pdf.render import compile_figure


def fixture(tmp_path):
    pdf = tmp_path / 'source.pdf'
    with fitz.open() as document:
        page = document.new_page(width=100, height=100)
        page.draw_circle((50, 50), 2, color=(0,), fill=(0,))
        page.insert_text((45, 40), '18')
        document.save(pdf)
    svg = tmp_path / 'source.svg'
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g id="axes_1"><g id="body"><path d="M10 90 L90 10" stroke="black" fill="none"/></g><g id="text_0"><text>18</text></g></g></svg>', encoding='utf-8')
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    return {'source_kind': 'svg', 'source': svg.name, 'sources': [{'path': pdf.name, 'sha256': sha}],
            'source_annotations': [{'id': 'value-18', 'source_pdf': pdf.name, 'source_pdf_sha256': sha,
                                    'source_span_index': 0, 'source_marker_index': 0,
                                    'source_text_group': 'text_0', 'placement': 'lower-right'}]}


def test_number_and_anchor_come_from_actual_original_text_and_marker(tmp_path):
    spec = fixture(tmp_path)
    values = source_annotations(spec, tmp_path)
    assert values[0].text == '18'
    assert values[0].marker_right == pytest.approx(52)
    assert values[0].marker_bottom == pytest.approx(52)
    root = ET.fromstring((tmp_path / 'source.svg').read_bytes())
    root.find('.//{*}text').text = '19'
    (tmp_path / 'source.svg').write_bytes(ET.tostring(root))
    with pytest.raises(FigureError):
        source_annotations(spec, tmp_path)


def test_unbound_parent_pdf_cannot_supply_annotation_positions(tmp_path):
    spec = fixture(tmp_path)
    spec['sources'] = []
    with pytest.raises(FigureError):
        source_annotations(spec, tmp_path)


def test_chart_places_source_value_below_and_right_of_original_marker(reg, tmp_path):
    spec = fixture(tmp_path)
    sha = hashlib.sha256((tmp_path / 'source.svg').read_bytes()).hexdigest()
    spec['sources'].append({'path': 'source.svg', 'sha256': sha})
    spec.update(kind='chart', axes_id='axes_1', plot_clip=[0, 0, 100, 100],
                axis_frame_source=[0, 0, 100, 100], plot_width_pt=100,
                series=[], series_source_groups=['body'], legend_source_id=None,
                legend_review={'present': False, 'source_sha256': sha, 'reason': 'No legend'},
                tick_length_source_units=0, x_title='Time(s)', y_title='Value(V)',
                x_ticks=[{'text': '0', 'position': 0}, {'text': '1', 'position': 100}],
                y_ticks=[{'text': '0', 'position': 100}, {'text': '1', 'position': 0}])
    assets = Assets()
    try:
        scene = compile_figure(spec, reg, assets, tmp_path)
        value = next(t for t in scene.texts if t['id'] == 'value-18')
        plot = next(a for a in scene.assets if a['id'] == 'plot')
        assert value['position']['bbox'][0] >= plot['rect'][0] + 55
        assert value['position']['bbox'][1] >= plot['rect'][1] + 55
        assert value['measurement']['text'] == '18'
        assert plot['asset'].audit['geometry_before'] == plot['asset'].audit['geometry_after']
    finally:
        assets.close()
