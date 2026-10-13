import fs from 'node:fs';

// Reports measured collisions for visual review; it does not approve a figure.
export function labelGeometry(record) {
  const snapshot=record.adobe?.snapshot??record.report?.snapshot;
  if(!snapshot?.texts||!snapshot.artboard)throw Error('Native snapshot required');
  const overlaps=[];
  for(let i=0;i<snapshot.texts.length;i++)for(let j=i+1;j<snapshot.texts.length;j++){
    const a=snapshot.texts[i],b=snapshot.texts[j];
    if(!a.inkBounds||!b.inkBounds)continue;
    const dx=Math.min(a.inkBounds[2],b.inkBounds[2])-Math.max(a.inkBounds[0],b.inkBounds[0]);
    const dy=Math.min(a.inkBounds[1],b.inkBounds[1])-Math.max(a.inkBounds[3],b.inkBounds[3]);
    if(dx>0&&dy>0)overlaps.push({indices:[a.index,b.index],texts:[a.text,b.text],intersectionPt:[dx,dy]});
  }
  const [l,t,r,b]=snapshot.artboard;
  return {widthMm:(r-l)*25.4/72,heightMm:(t-b)*25.4/72,textCount:snapshot.texts.length,
    unmeasured:snapshot.texts.filter(t=>!t.inkBounds).map(t=>t.index),overlaps,
    requiresVisualReview:true};
}
if(process.argv[1]?.replaceAll('\\','/').endsWith('/label_geometry.mjs')){
  const file=process.argv[2];if(!file)throw Error('Usage: node label_geometry.mjs render.json');
  console.log(JSON.stringify(labelGeometry(JSON.parse(fs.readFileSync(file,'utf8'))),null,2));
}
