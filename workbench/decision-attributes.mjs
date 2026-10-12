export const ATTRIBUTE_OPTIONS=Object.freeze({
 columns:Object.freeze(['小单栏','单栏','双栏','待判断']),
 method:Object.freeze(['PS直出','矢量换字','半重绘','完整重绘','待判断']),
 split:Object.freeze(['整体1张','拆2张','拆3张及以上','待判断'])
});

export function normalizeAttribute(key,raw){
 if(!Object.hasOwn(ATTRIBUTE_OPTIONS,key))throw TypeError('未知属性');
 if(typeof raw!=='string')return '待判断';
 const value=raw.trim();
 if(ATTRIBUTE_OPTIONS[key].includes(value))return value;
 if(/(?:待判断|待确认|待核对|未核实|未知|证据不足|证据不够)/.test(value))return '待判断';
 let matches;
 if(key==='columns'){
  matches=[['小单栏',/小单栏/],['单栏',/(?<!小)单栏/],['双栏',/双栏/]];
 }else if(key==='method'){
  matches=[['PS直出',/PS\s*直出/i],['矢量换字',/矢量换字/],['半重绘',/半重绘/],['完整重绘',/完整重绘/]];
 }else{
  matches=[['整体1张',/(?:不拆分|整体(?:保留|交付|输出)?\s*(?:1|一)\s*(?:张|幅|个))/],
   ['拆2张',/(?:拆分(?:为|成)?|拆成|拆为|分成|分为)\s*(?:2|两|二)\s*(?:张|幅|个)/],
   ['拆3张及以上',/(?:拆分(?:为|成)?|拆成|拆为|分成|分为)\s*(?:[3-9]|三|四|五|六|七|八|九|多)\s*(?:张|幅|个)/]];
 }
 const found=matches.filter(([,pattern])=>pattern.test(value));
 return found.length===1?found[0][0]:'待判断';
}
