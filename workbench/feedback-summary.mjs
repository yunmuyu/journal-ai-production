// Read-only projection of the existing authority, never a second task ledger.
export function feedbackSummary(records,{all=false}={}){
 return Object.entries(records.figures||{}).flatMap(([figureId,f])=>{
  const feedback=f.userFeedback;if(!feedback)return [];
  const resolution=f.feedbackResolution||{},pending=resolution.pending||[];
  const hasIssue=!!feedback.text?.trim()||!!feedback.attachments?.length;
  const accepted=f.userAcceptance?.accepted??feedback.accepted;
  const resolvedRevision=f.feedbackResolvedRevision;
  const current=Number.isInteger(resolvedRevision)&&resolvedRevision===feedback.revision&&pending.length===0;
  const reviewState=pending.length?'pending':hasIssue&&!current?(accepted?'accepted-needs-reconciliation':'pending'):current?'resolved':'none';
  if(!all&&['resolved','none'].includes(reviewState))return [];
  return [{figureId,status:f.status,...feedback,accepted,reviewState,resolution,sourceRevision:feedback.revision,action:accepted?'仅核对遗留意见；保留验收，不自动制作':'核对意见与当前成品后修订'}];
 });
}
