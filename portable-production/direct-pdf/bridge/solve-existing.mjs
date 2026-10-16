// Adapter for the existing uploaded layout solver. It must be installed with
// its actual repository dependencies, not an isolated .mjs copied at random.
// Usage: node solve-existing.mjs <path/to/constraint-layout.mjs> <scene.json> <result.json>
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
const [modulePath,inputPath,outputPath]=process.argv.slice(2);
try {
  if(!modulePath||!inputPath||!outputPath)throw Error('Usage: solve-existing.mjs SOLVER_MODULE INPUT OUTPUT');
  const input=JSON.parse(fs.readFileSync(inputPath,'utf8').replace(/^\uFEFF/,''));
  const {solveLayout}=await import(pathToFileURL(path.resolve(modulePath)).href);
  if(typeof solveLayout!=='function')throw Error('The configured module does not export solveLayout');
  const result=solveLayout(input,{budgetMs:input.budgetMs??100});
  const dest=path.resolve(outputPath);fs.mkdirSync(path.dirname(dest),{recursive:true});
  const temp=dest+'.tmp-'+process.pid;fs.writeFileSync(temp,JSON.stringify(result,null,2));fs.renameSync(temp,dest);
  console.log(JSON.stringify({status:result.status,output:dest,requiresFinalPdfReview:true}));
  if(result.status!=='solved')process.exitCode=2;
} catch(e) {console.error(JSON.stringify({status:'blocked',error:e.message,productionMutation:false}));process.exitCode=1;}
