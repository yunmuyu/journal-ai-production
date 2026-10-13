// Shared base dimensions at 8 pt. Whole-artwork fitting scales all dimensions together.
JFW.layoutMetrics={padX:4.5,padY:2.7,compactGap:3,framePad:3,arrowLength:3*72/25.4,minFontSize:6};
JFW.layoutFitScale=function(widthPt,targetPt,minFontPt){
 if(!(widthPt>0&&targetPt>.5&&minFontPt>0))throw Error('Invalid layout fit dimensions');
 var scale=Math.min(1,(targetPt-.5)/widthPt);
 if(minFontPt*scale<6-.000001)throw Error('LAYOUT_REFLOW_REQUIRED: final font '+(minFontPt*scale)+' pt is below 6 pt');
 return scale;
};
JFW.fitEditorialArtwork=function(doc,targetPt,bounds){
 var minimum=Infinity,i,j,items=[],original=[];
 for(i=0;i<doc.textFrames.length;i++)minimum=Math.min(minimum,doc.textFrames[i].textRange.characterAttributes.size);
 if(minimum===Infinity)minimum=8;
 var scale=JFW.layoutFitScale(bounds[2]-bounds[0],targetPt,minimum);
 if(scale<1){
  for(i=0;i<doc.layers.length;i++)for(j=0;j<doc.layers[i].pageItems.length;j++){
   var item=doc.layers[i].pageItems[j];if(item.parent===doc.layers[i]){items.push(item);original.push(JFW.bounds(item.geometricBounds));}
  }
  for(i=0;i<items.length;i++){
   var b=original[i],x=bounds[0]+(b[0]-bounds[0])*scale,y=bounds[1]+(b[1]-bounds[1])*scale;
   items[i].resize(scale*100,scale*100,true,true,true,true,scale*100);
   var after=items[i].geometricBounds;items[i].translate(x-after[0],y-after[1]);
  }
  app.redraw();
 }
 return {scale:scale,minimumFontPt:minimum*scale,baseWidthPt:bounds[2]-bounds[0],targetWidthPt:targetPt};
};

// Explicit exterior arrow labels must clear all diagram paths, including return lanes.
JFW.placeExteriorArrowLabels=function(doc,nodes){
 var excluded={},i,j;for(i=0;i<nodes.length;i++)if(nodes[i].shape==='arrow')excluded['AI_FLOW_NODE_'+nodes[i].id]=true;
 var left=Infinity,right=-Infinity;for(i=0;i<doc.pathItems.length;i++){var p=doc.pathItems[i];if(excluded[p.name]||p.guides||p.hidden||p.clipping)continue;var b=p.visibleBounds;left=Math.min(left,b[0]);right=Math.max(right,b[2]);}
 if(!isFinite(left))return;
 for(i=0;i<nodes.length;i++){var n=nodes[i];if(n.shape!=='arrow'||(n.arrowLabelSide!=='left'&&n.arrowLabelSide!=='right'))continue;
  for(j=0;j<doc.textFrames.length;j++){var t=doc.textFrames[j];if(t.name!=='AI_FLOW_ARROW_LABEL_'+n.id)continue;var o=t.duplicate().createOutline(),b=o.visibleBounds,ink=[b[0],b[1],b[2],b[3]];o.remove();var gap=3*t.textRange.characterAttributes.size/8;t.translate(n.arrowLabelSide==='left'?Math.min(0,left-gap-ink[2]):Math.max(0,right+gap-ink[0]),0);}
 }
};
