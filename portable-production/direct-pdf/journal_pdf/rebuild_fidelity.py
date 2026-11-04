"""Apply reviewed source style before drawing; reject semantic substitutions."""
from copy import deepcopy
from .common import FigureError, contains


def prepare_rebuild_fidelity(spec):
    """Use a source-bound fidelity contract, never executor allowedChanges prose."""
    contract=spec.get('rebuild_fidelity')
    if contract is None:return spec
    if contract.get('version')!=1 or not any(s.get('sha256')==contract.get('source_sha256') for s in spec.get('sources',[])):
        raise FigureError('rebuild_fidelity_source','保真约束必须绑定当前来源哈希')
    result=deepcopy(spec);issues=[]
    nodes={n['id']:n for n in result.get('nodes',[])}
    edges={e['id']:e for e in result.get('paths',[])+result.get('connections',[])}
    assets={a['id']:a for a in result.get('assets',[])}
    if contract.get('white_boxes'):
        for node in nodes.values():
            if node.get('fill')!=1:node.pop('fill',None)
    if contract.get('single_column'):
        result.setdefault('policy',{})['column']='single'
        result['policy']['design_font_size_pt']=8
    for ident,expected in contract.get('nodes',{}).items():
        node=nodes.get(ident)
        if node is None:issues.append({'code':'source_node_missing','id':ident});continue
        for key in ('shape','dash'):
            if key in expected:node[key]=deepcopy(expected[key])
        if 'parent' in expected and node.get('parent')!=expected['parent']:
            issues.append({'code':'source_parent_changed','id':ident,'expected':expected['parent'],'actual':node.get('parent')})
    for ident,expected in contract.get('connections',{}).items():
        edge=edges.get(ident)
        if edge is None:issues.append({'code':'source_connection_missing','id':ident});continue
        for key in ('from','to','endpoint_nodes','arrow','both','dash'):
            if key in expected and edge.get(key,False if key in ('arrow','both') else None)!=expected[key]:
                issues.append({'code':'source_connection_changed','id':ident,'field':key,'expected':expected[key],'actual':edge.get(key)})
        if 'segments' in expected and len(edge.get('points',[]))-1!=expected['segments']:
            issues.append({'code':'source_route_changed','id':ident,'expected_segments':expected['segments']})
    for ident,expected in contract.get('assets',{}).items():
        if ident not in assets or any(assets[ident].get(k)!=v for k,v in expected.items()):
            issues.append({'code':'source_icon_missing_or_changed','id':ident})
    if issues:raise FigureError('rebuild_fidelity_conflict','重绘方案改变了已核对原图结构、连接或图标',issues=issues)
    return result


def audit_rebuild_fidelity(scene,spec):
    """Verify declared hierarchy against the actual generated geometry."""
    contract=spec.get('rebuild_fidelity',{});nodes={n['id']:n for n in scene.nodes};issues=[]
    for ident,expected in contract.get('nodes',{}).items():
        parent=expected.get('parent')
        if parent and (parent not in nodes or ident not in nodes or not contains(nodes[parent]['rect'],nodes[ident]['rect'])):
            issues.append({'code':'source_parent_geometry','id':ident,'parent':parent})
    if issues:raise FigureError('rebuild_fidelity_geometry','生成后层级包络不符',issues=issues)
