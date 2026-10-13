import {normalizeAttribute} from './decision-attributes.mjs';
export const BATCH_SIZE=10;
export const BASIC_ATTRIBUTES=['kind','split','method','columns'];
export const basicConfirmed=f=>!f.decision?.stale&&(f.decision?.attributes?.kind?f.decision.attributes.kind.state==='confirmed':f.basicClassification?.confirmed===true);
export const attributeConfirmed=(f,key)=>!f.decision?.stale&&(key==='kind'?basicConfirmed(f):f.decision?.attributes?.[key]?.state==='confirmed');
const splitValue=f=>normalizeAttribute('split',f.decision?.attributes?.split?.value??f.aiProposal?.fields?.split?.value);
export const needsSplit=f=>f.decision?.attributes?.split?.value?(f.decision.attributes.split.state!=='confirmed'||splitValue(f)!=='整体1张'):!!(f.candidateDeliveryPreview?.managesColumns||f.deliveryPreview?.managesColumns||f.candidateDeliveryPreview?.outputs?.length>1||f.deliveryPreview?.outputs?.length>1||f.aiProposal?.candidateDelivery?.numbers?.length>1||splitValue(f)!=='整体1张');
export const deliveryManagesColumns=f=>needsSplit(f)&&(!f.decision?.attributes?.split?.value||!['整体1张','待判断'].includes(splitValue(f)))&&!!(f.candidateDeliveryPreview?.managesColumns||f.deliveryPreview?.managesColumns);
export const preReviewComplete=f=>f.productionComplete===true||(!f.decision?.stale&&((!Object.keys(f.decision?.attributes||{}).length&&f.decision?.state==='confirmed')||BASIC_ATTRIBUTES.filter(k=>k!=='split'||needsSplit(f)).filter(k=>k!=='columns'||!deliveryManagesColumns(f)).every(k=>attributeConfirmed(f,k))));
export function batchQueue(figures){return figures.filter(f=>!preReviewComplete(f));}
export function reviewPage(queue,page=0){const pages=Math.max(1,Math.ceil(queue.length/BATCH_SIZE)),index=Math.min(Math.max(0,page),pages-1);return {figures:queue.slice(index*BATCH_SIZE,(index+1)*BATCH_SIZE),page:index,pages,total:queue.length};}
export function figuresForAttribute(figures,key){return figures.filter(f=>!f.productionComplete&&(key==='kind'||key==='source'||basicConfirmed(f))&&(key!=='split'||needsSplit(f))&&(key!=='columns'||!deliveryManagesColumns(f)));}
