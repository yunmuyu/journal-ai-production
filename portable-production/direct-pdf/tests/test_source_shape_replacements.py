from pathlib import Path
from dataclasses import asdict
import copy
import pymupdf as fitz
import pytest

from journal_pdf.assets import Assets
from journal_pdf.common import FigureError,digest_file,digest_json
from journal_pdf.source_icons import path_record
from test_source_mixed_body import mixed_source


def shape_source(path:Path):
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    mixed_source(path)
    with fitz.open(path) as doc:
        page=doc[0];page.draw_rect(fitz.Rect(66,10,76.6,70),radius=.2,width=1.02)
        page.insert_text((74.4,55),'Norm',fontsize=6,rotate=90)
        data=doc.tobytes(garbage=4,deflate=True)
    path.write_bytes(data)
    with fitz.open(path) as doc:
        drawing=doc[0].get_drawings()[1];record=path_record(drawing);box=list(drawing['rect'])
        native=[{'source_text':s['text'],'source_bbox':list(s['bbox']),'target_text_id':'panel-text' if s['text']=='Norm' else 'label-a'} for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans'] if s['text'].strip()]
    reader=PdfReader(path);operations=ContentStream(reader.pages[0].get_contents(),reader).operations
    index=next(i for i in reversed(range(len(operations))) if operations[i][1]==b'S')
    row={'source_sha256':digest_file(path),'source_page':0,'source_path_index':1,'source_path_sha256':digest_json(asdict(record)),
         'source_paint_operation_index':index,'source_paint_operator':'S','source_bbox':box,'target_node_id':'panel','target_text_id':'panel-text',
         'horizontal_inset_pt':.15,'purpose':'source-bound-narrow-panel'}
    return native,row


def target_spec(path:Path,native,row):
    box=row['source_bbox'];rect=[box[0]+.15,box[1],box[2]-.15,box[3]]
    node={'id':'panel','shape':'rectangle','rect':rect,'role':'source-locked-viewport','fixed_size':{'purpose':'source-locked-viewport','evidence':{'constraint':'source-artwork-bounds','source_id':path.name,'source_sha256':digest_file(path),'source_page_index':0,'source_path_index':1,'source_rect':box,'target_rect':rect}}}
    return {'id':'shape','author':'test','kind':'scene','width_pt':100,'height_pt':100,'policy':{'design_font_size_pt':6},'sources':[{'path':path.name,'sha256':digest_file(path)}],
            'assets':[{'id':'body','path':path.name,'source_kind':'pdf','source_mixed_body':True,'clip':[0,0,100,80],'target':[0,0,100,80],'text_replacements':native,'source_shape_replacements':[row]}],
            'nodes':[node],'texts':[{'id':'label-a','text':'A','x':30,'y':90},{'id':'panel-text','text':'Norm','x':(box[0]+box[2])/2,'y':40,'rotation':90,'owner':'panel'}]}


def test_registered_roundrect_is_removed_without_touching_other_paint_or_images(tmp_path:Path):
    source=tmp_path/'shape.pdf';native,row=shape_source(source);assets=Assets()
    try:
        body=assets.source_mixed_body(source,0,[0,0,100,80],text_replacements=native,source_shape_replacements=[row])
        assert body.audit['source_original_path_count']==2
        assert body.audit['source_shape_removed_path_count']==1 and body.audit['path_count']==1
        assert body.audit['image_instance_count']==2
        assert body.audit['source_shape_bindings'][0]['target_node_id']=='panel'
    finally:assets.close()


def test_source_bound_narrow_target_has_real_six_point_rotated_owner_without_global_padding_exception(reg,tmp_path:Path):
    from journal_pdf.render import compile_figure
    source=tmp_path/'shape.pdf';native,row=shape_source(source);assets=Assets()
    try:
        scene=compile_figure(target_spec(source,native,row),reg,assets,tmp_path)
        assert len(scene.nodes)==1 and scene.nodes[0]['kind']=='rectangle'
        assert len(scene.layout_evidence['source_shape_replacements'])==1
        assert scene.layout_evidence['source_shape_replacements'][0]['verified']
    finally:assets.close()

@pytest.mark.parametrize('mutation',['source-hash','page','index','path-hash','paint','operator','bbox','inset','duplicate','protected-neighbor','missing-native-text'])
def test_shape_preparation_refuses_wrong_registration_or_neighbor(tmp_path:Path,mutation:str):
    source=tmp_path/'shape.pdf';native,row=shape_source(source);rows=[copy.deepcopy(row)]
    match mutation:
        case 'source-hash':rows[0]['source_sha256']='0'*64
        case 'page':rows[0]['source_page']=1
        case 'index':rows[0]['source_path_index']=99
        case 'path-hash':rows[0]['source_path_sha256']='0'*64
        case 'paint':rows[0]['source_paint_operation_index']+=1
        case 'operator':rows[0]['source_paint_operator']='f'
        case 'bbox':rows[0]['source_bbox'][0]+=.02
        case 'inset':rows[0]['horizontal_inset_pt']=.16
        case 'duplicate':rows.append(copy.deepcopy(rows[0]))
        case 'protected-neighbor':rows[0]['source_path_index']=0
        case 'missing-native-text':rows[0]['target_text_id']='unregistered'
    assets=Assets()
    try:
        with pytest.raises(FigureError):assets.source_mixed_body(source,0,[0,0,100,80],text_replacements=native,source_shape_replacements=rows)
    finally:assets.close()


@pytest.mark.parametrize('mutation',['missing-target','nonrect','roundrect','coerced-roundrect','radius','filled','container','wrong-width','shift','scale','owner','rotation','font','anchor','role','contract','extra-owner'])
def test_shape_targets_require_exact_narrow_geometry_owner_and_style(reg,tmp_path:Path,mutation:str):
    from journal_pdf.render import compile_figure
    source=tmp_path/'shape.pdf';native,row=shape_source(source);spec=target_spec(source,native,row);node=spec['nodes'][0];text=spec['texts'][1]
    match mutation:
        case 'missing-target':spec['nodes']=[]
        case 'nonrect':node['shape']='ellipse'
        case 'roundrect':node['shape']='roundrect';node['semantic_shape']=True
        case 'coerced-roundrect':node['shape']='roundrect'
        case 'radius':node['radius']=.1
        case 'filled':node['fill']=1
        case 'container':node['container']=True
        case 'wrong-width':node['width']=.7
        case 'shift':node['rect'][0]+=.02;node['rect'][2]+=.02
        case 'scale':node['rect'][3]+=1
        case 'owner':text['owner']=None
        case 'rotation':text['rotation']=0
        case 'font':spec['policy']['design_font_size_pt']=6.1
        case 'anchor':text['y']+=1
        case 'role':node['role']='source-bound-narrow-panel'
        case 'contract':node['fixed_size']['evidence']['source_path_index']=0
        case 'extra-owner':spec['texts'].append({'id':'extra','text':'x','x':71,'y':65,'owner':'panel'})
    assets=Assets()
    try:
        with pytest.raises(FigureError):compile_figure(spec,reg,assets,tmp_path)
    finally:assets.close()


def test_arbitrary_role_and_source_hash_do_not_grant_narrow_panel_padding(reg,tmp_path:Path):
    from journal_pdf.render import compile_figure
    source=tmp_path/'shape.pdf';native,row=shape_source(source);spec=target_spec(source,native,row)
    spec['assets'][0]['source_shape_replacements']=[]
    assets=Assets()
    try:
        with pytest.raises(FigureError) as error:compile_figure(spec,reg,assets,tmp_path)
        codes={issue['code'] for attempt in error.value.details.get('attempts',[]) for issue in attempt['issues']}
        assert codes&{'node_text_padding','primitive_box_measurement_contract'}
    finally:assets.close()
