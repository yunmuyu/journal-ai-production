function validateTechnical(g){
 const text=(s)=>{if(typeof s!=='string'||!s.trim())throw Error('Non-empty source text required');};
 if(g.schemaVersion!==3||g.kind!=='technical'||![6,7,8].includes(g.fontSize))throw Error('Technical graph requires schema3 and 6/7/8pt');
 if(g.layout==='memoryMap'){
  text(g.title);if(!Array.isArray(g.boundaries)||g.boundaries.length<2||!Array.isArray(g.regions)||g.regions.length!==g.boundaries.length-1)throw Error('Memory boundaries/regions mismatch');
  let previous=-1;for(const b of g.boundaries){text(b.text);if(!Number.isFinite(b.position)||b.position<0||b.position>1||b.position<=previous)throw Error('Memory boundary order');previous=b.position;}
  if(g.boundaries[0].position!==0||previous!==1)throw Error('Memory endpoints must span 0..1');g.regions.forEach(text);
 }else if(g.layout==='sequence'){
  if(!Array.isArray(g.participants)||g.participants.length!==3||!Array.isArray(g.steps)||!g.steps.length)throw Error('Sequence requires three participants and ordered steps');g.participants.forEach(text);
  for(const step of g.steps){text(step.name);text(step.request);text(step.response);if(step.operation!==undefined)text(step.operation);}
  if(g.selfMessage!==undefined)text(g.selfMessage);
  if(g.phases)for(const p of g.phases){text(p.text);if(!Number.isInteger(p.first)||!Number.isInteger(p.last)||p.first<0||p.last>=g.steps.length||p.first>p.last)throw Error('Phase range invalid');}
 }else if(g.layout==='photoComparison'){
  text(g.title);if(!Array.isArray(g.panels)||g.panels.length<2||g.panels.length>3)throw Error('Two or three comparison panels required');let count;
  for(const p of g.panels){text(p.title);if(!p.image||typeof p.image.path!=='string'||!/[.]png$|[.]jpe?g$/i.test(p.image.path)||! /^[a-f0-9]{64}$/.test(p.image.sha256))throw Error('Image path and source SHA-256 required');if(!Array.isArray(p.sections)||!p.sections.length)throw Error('Comparison sections required');if(count!==undefined&&p.sections.length!==count)throw Error('Comparison section count mismatch');count=p.sections.length;for(const s of p.sections){text(s.title);text(s.text);}}
 }else throw Error('Unknown technical layout');
 return g;
}
module.exports={validateTechnical};
