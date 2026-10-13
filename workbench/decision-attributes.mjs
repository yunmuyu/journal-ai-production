export const ATTRIBUTE_OPTIONS=Object.freeze({
 kind:Object.freeze(['流程/算法图','系统/模块框图','网络/拓扑图','电路/接线图','统计图表','曲线/波形/频谱','界面/代码截图','实物/设备照片','地图/空间图','结构/原理示意','表格','混合多子图','待判断']),
 columns:Object.freeze(['小单栏','单栏','双栏','待判断']),
 method:Object.freeze(['PS直出','矢量换字','半重绘','完整重绘','待判断']),
 split:Object.freeze(['整体1张','拆2张','拆3张及以上','待判断'])
});

export function normalizeAttribute(key,raw){
 if(!Object.hasOwn(ATTRIBUTE_OPTIONS,key))throw TypeError('未知属性');
 if(typeof raw!=='string')return '待判断';
 const value=raw.trim();
 if(ATTRIBUTE_OPTIONS[key].includes(value))return value;
 if(/(?:待判断|待确认|待核对|未核实|未知|证据不足|证据不够)/.test(value))return '待判断';
 if(key==='kind'){if(value==='待辨认')return '待判断';const found=ATTRIBUTE_OPTIONS.kind.filter(v=>v!=='待判断'&&value.includes(v));return found.length===1?found[0]:'待判断';}
 let matches;
 if(key==='columns'){
  matches=[['小单栏',/小单栏/],['单栏',/(?<!小)单栏/],['双栏',/双栏/]];
 }else if(key==='method'){
  matches=[['PS直出',/PS\s*(?:直出|直接处理)/i],['矢量换字',/矢量换字/],['半重绘',/(?:半重绘|局部重排|局部调整)/],['完整重绘',/完整重绘/]];
 }else{
  matches=[['整体1张',/(?:不拆分|整体(?:保留|交付|输出)?\s*(?:1|一)\s*(?:张|幅|个))/],
   ['拆2张',/(?:拆分(?:为|成)?|拆成|拆为|分成|分为|输出)\s*(?:2|两|二)\s*(?:张|幅|个)/],
   ['拆3张及以上',/(?:拆分(?:为|成)?|拆成|拆为|分成|分为|输出)\s*(?:[3-9]|三|四|五|六|七|八|九|多)\s*(?:张|幅|个)/]];
 }
 const found=matches.filter(([,pattern])=>pattern.test(value));
 return found.length===1?found[0][0]:'待判断';
}

export function figuresForScope(figures,scope){return scope?.startsWith('batch:')?figures.filter(f=>f.reviewBatch?.id===scope.slice(6)):figures;}


export function routingTaskBinding(figure){
 const d=figure.decision||{}, fields=d.fields||figure.aiProposal?.fields||{};
 const value=key=>normalizeAttribute(key,d.attributes?.[key]?.value??fields[key]?.value??fields[key]);
 const s=d.sourceReview||{};
 return {method:value('method'),columns:value('columns'),split:value('split'),sourceReview:JSON.stringify({state:s.state,text:s.text||'',choice:s.choice||'',attachments:s.attachments||[]}),deliveryText:d.deliveryReview?.text||'',sourceIdentity:JSON.stringify(figure.executionRouting?.sourceCheck||{}),scope:JSON.stringify(figure.executionRouting?.scope||{}),outputs:JSON.stringify(figure.deliveryPreview?.outputs||[])};
}

// Preparation is derived from reviewed inputs, never an execution permit or acceptance record.
export function buildRoutingTasks(figure,assets={}){
 const r=figure.executionRouting, p=r?.taskPreparation;
 if(!p)return {tasks:[],executionAllowed:false};
 const current=routingTaskBinding(figure), changed=Object.keys(current).filter(k=>current[k]!==p.binding?.[k]);
 const source=r.sourceCheck||{}, s=figure.decision?.sourceReview||{};
 const missing=[];
 if(!assets[source.sourceAsset])missing.push('原附件不可访问');
 if(!source.sha256||!source.wordHash)missing.push('原附件或Word哈希未登记');
 if(source.wordHash!==figure.sourceViews?.[0]?.wordHash)missing.push('最新Word已变化，需重核对应范围');
 if(s.state!=='confirmed'||s.text?.trim()||s.choice||s.attachments?.length)missing.push('图源审核有未解决事项');
 const stale=!!figure.decision?.stale||changed.length>0;
 const recipes=['image','vector','local-vector','native-chart','rebuild','compose'];
 const outputs=p.outputs||[], numbers=outputs.map(o=>o.number);
 const countOK=current.split==='整体1张'?outputs.length===1:current.split==='拆2张'?outputs.length===2:current.split==='拆3张及以上'?outputs.length>=3:false;
 if(!countOK||new Set(numbers).size!==numbers.length)missing.push('交付数量或编号与当前拆分要求不符');
 const tasks=outputs.map(o=>{
  const gaps=[...missing,...(o.missing||[])];
  if(!recipes.includes(o.recipe))gaps.push('尚无已支持的加工路线');
  if(o.recipe==='image'&&current.method!=='PS直出')gaps.push('加工范围不是PS直出，不能免除改动核验');
  if(!o.wordPart||!o.number||!o.columns||!o.steps?.length)gaps.push('交付对应范围、栏宽或操作清单未齐');
  return {id:figure.id+':'+o.number,number:o.number,wordPart:o.wordPart,columns:o.columns,recipe:o.recipe,steps:o.steps||[],missing:gaps,changed,
   state:stale?'needs-update':gaps.length?'missing':'prepared',
   generalChecks:['文件与导出数量','尺寸比例、裁切及清晰度','已确认的色彩规范'],
   specialChecks:o.recipe==='image'?[]:(r.scope?.checks||[]),
   executionAllowed:false};
 });
 return {tasks,executionAllowed:false,holdReason:'等待开始制作；当前仅为任务准备',changed};
}
