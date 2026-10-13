import {normalizeAttribute} from './decision-attributes.mjs';
export const BATCH_SIZE=10;
export const BASIC_ATTRIBUTES=['split','method','columns'];
export const basicConfirmed=f=>!f.decision?.stale&&(f.decision?.attributes?.kind?f.decision.attributes.kind.state==='confirmed':f.basicClassification?.confirmed===true);
export const attributeConfirmed=(f,key)=>!f.decision?.stale&&f.decision?.attributes?.[key]?.state==='confirmed';
const splitValue=f=>normalizeAttribute('split',f.decision?.attributes?.split?.value??f.aiProposal?.fields?.split?.value);
export const needsSplit=f=>f.decision?.attributes?.split?.value?(f.decision.attributes.split.state!=='confirmed'||splitValue(f)!=='整体1张'):!!(f.candidateDeliveryPreview?.managesColumns||f.deliveryPreview?.managesColumns||f.candidateDeliveryPreview?.outputs?.length>1||f.deliveryPreview?.outputs?.length>1||f.aiProposal?.candidateDelivery?.numbers?.length>1||splitValue(f)!=='整体1张');
export const deliveryManagesColumns=f=>needsSplit(f)&&(!f.decision?.attributes?.split?.value||!['整体1张','待判断'].includes(splitValue(f)))&&!!(f.candidateDeliveryPreview?.managesColumns||f.deliveryPreview?.managesColumns);
export const excludedFromReview=f=>f.productionComplete===true||f.existingFinal===true||f.reviewExclusion?.confirmedBy==='user';
export const sourceIssue=f=>f.sourceAssessment?.matched===false||f.aiProposal?.fields?.sourceMatch?.certainty!=='verified'||f.decision?.sourceReview?.state==='needs-review'||!!f.decision?.resolutions?.sourceMatch;
export const deliveryWidthsReady=f=>attributeConfirmed(f,'columns')||!!((f.candidateDeliveryPreview||f.deliveryPreview)?.outputs?.length&&(f.candidateDeliveryPreview||f.deliveryPreview).outputs.every(o=>normalizeAttribute('columns',o.columns)!=='待判断'));
export const preReviewComplete=f=>excludedFromReview(f)||(!f.decision?.stale&&(!deliveryManagesColumns(f)||deliveryWidthsReady(f))&&BASIC_ATTRIBUTES.filter(k=>k!=='columns'||!deliveryManagesColumns(f)).every(k=>attributeConfirmed(f,k)));
export function batchQueue(figures){return figures.filter(f=>!preReviewComplete(f));}
export function authorBatches(queue){const groups=new Map();for(const f of queue){const key=f.articleId||f.author||f.id;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(f);}const batches=[];let current=[];for(const group of groups.values()){if(current.length&&current.length+group.length>BATCH_SIZE){batches.push(current);current=[];}current.push(...group);if(current.length>=BATCH_SIZE){batches.push(current);current=[];}}if(current.length)batches.push(current);return batches;}
export function reviewPage(queue,page=0){const batches=authorBatches(queue),pages=Math.max(1,batches.length),index=Math.min(Math.max(0,page),pages-1);return {figures:batches[index]||[],page:index,pages,total:queue.length};}
export function figuresForAttribute(figures,key){return figures.filter(f=>!excludedFromReview(f)&&(key!=='split'||needsSplit(f))&&(key!=='columns'||!deliveryManagesColumns(f)));}
