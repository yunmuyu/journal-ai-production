JFW.existingInventory=function(d){
 var items=[],textOwners=[],textLists=[],textFrames=d.textFrames,textFrameCount=d.textFrames.length;
 for(var j=0;j<textFrameCount;j++){
  var tf=textFrames[j],owner=tf;
  while(owner&&owner.parent&&owner.parent.typename!=='Layer'&&owner.typename!=='Document')owner=owner.parent;
  if(!owner||!owner.parent||owner.parent.typename!=='Layer'||owner.guides)continue;
  var ownerIndex=-1;for(var k=0;k<textOwners.length;k++)if(textOwners[k]===owner){ownerIndex=k;break;}
  if(ownerIndex<0){ownerIndex=textOwners.length;textOwners.push(owner);textLists.push([]);}
  textLists[ownerIndex].push(tf.contents);
 }
 for(var i=0;i<d.pageItems.length;i++){
  var p=d.pageItems[i];if(p.parent.typename!=='Layer'||p.guides)continue;
  var texts=[];for(var n=0;n<textOwners.length;n++)if(textOwners[n]===p){texts=textLists[n];break;}
  items.push({index:i,type:p.typename,name:p.name,bounds:JFW.bounds(p.visibleBounds),hidden:p.hidden,locked:p.locked,texts:texts});
 }
 var artboards=[];for(var a=0;a<d.artboards.length;a++)artboards.push(JFW.bounds(d.artboards[a].artboardRect));
 return {items:items,artboards:artboards};
};
JFW.exportExisting=function(source,req){
 if(!req.items||!req.items.length)throw Error('Explicit item selection required');
 var scale=req.scale===undefined?1:req.scale;
 if(scale!==0.75&&scale!==0.875&&scale!==1)throw Error('Invalid export scale');
 var selected=[],box=null;
 for(var i=0;i<req.items.length;i++){
  var expected=req.items[i],p=source.pageItems[expected.index];if(!p||p.parent.typename!=='Layer'||p.hidden||p.guides)throw Error('Invalid root item selection');
  var b=p.visibleBounds;for(var k=0;k<4;k++)if(Math.abs(b[k]-expected.bounds[k])>0.05)throw Error('Selected item bounds changed');
  selected.push(p);if(!box)box=[b[0],b[1],b[2],b[3]];else box=[Math.min(box[0],b[0]),Math.max(box[1],b[1]),Math.max(box[2],b[2]),Math.min(box[3],b[3])];
 }
 var resultWidth=(box[2]-box[0])*scale,resultHeight=(box[1]-box[3])*scale;
 var d=app.documents.add(source.documentColorSpace,resultWidth+0.5,resultHeight+0.5);
 try{
  d.activate();var group=d.groupItems.add();for(var j=selected.length-1;j>=0;j--){var clone=selected[j].duplicate(d.layers[0],ElementPlacement.PLACEATBEGINNING);clone.move(group,ElementPlacement.PLACEATBEGINNING);}
  if(scale!==1)group.resize(scale*100,scale*100,true,true,true,true,scale*100);
  var actual=group.visibleBounds;group.translate(0.25-actual[0],-0.25-actual[1]);
  var after=group.visibleBounds;if(Math.abs((after[2]-after[0])-resultWidth)>.05||Math.abs((after[1]-after[3])-resultHeight)>.05)throw Error('Copied geometry bounds changed');
  d.artboards[0].artboardRect=[0,0,resultWidth+0.5,-(resultHeight+0.5)];
  return {doc:d,sourceBounds:box,scale:scale,resultBounds:JFW.bounds(after),selectedRootItems:selected.length};
 }catch(error){d.close(SaveOptions.DONOTSAVECHANGES);throw error;}
};
JFW.correctExistingPaths=function(doc,edits){
 function isArray(value){return Object.prototype.toString.call(value)==='[object Array]';}
 function isPoint(value){return isArray(value)&&value.length===2&&typeof value[0]==='number'&&isFinite(value[0])&&typeof value[1]==='number'&&isFinite(value[1]);}
 if(!isArray(edits))throw Error('Invalid path edits');
 var staged=[],indices=[],pathCount=doc.pathItems.length;
 for(var i=0;i<edits.length;i++){
  var edit=edits[i];if(!edit||typeof edit!=='object')throw Error('Invalid path edit');
  var index=edit.index;if(typeof index!=='number'||!isFinite(index)||Math.floor(index)!==index||index<0||index>=pathCount)throw Error('Invalid path index');
  for(var u=0;u<indices.length;u++)if(indices[u]===index)throw Error('Duplicate path index');
  var path=doc.pathItems[index];if(!path||path.closed||path.clipping||path.hidden||!path.stroked)throw Error('Invalid path for correction');
  var expected=edit.expectedAnchors,points=edit.points,pathPoints=path.pathPoints;
  if(!isArray(expected)||!isArray(points)||expected.length<2||points.length<2||expected.length!==pathPoints.length)throw Error('Path anchor count changed');
  for(var a=0;a<expected.length;a++){
   var expectedPoint=expected[a],actualPoint=pathPoints[a].anchor;
   if(!isPoint(expectedPoint)||!isPoint(actualPoint))throw Error('Invalid anchor coordinates');
   if(Math.abs(actualPoint[0]-expectedPoint[0])>0.05||Math.abs(actualPoint[1]-expectedPoint[1])>0.05)throw Error('Path anchor mismatch');
  }
  var copiedPoints=[];for(var p=0;p<points.length;p++){if(!isPoint(points[p]))throw Error('Invalid target coordinate');copiedPoints.push([points[p][0],points[p][1]]);}
  indices.push(index);staged.push({index:index,path:path,points:copiedPoints});
 }
 for(var s=0;s<staged.length;s++)staged[s].path.setEntirePath(staged[s].points);
 return indices;
};
