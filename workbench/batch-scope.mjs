export function catalogFor(config,batchHash){
 const catalog=batchHash===undefined?config.catalog:config.catalogs?.[batchHash]||(config.catalog?.batchHash===batchHash?config.catalog:null);
 if(!catalog||batchHash!==undefined&&catalog.batchHash!==batchHash)throw Error('未配置所请求批次，不能回退到其他批次');
 return catalog;
}
export function belongsToBatch(job,batchHash){
 return batchHash===undefined||(job.batchHash||job.key?.split(':')[0])===batchHash;
}
