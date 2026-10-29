import hashlib

import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import compile_figure


def _spec(tmp_path):
    source = tmp_path/'series.svg'
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="100pt" height="80pt" viewBox="0 0 100 80">'
        '<g id="series"><path d="M 40 40 L 60 50" style="fill:none;stroke:#003366"/>'
        '<defs><path id="dot" d="M-2 -2 L2 -2 L2 2 L-2 2 Z"/></defs>'
        '<use xlink:href="#dot" x="40" y="40" style="fill:#003366"/>'
        '<use xlink:href="#dot" x="60" y="50" style="fill:#003366"/></g>'
        '<g id="value"><text x="40" y="34" style="fill:#003366">0.108</text></g></svg>',
        encoding='utf-8',
    )
    return {'version': 1, 'id': 'binding', 'author': 'synthetic', 'kind': 'scene', 'synthetic': True,
            'width_pt': 110, 'height_pt': 90, 'nodes': [], 'paths': [],
            'sources': [{'path': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'role': 'source'}],
            'assets': [{'id': 'plot', 'path': source.name, 'source_kind': 'svg', 'source_svg_group': True,
                        'group_id': 'series', 'clip': [0,0,100,80], 'target': [5,5,105,85]}],
            'texts': [{'id':'value', 'text':'0.108', 'x':45, 'y':35}],
            'data_label_bindings': [{'text_id':'value', 'asset_id':'plot', 'source_label_id':'value',
                                     'marker_index':0}],
            'policy': {'column':'single', 'design_font_size_pt':8}}


def test_source_series_label_is_bound_to_original_marker(tmp_path, reg):
    spec = _spec(tmp_path)
    assets = Assets()
    try:
        scene = compile_figure(spec, reg, assets, tmp_path)
        binding = scene.layout_evidence['data_label_bindings'][0]
        assert binding['source_group'] == 'series'
        assert binding['marker_index'] == 0
        assert binding['marker_target_pt'] == [45,45]
    finally:
        assets.close()


@pytest.mark.parametrize('change', ['wrong_value', 'wrong_marker', 'far', 'outside', 'wrong_source_label', 'duplicate', 'wrong_color'])
def test_rejects_misbound_or_unclear_data_labels(tmp_path, reg, change):
    spec = _spec(tmp_path)
    if change == 'wrong_value': spec['texts'][0]['text'] = '0.000'
    elif change == 'wrong_marker': spec['data_label_bindings'][0]['marker_index'] = 1
    elif change == 'far': spec['texts'][0].update(x=45, y=10)
    elif change == 'outside': spec['texts'][0].update(x=45, y=87)
    elif change == 'wrong_source_label': spec['data_label_bindings'][0]['source_label_id'] = 'missing'
    elif change == 'wrong_color':
        source = tmp_path/'series.svg'
        source.write_text(source.read_text(encoding='utf-8').replace('fill:#003366">0.108', 'fill:#ef6c00">0.108'), encoding='utf-8')
        spec['sources'][0]['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    else: spec['data_label_bindings'].append(dict(spec['data_label_bindings'][0]))
    assets = Assets()
    try:
        with pytest.raises(FigureError):
            compile_figure(spec, reg, assets, tmp_path)
    finally:
        assets.close()


@pytest.mark.parametrize('change', ['same_x', 'far_source_label', 'css_color_override'])
def test_binding_rejects_ambiguous_or_overridden_source(tmp_path, reg, change):
    spec = _spec(tmp_path)
    source = tmp_path / 'series.svg'
    svg = source.read_text(encoding='utf-8')
    if change == 'same_x':
        svg = svg.replace('x="60" y="50"', 'x="40" y="50"')
    elif change == 'far_source_label':
        svg = svg.replace('x="40" y="34"', 'x="40" y="5"')
    else:
        svg = svg.replace('<g id="series">', '<style>text { fill: #f00 }</style><g id="series">')
    source.write_text(svg, encoding='utf-8')
    spec['sources'][0]['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    assets = Assets()
    try:
        with pytest.raises(FigureError) as error:
            compile_figure(spec, reg, assets, tmp_path)
        assert error.value.code == 'data_label_binding_invalid'
    finally:
        assets.close()


@pytest.mark.parametrize('endpoint,ok', [([45,45],True), ([65,55],False)])
def test_moved_label_leader_must_end_on_the_declared_source_marker(tmp_path,reg,endpoint,ok):
    spec=_spec(tmp_path)
    spec['texts'][0].update(x=45,y=15)
    spec['paths']=[{'id':'leader','points':[[45,20],endpoint],'semantic_role':'data-annotation'}]
    spec['data_label_bindings'][0]['leader_path_id']='leader'
    assets=Assets()
    try:
        if ok:
            scene=compile_figure(spec,reg,assets,tmp_path)
            assert scene.layout_evidence['data_label_bindings'][0]['leader_path_id']=='leader'
        else:
            with pytest.raises(FigureError):compile_figure(spec,reg,assets,tmp_path)
    finally:assets.close()
