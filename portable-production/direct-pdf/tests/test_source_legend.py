import hashlib

import fitz
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import render_one


def spec_for(tmp_path):
    source=tmp_path/'source';source.mkdir()
    svg=source/'chart.svg'
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="100pt" height="80pt" viewBox="0 0 100 80">'
        '<g id="series"><path d="M 10 40 L 80 50" style="fill:none;stroke:#444;stroke-width:1;stroke-dasharray:6,3"/>'
        '<defs><path id="marker" d="M -2 -2 L 2 -2 L 2 2 L -2 2 Z" style="fill:#888;stroke:#333;stroke-width:.5"/></defs>'
        '<use xlink:href="#marker" x="10" y="40"/><use xlink:href="#marker" x="80" y="50"/></g></svg>',encoding='utf-8')
    spec={'version':1,'id':'legend','author':'synthetic','kind':'scene','synthetic':True,'width_pt':130,'height_pt':100,
          'policy':{'column':'single'},'sources':[{'path':'chart.svg','sha256':hashlib.sha256(svg.read_bytes()).hexdigest(),'role':'source'}],
          'assets':[{'id':'plot','path':'chart.svg','source_kind':'svg','source_svg_group':True,'group_id':'series',
                     'clip':[0,0,100,80],'target':[0,0,100,80]}],
          'nodes':[{'id':'key','shape':'rectangle','rect':[107,18,111,22],'width':.5,'gray':51/255,'fill':136/255}],
          'paths':[{'id':'key-line','points':[[100,20],[125,20]],'gray':68/255,'width':1,'dash':[6,3],
                    'semantic_role':'data-annotation'}],
          'source_legend_bindings':[{'asset_id':'plot','path_id':'key-line','marker_node_id':'key'}]}
    return source,spec


def test_source_legend_style_survives_real_pdf_audit(tmp_path,reg):
    source,spec=spec_for(tmp_path);assets=Assets()
    try:result=render_one(spec,reg,assets,source,tmp_path/'out')
    finally:assets.close()
    with fitz.open(tmp_path/'out'/result['output_pdf']) as doc:
        assert any(x['dashes'].startswith('[ 6 3 ]') for x in doc[0].get_drawings())


@pytest.mark.parametrize('change',['dash','line_gray','marker_gray','marker_shape'])
def test_mismatched_source_legend_is_rejected(tmp_path,reg,change):
    source,spec=spec_for(tmp_path)
    if change=='dash':spec['paths'][0]['dash']=[3,3]
    elif change=='line_gray':spec['paths'][0]['gray']=0
    elif change=='marker_gray':spec['nodes'][0]['fill']=0
    else:spec['nodes'][0]['shape']='ellipse'
    assets=Assets()
    try:
        with pytest.raises(FigureError,match='图例'):render_one(spec,reg,assets,source,tmp_path/'out')
    finally:assets.close()
