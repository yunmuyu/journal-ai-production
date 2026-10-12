import {fileHash,readJson,sha256} from './core.mjs';

// Experimental, only for the AI just saved by this render call. Legacy stays full-read.
export function buildTrimGeometryReuse({plan,result,ai,drawResultFile,expectedSavedAiHash,expectedDrawResultHash}){
 if(plan.trimGeometryReuseExperiment!==true)return null;
 if(plan.route!=='vector-reletter')throw Error('Trim geometry reuse requires vector-reletter');
 if(result.ok!==true||result.pathGeometryPreserved!==true)throw Error('Draw geometry protection did not pass');
 if((result.mechanicalIssues||[]).length)throw Error('Fix draw mechanical issues before experimental trim');
 if(!Array.isArray(result.snapshot?.pathGeometry))throw Error('Draw full path geometry missing');
 if(!expectedSavedAiHash||fileHash(ai)!==expectedSavedAiHash)throw Error('Just-saved AI changed before trim');
 if(!expectedDrawResultHash||fileHash(drawResultFile)!==expectedDrawResultHash)throw Error('Draw evidence changed before trim');
 const saved=readJson(drawResultFile);
 if(saved.ok!==true||saved.pathGeometryPreserved!==true||JSON.stringify(saved.snapshot?.pathGeometry)!==JSON.stringify(result.snapshot.pathGeometry))throw Error('Saved draw evidence differs from current render result');
 if(saved.closeError||saved.restoreError)throw Error('Draw session did not close cleanly');
 const paths=JSON.parse(JSON.stringify(result.snapshot.pathGeometry));
 for(const p of paths){if(!Array.isArray(p.points))throw Error('Incomplete path geometry');for(const point of p.points){if(!Array.isArray(point)||point.length!==2||point[0].length!==4||point[1].length!==2||!point.flat().every(Number.isFinite))throw Error('Invalid control point');}}
 return {kind:'controlled-trim-v1',operation:'artboard-only',source:ai,savedAiHash:expectedSavedAiHash,drawResultHash:expectedDrawResultHash,pathGeometryHash:sha256(JSON.stringify(paths)),pathGeometry:paths};
}
