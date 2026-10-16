import copy
from types import SimpleNamespace
import pytest
from journal_pdf.axis_units import normalize_axis_title,plain_content,axis_title_evidence,audit_axis_titles
from journal_pdf.editorial import display_content

@pytest.mark.parametrize('source,expected',[
 ('Freq(Hz)','Freq/Hz'),('Freq (Hz)','Freq/Hz'),('Freq（Hz）','Freq/Hz'),
 ('Freq ( Hz )  ','Freq/Hz'),('S21(dB)','S21/dB'),('nf(dB)','nf/dB'),
 ('OP1(dBm)','OP1/dBm'),('时间(s)','时间/s'),('长度(mm)','长度/mm'),
 ('电阻（kΩ）','电阻/kΩ'),('Accuracy(%)','Accuracy/%'),
 ('Freq/Hz','Freq/Hz'),('MCC','MCC'),('AUC','AUC'),('train/loss','train/loss'),
 ('P(x)','P(x)'),('理想线（y=x）','理想线（y=x）'),
 ('f(x) (Hz)','f(x) (Hz)'),('速度(m/s)','速度(m/s)'),
 ('Freq(Hz）','Freq(Hz）'),('Freq/（Hz）','Freq/（Hz）'),
])
def test_axis_only_normalization(source,expected):
 assert normalize_axis_title(source)==expected
 assert normalize_axis_title(expected)==expected
 assert display_content(source,'axis-title')==expected
 legend_expected = source.replace('(', '（').replace(')', '）') if any('\u4e00' <= c <= '\u9fff' for c in source) else source
 assert display_content(source,'legend-label')==legend_expected
 assert display_content(source,'label')==source


def test_no_mutation_of_rich_styles():
 source=[{'text':'S','style':'italic'},{'text':'21','scale':.7,'baseline_shift_pt':2},
         {'text':' (','style':'regular'},{'text':'dB','style':'regular'},{'text':')'}]
 before=copy.deepcopy(source)
 result=normalize_axis_title(source)
 assert source==before
 assert plain_content(result)=='S21/dB'
 assert result[0]==source[0] and result[1]==source[1]
 assert result[-1]==source[3]


def test_audit_catches_bypassed_formatter_even_if_pdf_matches_bad_scene():
 source='Freq(Hz)'
 t={'id':'x','source_content':source,'content':source,'measurement':{'text':source},'role':'axis-title'}
 audit=audit_axis_titles(SimpleNamespace(texts=[t]),source)
 assert not audit['ok'] and audit['issues'][0]['code']=='axis_unit_rule_violation'


def test_audit_accepts_actual_normalized_text():
 t={'id':'x','source_content':'Freq(Hz)','content':'Freq/Hz','measurement':{'text':'Freq/Hz'},'role':'axis-title'}
 assert audit_axis_titles(SimpleNamespace(texts=[t]),'1.5G 2.0G\nFreq/Hz')['ok']
 assert not audit_axis_titles(SimpleNamespace(texts=[t]),'FreqHz')['ok']


def test_unsupported_formula_is_not_claimed_as_completed():
 assert axis_title_evidence('速度(m/s)')['status']=='semantic_review_needed'
 assert not axis_title_evidence('Freq(Hz)')['numeric_scale_changed']


def test_chart_measures_normalized_title_before_placement(reg,tmp_path):
 from test_v012_new_raster import _synthetic
 from journal_pdf.assets import Assets
 from journal_pdf.render import compile_figure
 spec=_synthetic(tmp_path);before=copy.deepcopy(spec);assets=Assets()
 try:
  scene=compile_figure(spec,reg,assets,tmp_path)
  assert spec==before
  x=next(t for t in scene.texts if t['id']=='xtitle')
  y=next(t for t in scene.texts if t['id']=='ytitle')
  assert x['source_content']=='Freq(Hz)' and x['measurement']['text']=='Freq/Hz'
  assert y['source_content']=='S21(dB)' and y['measurement']['text']=='S21/dB'
  assert scene.layout_evidence['layout_build_count']==1 and scene.size==8
 finally:assets.close()
