// Curve anchors and handles follow the existing editorial brace script (7.6 x 36.5).
JFW.drawEditorialBrace=function(n,layer,stroke,all,strokeWidth){
 var anchors=[[7.6,.3],[4.9,3.4],[4.9,15.2],[0,18.3],[4.9,21.4],[4.9,33.2],[7.6,36.3]];
 var left=[[5.8,.3],[4.9,1.3],[4.9,15.2],[3.3,18.3],[4.9,19.3],[4.9,33.2],[5.8,36.3]];
 var right=[[7.6,.3],[4.9,3.4],[4.9,17.3],[3.3,18.3],[4.9,21.4],[5.8,36.3],[7.6,36.3]];
 function map(q){var x=q[0]/7.6,y=q[1]/36.5,side=n.braceSide||'left';if(side==='right')x=1-x;else if(side==='top'){var oldX=x;x=y;y=oldX;}else if(side==='bottom'){var oldX=x;x=y;y=1-oldX;}return [n.left+x*(n.right-n.left),n.top-y*(n.top-n.bottom)];}
 var p=layer.pathItems.add(),points=[],i;for(i=0;i<anchors.length;i++)points.push(map(anchors[i]));p.setEntirePath(points);
 for(i=0;i<anchors.length;i++){p.pathPoints[i].anchor=map(anchors[i]);p.pathPoints[i].leftDirection=map(left[i]);p.pathPoints[i].rightDirection=map(right[i]);p.pathPoints[i].pointType=PointType.CORNER;}
 p.closed=false;p.filled=false;p.stroked=true;p.strokeColor=stroke;p.strokeWidth=strokeWidth;p.strokeDashes=[];p.name='AI_FLOW_NODE_'+n.id;all.push(p);
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
// Layout reserves the label and the arrow as one block; drawing keeps the symbol narrow.
JFW.editorialArrowSymbol=function(n){
 if(!n.arrowSymbol)return n;
 var symbol={},key;for(key in n)if(n.hasOwnProperty(key))symbol[key]=n[key];
 symbol.w=n.arrowSymbol.w;symbol.h=n.arrowSymbol.h;
 symbol.left=n.cx-symbol.w/2;symbol.right=n.cx+symbol.w/2;
 symbol.top=n.bottom+symbol.h;symbol.cy=n.bottom+symbol.h/2;
 return symbol;
};
JFW.reserveContainerColumns=function(containers,byId,gaps){
 var ranges=[],i,j,k,n,s;
 for(i=0;i<containers.length;i++){
  s=containers[i];var r={left:Infinity,right:-Infinity,top:Infinity,bottom:-Infinity,pad:s.framePaddingX};
  for(k=0;k<s.members.length;k++){n=byId[s.members[k]];r.left=Math.min(r.left,n.column);r.right=Math.max(r.right,n.column+n.columnSpan-1);r.top=Math.min(r.top,n.row);r.bottom=Math.max(r.bottom,n.row+n.rowSpan-1);}
  ranges.push(r);
 }
 for(i=0;i<ranges.length;i++)for(j=0;j<ranges.length;j++){
  var a=ranges[i],b=ranges[j];
  if(a.right+1!==b.left||a.bottom<b.top||b.bottom<a.top)continue;
  if(Math.floor(a.right)!==a.right)continue;
  gaps[a.right]=Math.max(gaps[a.right],a.pad+b.pad+3);
 }
};
JFW.adaptEditorialGenerator=function(code){
 var metrics=JFW.layoutMetrics||{padX:4.5,padY:2.7,compactGap:3};
 function replaceOnce(from,to){var i=code.indexOf(from);if(i<0||code.indexOf(from,i+from.length)>=0)throw Error('Generator adaptation boundary changed: '+from);code=code.slice(0,i)+to+code.slice(i+from.length);}
 replaceOnce('PAD_X: 4.5,','PAD_X: '+metrics.padX+',');replaceOnce('PAD_Y: 2.7,','PAD_Y: '+metrics.padY+',');
 replaceOnce('var w = (units * CFG.HORIZONTAL_CHAR_WIDTH + CFG.HORIZONTAL_PADDING_TOTAL) * scale;','var w = measure.w + 2 * CFG.PAD_X * scale;');
 var start=code.indexOf('var h = Math.max(',code.indexOf('var w = measure.w + 9 * scale;')),end=code.indexOf('if (node.shape === "functionBlock")',start);
 if(start<0||end<0)throw Error('Generator rectangle boundary changed');code=code.slice(0,start)+'var h = measure.h + 2 * CFG.PAD_Y * scale;\n        '+code.slice(end);
 start=code.indexOf('} else if (node.shape === "decision" && lines.length >= 4)');end=code.indexOf('} else if (node.shape === "ellipse")',start);
 if(start<0||end<0)throw Error('Generator diamond boundary changed');code=code.slice(0,start)+'} else if (node.shape === "decision") { var a = measure.w * 0.85 + 2 * scale, b = measure.h * 0.8 + 2 * scale; var clearance = Math.max(1, measure.w / (2 * (a - scale)) + measure.h / (2 * (b - scale))); w = 2 * a * clearance; h = 2 * b * clearance;\n        '+code.slice(end);
 start=code.indexOf('function resolveFont() {');end=code.indexOf('function findFont(names)',start);
 if(start<0||end<0)throw Error('Generator font boundary changed');code=code.slice(0,start)+'function resolveFont() { return {font:JFW.editorialFont(),composite:true}; }\n    '+code.slice(end);
 replaceOnce('GAP_MINIMAL: 1 * PT_PER_MM,','GAP_MINIMAL: 3,');
 replaceOnce('size = calibratedBoxSize(n, measure, fontSize);','size = calibratedBoxSize(n, measure, fontSize); if(n.shape==="arrow" && text && !n.arrowLabelSide){size.symbol={w:size.w,h:size.h};size.w=Math.max(size.w,measure.w);size.h+=measure.h+3*fontSize/8;}');
 replaceOnce('w: size.w, h: size.h, rowSpan:', 'w: size.w, h: size.h, arrowSymbol: size.symbol, rowSpan:');
 replaceOnce('n.shape === "arrow" && n.text ? 2 *', 'n.shape === "arrow" && n.text && !n.arrowSymbol ? 2 *');
 replaceOnce('drawArrowSymbol(n, targetLayer, stroke, all);','drawArrowSymbol(JFW.editorialArrowSymbol(n), targetLayer, stroke, all);');
 replaceOnce('n.top + labelInk.h / 2 + 3 * fontSize / 8','n.arrowSymbol ? n.top-labelInk.h/2 : n.top + labelInk.h / 2 + 3 * fontSize / 8');
 replaceOnce('if (!containers[ci].label || data.swimlaneLayout || containers[ci].sizeClass) continue;', 'containers[ci].framePaddingX=containerPaddingX(containers[ci]); if (!containers[ci].label || data.swimlaneLayout || containers[ci].sizeClass) continue;');
 replaceOnce('var columnGaps = columnTrackGaps(nodes, byId, edges, colCount, columnGap);','var columnGaps = columnTrackGaps(nodes, byId, edges, colCount, columnGap); JFW.reserveContainerColumns(containers,byId,columnGaps);');


 start=code.indexOf('function applyVerticalStacks(specs, byId) {');end=code.indexOf('function compactSiblingBusMembers(',start);
 if(start<0||end<0)throw Error('Generator stack boundary changed');
 code=code.slice(0,start)+'function applyVerticalStacks(specs,byId){for(var i=0;i<specs.length;i++){var spec=specs[i],first=byId[spec.members[0]],last=byId[spec.members[spec.members.length-1]],anchor=(first.cy+last.cy)/2,gap=spec.gap==="minimal"?CFG.GAP_MINIMAL:CFG.GAP,previous=first;for(var j=1;j<spec.members.length;j++){var current=byId[spec.members[j]];current.cy=previous.bottom-gap-current.h/2;current.top=current.cy+current.h/2;current.bottom=current.cy-current.h/2;previous=current;}var shift=anchor-(first.cy+previous.cy)/2;for(var j=0;j<spec.members.length;j++){var node=byId[spec.members[j]];node.cy+=shift;node.top+=shift;node.bottom+=shift;}}} '+code.slice(end);
 replaceOnce('function opposingHorizontalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition) {','function opposingHorizontalPortPoints(source, target, fromPort, toPort, fromPortPosition, toPortPosition) { if(source.shape==="decision"||target.shape==="decision")return [portPoint(source,fromPort,fromPortPosition),portPoint(target,toPort,toPortPosition)];');
 start=code.indexOf('function columnTrackGaps(');end=code.indexOf('return gaps;',start);if(start<0||end<0)throw Error('Column gaps boundary changed');code=code.slice(0,end)+'var fanouts={};for(var e=0;e<edges.length;e++){var edge=edges[e],source=byId[edge.from],target=byId[edge.to];if(source&&target&&target.column===source.column+1&&edge.fromPort==="right"&&edge.toPort==="left"){var key=source.id;fanouts[key]=(fanouts[key]||0)+1;if(fanouts[key]>=2)gaps[source.column]=Math.max(gaps[source.column],CFG.BUS_LEG*2);}} '+code.slice(end);
 replaceOnce("point = containerLabelPoint(frame);\n                addEdgeLabel(frame.label, point[0], point[1], all, fontSize, font, stroke);","point = containerLabelPoint(frame);\n                addEdgeLabel(frame.label, point[0], point[1], all, fontSize, font, stroke); JFW.alignContainerLabel(all[all.length-1],frame,fontSize);");
 start=code.indexOf('function drawBraceSymbol(');end=code.indexOf('function drawSignalOperator(',start);
 if(start<0||end<0)throw Error('Generator brace boundary changed');
 code=code.slice(0,start)+'function drawBraceSymbol(n,targetLayer,stroke,all){JFW.drawEditorialBrace(n,targetLayer,stroke,all,CFG.STROKE);} '+code.slice(end);
 return code;
};
