import hashlib
import fitz
import pytest
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError
from journal_pdf.fonts import position_text
from journal_pdf.render import render_one


@pytest.mark.parametrize('cap',[0,1,2])
@pytest.mark.parametrize('change', ['none','wide','missing'])
def test_source_tick_gap_checked_on_real_pdf(tmp_path,reg,change,cap):
    root=tmp_path/'src';root.mkdir();source=root/'chart.pdf'
    with fitz.open() as d:
        page=d.new_page(width=100,height=80)
        page.draw_line((20,50),(20,53),width=.5,lineCap=cap)
        d.save(source)
    m=reg.measure('10',8);position=position_text(m,20,60,'center',0)
    y=60+(55.5+(.25 if cap else 0)-position['bbox'][1])
    spec={'version':1,'id':'ticks','author':'synthetic','kind':'scene','synthetic':True,
          'width_pt':110,'height_pt':90,'policy':{'column':'single'},'nodes':[],'paths':[],
          'sources':[{'path':'chart.pdf','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'role':'source'}],
          'assets':[{'id':'chart','path':'chart.pdf','source_kind':'pdf','page':0,
                     'clip':[0,0,100,80],'target':[0,0,100,80]}],
          'texts':[{'id':'tick','text':'10','x':20,'y':y}],
          'source_tick_gap_checks':[{'asset_id':'chart','text_id':'tick'}]}
    if change=='wide':spec['texts'][0]['y']+=3
    if change=='missing':spec['texts'][0]['x']+=5
    assets=Assets()
    try:
        if change=='none':
            result=render_one(spec,reg,assets,root,tmp_path/'out')
            assert result['output_pdf']
            measured=result['pdf_audit']['source_tick_gap']['checks'][0]
            assert measured['line_cap']==cap
            assert measured['gap_pt']==pytest.approx(2.5,abs=.02)
        else:
            with pytest.raises(FigureError):render_one(spec,reg,assets,root,tmp_path/'out')
    finally:assets.close()
