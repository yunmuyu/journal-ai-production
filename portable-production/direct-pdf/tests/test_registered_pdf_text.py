from pathlib import Path
import pytest
import pymupdf as fitz
from journal_pdf.assets import Assets
from journal_pdf.common import FigureError,digest_file


def fixture(tmp_path):
    pdf=tmp_path/'source.pdf';svg=tmp_path/'source.svg'
    with fitz.open() as d:
        p=d.new_page(width=100,height=80);p.draw_rect((5,5,95,75));p.insert_text((10,20),'Native',fontsize=8)
        span=p.get_text('dict')['blocks'][0]['lines'][0]['spans'][0];d.save(pdf)
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><g id="text_1"><text>Native</text></g></svg>')
    registration={'pdf_sha256':digest_file(pdf),'svg_sha256':digest_file(svg),'groups':[{'svg_group_id':'text_1','entries':[{'svg_text_index':0,'pdf_span_indices':[0]}]}]}
    rows=[{'source_text':'Native','source_bbox':list(span['bbox']),'target_text_id':'native'}]
    return pdf,svg,registration,rows


def test_registered_native_pdf_text_preserves_paints_and_removes_all_native(tmp_path):
    pdf,svg,registration,rows=fixture(tmp_path);assets=Assets()
    try:
        a=assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=rows)
        assert a.audit['mode']=='registered-native-pdf-text'
        assert not a.doc[0].get_text().strip()
        assert len(a.doc[0].get_drawings())==1
    finally:assets.close()


@pytest.mark.parametrize('mutation',['missing','duplicate','wrong','changed-svg','unregistered-native'])
def test_registration_rejects_incomplete_or_changed_sources(tmp_path,mutation):
    pdf,svg,registration,rows=fixture(tmp_path);assets=Assets()
    if mutation=='missing':registration['groups']=[]
    elif mutation=='duplicate':registration['groups']*=2
    elif mutation=='wrong':registration['groups'][0]['entries'][0]['pdf_span_indices']=[1]
    elif mutation=='changed-svg':svg.write_text(svg.read_text().replace('Native','Other'))
    else:rows=[]
    try:
        with pytest.raises(FigureError):assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=rows)
    finally:assets.close()

def test_registered_white_native_label_is_rendered_and_audited(reg,tmp_path):
    from journal_pdf.render import render_one
    source=tmp_path/'input';source.mkdir()
    pdf,svg,registration,rows=fixture(source)
    with fitz.open() as d:
        p=d.new_page(width=100,height=80);p.draw_rect((5,5,95,75),color=(0,),fill=(0,));p.insert_text((10,20),'Native',fontsize=8,color=(1,))
        s=p.get_text('dict')['blocks'][0]['lines'][0]['spans'][0];d.save(pdf)
    svg.write_text(svg.read_text().replace('<text>','<text fill="#ffffff">'))
    registration['svg_sha256']=digest_file(svg)
    rows[0]['source_bbox']=list(s['bbox']);registration['pdf_sha256']=digest_file(pdf);registration['svg_path']=svg.name
    spec={'id':'white','author':'Synthetic','kind':'scene','width_pt':100,'height_pt':80,
          'sources':[{'path':pdf.name,'sha256':digest_file(pdf)},{'path':svg.name,'sha256':digest_file(svg)}],
          'texts':[{'id':'native','text':'Native','x':50,'y':40,'gray':1}],
          'assets':[{'id':'body','path':pdf.name,'source_kind':'pdf','clip':[0,0,100,80],'target':[0,0,100,80],
                     'source_registered_pdf_text':True,'text_registration':registration,'text_replacements':rows}]}
    assets=Assets()
    try:
        result=render_one(spec,reg,assets,source,tmp_path/'output')
        assert result['mechanical_checks_passed']
        assert not result['pdf_audit']['editable_text_pure_black']
        assert result['pdf_audit']['editable_text_declared_black_white_exact']
    finally:assets.close()


def test_type3_text_paint_is_removed_without_deleting_body_path(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,ArrayObject,NumberObject,FloatObject,DecodedStreamObject
    pdf=tmp_path/'type3.pdf';svg=tmp_path/'type3.svg';w=PdfWriter();p=w.add_blank_page(100,80)
    glyph=DecodedStreamObject();glyph.set_data(b'600 0 0 0 600 700 d1 0 0 500 700 re f')
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type3'),
      NameObject('/FontBBox'):ArrayObject([NumberObject(v) for v in (0,0,600,700)]),
      NameObject('/FontMatrix'):ArrayObject([FloatObject(v) for v in (.001,0,0,.001,0,0)]),
      NameObject('/CharProcs'):DictionaryObject({NameObject('/A'):w._add_object(glyph)}),
      NameObject('/Encoding'):DictionaryObject({NameObject('/Type'):NameObject('/Encoding'),NameObject('/Differences'):ArrayObject([NumberObject(65),NameObject('/A')])}),
      NameObject('/FirstChar'):NumberObject(65),NameObject('/LastChar'):NumberObject(65),NameObject('/Widths'):ArrayObject([NumberObject(600)]),NameObject('/Resources'):DictionaryObject()})
    p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'0 0 100 80 re S BT /F1 8 Tf 10 30 Td (A) Tj ET');p[NameObject('/Contents')]=w._add_object(stream)
    with pdf.open('wb') as handle:w.write(handle)
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><g id="text_1"><text>A</text></g></svg>')
    with fitz.open(pdf) as d:
        span=d[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        assert len(d[0].get_drawings())==2
    registration={'pdf_sha256':digest_file(pdf),'svg_sha256':digest_file(svg),'groups':[{'svg_group_id':'text_1','entries':[{'svg_text_index':0,'pdf_span_indices':[0]}]}]}
    assets=Assets()
    try:
        a=assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=[{'source_text':'A','source_bbox':list(span['bbox']),'target_text_id':'a'}])
        assert len(a.doc[0].get_drawings())==1
        assert not a.doc[0].get_fonts() and not a.doc[0].get_text()
    finally:assets.close()


def test_indexed_image_is_preserved_or_explicitly_grayscaled(tmp_path):
    from io import BytesIO
    from PIL import Image
    from journal_pdf.source_pdf_text import image_records
    pdf,svg,registration,rows=fixture(tmp_path)
    with fitz.open(pdf) as d:
        pix=Image.new('P',(3,2));pix.putpalette([255,0,0,0,0,255]+[0]*762);pix.putdata([0,1,0,1,0,1]);buf=BytesIO();pix.save(buf,format='PNG')
        d[0].insert_image((60,40,90,60),stream=buf.getvalue());data=d.tobytes()
    pdf.write_bytes(data);registration['pdf_sha256']=digest_file(pdf);assets=Assets()
    try:
        a=assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=rows)
        with fitz.open(pdf) as d:assert image_records(d,d[0])==image_records(a.doc,a.doc[0])
        gray=assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=rows,grayscale=True)
        assert gray.audit['grayscale_proof']
        im=fitz.Pixmap(gray.doc,gray.doc[0].get_images()[0][0])
        assert im.width==3 and im.height==2
        assert set(im.samples)=={76,29}
    finally:assets.close()

def test_type3_white_color_uses_svg_and_pdf_paint_not_span_color(tmp_path):
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import ContentStream
    # Reuse the fully synthetic Type3 fixture produced by its preservation test.
    test_type3_text_paint_is_removed_without_deleting_body_path(tmp_path)
    pdf=tmp_path/'type3.pdf';svg=tmp_path/'type3.svg'
    w=PdfWriter(clone_from=PdfReader(str(pdf)));p=w.pages[0];stream=ContentStream(p.get_contents(),w)
    from pypdf.generic import FloatObject
    stream.operations=[([FloatObject(1)],b'g')]+stream.operations;p.replace_contents(stream)
    from io import BytesIO
    buf=BytesIO();w.write(buf);pdf.write_bytes(buf.getvalue())
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><g id="text_1"><text fill="#ffffff">A</text></g></svg>')
    with fitz.open(pdf) as d:span=d[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
    assert span['color']==0  # Reproduces the extractor's Type3 color limitation.
    registration={'pdf_sha256':digest_file(pdf),'svg_sha256':digest_file(svg),'groups':[{'svg_group_id':'text_1','entries':[{'svg_text_index':0,'pdf_span_indices':[0]}]}]}
    assets=Assets()
    try:
        a=assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=[{'source_text':'A','source_bbox':list(span['bbox']),'target_text_id':'a'}])
        assert a.audit['text_replacements'][0]['source_gray']==1
    finally:assets.close()

@pytest.mark.parametrize('mutation',['white-mismatch','paint-in-text','clip-cuts-text','changed-source-after-prepare'])
def test_registered_route_refuses_unproven_evidence(tmp_path,mutation):
    from journal_pdf.source_icons import audit_icon_paths
    pdf,svg,registration,rows=fixture(tmp_path);assets=Assets();clip=[0,0,100,80]
    if mutation=='white-mismatch':svg.write_text(svg.read_text().replace('<text>','<text fill="white">'));registration['svg_sha256']=digest_file(svg)
    elif mutation=='paint-in-text':svg.write_text(svg.read_text().replace('</g>','<path d="M0 0L1 1"/></g>'));registration['svg_sha256']=digest_file(svg)
    elif mutation=='clip-cuts-text':clip=[0,0,20,80]
    try:
        if mutation=='changed-source-after-prepare':
            a=assets.registered_pdf_text(pdf,0,clip,svg,registration,text_replacements=rows)
            with fitz.open() as out:
                page=out.new_page(width=100,height=80);assets.place(page,a,fitz.Rect(clip));svg.write_text(svg.read_text().replace('Native','Other'))
                with pytest.raises(FigureError):audit_icon_paths(page,[{'asset':a,'id':'body','rect':fitz.Rect(clip)}])
        else:
            with pytest.raises(FigureError):assets.registered_pdf_text(pdf,0,clip,svg,registration,text_replacements=rows)
    finally:assets.close()

def test_scene_layout_preserves_declared_white_in_actual_pdf(reg,tmp_path):
    from journal_pdf.layouts import primitive
    from journal_pdf.fonts import draw_text
    scene=primitive({'width_pt':100,'height_pt':80,'texts':[{'id':'white','text':'A','x':50,'y':40,'gray':1}]},reg,8)
    reg.prepare_document_fonts(scene.texts)
    output=tmp_path/'scene-white.pdf'
    with fitz.open() as d:
        p=d.new_page(width=100,height=80);p.draw_rect((0,0,100,80),color=None,fill=(0,))
        for text in scene.texts:draw_text(p,reg,text)
        d.save(output)
    with fitz.open(output) as d:
        traces=d[0].get_texttrace()
        assert traces and all(all(abs(component-1)<1e-8 for component in trace['color']) for trace in traces)

def test_indexed_png_predictor_is_not_reused_for_new_rgb_stream(tmp_path):
    pdf,svg,registration,rows=fixture(tmp_path)
    with fitz.open(pdf) as d:
        pix=fitz.Pixmap(fitz.csRGB,(0,0,30,20),False);pix.clear_with(0)
        x=d[0].insert_image((60,40,90,60),pixmap=pix)
        d.xref_set_key(x,'ColorSpace','[/Indexed /DeviceRGB 1 <FF00000000FF>]')
        import zlib
        d.update_stream(x,zlib.compress((bytes([0])+bytes([0,1])*15)*20),compress=False)
        d.xref_set_key(x,'Filter','/FlateDecode')
        d.xref_set_key(x,'DecodeParms','<< /Predictor 10 /Colors 1 /Columns 30 /BitsPerComponent 8 >>')
        data=d.tobytes()
    pdf.write_bytes(data);registration['pdf_sha256']=digest_file(pdf);assets=Assets()
    try:
        a=assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=rows,grayscale=True)
        x=a.doc[0].get_images()[0][0];pix=fitz.Pixmap(a.doc,x)
        assert pix.samples==bytes([76,76,76,29,29,29])*300
        assert a.doc.xref_get_key(x,'DecodeParms')[0]=='null'
    finally:assets.close()

def test_svg_positioned_tspan_structural_whitespace_is_not_visible_text(tmp_path):
    pdf,svg,registration,rows=fixture(tmp_path);assets=Assets()
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><g id="text_1"><text>\n  <tspan x="0">Na</tspan>\n  <tspan x="12">tive</tspan>\n</text></g></svg>')
    registration['svg_sha256']=digest_file(svg)
    try:
        a=assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=rows)
        assert not a.doc[0].get_text()
    finally:assets.close()


@pytest.mark.parametrize('svg_text,allowed,passes',[('Na tive',True,True),('Na tive',False,False),('Na other',True,False)])
def test_pdf_svg_layout_whitespace_equivalence_requires_explicit_evidence(tmp_path,svg_text,allowed,passes):
    pdf,svg,registration,rows=fixture(tmp_path);assets=Assets()
    svg.write_text(svg.read_text().replace('Native',svg_text));registration['svg_sha256']=digest_file(svg)
    registration['groups'][0]['entries'][0]['layout_whitespace_equivalent']=allowed
    try:
        if passes:assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=rows)
        else:
            with pytest.raises(FigureError):assets.registered_pdf_text(pdf,0,[0,0,100,80],svg,registration,text_replacements=rows)
    finally:assets.close()
