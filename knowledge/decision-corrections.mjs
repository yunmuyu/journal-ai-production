// Read-only context from user-confirmed edits; never a second acceptance ledger.
export function correctionContext(production,figure){
 const same=production.figures?.[figure.id]?.productionDecision;
 const fields=[];
 for(const key of ['split','method','columns']){const a=same?.attributes?.[key];if(a?.state!=='confirmed')continue;fields.push({field:key,value:a.value,originalAIValue:a.originalAIValue,sourceFingerprint:same.aiProposal?.sourceFingerprint,history:a.history||[],evidence:'/figures/'+figure.id+'/productionDecision/attributes/'+key});}
 return {figureId:figure.id,confirmedConstraints:fields,sourceChanged:!!same&&same.aiProposal?.sourceFingerprint!==figure.aiProposal?.sourceFingerprint,limits:['用户已确认值是当前图约束，不能被新模型建议覆盖','来源发生实质变化时只重核受影响项目，不自动推翻','这是一张图的纠错记录，不证明其他图都应采用相同栏宽或路线']};
}
