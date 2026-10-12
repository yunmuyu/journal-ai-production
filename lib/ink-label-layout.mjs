const isTick=role=>role==='x-tick'||role==='y-tick';
const isTitle=role=>role==='x-axis-title'||role==='y-axis-title';
const tickPeers=(rows,row,role)=>rows.filter(r=>r.role===role&&(row.plot==='all'||(row.plots||[row.plot]).includes(r.plot)));
const move=(row,dx,dy)=>({...row,offsetPt:[dx,dy],ink:row.ink.map((v,i)=>v+(i%2?dy:dx))});

export function positionInkLabels(rows,{tickGapPt=2.5,titleGapPt=3}={}){
 const ids=new Set();
 for(const row of rows){
  if(ids.has(row.id))throw Error('Duplicate label identity');ids.add(row.id);
  if(!Array.isArray(row.ink)||row.ink.length!==4||row.ink.some(v=>!Number.isFinite(v)))throw Error('Missing measured ink bounds');
  if(isTick(row.role)&&(!Array.isArray(row.anchor)||row.anchor.length!==2||row.anchor.some(v=>!Number.isFinite(v))))throw Error('Missing actual tick anchor');
 }
 const placed=rows.map(row=>{
  const [l,t,r,b]=row.ink,gap=row.gapPt??tickGapPt;
  if(row.role==='y-tick')return move(row,row.anchor[0]-gap-r,row.anchor[1]-(t+b)/2);
  if(row.role==='x-tick')return move(row,row.anchor[0]-(l+r)/2,row.anchor[1]-gap-t);
  return move(row,0,0);
 });
 return placed.map(row=>{
  if(!isTitle(row.role))return row;
  const yTitle=row.role==='y-axis-title',peers=tickPeers(placed,row,yTitle?'y-tick':'x-tick');
  if(!peers.length)throw Error('Axis title has no associated ticks');
  const gap=row.gapPt??titleGapPt;
  return yTitle?move(row,Math.min(...peers.map(p=>p.ink[0]))-gap-row.ink[2],0):move(row,0,Math.min(...peers.map(p=>p.ink[3]))-gap-row.ink[1]);
 });
}

export function verifyInkLabelGaps(rows,{tickGapPt=2.5,titleGapPt=3,tolerancePt=.03}={}){
 const gaps=rows.filter(r=>isTick(r.role)||isTitle(r.role)).map(row=>{
  let actual;
  if(row.role==='y-tick')actual=row.anchor[0]-row.ink[2];
  else if(row.role==='x-tick')actual=row.anchor[1]-row.ink[1];
  else{
   const yTitle=row.role==='y-axis-title',peers=tickPeers(rows,row,yTitle?'y-tick':'x-tick');
   if(!peers.length)throw Error('Axis title has no associated ticks');
   actual=yTitle?Math.min(...peers.map(p=>p.ink[0]))-row.ink[2]:Math.min(...peers.map(p=>p.ink[3]))-row.ink[1];
  }
  const expected=row.gapPt??(isTick(row.role)?tickGapPt:titleGapPt);
  return {id:row.id,role:row.role,plot:row.plot,actual,expected,ok:Math.abs(actual-expected)<=tolerancePt};
 });
 return {ok:gaps.every(g=>g.ok),gaps};
}

export function refineRasterInkLayout(plan,roles,snapshot,pixelSize){
 if((plan.crop||[]).some(v=>v!==0))throw Error('Cropped source requires mapped axis anchors');
 const [pixelW,pixelH]=pixelSize,W=plan.widthMm*72/25.4,H=(plan.heightMm??plan.widthMm*pixelH/pixelW)*72/25.4;
 const rows=roles.map(role=>{
  const index=role.overlayIndex??role.textIndex;
  const names=role.frameNames||['JFW_TEXT_'+(index+1)];
  const frames=names.map(name=>snapshot.texts.find(t=>t.name===name));
  if(!frames.length||frames.some(t=>!t)||frames.map(t=>t.text).join('\r')!==plan.texts[index].text)throw Error('Axis label identity mismatch');
  const ink=[Math.min(...frames.map(t=>t.inkBounds[0])),Math.max(...frames.map(t=>t.inkBounds[1])),Math.max(...frames.map(t=>t.inkBounds[2])),Math.min(...frames.map(t=>t.inkBounds[3]))];
  return {...role,id:index,ink,plot:Array.isArray(role.plot)?undefined:role.plot||'plot',plots:Array.isArray(role.plot)?role.plot:role.plots,anchor:role.anchorPx?[role.anchorPx[0]*W/pixelW,-role.anchorPx[1]*H/pixelH]:undefined};
 });
 const placed=positionInkLabels(rows),texts=plan.texts.map((text,index)=>{
  const row=placed.find(r=>r.id===index);
  return row?{...text,x:text.x+row.offsetPt[0]/W,y:text.y-row.offsetPt[1]/H}:{...text};
 });
 return {plan:{...plan,texts},rows};
}
