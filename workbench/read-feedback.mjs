import fs from 'node:fs';
import {root} from './model.mjs';
const records=JSON.parse(fs.readFileSync(root+'/production-results.json','utf8'));
const items=Object.entries(records.figures).filter(([,f])=>f.userFeedback&&(process.argv.includes('--all')||!f.userFeedback.accepted)).map(([id,f])=>({figureId:id,status:f.status,...f.userFeedback}));
console.log(JSON.stringify(items,null,2));
