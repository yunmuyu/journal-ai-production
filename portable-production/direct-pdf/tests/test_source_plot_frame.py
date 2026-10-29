import hashlib

import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import compile_figure
from test_data_label_bindings import _spec


def chart(tmp_path):
    spec = _spec(tmp_path)
    source = tmp_path / 'series.svg'
    svg = source.read_text(encoding='utf-8').replace('</svg>',
        '<g id="left"><path d="M 10 70 L 10 10"/></g>'
        '<g id="right"><path d="M 90 70 L 90 10"/></g>'
        '<g id="bottom"><path d="M 10 70 L 90 70"/></g>'
        '<g id="top"><path d="M 10 10 L 90 10"/></g></svg>')
    source.write_text(svg, encoding='utf-8')
    spec['sources'][0]['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    spec['paths'] = [{'id':'frame','points':[[15,15],[95,15],[95,75],[15,75],[15,15]],'semantic_role':'data-annotation'}]
    spec['source_plot_frame'] = {'asset_id':'plot','frame_path_id':'frame','spine_ids':['left','right','bottom','top']}
    return spec


def test_frame_bound_to_actual_source_axes(tmp_path, reg):
    spec=chart(tmp_path);assets=Assets()
    try:
        scene=compile_figure(spec,reg,assets,tmp_path)
        assert scene.layout_evidence['source_plot_frame']['verified'] is True
        assert scene.layout_evidence['source_plot_frame']['target_rect'] == [15,15,95,75]
    finally:assets.close()


@pytest.mark.parametrize('change',['oversized_bottom','crossed_frame','nonuniform','missing_spine'])
def test_incorrect_or_unproven_frame_is_rejected(tmp_path,reg,change):
    spec=chart(tmp_path)
    if change=='oversized_bottom':
        spec['paths'][0]['points']=[[15,15],[95,15],[95,80],[15,80],[15,15]]
    elif change=='crossed_frame':
        spec['paths'][0]['points']=[[15,15],[95,75],[95,15],[15,75],[15,15]]
    elif change=='nonuniform':
        spec['assets'][0]['target']=[5,5,105,75]
    else:
        spec['source_plot_frame']['spine_ids'][-1]='unknown'
    assets=Assets()
    try:
        with pytest.raises(FigureError):compile_figure(spec,reg,assets,tmp_path)
    finally:assets.close()
