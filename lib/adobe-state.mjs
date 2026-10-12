export function executionUncertain(error,bridge,resultExists){
 if(error.code==='ETIMEDOUT'||!resultExists)return true;
 return bridge?.stage!=='failed'||bridge.detail?.during!=='returned';
}
export function executionTimeoutMs(request){
 if(request.mode==='aggregate')return 360000;
 // Observed full before/after control-point scans completed cleanly after 465 seconds.
 if(request.mode==='render'&&request.plan?.route==='vector-reletter')return 600000;
 return 180000;
}
