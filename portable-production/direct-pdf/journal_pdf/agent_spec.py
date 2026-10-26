"""Compile an Agent's DATA-ONLY semantic response into existing render specs.
Coordinates, crop identities and source paths come only from bound evidence.
"""
from __future__ import annotations
import copy,math
from .common import FigureError,contains,digest_json,safe_name
from .editorial import group_number
from .ingest_geometry import union_rect

PROTOCOL='journal-pdf-agent/1'


def require(condition,code,message,**details):
    if not condition:raise FigureError(code,message,**details)


def lookup(rows,ref,kind='object'):
    found=[r for r in rows if r.get('id')==ref]
    require(len(found)==1,'candidate_ref_invalid','候选ID不存在或不唯一',ref=ref,kind=kind)
    return found[0]


def content(value):
    require(isinstance(value,str) and bool(value.strip()) and len(value)<4000,'semantic_text','需要非空原稿文字')
    return value


def validate_production_policy_exception(record,reply_sha256,source_sha256,size):
    """Validate binding, not approval authenticity. Only the production caller supplies this.
    Semantic replies cannot grant themselves a design-size policy exception.
    """
    fields={'reply_sha256','source_sha256','design_font_size_pt','reason','evidence_ref'}
    require(isinstance(record,dict) and set(record)==fields,'production_policy_exception_schema',
            '制作字号例外须单独提供回复/来源哈希、字号、具体原因和外部依据引用')
    require(all(isinstance(record[k],str) and record[k].strip() for k in ('reason','evidence_ref')),
            'production_policy_exception_evidence','制作字号例外缺少具体原因或外部依据引用')
    require(all(isinstance(record[k],str) and len(record[k])==64 and all(c in '0123456789abcdef' for c in record[k])
                for k in ('reply_sha256','source_sha256')),'production_policy_exception_binding','制作字号例外需要有效的SHA256绑定')
    declared=record['design_font_size_pt']
    require(isinstance(declared,(int,float)) and not isinstance(declared,bool) and math.isfinite(declared)
            and 6<=declared<8,'production_policy_exception_size','字号例外只接受6至不足8pt的有限数值')
    require(record['reply_sha256']==reply_sha256 and record['source_sha256']==source_sha256
            and declared==size,'production_policy_exception_binding','制作字号例外未绑定当前语义回复、来源或设计字号')
    return copy.deepcopy(record)


def compile_reply_figure(reply,source,page,*,production_policy_exception=None):
    require(isinstance(reply,dict),'semantic_schema','图件回复必须是对象')
    allowed={'id','author','source_id','page_id','kind','review','axis_ref','x_ticks','y_ticks','x_title','y_title',
             'legend_rows','mask_review','chart_ref','accept_source_text_hints','series_pairs','nodes','edges',
             'outline_chart','direction','scope_refs','scope_reason','ignored_texts','ignored_ticks','policy','model','structure','tree_layout','root_vertical'}
    require(not set(reply)-allowed,'semantic_unknown_fields','回复含未允许字段；不接受路径/命令/自定义坐标',fields=sorted(set(reply)-allowed))
    id=safe_name(reply['id']);author=safe_name(reply.get('author','未归属'))
    review=reply.get('review',{})
    require(review.get('source_checked') is True and review.get('labels_checked') is True,'source_review_required','Agent须先看原稿并核对文字，不把检测候选当事实')
    policy=reply.get('policy',{})
    require(isinstance(policy,dict),'policy_schema','出版参数须为对象')
    require(not set(policy)-{'column','design_font_size_pt'},'policy_unknown','入口不允许隐式扩展出版参数')
    policy={'column':'single','design_font_size_pt':8}|policy
    require(policy['column'] in ('single','double'),'column_policy','单/双栏须明确；不隐式改双栏')
    size=policy['design_font_size_pt']
    require(isinstance(size,(int,float)) and not isinstance(size,bool) and math.isfinite(size) and 6<=size<=8,'font_policy','字号须为6—8pt有限数')
    font_basis={'design_font_size_pt':size,'basis':'default-8pt'}
    if size<8:
        require(production_policy_exception is not None,'production_font_policy_required',
                '语义入口必须从8pt测量完整布局；降低设计字号须由制作调用方另行提供绑定当前回复和来源的政策例外',
                requested_design_font_size_pt=size,default_design_font_size_pt=8)
        font_basis={'design_font_size_pt':size,'basis':'explicit-production-policy-exception',
                    'exception':validate_production_policy_exception(production_policy_exception,digest_json(reply),source['sha256'],size)}
    else:
        require(production_policy_exception is None,'production_policy_exception_unused','8pt默认设计不应绑定降字号例外')
    if reply.get('model') == 'grouped-chains': _preflight_group_dashes(reply)
    base={'version':1,'id':id,'author':author,'policy':policy,
        'sources':[{'path':source['snapshot'],'sha256':source['sha256'],'role':'original'}],
        'ingest_provenance':{'source_id':source['id'],'page_id':page['id'],'reply_hash':digest_json(reply),
             'geometry_origin':'bound-native-or-detected-candidate-IDs','source_content_review':review,
             'source_file_sha256':source['sha256'],'production_font_policy':font_basis}}
    kind=reply.get('kind')
    if 'tree_layout' in reply or 'root_vertical' in reply:
        require(kind=='diagram' and reply.get('model')=='tree','tree_options','树布局选项仅用于tree')
    if kind=='raster-chart':return _raster(reply,source,page,base)
    if kind=='svg-chart':return _svg(reply,source,page,base)
    if kind=='outlined-svg-chart':return _outline_chart(reply,source,page,base)
    if kind=='diagram':
        if reply.get('model')=='grouped-chains':return _grouped_chains(reply,source,page,base)
        if reply.get('model') and reply['model']!='graph':return _structured(reply,source,page,base)
        return _diagram(reply,source,page,base)
    raise FigureError('semantic_kind','未支持的语义类型',kind=kind)


def _ticks(rows,candidates):
    require(isinstance(rows,list) and 1<=len(rows)<=150,'tick_count','每轴需要1—150个确认刻度')
    refs=[r.get('ref') for r in rows]
    require(len(refs)==len(set(refs)),'duplicate_tick_ref','重复刻度ID')
    out=[]
    for row in rows:
        require(not set(row)-{'ref','text','number','suffix','power10'},'tick_schema','刻度只填候选ID及原文、已核对的数学语义，不填坐标')
        q=lookup(candidates,row['ref'],'tick');text=content(row['text']);d={'text':text,'position':q['position']}
        if 'power10' in row:
            from .charts import tick_content
            tick_content(row)
            d['power10']=row['power10']
        elif 'number' in row:
            require(str(row['number'])+row.get('suffix','')==text,'tick_components','刻度数值与后缀不等于原文')
            group_number(str(row['number']));d|={'number':str(row['number']),'suffix':row.get('suffix','')}
        else:group_number(text)
        out.append(d)
    return sorted(out,key=lambda r:r['position'])


def _raster(reply,source,page,base):
    require(page['kind']=='raster','source_kind_mismatch','位图路线不能默默替代矢量源')
    require(reply['review'].get('inward_ticks_confirmed') is True,'raster_tick_direction_pending','当前位图自动输出要求核对刻线朝内；外向刻线不能被版位裁掉')
    g=page['geometry'];axis=lookup(g['axes'],reply.get('axis_ref'),'axis')
    xt=_ticks(reply.get('x_ticks'),axis['x_ticks']);yt=_ticks(reply.get('y_ticks'),axis['y_ticks'])
    selected=reply.get('legend_rows',[])
    require(1<=len(selected)<=30,'legend_count','本路线需1—30项图例；无图例需另行适配')
    entries=[];rects=[];sids=[]
    for row in selected:
        require(not set(row)-{'ref','label','series_id'},'legend_schema','图例只填候选ID、系列ID与原文')
        q=lookup(g['legend_rows'],row['ref'],'legend-row');sid=safe_name(row['series_id']);sids.append(sid)
        entries.append({'id':sid,'label':content(row['label']),'swatch_clip':q['swatch_clip']});rects.append(q['rect'])
    require(len(sids)==len(set(sids)) and len({r['ref'] for r in selected})==len(selected),'legend_binding_duplicate','系列或图例候选重复')
    mask_review=reply.get('mask_review',{})
    require(mask_review.get('approved_empty_background') is True and bool(mask_review.get('reason')),
        'mask_semantics_required','原图例清除需逐图确认其背景没有数据；候选矩形不是授权')
    all_ticks=axis['x_ticks']+axis['y_ticks'];all_ids={t['id'] for t in all_ticks}
    expected={t['id'] for t in all_ticks if t.get('label_candidate')}
    selected_ids={t['ref'] for t in reply['x_ticks']+reply['y_ticks']}
    ignored=reply.get('ignored_ticks',[])
    require(isinstance(ignored,list) and all(isinstance(t,dict) and set(t)=={'ref','reason'} and t['ref'] in all_ids and isinstance(t['reason'],str) and t['reason'].strip() for t in ignored),
        'ignored_tick_evidence','忽略刻度候选需有效ID与具体原因')
    ignored_ids={t['ref'] for t in ignored}
    require(not ignored_ids & selected_ids,'tick_used_and_ignored','刻度候选不能同时保留与忽略')
    require(not (expected-selected_ids-ignored_ids),'unaccounted_tick_candidates','带标签的刻度候选遗漏，需补全或说明误检依据',
        object_ids=sorted(expected-selected_ids-ignored_ids))
    base['ingest_provenance']['ignored_tick_candidates']=ignored
    r=union_rect(rects);pad=3;f=axis['frame'];mask=[max(f[0]+2,r[0]-pad),max(f[1]+2,r[1]-pad),min(f[2]-2,r[2]+pad),min(f[3]-2,r[3]+pad)]
    require(contains(mask,r),'legend_mask_clip','图例候选接近轴线，禁止裁掉或涂抹坐标轴')
    # The exact approved mask is derived from selected evidence, not an arbitrary Agent rectangle.
    return base|{'kind':'chart','source_kind':'raster','source':source['snapshot'],'plot_clip':axis['plot_clip'],
        'axis_frame_source':axis['frame'],'x_ticks':xt,'y_ticks':yt,'x_title':content(reply['x_title']),'y_title':content(reply['y_title']),
        'series':entries,'masks':[mask],'approved_empty_regions':[mask],
        'legend_safe_region':mask,'legend_placement':'outside-top','legend_frame':False,
        'mask_semantic_evidence':mask_review,'plot_width_pt':180,
        'tick_length_source_units':0,'tick_source_evidence':{'mode':'geometry-candidate-confirmed','axis_id':axis['id'],
            'note':'detected ticks bound by identity; zero exterior tick length only for inward-tick source; reviewer must confirm'},
        'ingest_notes':['图例确认原背景安全后置于绘图区上方；保留样符，不恢复原先被遮挡曲线']}


def _svg(reply,source,page,base):
    require(page['kind']=='svg','source_kind_mismatch','SVG路线只接受原SVG')
    c=lookup(page['chart_candidates'],reply.get('chart_ref'),'chart')
    require(reply.get('accept_source_text_hints') is True,'svg_text_hint_review','转曲SVG注释只是提示；须看图确认后接受')
    require(c['x_ticks'] and c['y_ticks'] and set(c['titles'])=={'x','y'},'svg_chart_incomplete','缺少可绑定刻度/轴题')
    for t in c['x_ticks']+c['y_ticks']:group_number(t['text_hint'])
    pairs=reply.get('series_pairs',[])
    require(len(pairs)==len(c['legend_rows']),'svg_series_coverage','图例绑定不完整')
    require(len({p['row_ref'] for p in pairs})==len(pairs),'svg_duplicate_legend','图例重复绑定')
    require({p['source_group'] for p in pairs}==set(c['series_groups']) and len(pairs)==len(c['series_groups']),
        'svg_series_identity','当前支持一条原系列对应一项图例，需全量明确绑定')
    entries=[]
    for p in pairs:
        row=lookup(c['legend_rows'],p['row_ref'],'legend-row')
        entries.append({'id':p['source_group'],'label':row['text_hint'],'source_group':p['source_group'],
            'swatch_group':row['swatch_group'],'swatch_clip':row['swatch_clip']})
    require(c['tick_length'] is not None,'svg_tick_geometry','没有可靠刻线几何')
    return base|{'kind':'chart','source_kind':'svg','source':source['snapshot'],'axes_id':c['axes_id'],
        'plot_clip':c['plot_clip'],'axis_frame_source':c['frame'],'plot_width_pt':180,
        'x_ticks':[{'text':t['text_hint'],'position':t['position']} for t in c['x_ticks']],
        'y_ticks':[{'text':t['text_hint'],'position':t['position']} for t in c['y_ticks']],
        'x_title':c['titles']['x']['text_hint'],'y_title':c['titles']['y']['text_hint'],
        'series':entries,'legend_source_id':c['legend_id'],'legend_placement':'outside-top','legend_frame':False,
        'protected_path_points':c['protected_path_points'],'tick_length_source_units':c['tick_length'],
        'restore_verified_tick_stubs':True,'tick_source_evidence':{'mode':'original-svg-use-and-def','axes_id':c['axes_id']}}


def _diagram(reply,source,page,base):
    require(reply['review'].get('topology_checked') is True,'topology_review_required','框图必须核对箭头/连接关系')
    nodes=reply.get('nodes',[]);edges=reply.get('edges',[])
    require(isinstance(nodes,list) and 1<=len(nodes)<=80 and isinstance(edges,list),'diagram_schema','节点或连接列表无效')
    originals=page.get('objects',[]);byid={r['id']:r for r in originals};used=[];out=[]
    for n in nodes:
        require(not set(n)-{'id','ref','refs','join','text','shape'} and ('ref' in n)!=('refs' in n)
                and ('join' not in n or 'refs' in n),'diagram_node_schema','节点只能绑定单个ref或原生文字refs，不接受手写坐标')
        ident=safe_name(n['id']);ref=n.get('ref');shape=n.get('shape','rectangle')
        if page['kind']=='raster':
            require('refs' not in n,'diagram_node_schema','位图节点只能绑定一个候选区域')
            q=lookup(page['geometry']['shapes']+page['geometry']['regions'],ref,'node-region');text=content(n.get('text'));used.append(ref)
        else:
            refs=n['refs'] if 'refs' in n else [ref]
            if 'refs' in n:
                require(isinstance(refs,list) and bool(refs) and all(isinstance(r,str) for r in refs)
                        and n.get('join','\n') in ('',' ','\n'),
                        'text_join','原生文字片段列表不能为空，只允许明确的拼接方式')
                require(len(refs)==len(set(refs)),'duplicate_node_ref','同一节点不可重复引用原稿文字')
            texts=[]
            for native_ref in refs:
                q=lookup(originals,native_ref);require(bool(q.get('text')),'native_text_missing','所选原生对象没有文字，不凭空生成')
                texts.append(q['text']);used.append(native_ref)
            text=n.get('join','\n').join(texts)
            if 'text' in n:require(n['text']==text,'native_text_changed','原生文字不允许静默改写；需要另行内容修订证据')
        require(shape in ('rectangle','diamond','roundrect','terminator','ellipse','inputOutput'),'shape_not_supported','特殊形状需明确适配',shape=shape)
        out.append({'id':ident,'text':text,'shape':shape})
    require(len(used)==len(set(used)),'duplicate_node_ref','同一原稿对象不能无依据拆成重复节点')
    # Selective figure extraction must name its exact semantic scope; not a claim of whole-page/whole-paper completeness.
    scope=reply.get('scope_refs')
    if page['kind']!='raster':
        alltexts={r['id'] for r in originals if r.get('text')}
        if scope is None:scope=list(alltexts)
        else:
            require(bool(reply.get('scope_reason')),'scope_reason_required','从多图页面选取范围需说明依据')
            require(set(scope)<=alltexts,'scope_ref_invalid','所选范围不是可读文字对象')
        ignored=reply.get('ignored_texts',[])
        require(all(isinstance(q,dict) and q.get('reason') and q.get('ref') in scope for q in ignored),'ignored_text_evidence','忽略文字需对象ID及具体理由')
        ignored_ids={q['ref'] for q in ignored}
        require(set(used)<=set(scope),'used_outside_scope','节点超出已声明图件范围')
        # Edge labels can bind to native text too, so they must be counted as used.
        for e in edges:
            if e.get('label_ref'):
                q=lookup(originals,e['label_ref']);require(bool(q.get('text')),'edge_label_empty','连接标签对象无文字');used.append(e['label_ref'])
        require(len(used)==len(set(used)),'duplicate_node_ref','同一原稿文字不能同时作为节点或连接标签')
        require(set(used)<=set(scope),'used_outside_scope','连接标签超出已声明图件范围')
        require(not (set(used)&ignored_ids),'used_and_ignored','文字不能同时使用和忽略')
        missing=set(scope)-set(used)-ignored_ids
        require(not missing,'unaccounted_source_text','选定图件中有文字未解释；不默默漏字',object_ids=sorted(missing))
    nids={n['id'] for n in out};eout=[]
    for i,e in enumerate(edges):
        require(not set(e)-{'id','from','to','label','label_ref','return_edge','arrow','both','dash','from_port','to_port','ref'},'edge_schema','连接只描述语义，不填坐标')
        require(e.get('from') in nids and e.get('to') in nids,'edge_endpoint','连接节点不存在',edge=i)
        ee={k:v for k,v in e.items() if k not in ('label_ref','ref')};ee.setdefault('id','edge-'+str(i+1))
        if page['kind'] != 'raster':
            require(not e.get('label') or bool(e.get('label_ref')), 'native_edge_label_unbound',
                    '原生连接标签必须绑定原稿文字，不接受凭空转录')
            if e.get('label_ref') and 'label' in e:
                require(e['label'] == byid[e['label_ref']]['text'], 'native_text_changed',
                        '原生连接标签不允许静默改写')
        if e.get('label_ref'):ee['label']=byid[e['label_ref']]['text']
        if e.get('ref'):
            q=lookup(originals,e['ref'],'connector')
            require(q['kind']=='native-connector','connector_ref','不是原生连接对象')
            # Native connector IDs cannot be contradicted merely because a rendered line looks nearby.
            fr,to=q.get('from_ref'),q.get('to_ref')
            if fr and to:
                endpoints=[next(n for n in nodes if n['id']==node_id) for node_id in (e['from'],e['to'])]
                require(all('ref' in n for n in endpoints),'native_topology_ambiguous','多段文字节点无法唯一绑定原生连接端点')
                mapping={n['id']:n['ref'] for n in endpoints}
                actual=(mapping[e['from']],mapping[e['to']])
                require(set(actual)=={fr,to},'native_topology_mismatch','原生连接绑定与Agent语义不一致')
                head=q.get('head','none')!='none';tail=q.get('tail','none')!='none'
                # OOXML headEnd decorates the starting endpoint, tailEnd the ending endpoint.
                # Only arrow-shaped decorations prove direction; a circle is not an arrow.
                directed={'triangle','stealth','arrow'}
                ha=q.get('head') in directed;ta=q.get('tail') in directed
                if ha != ta:
                    expected=(to,fr) if ha else (fr,to)
                    require(actual==expected and e.get('arrow',True) is True and not e.get('both',False),
                        'native_arrow_direction_mismatch','原生箭头方向不可倒转、删除或变成双向')
                elif ha and ta:
                    require(e.get('arrow',True) is True and e.get('both') is True,
                        'native_arrow_direction_mismatch','原生双向箭头必须明确保留')
                elif not head and not tail:
                    require(e.get('arrow') is False and not e.get('both',False),
                        'native_arrow_direction_mismatch','原生无箭头连接不能默认添加箭头')
        eout.append(ee)
    return base|{'kind':'graph','nodes':out,'edges':eout,'direction':reply.get('direction','TB'),
        'source_scope':{'refs':scope or used,'reason':reply.get('scope_reason'),'ignored':reply.get('ignored_texts',[])}}


def _structured(reply,source,page,base):
    """Measured existing diagram templates, populated by native source references.
    No per-author drawing code or manual layout coordinates are accepted.
    """
    require(reply['review'].get('topology_checked') is True,'topology_review_required','必须核对分组/连接关系')
    model=reply.get('model')
    allowed={
        'cycle':{'stages','reject_labels','decision','end'},
        'layered':{'stages','support','down_labels','return_label'},
        'fanout':{'top','bottom','items'},
        'tree':{'root','branches'},
    }
    require(model in allowed,'structured_model','尚未适配的语义模板',model=model)
    data=reply.get('structure',{})
    require(isinstance(data,dict) and set(data)==allowed[model],'structured_fields','语义模板缺少字段或夹带几何参数',expected=sorted(allowed[model]))
    tree_options={}
    if 'tree_layout' in reply or 'root_vertical' in reply:
        require(model=='tree','tree_options','树布局选项仅用于tree')
        require(reply.get('tree_layout','right') in ('right','bilateral'),'tree_layout','树布局须为right或bilateral')
        require(isinstance(reply.get('root_vertical',False),bool),'tree_root_orientation','root_vertical须为布尔值')
        tree_options={'tree_layout':reply.get('tree_layout','right'),'root_vertical':reply.get('root_vertical',False)}
    raster=page['kind']=='raster'
    objects=(page['geometry']['shapes']+page['geometry']['regions']) if raster else page['objects'];used=[]
    def resolve(v):
        if isinstance(v,list):return [resolve(x) for x in v]
        require(isinstance(v,dict),'structured_leaf','文字必须来自原生对象ref，不接受临时写图代码')
        if raster and set(v)=={'ref','text'}:
            lookup(objects,v['ref']);used.append(v['ref']);return content(v['text'])
        if raster and ('ref' in v or 'refs' in v):
            raise FigureError('raster_transcription_required','位图模板叶子需候选ref和核对过的原文字text')
        if set(v)=={'ref'}:
            q=lookup(objects,v['ref']);require(bool(q.get('text')),'native_text_missing','引用对象没有文字');used.append(v['ref']);return q['text']
        if set(v)<= {'refs','join'} and 'refs' in v:
            require(isinstance(v['refs'],list) and v.get('join','\n') in ('',' ','\n'),'text_join','只允许明确原文片段拼接')
            return v.get('join','\n').join(resolve({'ref':r}) for r in v['refs'])
        extras={'side','wrap_chars'} if model=='tree' and tree_options.get('tree_layout')=='bilateral' else set()
        require(set(v)<={'title','items','text','children'}|extras,'structured_nested_fields','分组只接受已支持的语义字段')
        out={}
        for k,x in v.items():
            if k=='side':
                require(x in ('left','right'),'tree_side','side须为left或right');out[k]=x
            elif k=='wrap_chars':
                require(isinstance(x,int) and not isinstance(x,bool) and 1<=x<=20,'tree_wrap','中文换行宽度须为1—20');out[k]=x
            else:out[k]=resolve(x)
        return out
    resolved={k:resolve(v) for k,v in data.items()}
    scope=reply.get('scope_refs') or (list(used) if raster else [q['id'] for q in objects if q.get('text')])
    if reply.get('scope_refs'):require(bool(reply.get('scope_reason')),'scope_reason_required','选择页面局部需记录范围依据')
    require(set(scope)<={q['id'] for q in objects if raster or q.get('text')},'scope_ref_invalid','范围引用不是当前源文字/候选区域')
    require(len(used)==len(set(used)),'duplicate_node_ref','同一原稿文字不无依据重复')
    ignored=reply.get('ignored_texts',[])
    require(all(q.get('reason') and q.get('ref') in scope for q in ignored),'ignored_text_evidence','忽略项需理由')
    require(set(used).isdisjoint({q['ref'] for q in ignored}) and set(used)|{q['ref'] for q in ignored}==set(scope),
        'unaccounted_source_text','选定图件文字有遗漏、重复或越界',missing=sorted(set(scope)-set(used)-{q['ref'] for q in ignored}))
    return base|{'kind':model,**resolved,**tree_options,'source_scope':{'refs':scope,'reason':reply.get('scope_reason'),'ignored':ignored},
        'ingest_notes':['分组/层级由Agent核对，原生文字绑定ID，位图逐节点转写；布局坐标由既有测字模板生成']}


def _grouped_chains(reply, source, page, base):
    """Reuse graph native-text and connector binding, including container titles."""
    from .grouped_chains import validate_grouped_chains
    require('direction' not in reply, 'grouped_chains_schema', '方向须逐容器声明，不能同时设置全图方向')
    structure = reply.get('structure')
    require(isinstance(structure, dict) and set(structure) == {'groups', 'bridge'},
            'grouped_chains_schema', '分组链仅接受groups与bridge，不接受坐标、间距或字号')
    require(isinstance(structure['groups'], list) and len(structure['groups']) == 2,
            'grouped_chains_schema', '分组链须有两个容器')
    extended = copy.deepcopy(reply)
    extended['nodes'] = copy.deepcopy(reply.get('nodes', []))
    groups = []
    style_bindings = {}
    for group in structure['groups']:
        require(isinstance(group, dict) and {'id', 'title', 'direction', 'nodes'} <= set(group) <= {'id', 'title', 'direction', 'nodes', 'dash', 'style_ref'},
                'grouped_chains_schema', '分组仅接受ID、绑定标题、方向、成员和可选源线型')
        title = group['title']
        require(isinstance(title, dict) and bool(title) and set(title) <= {'ref', 'refs', 'join', 'text'},
                'grouped_chains_title', '容器标题必须绑定源文字，不接受手写替换标题')
        require(isinstance(group['id'], str) and group['id'] == safe_name(group['id']),
                'grouped_chains_schema', '容器ID无效')
        require(group['id'] not in [n.get('id') for n in extended['nodes']],
                'grouped_chains_schema', '容器与节点ID不得重复')
        extended['nodes'].append({'id': group['id'], **title})
        resolved_group = copy.deepcopy(group)
        if 'style_ref' in group:
            style_bindings[group['id']] = _group_dash_binding(group, source, page)
            resolved_group.pop('style_ref')
        groups.append(resolved_group)
    # Counts every title exactly once in the same source scope as node and edge text.
    compiled = _diagram(extended, source, page, base)
    title_ids = {g['id'] for g in groups}
    for group in groups:
        group['title'] = next(n['text'] for n in compiled['nodes'] if n['id'] == group['id'])
    compiled['nodes'] = [n for n in compiled['nodes'] if n['id'] not in title_ids]
    compiled.update(kind='grouped-chains', groups=groups, bridge=copy.deepcopy(structure['bridge']), group_style_bindings=style_bindings)
    validate_grouped_chains(compiled)
    return compiled


def _group_dash_binding(group, source, page):
    """Verify only dash pattern against an existing native rectangle, not membership."""
    import re
    native = lookup(page.get('objects', []), group['style_ref'], 'container-style')
    require(native.get('kind') == 'native-path' and native.get('shape_hint') == 'rectangle',
            'grouped_chains_style_source', '线型绑定仅支持已提取的原生矩形路径')
    raw = native.get('geometry', {}).get('dashes')
    match = re.fullmatch(r'\s*\[([^]]*)\]\s*([+\-0-9.eE]+)\s*', raw) if isinstance(raw, str) else None
    require(match is not None, 'grouped_chains_style_source', '原生路径未提供可核对的虚线数列及相位')
    try:
        pattern = [float(value) for value in match.group(1).split()]
        phase = float(match.group(2))
    except ValueError:
        raise FigureError('grouped_chains_style_source', '原生路径虚线数列无效')
    require(math.isfinite(phase) and phase == 0, 'grouped_chains_style_source', '非零虚线相位尚未适配，不默默归零')
    from .scene import validate_node_dash
    if pattern: validate_node_dash(pattern, id=group['id'])
    declared = group.get('dash', [])
    require(declared == pattern, 'grouped_chains_style_mismatch', '声明虚线与绑定源路径不符，不覆盖源线型')
    return {'method': 'native-path-dash-match', 'mechanically_verified': True,
            'verified_property': 'dash-pattern-only', 'source_id': source['id'],
            'source_sha256': source['sha256'], 'object_ref': group['style_ref'], 'dash_phase_pt': phase}


def _preflight_group_dashes(reply):
    # Reject nonfinite patterns before reply hashing (which requires valid JSON).
    from .scene import validate_node_dash
    structure = reply.get('structure')
    if isinstance(structure, dict) and isinstance(structure.get('groups'), list):
        for group in structure['groups']:
            if isinstance(group, dict) and 'dash' in group:
                validate_node_dash(group['dash'], id=group.get('id'))


def _outline_chart(reply,source,page,base):
    from .source_outline_chart import bind_registration
    require(page['kind']=='svg' and 'outline_inventory' in page,'outline_chart_evidence','缺少原SVG图元清单')
    require(reply['review'].get('outline_transcription_checked') is True and reply['review'].get('series_identity_checked') is True,
            'outline_chart_semantic_review','哈希不证明转曲文字或系列含义；须逐项视觉核对')
    inventory=page['outline_inventory']
    require(inventory['source_sha256']==source['sha256'],'outline_chart_source','图元清单与原稿不匹配')
    bound=bind_registration(inventory,reply.get('outline_chart'))
    return base|{'kind':'chart','source_kind':'registered-outline-svg','source':source['snapshot'],
                 'outline_chart_registration':bound['registration'],
                 **{k:bound[k] for k in ('plot_clip','axis_frame_source','x_ticks','y_ticks','x_title','y_title',
                      'figure_title','title_source_bbox','series','legend_safe_region','legend_original_region','protected_ink_boxes')},
                 'plot_width_pt':180,'legend_placement':'registered-source-region','legend_frame':True,
                 'tick_length_source_units':0,'restore_verified_tick_stubs':False,
                 'tick_source_evidence':{'mode':'registered-original-inward-lines','source_sha256':source['sha256']},
                 'ingest_notes':['转曲字已显式登记；哈希只证明对象身份，不替代原文/系列语义复核。']}
