"""Regression cases use synthetic assets, not private author figures."""
import io
from pathlib import Path
import pytest
from PIL import Image,ImageDraw,ImageCms
from journal_pdf.assets import Assets
from journal_pdf.charts import tick_content
from journal_pdf.common import FigureError
from journal_pdf.editorial import display_content
from journal_pdf.render import compile_figure

@pytest.mark.parametrize('number,suffix,want',[
 ('1.5','G','1.5G'),('1000.0000','G','1 000.000 0G'),('-1200','k','-1 200k')])
def test_numeric_prefix_and_literal_suffix(number,suffix,want,reg):
 content=tick_content({'text':number+suffix,'number':number,'suffix':suffix})
 assert reg.measure(content,8)['text']==want

def test_suffix_must_not_change_source():
 with pytest.raises(FigureError) as e:tick_content({'text':'1.5G','number':'1.5','suffix':'GHz'})
 assert e.value.code=='tick_component_mismatch'

def test_suffix_needs_explicit_identity():
 with pytest.raises(FigureError):tick_content({'text':'1.5G'})

def test_gray_raster_drops_incompatible_rgb_icc_without_pixel_change(tmp_path):
 p=tmp_path/'rgb.png';im=Image.new('RGB',(30,20),(121,121,121))
 icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
 im.save(p,icc_profile=icc)
 a=Assets()
 try:
  asset=a.raster(p,[0,0,30,20]);work=Image.open(io.BytesIO(asset.data))
  assert work.mode=='L' and not work.info.get('icc_profile')
  assert set(work.getdata())=={121}
  assert asset.audit['rgb_icc_removed_for_gray']
 finally:a.close()

def _synthetic(tmp_path):
 im=Image.new('RGB',(500,400),'white');d=ImageDraw.Draw(im)
 d.line([(50,30),(50,330),(450,330)],fill='black',width=2)
 d.line([(260,60),(300,60)],fill='black',width=2)
 d.line([(260,90),(300,90)],fill='black',width=1)
 d.rectangle((278,87,282,93),fill='black')
 im.save(tmp_path/'s.png')
 return {'kind':'chart','source_kind':'raster','source':'s.png','plot_clip':[48,28,454,334],
 'axis_frame_source':[50,30,450,330],'plot_width_pt':175,'tick_length_source_units':0,
 'masks':[[250,50,310,100]],'approved_empty_regions':[[240,40,440,160]],
 'legend_safe_region':[240,40,445,160],'legend_placement':'source-region','legend_frame':False,
 'x_title':'Freq(Hz)','y_title':'S21(dB)',
 'x_ticks':[{'text':'1.5G','number':'1.5','suffix':'G','position':50},{'text':'2.0G','number':'2.0','suffix':'G','position':300}],
 'y_ticks':[{'text':'40.0','position':30},{'text':'37.0','position':330}],
 'series':[{'id':'s','label':'simulate','swatch_clip':[260,59,301,62]},{'id':'m','label':'measure','swatch_clip':[260,87,301,94]}],
 'policy':{'column':'single','design_font_size_pt':8}}

def test_corner_avoidance_keeps_8pt_and_source_x_anchors(reg,tmp_path):
 s=_synthetic(tmp_path);a=Assets()
 try:
  scene=compile_figure(s,reg,a,tmp_path)
  assert scene.size==8 and scene.layout_evidence['corner_tick_adjustment_pt']>0
  assert scene.layout_evidence['layout_build_count']==1
  assert not scene.layout_evidence['pdf_font_ladder_renders']
  assert not scene.nodes # no invented legend frame
  assert all(t['owner'] is None for t in scene.texts if t['role']=='legend-label')
  plot=scene.assets[0]['rect'];tick=next(t for t in scene.texts if t['id']=='xtick0')
  assert tick['x']==pytest.approx(plot[0]+(50-48)*175/406)
 finally:a.close()

def test_legacy_size_list_does_not_run_multiple_layouts(reg,tmp_path,monkeypatch):
 import journal_pdf.render as module
 spec=_synthetic(tmp_path);spec['policy']={'column':'single','font_sizes':[8,7,6]}
 original=module.chart;calls=[]
 def wrapped(spec,reg,size,assets,root):
  calls.append(size);return original(spec,reg,size,assets,root)
 monkeypatch.setattr(module,'chart',wrapped);a=Assets()
 try:
  compile_figure(spec,reg,a,tmp_path);assert calls==[8]
 finally:a.close()
