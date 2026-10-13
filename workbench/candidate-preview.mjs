export function candidateDeliveryPreview(figure,register){
 const proposal=figure.aiProposal,delivery=proposal?.candidateDelivery;
 if(!delivery||!Array.isArray(delivery.numbers)||delivery.numbers.length<2)return null;
 const regions=proposal.regionEvidence||[];
 return {prototype:true,candidate:true,managesColumns:false,note:delivery.numbers.length+'张范围候选，未制作、待审核',explanation:delivery.basis+' 裁片只示意范围，共用标题、标签和图例仍需按方案处理。',outputs:delivery.numbers.map((number,index)=>{
  const part=proposal.candidateSourceParts?.find(p=>(!p.id||p.id===figure.id)&&String(p.number)===String(number));
  const region=regions.find(r=>r.id===figure.id&&String(r.candidateOutput)===String(index+1))||(part?{source:part.sourcePath,sourceHash:part.sourceSha256,path:part.previewPath,previewHash:part.previewSha256}:null);
  return {number:String(number),columns:'栏宽待审核',partLabel:region?'原图或裁片已变化，范围待重核':'对应区域待核',...(region?{asset:register(figure.id+'-candidate-output-'+number,region)}:{})};
 })};
}
