export function validateLabelLayout(text, plan) {
  const layout=text.layout;
  if (layout===undefined) return;
  const allowed=['ownerPathIndex','placements','clearancePt','maxDistancePt','allowFrameExpansionPt','rotations'];
  if (!layout || typeof layout!=='object' || Array.isArray(layout) || Object.keys(layout).some(key=>!allowed.includes(key)) || plan.route!=='vector-reletter' || !Number.isInteger(layout.ownerPathIndex) || layout.ownerPathIndex<0) throw Error('invalid label layout owner on vector route');
  if (layout.placements!==undefined && (!Array.isArray(layout.placements) || !layout.placements.length || new Set(layout.placements).size!==layout.placements.length || layout.placements.some(value=>!['inside','left','right','above','below'].includes(value)))) throw Error('invalid label layout placements');
  if (layout.rotations!==undefined && (!Array.isArray(layout.rotations) || !layout.rotations.length || new Set(layout.rotations).size!==layout.rotations.length || layout.rotations.some(value=>![-90,0,90].includes(value)) || ![-90,0,90].includes(text.rotation||0))) throw Error('invalid label layout rotations');
  for (const [key,min,max] of [['clearancePt',0.5,6],['maxDistancePt',0,24],['allowFrameExpansionPt',0,6]]) {
    if (layout[key]!==undefined && (!Number.isFinite(layout[key]) || layout[key]<min || layout[key]>max)) throw Error('invalid label layout '+key);
  }
  if (text.align!=='center' || text.valign!=='center') throw Error('label layout requires centered measured ink');
}
