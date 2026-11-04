// A compound figure passes only after every output of the same version was viewed.
const viewerReviewedOutputs=new Map();
function viewerCompleteReview(item,ready,version){
 if(!item||!ready)return;
 const f=find(item.figureId),d=draft(f);
 if(f.previewCurrent===false||f.reviewVersion!==version||d.dirty||d.saving||d.loadingImages||d.error||d.text?.trim()||d.images?.length||d.points?.length)return;
 const key=f.id+':'+version;
 const seen=viewerReviewedOutputs.get(key)||new Set();
 seen.add(item.file.token);viewerReviewedOutputs.set(key,seen);
 if(f.status!=='终检通过'&&f.outputs.length&&f.outputs.every(o=>o.file&&seen.has(o.file.token)))return setAcceptance(f.id,true,version);
}
