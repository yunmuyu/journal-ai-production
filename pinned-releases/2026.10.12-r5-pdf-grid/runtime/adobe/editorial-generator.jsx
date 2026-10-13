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
 if(start<0||end<0)throw Error('Generator diamond boundary changed');code=code.slice(0,start)+'} else if (node.shape === "decision") { w = 2 * (measure.w + 9 * scale + 0.5); h = 2 * (measure.h + 5.4 * scale + 0.5);\n        '+code.slice(end);
 start=code.indexOf('function resolveFont() {');end=code.indexOf('function findFont(names)',start);
 if(start<0||end<0)throw Error('Generator font boundary changed');code=code.slice(0,start)+'function resolveFont() { return {font:JFW.editorialFont(),composite:true}; }\n    '+code.slice(end);
 replaceOnce('GAP_MINIMAL: 1 * PT_PER_MM,','GAP_MINIMAL: 3,');

 start=code.indexOf('function applyVerticalStacks(specs, byId) {');end=code.indexOf('function compactSiblingBusMembers(',start);
 if(start<0||end<0)throw Error('Generator stack boundary changed');
 code=code.slice(0,start)+'function applyVerticalStacks(specs,byId){for(var i=0;i<specs.length;i++){var spec=specs[i],first=byId[spec.members[0]],last=byId[spec.members[spec.members.length-1]],anchor=(first.cy+last.cy)/2,gap=spec.gap==="minimal"?CFG.GAP_MINIMAL:CFG.GAP,previous=first;for(var j=1;j<spec.members.length;j++){var current=byId[spec.members[j]];current.cy=previous.bottom-gap-current.h/2;current.top=current.cy+current.h/2;current.bottom=current.cy-current.h/2;previous=current;}var shift=anchor-(first.cy+previous.cy)/2;for(var j=0;j<spec.members.length;j++){var node=byId[spec.members[j]];node.cy+=shift;node.top+=shift;node.bottom+=shift;}}} '+code.slice(end);
 replaceOnce('function opposingHorizontalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition) {','function opposingHorizontalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition) { if(source.shape==="decision"||target.shape==="decision")return [portPoint(source,fromPort,fromPortPosition),portPoint(target,toPort,toPortPosition)];');
 start=code.indexOf('function columnTrackGaps(');end=code.indexOf('return gaps;',start);if(start<0||end<0)throw Error('Column gaps boundary changed');code=code.slice(0,end)+'var fanouts={};for(var e=0;e<edges.length;e++){var edge=edges[e],source=byId[edge.from],target=byId[edge.to];if(source&&target&&target.column===source.column+1&&edge.fromPort==="right"&&edge.toPort==="left"){var key=source.id;fanouts[key]=(fanouts[key]||0)+1;if(fanouts[key]>=2)gaps[source.column]=Math.max(gaps[source.column],CFG.BUS_LEG*2);}} '+code.slice(end);
 replaceOnce("point = containerLabelPoint(frame);\n                addEdgeLabel(frame.label, point[0], point[1], all, fontSize, font, stroke);","point = containerLabelPoint(frame);\n                addEdgeLabel(frame.label, point[0], point[1], all, fontSize, font, stroke); JFW.alignContainerLabel(all[all.length-1],frame,fontSize);");
 return code;
};
