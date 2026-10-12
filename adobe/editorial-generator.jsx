JFW.positionDiagramSideLabel=function(tf,side,doc,fontSize){
 var extreme=null,half=0;for(var i=0;i<doc.pathItems.length;i++){var p=doc.pathItems[i];if(!p.name||p.name.indexOf('AI_FLOW_')!==0||p.guides||p.hidden)continue;var b=p.geometricBounds,value=side==='left'?b[0]:b[2];if(extreme===null||(side==='left'?value<extreme:value>extreme)){extreme=value;half=p.stroked?p.strokeWidth/2:0;}}
 if(extreme===null)throw Error('No diagram boundary for side label');var o=tf.duplicate().createOutline(),ink=o.visibleBounds;o.remove();var gap=3*fontSize/8;tf.translate(side==='left'?extreme-half-gap-ink[2]:extreme+half+gap-ink[0],0);tf.note='JFW_DIAGRAM_SIDE_'+side.toUpperCase();
};
JFW.alignContainerLabel=function(tf,frame,fontSize){
 if(frame.labelPosition!=='bottomRight')return;
 var outline=tf.duplicate().createOutline(),b=outline.visibleBounds;
 var ink=[b[0],b[1],b[2],b[3]];outline.remove();
 var pad=3*fontSize/8;
 if(ink[2]-ink[0]>frame.right-frame.left-2*pad||ink[1]-ink[3]>frame.top-frame.bottom-2*pad)throw Error('Container title exceeds frame: '+frame.id);
 var dx=frame.right-pad-ink[2],dy=0;
 if(ink[3]<frame.bottom+pad)dy=frame.bottom+pad-ink[3];
 if(ink[1]+dy>frame.top-pad)dy=frame.top-pad-ink[1];
 tf.translate(dx,dy);
};
JFW.editorialFont=function(){var f=app.textFonts.getByName('ATC-73b000205b8b4f530020*1');if(f.family!=='现 宋体 1')throw Error('Required composite font family differs');return f;};
JFW.adaptEditorialGenerator=function(code){
 function replaceOnce(from,to){var i=code.indexOf(from);if(i<0||code.indexOf(from,i+from.length)>=0)throw Error('Generator adaptation boundary changed: '+from);code=code.slice(0,i)+to+code.slice(i+from.length);}
 replaceOnce('var w = (units * CFG.HORIZONTAL_CHAR_WIDTH + CFG.HORIZONTAL_PADDING_TOTAL) * scale;','var w = measure.w + 9 * scale;');
 var start=code.indexOf('var h = Math.max(',code.indexOf('var w = measure.w + 9 * scale;')),end=code.indexOf('if (node.shape === "functionBlock")',start);
 if(start<0||end<0)throw Error('Generator rectangle boundary changed');code=code.slice(0,start)+'var h = measure.h + 5.4 * scale;\n        '+code.slice(end);
 start=code.indexOf('} else if (node.shape === "decision" && lines.length >= 4)');end=code.indexOf('} else if (node.shape === "ellipse")',start);
 if(start<0||end<0)throw Error('Generator diamond boundary changed');code=code.slice(0,start)+'} else if (node.shape === "decision") { w = 1.7 * measure.w + 4 * scale; h = 1.6 * measure.h + 4 * scale;\n        '+code.slice(end);
 start=code.indexOf('function resolveFont() {');end=code.indexOf('function findFont(names)',start);
 if(start<0||end<0)throw Error('Generator font boundary changed');code=code.slice(0,start)+'function resolveFont() { return {font:JFW.editorialFont(),composite:true}; }\n    '+code.slice(end);
 replaceOnce('GAP_MINIMAL: 1 * PT_PER_MM,','GAP_MINIMAL: 3,');

 start=code.indexOf('function applyVerticalStacks(specs, byId) {');end=code.indexOf('function compactSiblingBusMembers(',start);
 if(start<0||end<0)throw Error('Generator stack boundary changed');
 code=code.slice(0,start)+'function applyVerticalStacks(specs,byId){for(var i=0;i<specs.length;i++){var spec=specs[i],first=byId[spec.members[0]],last=byId[spec.members[spec.members.length-1]],anchor=(first.cy+last.cy)/2,gap=spec.gap==="minimal"?CFG.GAP_MINIMAL:CFG.GAP,previous=first;for(var j=1;j<spec.members.length;j++){var current=byId[spec.members[j]];current.cy=previous.bottom-gap-current.h/2;current.top=current.cy+current.h/2;current.bottom=current.cy-current.h/2;previous=current;}var shift=anchor-(first.cy+previous.cy)/2;for(var j=0;j<spec.members.length;j++){var node=byId[spec.members[j]];node.cy+=shift;node.top+=shift;node.bottom+=shift;}}} '+code.slice(end);
 replaceOnce('function opposingHorizontalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition) {','function opposingHorizontalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition) { if(source.shape==="decision"||target.shape==="decision")return [portPoint(source,fromPort,fromPortPosition),portPoint(target,toPort,toPortPosition)];');
 start=code.indexOf('function columnTrackGaps(');end=code.indexOf('return gaps;',start);if(start<0||end<0)throw Error('Column gaps boundary changed');code=code.slice(0,end)+'var fanouts={};for(var e=0;e<edges.length;e++){var edge=edges[e],source=byId[edge.from],target=byId[edge.to];if(source&&target&&target.column===source.column+1&&edge.fromPort==="right"&&edge.toPort==="left"){var key=source.id;fanouts[key]=(fanouts[key]||0)+1;if(fanouts[key]>=2)gaps[source.column]=Math.max(gaps[source.column],CFG.BUS_LEG*2);}} '+code.slice(end);
 replaceOnce("point = containerLabelPoint(frame);\n                addEdgeLabel(frame.label, point[0], point[1], all, fontSize, font, stroke);","point = containerLabelPoint(frame);\n                addEdgeLabel(frame.label, point[0], point[1], all, fontSize, font, stroke); JFW.alignContainerLabel(all[all.length-1],frame,fontSize);");

 replaceOnce('var b = tf.visibleBounds;\n        tf.translate(cx - (b[0] + b[2]) / 2, cy - (b[1] + b[3]) / 2);','var outline = tf.duplicate().createOutline(), b = outline.visibleBounds; outline.remove();\n        tf.translate(cx - (b[0] + b[2]) / 2, cy - (b[1] + b[3]) / 2);');
 replaceOnce('var b = tf.visibleBounds, result = { w: b[2] - b[0], h: b[1] - b[3] };','var outline=tf.duplicate().createOutline(), b=outline.visibleBounds, result = { w: b[2] - b[0], h: b[1] - b[3] }; outline.remove();');
 replaceOnce('return containerPaddingY(container);\n    }\n\n    function shaftRouteGap','if(container.label && container.labelPosition === "bottomRight") return Math.max(containerPaddingY(container),measureText(container.label,data.fontSize || 8,resolveFont().font).h+6); return containerPaddingY(container);\n    }\n\n    function shaftRouteGap');
 replaceOnce('if (spec.sizeClass === "wideNested") padBottom = containerPaddingBottom(spec, byId[spec.members[0]].h);','if (spec.sizeClass === "wideNested" || spec.labelPosition === "bottomRight") padBottom = containerPaddingBottom(spec, byId[spec.members[0]].h);');
 replaceOnce('} else if (spec.labelPosition === "bottomRight") frame.top = frame.top - padY + containerPaddingTop(spec);','} else if (spec.labelPosition === "bottomRight") { frame.top = frame.top - padY + containerPaddingTop(spec); frame.bottom += padY-containerPaddingBottom(spec,members[0].h); }');
 replaceOnce('var requiredGap = shaftRouteGap(edge), j, axis;','var requiredGap = shaftRouteGap(edge), j, axis; if(edge.label){var lm=measureText(displayText(edge.label,false),data.fontSize || 8,resolveFont().font), labelPad=6; for(var ci=0;ci<(data.containers||[]).length;ci++){var owner=data.containers[ci];for(var mi=0;mi<owner.members.length;mi++)if(owner.members[mi]===edge.from || owner.members[mi]===edge.to)labelPad+=containerPaddingX(owner);} requiredGap=Math.max(requiredGap,lm.w+labelPad);}');
 replaceOnce('if (edge.labelSide === "below") y -= 5;\n            else if (edge.labelSide === "left") x -= 6;\n            else if (edge.labelSide === "right") x += 6;\n            else y += 5;','var lm=measureText(displayText(edge.label,false),data.fontSize || 8,resolveFont().font); if (edge.labelSide === "below") y -= lm.h/2+3;\n            else if (edge.labelSide === "left") x -= lm.w/2+3;\n            else if (edge.labelSide === "right") x += lm.w/2+3;\n            else y += lm.h/2+3;');

 replaceOnce('shapeW = n.w - CFG.STROKE; shapeH = n.h - CFG.STROKE;\n            shapeLeft = n.left + CFG.STROKE / 2; shapeTop = n.top - CFG.STROKE / 2;','shapeW = n.w; shapeH = n.h;\n            shapeLeft = n.left; shapeTop = n.top;');
 replaceOnce('if (lastRow < gaps.length && !hasSharedBoundary(spec, i, lastRow, false, byId, containerRanges, memberOwners)) ends[lastRow] = Math.max(ends[lastRow] || 0, padBottom);','var needsLowerBand=false; for(var ni=0;ni<nodes.length;ni++){var next=nodes[ni];if(next.row<=lastRow)continue;for(var mi=0;mi<spec.members.length;mi++){var owned=byId[spec.members[mi]];if(next.column===owned.column)needsLowerBand=true;}} if (needsLowerBand && lastRow < gaps.length && !hasSharedBoundary(spec, i, lastRow, false, byId, containerRanges, memberOwners)) ends[lastRow] = Math.max(ends[lastRow] || 0, padBottom);');

 replaceOnce('centerText(tf, cx, ay); return tf;','centerText(tf, cx, ay); if(item.vertical && ((item.xr === 0 && item.align === "right") || (item.xr === 1 && item.align === "left"))) JFW.positionDiagramSideLabel(tf,item.xr === 0 ? "left" : "right",doc,size); return tf;');
 replaceOnce('requiredGap = CFG.GAP * 2;','requiredGap = Math.max(requiredGap, CFG.GAP * 2);');
 return code;
};
