export function executionUncertain(error,bridge,resultExists){
 if(error.code==='ETIMEDOUT'||!resultExists)return true;
 return bridge?.stage!=='failed'||bridge.detail?.during!=='returned';
}
