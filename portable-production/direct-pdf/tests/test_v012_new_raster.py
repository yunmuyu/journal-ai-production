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


def test_chart_framed_legend_measures_text_rows_and_vertical_padding(reg,tmp_path):
 s=_synthetic(tmp_path);s['legend_frame']=True;a=Assets()
 try:
  scene=compile_figure(s,reg,a,tmp_path)
  frame=next(n for n in scene.nodes if n['id']=='legend-frame')
  labels=sorted((t['position']['bbox'] for t in scene.texts if t['role']=='legend-label'),key=lambda b:b[1])
  assert labels[0][1]-frame['rect'][1]-frame['width']/2==pytest.approx(2.7,abs=.15)
  assert frame['rect'][3]-frame['width']/2-labels[-1][3]==pytest.approx(2.7,abs=.15)
  assert labels[1][1]-labels[0][3]==pytest.approx(3,abs=.15)
 finally:a.close()

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

def test_chart_axis_titles_are_checked_and_unverified_raster_ticks_are_flagged(reg,tmp_path):
 spec=_synthetic(tmp_path);assets=Assets()
 try:
  scene=compile_figure(spec,reg,assets,tmp_path)
  evidence=scene.layout_evidence['axis_label_gap_checks']
  assert {v['title_id'] for v in evidence}=={'xtitle','ytitle'}
  assert all(v['gap_pt']==pytest.approx(3,abs=.15) for v in evidence)
  assert any(v['code']=='axis_tick_source_unverified' for v in scene.notes)
  ticks=[v for v in scene.layout_evidence['annotation_clearance_checks'] if v['kind']=='ticks']
  assert {tuple(v['ids']) for v in ticks}=={('xtick0','xtick1'),('ytick0','ytick1'),('xtick0','ytick0'),('xtick0','ytick1'),('xtick1','ytick0'),('xtick1','ytick1')}
  assert any(v['code']=='legend_marker_alignment_unverified' for v in scene.notes)
 finally:assets.close()

def test_framed_chart_measures_label_before_sizing_legend(reg,tmp_path):
 spec=_synthetic(tmp_path);spec['legend_frame']=True
 assets=Assets()
 try:
  scene=compile_figure(spec,reg,assets,tmp_path)
  frame=next(n for n in scene.nodes if n['id']=='legend-frame')
  labels=[t for t in scene.texts if t['role']=='legend-label']
  assert frame['rect'][2]-frame['width']/2-max(t['position']['bbox'][2] for t in labels)==pytest.approx(4.5)
  assert any(n['code']=='legend_swatch_ink_review' for n in scene.notes)
 finally:assets.close()

def test_dense_x_ticks_reflow_without_losing_labels_or_source_anchors(reg,tmp_path):
 # Given: numeric labels overlap horizontally, but their rotated ink fits.
 spec=_synthetic(tmp_path)
 spec['x_ticks']=[{'text':f'0.{i:02d}','position':50+20*i} for i in range(8)]
 assets=Assets()
 try:
  # When: the ordinary public chart compiler lays out the complete figure.
  scene=compile_figure(spec,reg,assets,tmp_path)
  # Then: every original label and anchor remains, at 8pt, with a clear title.
  ticks=[t for t in scene.texts if t['id'].startswith('xtick')]
  assert len(ticks)==len(spec['x_ticks'])
  assert [t['source_content'] for t in ticks]==[t['text'] for t in spec['x_ticks']]
  assert {t['position']['rotation'] for t in ticks}=={90}
  assert scene.size==8
  plot=scene.assets[0]['rect']
  assert [t['x'] for t in ticks]==pytest.approx([plot[0]+(v['position']-48)*175/406 for v in spec['x_ticks']])
  title=next(t for t in scene.texts if t['id']=='xtitle')
  assert title['position']['bbox'][1]>max(t['position']['bbox'][3] for t in ticks)
 finally:assets.close()


def test_x_ticks_too_dense_even_when_rotated_remain_blocked(reg,tmp_path):
 # Given: even 90-degree labels cannot fit between these original anchors.
 spec=_synthetic(tmp_path)
 spec['x_ticks']=[{'text':f'0.{i:02d}','position':50+2*i} for i in range(8)]
 assets=Assets()
 try:
  # When / Then: the collision gate still refuses the layout.
  with pytest.raises(FigureError) as error:compile_figure(spec,reg,assets,tmp_path)
  assert error.value.code=='no_feasible_layout'
 finally:assets.close()


def test_explicit_no_legend_preserves_plot_and_axes_without_invented_objects(reg,tmp_path):
 # Given: a verified source viewport with explicitly no legend.
 spec=_synthetic(tmp_path)
 spec['series']=[]
 for key in ('masks','approved_empty_regions','legend_safe_region','legend_placement','legend_frame'):
  spec.pop(key,None)
 assets=Assets()
 try:
  # When: the shared chart compiler performs ordinary measured axis replacement.
  scene=compile_figure(spec,reg,assets,tmp_path)
  # Then: all axis labels remain, and no legend or extra masks are fabricated.
  assert len(scene.assets)==1 and scene.assets[0]['id']=='plot'
  assert not any(t['role']=='legend-label' for t in scene.texts)
  assert not any(n['id']=='legend-frame' for n in scene.nodes)
  assert {t['id'] for t in scene.texts}=={'xtick0','xtick1','ytick0','ytick1','xtitle','ytitle'}
  assert scene.layout_evidence['legend_placement']=='none'
  assert scene.layout_evidence['legend_bindings']==[]
  assert scene.layout_evidence['legend_background_audit'] is None
  assert scene.assets[0]['asset'].audit.get('masks',[])==[]
 finally:assets.close()


def test_right_endpoint_tick_expands_canvas_without_moving_source_anchor(reg,tmp_path):
 # Given: the last numeric label extends beyond the old fixed right margin.
 spec=_synthetic(tmp_path)
 spec['series']=[]
 spec['x_ticks']=[{'text':'0','position':50},{'text':'1000.00','position':450}]
 assets=Assets()
 try:
  # When: the standard chart compiler fits the complete measured content.
  scene=compile_figure(spec,reg,assets,tmp_path)
  # Then: the long right label fits; its data anchor and 8pt size are unchanged.
  last=next(t for t in scene.texts if t['id']=='xtick1')
  plot=scene.assets[0]['rect']
  assert last['x']==pytest.approx(plot[0]+(450-48)*175/406)
  assert last['position']['bbox'][2]<scene.width
  assert last['measurement']['text']=='1 000.00'
  assert scene.size==8
 finally:assets.close()


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
