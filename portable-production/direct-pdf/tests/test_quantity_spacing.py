import copy
import pytest
from journal_pdf.editorial import display_content

@pytest.mark.parametrize('source,expected',[
    ('15kHz 30kHz 60kHz 120kHz 3GHz 2.5MHz 1Hz','15 kHz 30 kHz 60 kHz 120 kHz 3 GHz 2.5 MHz 1 Hz'),
    ('10mm 2.5kg 3mV 5ms 12MPa','10 mm 2.5 kg 3 mV 5 ms 12 MPa'),
    ('10mm_file 2.5kg.png X3mV 5ms_rate','10mm_file 2.5kg.png X3mV 5ms_rate'),
    ('15 kHz 15kHz_rate 15kHz.png x15kHz','15 kHz 15kHz_rate 15kHz.png x15kHz'),
    ('（52.4KB）','（52.4 KB）'),('52.4 KB','52.4 KB'),('52.4kB 1MB 2KiB 3MiB 4GB 5TB 6GiB 7TiB','52.4 kB 1 MB 2 KiB 3 MiB 4 GB 5 TB 6 GiB 7 TiB'),('52.4\u00a0KB','52.4\u00a0KB'),
    ('GLM-5.2 R2 52.4kb 52.4qux 52.4unknown 50% 90° 5m 2A 3B 52.4KBps','GLM-5.2 R2 52.4kb 52.4qux 52.4unknown 50% 90° 5m 2A 3B 52.4KBps'),
    ('52.4KB.png C:/52.4KB /52.4KB x52.4KB v52.4KB','52.4KB.png C:/52.4KB /52.4KB x52.4KB v52.4KB'),
])
def test_confirmed_quantity_token_spacing_is_conservative_and_idempotent(source,expected):
    # Given a journal label with confirmed KB or an identifier.
    # When the shared display policy runs, then only the quantity token changes.
    assert display_content(source)==expected
    assert display_content(expected)==expected

def test_rich_quantity_spacing_crosses_runs_without_changing_styles_or_input():
    # Given a number and unit split across independently styled runs.
    source=[{'text':'（52.','style':'italic'},{'text':'4','baseline_shift_pt':1},{'text':'K','style':'regular'},{'text':'B）','scale':.9}]
    original=copy.deepcopy(source)
    # When the shared display policy runs.
    result=display_content(source)
    # Then only the boundary space is inserted, all original style data survives.
    assert result==[{'text':'（52.','style':'italic'},{'text':'4','baseline_shift_pt':1},{'text':' K','style':'regular'},{'text':'B）','scale':.9}]
    assert source==original
    assert display_content(result)==result

@pytest.mark.parametrize('role',['literal','code','command','path'])
def test_quantity_spacing_respects_outer_and_run_literal_roles(role):
    # Given literal content at either API level.
    source=[{'text':'52.4','role':role},{'text':'KB','style':'italic'}]
    # When display policy runs, then literals retain their exact bytes.
    assert display_content('52.4KB',role)=='52.4KB'
    assert display_content(source)==source
    assert display_content([{'text':'52.4'},{'text':'KB','role':role}])==[{'text':'52.4'},{'text':'KB','role':role}]

def test_font_measurement_applies_quantity_policy_to_single_rich_run(reg):
    # Given the actual A4 caption shape; when measured through the real font entry.
    result=reg.measure([{'text':'（52.4KB）'}],8)
    # Then the measured/rendered source text includes the required space.
    assert result['text']=='（52.4 KB）'


def test_audit_rederives_from_source_and_detects_missing_actual_space():
    from types import SimpleNamespace
    from journal_pdf.quantity_spacing import audit_quantity_spacing
    # Given a bypassed formatter and the same faulty actual PDF text.
    item={'id':'caption','role':'label','source_content':[{'text':'（52.4KB）'}],
          'measurement':{'text':'（52.4KB）'}}
    scene=SimpleNamespace(texts=[item])
    # When independently auditing original source requirements.
    result=audit_quantity_spacing(scene,'（52.4KB）')
    # Then character equality without whitespace is insufficient.
    assert not result['ok']
    assert result['issues'][0]['code']=='quantity_unit_spacing_violation'
    item['measurement']['text']='（52.4 KB）'
    assert not audit_quantity_spacing(scene,'（52.4KB）')['ok']
    assert audit_quantity_spacing(scene,'（52.4 KB）')['ok']

def test_frequency_spacing_is_audited_against_actual_pdf_text():
    from types import SimpleNamespace
    from journal_pdf.quantity_spacing import audit_quantity_spacing
    item={'id':'frequency','role':'label','source_content':'15kHz',
          'measurement':{'text':'15 kHz'}}
    scene=SimpleNamespace(texts=[item])
    assert not audit_quantity_spacing(scene,'15kHz')['ok']
    assert audit_quantity_spacing(scene,'15 kHz')['ok']

def test_frequency_spacing_survives_actual_pdf_render(reg, tmp_path):
    import pymupdf as fitz
    from journal_pdf.assets import Assets
    from journal_pdf.render import render_one
    source=tmp_path/'source';source.mkdir()
    spec={'id':'frequency','author':'Synthetic','synthetic':True,'kind':'scene','width_pt':100,'height_pt':60,
          'texts':[{'id':'label','text':'15kHz','x':50,'y':30}],
          'policy':{'export_crop_padding_pt':4}}
    assets=Assets()
    try:
        result=render_one(spec,reg,assets,source,tmp_path/'output')
        with fitz.open(tmp_path/'output'/result['output_pdf']) as doc:
            assert '15 kHz' in doc[0].get_text()
        assert result['mechanical_checks_passed']
    finally:
        assets.close()

def test_audit_checks_quantity_occurrence_counts_and_literal_baseline():
    from types import SimpleNamespace
    from journal_pdf.quantity_spacing import audit_quantity_spacing
    # Given two quantity occurrences plus a literal with an already spaced token.
    items=[{'id':str(i),'role':'label','source_content':'52.4KB','measurement':{'text':'52.4 KB'}} for i in range(2)]
    items.append({'id':'literal','role':'code','source_content':'52.4 KB','measurement':{'text':'52.4 KB'}})
    # When one actual quantity has no gap, a second correct occurrence cannot mask it.
    assert not audit_quantity_spacing(SimpleNamespace(texts=items),'52.4 KB\n52.4KB\n52.4 KB')['ok']
    assert audit_quantity_spacing(SimpleNamespace(texts=items),'52.4 KB\n52.4 KB\n52.4 KB')['ok']


@pytest.mark.parametrize('pdf_label,expected_ok',[('52.4KB',False),('52.4 KB',True)])
def test_independent_audit_reads_real_pdf_whitespace(tmp_path,pdf_label,expected_ok):
    from types import SimpleNamespace
    import pymupdf as fitz
    from journal_pdf.quantity_spacing import audit_quantity_spacing
    # Given an actual PDF whose label may bypass the quantity formatter.
    path=tmp_path/'quantity.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=120,height=40)
        page.insert_text((10,20),pdf_label,fontsize=8)
        doc.save(path)
    item={'id':'caption','role':'label','source_content':[{'text':'52.4KB'}],
          'measurement':{'text':'52.4 KB'}}
    # When the auditor reads the real PDF's extracted spaces.
    with fitz.open(path) as doc:
        result=audit_quantity_spacing(SimpleNamespace(texts=[item]),doc[0].get_text())
    # Then an otherwise identical string missing the unit separator fails.
    assert result['ok'] is expected_ok

@pytest.mark.parametrize('target_text',['52.4KB','52.5KB'])
def test_registered_native_pdf_quantity_relettering_applies_shared_spacing(reg,tmp_path,target_text):
    import pymupdf as fitz
    from journal_pdf.assets import Assets
    from journal_pdf.common import digest_file
    from journal_pdf.render import render_one
    # Given a fully registered native PDF quantity without its separator.
    source=tmp_path/'source';source.mkdir()
    pdf=source/'source.pdf';svg=source/'source.svg'
    with fitz.open() as doc:
        p=doc.new_page(width=100,height=60);p.draw_rect((5,5,95,55));p.insert_text((10,20),'52.4KB',fontsize=8)
        span=p.get_text('dict')['blocks'][0]['lines'][0]['spans'][0];doc.save(pdf)
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><g id="text_1"><text>52.4KB</text></g></svg>')
    registration={'pdf_sha256':digest_file(pdf),'svg_sha256':digest_file(svg),'svg_path':svg.name,
                  'groups':[{'svg_group_id':'text_1','entries':[{'svg_text_index':0,'pdf_span_indices':[0]}]}]}
    spec={'id':'quantity','author':'Synthetic','kind':'scene','width_pt':100,'height_pt':60,
          'sources':[{'path':pdf.name,'sha256':digest_file(pdf)},{'path':svg.name,'sha256':digest_file(svg)}],
          'texts':[{'id':'caption','text':[{'text':target_text}],'x':50,'y':30}],
          'assets':[{'id':'body','path':pdf.name,'source_kind':'pdf','clip':[0,0,100,60],'target':[0,0,100,60],
                     'source_registered_pdf_text':True,'text_registration':registration,
                     'text_replacements':[{'source_text':'52.4KB','source_bbox':list(span['bbox']),'target_text_id':'caption'}]}]}
    assets=Assets()
    try:
        # When the public registered-source route reletters the quantity.
        if target_text!='52.4KB':
            from journal_pdf.common import FigureError
            with pytest.raises(FigureError) as error:
                render_one(spec,reg,assets,source,tmp_path/'out')
            assert error.value.code=='source_icon_replacement_missing'
            return
        result=render_one(spec,reg,assets,source,tmp_path/'out')
        # Then identity remains source-bound and actual output has the separator.
        assert result['mechanical_checks_passed']
        with fitz.open(tmp_path/'out'/result['output_pdf']) as doc:
            assert '52.4 KB' in doc[0].get_text()
    finally:assets.close()




def test_render_pipeline_rejects_quantity_when_both_formatters_are_bypassed(reg,tmp_path,monkeypatch):
    from journal_pdf.assets import Assets
    from journal_pdf.common import FigureError
    from journal_pdf.render import render_one
    # Given a formatter regression at both actual measurement entry points.
    source=tmp_path/'source';source.mkdir()
    monkeypatch.setattr('journal_pdf.scene.display_content',lambda content,role='label':content)
    monkeypatch.setattr('journal_pdf.fonts.display_content',lambda content,role='label':content)
    spec={'id':'bypass','author':'Synthetic','synthetic':True,'kind':'scene','width_pt':100,'height_pt':60,
          'texts':[{'id':'caption','text':[{'text':'52.4KB'}],'x':50,'y':30}],
          'policy':{'export_crop_padding_pt':4}}
    assets=Assets()
    try:
        # When the real pipeline writes and inspects the faulty actual PDF.
        with pytest.raises(FigureError) as error:
            render_one(spec,reg,assets,source,tmp_path/'output')
        # Then source-derived unit audit rejects it despite matching character counts.
        result=error.value.as_dict()
        assert result['code']=='actual_pdf_audit_failed'
        assert result['audit']['text_multiset_exact']
        assert not result['audit']['quantity_unit_spacing']['ok']
        assert result['audit']['quantity_unit_spacing']['issues'][0]['code']=='quantity_unit_spacing_violation'
    finally:assets.close()
