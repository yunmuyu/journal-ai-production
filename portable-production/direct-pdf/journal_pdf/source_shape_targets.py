from __future__ import annotations

import math
import pymupdf as fitz
from .common import FigureError


def audit_shape_targets(scene):
    contracts={};issues=[];used_nodes=set();used_texts=set();evidence=[]
    declarations=getattr(scene,'source_shape_target_declarations',{})
    nodes={row['id']:row for row in scene.nodes};texts={row['id']:row for row in scene.texts}
    for placement in scene.assets:
        asset=placement.get('asset');receipt=getattr(asset,'audit',{})
        bindings=receipt.get('source_shape_bindings',[])
        if not bindings:continue
        for binding in bindings:
            node_id=binding['target_node_id'];text_id=binding['target_text_id']
            try:
                if node_id in used_nodes or text_id in used_texts:raise FigureError('source_shape_duplicate_target','源shape目标须逐实例双向一一消费')
                used_nodes.add(node_id);used_texts.add(text_id)
                node=nodes.get(node_id);text=texts.get(text_id);decl=declarations.get(node_id,{})
                if node is None or text is None:raise FigureError('source_shape_target_missing','登记的目标矩形或文字缺失')
                radii=[decl.get(key,0) for key in ('radius','corner_radius','corner_radius_pt')]
                if decl.get('shape','rectangle')!='rectangle' or node['kind']!='rectangle' or node['container'] or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v!=0 for v in radii):raise FigureError('source_shape_target_kind','目标必须为真实非容器无圆角直角矩形')
                if abs(node['width']-.5)>1e-7 or node.get('dash') or node.get('fill') is not None or decl.get('fill') is not None or any(key in decl and decl[key]!=.5 for key in ('width','width_pt','stroke_width_pt')):raise FigureError('source_shape_target_style','目标须无填充、无虚线、0.5pt黑描边')
                fixed=decl.get('fixed_size',{});fixed=fixed if isinstance(fixed,dict) else {}
                origin=fixed.get('evidence',{});origin=origin if isinstance(origin,dict) else {}
                if decl.get('role')!='source-locked-viewport' or fixed.get('purpose')!='source-locked-viewport' or origin.get('constraint')!='source-artwork-bounds' or origin.get('source_sha256')!=asset.source_hash or scene.source_bindings.get(origin.get('source_id'))!=asset.source_hash or origin.get('source_page_index')!=receipt['source_page'] or origin.get('source_path_index')!=binding['source_path_index']:raise FigureError('source_shape_target_contract','窄panel须与真实准备receipt及固定源几何合同互绑')
                same=lambda a,b:isinstance(a,list) and isinstance(b,list) and len(a)==len(b)==4 and all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and abs(x-y)<=.01 for x,y in zip(a,b))
                if not same(origin.get('source_rect'),binding['source_bbox']) or not same(origin.get('target_rect'),decl.get('rect',[])):raise FigureError('source_shape_target_contract','目标合同源bbox或声明bbox不匹配')
                viewport=fitz.Rect(asset.rect);target=fitz.Rect(placement['rect']);clip=receipt['source_clip']
                scale=min(target.width/viewport.width,target.height/viewport.height)
                dx=target.x0+(target.width-viewport.width*scale)/2-viewport.x0*scale
                dy=target.y0+(target.height-viewport.height*scale)/2-viewport.y0*scale
                source=binding['source_bbox'];inset=.15*scene.layout_evidence.get('whole_artwork_scale',1.)
                expected=[dx+(source[0]-clip[0])*scale+inset,dy+(source[1]-clip[1])*scale,dx+(source[2]-clip[0])*scale-inset,dy+(source[3]-clip[1])*scale]
                if not same(node['rect'],expected):raise FigureError('source_shape_target_bbox','只允许映射源bbox左右各内收0.15pt，不能移动、扩框或缩放')
                owners=[row for row in scene.texts if row.get('owner')==node_id]
                if len(owners)!=1 or owners[0]['id']!=text_id or text['position']['rotation']!=90 or abs(text['measurement']['size']-6)>1e-7 or text['measurement']['text']!=binding['source_text']:raise FigureError('source_shape_target_owner','仅接受同文6pt90度且唯一真实owner的源绑定窄panel')
                if abs(text['x']-(expected[0]+expected[2])/2)>.01 or abs(text['y']-(expected[1]+expected[3])/2)>.01:raise FigureError('source_shape_text_anchor','必须保留原框中心和文字基线')
                ink=text['position']['bbox'];box=node['rect'];margins=[ink[0]-box[0],ink[1]-box[1],box[2]-ink[2],box[3]-ink[3]]
                if any(m<=.25 for m in margins):raise FigureError('source_shape_text_clearance','实际字墨须与0.5pt框线保持正净距')
                contract={'kind':'source-bound-narrow-panel','asset':placement['id'],'target_node_id':node_id,'target_text_id':text_id,'source_path_index':binding['source_path_index'],'source_sha256':asset.source_hash,'expected_bbox':expected,'actual_ink_bbox':ink,'actual_centerline_margins_pt':margins,'actual_paint_clearance_pt':[m-.25 for m in margins],'verified':True}
                contracts[node_id]=contract;evidence.append(contract)
                node['role']=decl['role'];node['source_shape_replacement_contract']=contract
            except FigureError as error:issues.append(error.as_dict()|{'id':node_id,'asset':placement['id']})
    scene.layout_evidence['source_shape_replacements']=evidence
    return contracts,issues
