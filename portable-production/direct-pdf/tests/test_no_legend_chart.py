import hashlib
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import compile_figure
from test_v012_new_raster import _synthetic


def no_legend_spec(tmp_path):
    spec=_synthetic(tmp_path)
    spec['series']=[]
    spec['masks']=[];spec['approved_empty_regions']=[]
    spec['legend_review']={'present':False,'source_sha256':hashlib.sha256((tmp_path/'s.png').read_bytes()).hexdigest(),'reason':'原图无图例，保留完整绘图区'}
    return spec


def test_no_legend_chart_has_no_invented_legend_or_masks(reg,tmp_path):
    spec=no_legend_spec(tmp_path);a=Assets()
    try:
        scene=compile_figure(spec,reg,a,tmp_path)
        assert not [t for t in scene.texts if t['role']=='legend-label']
        assert scene.layout_evidence['legend_review']==spec['legend_review']
        assert scene.assets[0]['asset'].audit['protected_pixels_unchanged_before_color_conversion'] is True
    finally:a.close()


@pytest.mark.parametrize('change', ['missing','wrong_source','contradiction'])
def test_absence_requires_source_bound_explicit_evidence(reg,tmp_path,change):
    spec=no_legend_spec(tmp_path)
    if change=='missing':spec.pop('legend_review')
    if change=='wrong_source':spec['legend_review']['source_sha256']='0'*64
    if change=='contradiction':spec['legend_review']['present']=True
    a=Assets()
    try:
        with pytest.raises(FigureError):compile_figure(spec,reg,a,tmp_path)
    finally:a.close()

def test_agent_no_legend_requires_explicit_review_and_no_mask():
    from journal_pdf.agent_spec import compile_reply_figure
    source={'id':'s','snapshot':'x.png','sha256':'a'*64}
    page={'id':'p','kind':'raster','geometry':{'axes':[{'id':'axis','frame':[0,0,200,200],'plot_clip':[0,0,200,200],
        'x_ticks':[{'id':'x','position':0,'label_candidate':True}],
        'y_ticks':[{'id':'y','position':100,'label_candidate':True}]}],'legend_rows':[]}}
    rep={'id':'fig','kind':'raster-chart','review':{'source_checked':True,'labels_checked':True,'inward_ticks_confirmed':True},
         'axis_ref':'axis','x_ticks':[{'ref':'x','text':'1'}],'y_ticks':[{'ref':'y','text':'2'}],
         'x_title':'Time(s)','y_title':'Value(V)','legend_rows':[]}
    with pytest.raises(FigureError):compile_reply_figure(rep,source,page)
    rep['review']['no_legend_reason']='原图无图例'
    spec=compile_reply_figure(rep,source,page)
    assert spec['legend_review']['source_sha256']==source['sha256']
    assert spec['series']==[] and spec['masks']==[]

def test_svg_agent_no_legend_requires_source_review_and_keeps_series():
    from journal_pdf.agent_spec import compile_reply_figure
    source={'id':'s','snapshot':'x.svg','sha256':'a'*64}
    chart={'id':'axes_1','axes_id':'axes_1','x_ticks':[{'text_hint':'1','position':0}],
           'y_ticks':[{'text_hint':'2','position':100}],'titles':{'x':{'text_hint':'Time(s)'},'y':{'text_hint':'Value(V)'}},
           'legend_rows':[],'legend_id':None,'series_groups':['line_1'],'plot_clip':[0,0,200,200],
           'frame':[0,0,200,200],'protected_path_points':[],'tick_length':1}
    page={'id':'p','kind':'svg','chart_candidates':[chart]}
    rep={'id':'fig','kind':'svg-chart','review':{'source_checked':True,'labels_checked':True},
         'chart_ref':'axes_1','accept_source_text_hints':True,'series_pairs':[]}
    with pytest.raises(FigureError):compile_reply_figure(rep,source,page)
    rep['review']['no_legend_reason']='原图无图例'
    spec=compile_reply_figure(rep,source,page)
    assert spec['series_source_groups']==['line_1'] and spec['series']==[]
    assert spec['legend_review']['source_sha256']==source['sha256']

def test_no_legend_svg_keeps_series_geometry(reg,tmp_path):
    import hashlib
    from journal_pdf.assets import Assets
    from journal_pdf.render import compile_figure
    p=tmp_path/'curve.svg'
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="160" viewBox="0 0 200 160"><g id="axes_1"><path d="M20 10 L20 130 L190 130" stroke="black" fill="none"/><g id="line_1"><path d="M20 120 L90 90 L170 35" fill="none" stroke="black"/></g></g></svg>',encoding='utf-8')
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    spec={'kind':'chart','source_kind':'svg','source':'curve.svg','axes_id':'axes_1','legend_source_id':None,
       'plot_clip':[15,5,195,135],'axis_frame_source':[20,10,190,130],'plot_width_pt':150,'tick_length_source_units':0,
       'x_title':'Time(s)','y_title':'Value(V)','x_ticks':[{'text':'1','position':20},{'text':'2','position':180}],
       'y_ticks':[{'text':'0','position':130},{'text':'1','position':10}],'series':[],
       'series_source_groups':['line_1'],'legend_review':{'present':False,'source_sha256':sha,'reason':'无图例'},
       'policy':{'column':'single','design_font_size_pt':8}}
    assets=Assets()
    try:
        scene=compile_figure(spec,reg,assets,tmp_path)
        audit=scene.assets[0]['asset'].audit
        assert audit['geometry_before']==audit['geometry_after'] and audit['series_ids']==['line_1']
        assert not [t for t in scene.texts if t['role']=='legend-label']
    finally:assets.close()
