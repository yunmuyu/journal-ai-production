import fs from 'node:fs';
import {root} from './model.mjs';
import {feedbackSummary} from './feedback-summary.mjs';
const records=JSON.parse(fs.readFileSync(root+'/production-results.json','utf8'));
console.log(JSON.stringify(feedbackSummary(records,{all:process.argv.includes('--all')}),null,2));
