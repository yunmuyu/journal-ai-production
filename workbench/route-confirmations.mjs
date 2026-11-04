import fs from 'node:fs';
import {createHash} from 'node:crypto';

const fileHash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const sourceBinding=figure=>{
 const s=figure.productionRoute?.sourceReview;
 if(!figure.id||!figure.articleId||!s?.archive?.sha256||!s?.word?.sha256||!s?.selected?.sha256)return null;
 return {figureId:figure.id,articleId:figure.articleId,archive:s.archive.sha256,word:s.word.sha256,selected:s.selected.sha256};
};

export function createRouteConfirmations(file){
 const records=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{version:1,figures:{}};
 if(records.version!==1||!records.figures||typeof records.figures!=='object')throw Error('制作决定记录格式错误');
 const hashes=new Map();
 return {
  get(figure){
   const saved=records.figures[figure.id];if(!saved)return null;
   const source=sourceBinding(figure),stale=JSON.stringify(source)!==JSON.stringify(saved.sourceBinding)||(figure.feedback?.revision??0)!==saved.feedbackRevision;
   return {...saved,stale};
  },
  save(figure,input){
   if(input?.baseVersion!==figure.reviewVersion)throw Error('图稿或批注已变化，请刷新后重新核对');
   if(input.method!=='完整重绘'||typeof input.evidence!=='string'||!input.evidence.trim()||input.evidence.length>2000)throw Error('制作决定或确认依据无效');
   const source=sourceBinding(figure);if(!source)throw Error('图件尚未绑定完整来源，不能确认路线');
   for(const key of ['archive','word','selected']){
    const ref=figure.productionRoute.sourceReview[key],stat=fs.statSync(ref.path),keyed=[ref.path,stat.size,stat.mtimeMs].join('|');
    const actual=hashes.get(keyed)??fileHash(ref.path);hashes.set(keyed,actual);
    if(actual!==ref.sha256)throw Error('制作决定图源已变化: '+key);
   }
   const prior=records.figures[figure.id];
   const saved={attributes:{method:{state:'confirmed',value:input.method}},sourceBinding:source,
    feedbackRevision:figure.feedback?.revision??0,confirmedReviewVersion:figure.reviewVersion,
    evidence:input.evidence,confirmedAt:new Date().toISOString(),revision:(prior?.revision??0)+1,
    history:prior?[...(prior.history??[]),{revision:prior.revision,attributes:prior.attributes,sourceBinding:prior.sourceBinding,evidence:prior.evidence,confirmedAt:prior.confirmedAt}]:[]};
   const next={...records,figures:{...records.figures,[figure.id]:saved}},tmp=file+'.'+process.pid+'.tmp';
   fs.writeFileSync(tmp,JSON.stringify(next,null,2)+'\n');fs.renameSync(tmp,file);records.figures=next.figures;
   return {...saved,stale:false};
  },
 };
}
