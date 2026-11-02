import path from 'node:path';
import {pathToFileURL} from 'node:url';

export function activateRevision({rows,metadata,pending,link},record){
 const figure=rows.find(f=>f.id===record.figureId);
 if(!figure)throw Error('修订任务对应图件已不存在');
 if(!figure.previousOutputs?.length)figure.previousOutputs=figure.outputs;
 figure.revisionHistory=[...(figure.revisionHistory||[]),...figure.outputs];
 for(const o of record.result.outputs)metadata[o.path]={sha256:o.sha256,previewPath:o.preview,format:path.extname(o.path).slice(1).toUpperCase(),columnLabel:o.columnLabel,fontLabel:o.fontLabel};
 figure.outputs=record.result.outputs.map(o=>({number:o.number,file:link(pathToFileURL(o.path))}));
 pending[record.pendingKey||figure.author+'-'+figure.number]={addressedFeedbackRevision:record.feedbackRevision,outputs:record.result.outputs,note:record.result.summary};
 figure.notices=[{text:record.result.summary}];
}
