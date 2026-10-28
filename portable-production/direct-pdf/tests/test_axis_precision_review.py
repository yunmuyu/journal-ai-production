import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.render import render_one
from journal_pdf.tick_precision import precision_notice


@pytest.mark.parametrize(('values','flagged'),[
    (['0','0.2','0.4','0.6','0.8','1','1.2'],True),
    (['0.0','0.2','0.4','0.6','0.8','1.0','1.2'],False),
    (['1','2','3','4'],False),
    (['0.1','0.2','1 MHz'],False),
    (['10^1','10^2','10^3'],False),
    (['-0.5','0','0.50'],True),
])
def test_axis_precision_notice_requires_identifiable_numeric_axis(values,flagged):
    assert (precision_notice('y',values) is not None)==flagged


def render_ticks(reg,tmp_path,values,groups='auto',size=8):
    texts=[{'id':f'y{i}','text':value,'x':20,'y':15+12*i,'role':'axis-tick'} for i,value in enumerate(values)]
    spec={'id':'precision','author':'Synthetic','synthetic':True,'kind':'scene','width_pt':80,'height_pt':110,
          'policy':{'design_font_size_pt':size,'export_crop_padding_pt':4},'texts':texts}
    if groups=='auto':spec['axis_tick_groups']=[{'id':'y','text_ids':[t['id'] for t in texts]}]
    elif groups is not None:spec['axis_tick_groups']=groups
    source=tmp_path/'source';source.mkdir(exist_ok=True);assets=Assets()
    try:return render_one(spec,reg,assets,source,tmp_path/'out')
    finally:assets.close()


def test_real_pdf_report_flags_mixed_tick_precision(reg,tmp_path):
    result=render_ticks(reg,tmp_path,['0','0.2','0.4','1'])
    note=next(w for w in result['warnings'] if w['code']=='axis_decimal_precision_mismatch')
    assert note['axis']=='y' and note['labels']==['0','0.2','0.4','1']
    assert result['pdf_audit']['text_multiset_exact']
    assert result['status']=='candidate-editorial-review' and not result['overall_checks_passed']


def test_real_pdf_report_warns_when_axis_group_is_missing(reg,tmp_path):
    result=render_ticks(reg,tmp_path,['0','0.2','0.4','1'],groups=None)
    assert any(w['code']=='axis_tick_group_missing' for w in result['warnings'])


def test_real_pdf_report_flags_base_font_below_eight(reg,tmp_path):
    result=render_ticks(reg,tmp_path,['0.0','0.2','0.4','1.0'],size=6)
    assert any(w['code']=='base_font_below_8_requires_review' for w in result['warnings'])
    assert result['status']=='candidate-editorial-review' and not result['overall_checks_passed']
    assert not any(w['code']=='axis_decimal_precision_mismatch' for w in result['warnings'])


def test_invalid_tick_group_is_not_silently_accepted(reg,tmp_path):
    with pytest.raises(FigureError) as error:
        render_ticks(reg,tmp_path,['0','0.2','0.4'],groups=[{'id':'y','text_ids':['y0','missing']}])
    assert error.value.code=='axis_tick_groups_invalid'


def test_local_reduction_flags_non_script_but_not_true_superscript():
    from types import SimpleNamespace
    from journal_pdf.font_review import font_size_notices
    scene=SimpleNamespace(size=8,texts=[
        {'id':'ordinary','content':[{'text':'12','scale':0.6}]},
        {'id':'power','content':[{'text':'10'},{'text':'-3','scale':0.7,'baseline_shift_pt':-3.2}]},
    ])
    notices=font_size_notices(scene)
    assert [w['id'] for w in notices]==['ordinary']
    assert notices[0]['code']=='reduced_nonscript_text_requires_review'


def test_chart_groups_axes_before_precision_review(reg,tmp_path):
    from PIL import Image
    from journal_pdf.charts import chart
    source=tmp_path/'chart.png';Image.new('RGB',(500,400),'white').save(source)
    spec={'source_kind':'raster','source':source.name,'plot_clip':[0,0,500,400],
          'plot_width_pt':180,'x_title':'x','y_title':'y','series':[],
          'x_ticks':[{'text':str(i),'position':i*200} for i in range(3)],
          'y_ticks':[{'text':v,'position':i*100} for i,v in enumerate(['0','0.2','0.4','1'])]}
    assets=Assets()
    try:
        scene=chart(spec,reg,8,assets,tmp_path)
        assert [n['axis'] for n in scene.notes if n['code']=='axis_decimal_precision_mismatch']==['y']
    finally:
        assets.close()
