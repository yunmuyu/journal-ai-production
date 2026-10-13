export const BATCH_SIZE=10;
export const BASIC_ATTRIBUTES=['kind','split','method','columns'];
export const basicConfirmed=f=>!f.decision?.stale&&(f.decision?.attributes?.kind?.state==='confirmed'||f.basicClassification?.confirmed===true);
export const attributeConfirmed=(f,key)=>!f.decision?.stale&&(key==='kind'?basicConfirmed(f):f.decision?.attributes?.[key]?.state==='confirmed');
export const preReviewComplete=f=>f.productionComplete===true||(!f.decision?.stale&&(f.decision?.state==='confirmed'||BASIC_ATTRIBUTES.every(k=>attributeConfirmed(f,k))));
export function batchQueue(figures,attribute){return figures.filter(f=>!preReviewComplete(f)&&(attribute==='source'?f.decision?.sourceReview?.state!=='confirmed':!attributeConfirmed(f,attribute)&&(attribute==='kind'||basicConfirmed(f))));}
export function reviewPage(queue,page=0){const pages=Math.max(1,Math.ceil(queue.length/BATCH_SIZE)),index=Math.min(Math.max(0,page),pages-1);return {figures:queue.slice(index*BATCH_SIZE,(index+1)*BATCH_SIZE),page:index,pages,total:queue.length};}
