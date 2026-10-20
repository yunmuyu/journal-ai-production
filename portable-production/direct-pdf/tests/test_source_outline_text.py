from pathlib import Path
from dataclasses import asdict
import copy

import pymupdf as fitz
import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError,digest_file,digest_json
from journal_pdf.source_icons import path_record
from test_source_mixed_body import mixed_source


def outlined_source(path:Path):
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    native=mixed_source(path)
    with fitz.open(path) as doc:
        page=doc[0];shape=page.new_shape();shape.draw_polyline([(70,50),(75,35),(80,50),(78,50),(76,43),(74,43),(72,50)])
        shape.finish(color=None,fill=(0,),closePath=True);shape.commit()
        data=doc.tobytes(garbage=4,deflate=True)
    path.write_bytes(data)
    with fitz.open(path) as doc:record=path_record(doc[0].get_drawings()[1])
    reader=PdfReader(path);operations=ContentStream(reader.pages[0].get_contents(),reader).operations
    index=next(i for i in reversed(range(len(operations))) if operations[i][1] in (b'f',b'f*'))
    return native,{'source_sha256':digest_file(path),'source_page':0,'source_path_index':1,'source_path_sha256':digest_json(asdict(record)),
                   'source_paint_operation_index':index,'source_text':'A','target_text_id':'outline-a'}


def test_registered_outline_removes_only_complete_native_text_paint(tmp_path:Path):
    source=tmp_path/'outline.pdf';native,row=outlined_source(source);assets=Assets()
    try:
        body=assets.source_mixed_body(source,0,[0,0,100,80],text_replacements=native,outline_text_replacements=[row])
        assert body.audit['source_original_path_count']==2
        assert body.audit['path_count']==1 and body.audit['outline_removed_path_count']==1
        assert body.audit['image_instance_count']==2
        assert body.audit['outline_text_bindings'][0]['source_path_sha256']==row['source_path_sha256']
        assert body.audit['text_replacements'][-1]['target_text_id']=='outline-a'
    finally:assets.close()


@pytest.mark.parametrize('mutation',['source-hash','page','path-hash','index','paint','duplicate','protected-neighbor'])
def test_outline_registration_rejects_wrong_source_paint_or_protected_neighbor(tmp_path:Path,mutation:str):
    source=tmp_path/'outline.pdf';native,row=outlined_source(source);rows=[copy.deepcopy(row)]
    match mutation:
        case 'source-hash':rows[0]['source_sha256']='0'*64
        case 'page':rows[0]['source_page']=1
        case 'path-hash':rows[0]['source_path_sha256']='0'*64
        case 'index':rows[0]['source_path_index']=9
        case 'paint':rows[0]['source_paint_operation_index']+=1
        case 'duplicate':rows.append(copy.deepcopy(row))
        case 'protected-neighbor':rows[0]['source_path_index']=0
    assets=Assets()
    try:
        with pytest.raises(FigureError):assets.source_mixed_body(source,0,[0,0,100,80],text_replacements=native,outline_text_replacements=rows)
    finally:assets.close()


@pytest.mark.parametrize('target',['missing','wrong'])
def test_outline_requires_its_exact_editable_scene_target(reg,tmp_path:Path,target:str):
    from journal_pdf.render import compile_figure
    source=tmp_path/'outline.pdf';native,row=outlined_source(source);assets=Assets()
    spec={'id':'outline','author':'test','kind':'scene','width_pt':100,'height_pt':110,'policy':{'design_font_size_pt':6},
          'assets':[{'id':'original','path':'outline.pdf','source_kind':'pdf','source_mixed_body':True,'clip':[0,0,100,80],'target':[0,0,100,80],'text_replacements':native,'outline_text_replacements':[row]}],
          'texts':[{'id':'label-a','text':'A','x':30,'y':90}]}
    if target=='wrong':spec['texts'].append({'id':'outline-a','text':'B','x':70,'y':90})
    try:
        with pytest.raises(FigureError) as error:compile_figure(spec,reg,assets,tmp_path)
        assert error.value.code=='source_icon_replacement_missing'
    finally:assets.close()
