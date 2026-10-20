import pytest

from journal_pdf.editorial import display_content


@pytest.mark.parametrize(('source','expected'),[
    ('1~15 d','1～15 d'),
    ('1 ~ 15 d','1 ～ 15 d'),
    ('-1.50~+2.00','-1.50～+2.00'),
    ('−0.5〜3.250','−0.5～3.250'),
])
def test_numeric_range_connector_uses_fullwidth_tilde_without_changing_values(source,expected):
 assert display_content(source,'axis-category')==expected


def test_numeric_range_connector_preserves_rich_text_parts():
 source=[{'text':'1.00'},{'text':'~','style':'regular'},{'text':'15.00 d','style':'italic'}]
 expected=[{'text':'1.00'},{'text':'～','style':'regular'},{'text':'15.00 d','style':'italic'}]
 assert display_content(source,'axis-title')==expected
 assert source[1]['text']=='~'


@pytest.mark.parametrize('source',['a~b','~1','AT~1~2',r'C:\data\1~2\value'])
def test_non_range_or_literal_tildes_are_preserved(source):
 role='command' if source.startswith('AT') else 'path' if source.startswith('C:') else 'label'
 assert display_content(source,role)==source


def test_numeric_range_connector_is_not_gated_by_cjk_text():
 assert display_content('1~15 d','label')=='1～15 d'


def test_axis_title_evidence_includes_numeric_range_normalization():
 from journal_pdf.axis_units import axis_title_evidence
 assert axis_title_evidence('时间1~15 d')['display']=='时间1～15 d'
