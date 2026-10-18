JFW.adjustTextOnly=function(doc,request,capture){
 var evidence=request.textOnlyEvidence;
 if(!evidence||evidence.kind!=='controlled-text-v1'||evidence.operation!=='text-only')throw Error('Invalid text-only geometry evidence');
 function near(a,b,tolerance){return typeof a==='number'&&typeof b==='number'&&isFinite(a)&&isFinite(b)&&Math.abs(a-b)<=tolerance;}
 function boundsEqual(a,b){if(!a||!b||a.length!==4||b.length!==4)return false;for(var i=0;i<4;i++)if(!near(a[i],b[i],.01))return false;return true;}
 function ink(frame){var paths=doc.pathItems.length,items=doc.pageItems.length,texts=doc.textFrames.length,outline=frame.duplicate().createOutline(),b;try{b=JFW.bounds(outline.visibleBounds);}finally{outline.remove();}if(doc.pathItems.length!==paths||doc.pageItems.length!==items||doc.textFrames.length!==texts)throw Error('Measurement outline was not fully cleaned up');return b;}
 function measured(){var s=capture(doc,evidence.pathGeometry);for(var i=0;i<doc.textFrames.length;i++)s.texts[i].inkBounds=ink(doc.textFrames[i]);return s;}
 function unchanged(a,b){return a.text===b.text&&a.font===b.font&&near(a.size,b.size,.001)&&boundsEqual(a.bounds,b.bounds)&&boundsEqual(a.inkBounds,b.inkBounds)&&JFW.stringify(a.characterStyles||[])===JFW.stringify(b.characterStyles||[]);}
 var count=doc.pageItems.length,pathCount=doc.pathItems.length,textCount=doc.textFrames.length,before=measured(),old=evidence.sourceTexts,i,j;
 if(textCount!==old.length||!boundsEqual(before.artboard,evidence.sourceArtboard))throw Error('Text count/artboard changed');
 for(i=0;i<textCount;i++)if(!unchanged(before.texts[i],old[i]))throw Error('Actual text changed before adjustment at '+i);
 var targets=[];
 for(i=0;i<evidence.edits.length;i++){
  var edit=evidence.edits[i],text=before.texts[edit.index],frame=doc.textFrames[edit.index],expected=edit.expected;
  if(!text||text.index!==edit.index||text.text!==expected.text||!near(text.size,expected.size,.001)||!boundsEqual(text.inkBounds,expected.inkBounds))throw Error('Actual expected text mismatch');
  if(edit.fontSize!==undefined&&((text.characterStyles&&text.characterStyles.length)||!/^[0-9 .,\-−]+$/.test(text.text)))throw Error('Resizing mixed styled text is not supported');
  var b=text.inkBounds,anchor=edit.anchor||'center',x=anchor==='left'?b[0]:anchor==='right'?b[2]:(b[0]+b[2])/2,y=(b[1]+b[3])/2;
  if(edit.fontSize!==undefined){if(edit.fontSize<6||edit.fontSize>8)throw Error('Unsupported text size');frame.textRange.characterAttributes.size=edit.fontSize;}
  var changed=ink(frame),newX=anchor==='left'?changed[0]:anchor==='right'?changed[2]:(changed[0]+changed[2])/2,newY=(changed[1]+changed[3])/2;
  frame.translate(x-newX+(edit.dx||0),y-newY+(edit.dy||0));targets.push({index:edit.index,x:x+(edit.dx||0),y:y+(edit.dy||0),anchor:anchor,size:edit.fontSize===undefined?text.size:edit.fontSize,fontSizeChanged:edit.fontSize!==undefined});
 }
 var after=measured();
 if(doc.pathItems.length!==pathCount||doc.pageItems.length!==count||doc.textFrames.length!==textCount||!boundsEqual(after.artboard,before.artboard))throw Error('Text-only object count/artboard changed');
 for(i=0;i<textCount;i++){
  var target=null;for(j=0;j<targets.length;j++)if(targets[j].index===i)target=targets[j];
  if(!target){if(!unchanged(before.texts[i],after.texts[i]))throw Error('Unrequested text changed at '+i);continue;}
  var actual=after.texts[i],b=actual.inkBounds,x=target.anchor==='left'?b[0]:target.anchor==='right'?b[2]:(b[0]+b[2])/2;
  if(!target.fontSizeChanged&&JFW.stringify(actual.characterStyles||[])!==JFW.stringify(before.texts[i].characterStyles||[]))throw Error('Adjusted text script styles changed at '+i);
  if(actual.text!==before.texts[i].text||actual.font!==before.texts[i].font||!near(actual.size,target.size,.001)||!near(x,target.x,.01)||!near((b[1]+b[3])/2,target.y,.01))throw Error('Text-only output mismatch at '+i);
 }
 after.geometryEvidence={kind:'controlled-text-v1',operation:'text-only',mode:'reused',sourceAIHash:evidence.sourceAIHash,sourceSnapshotHash:evidence.sourceSnapshotHash,pathGeometryHash:evidence.pathGeometryHash,origin:'Previously verified complete source path geometry reused; only existing text size and translate were executed; control points were not read again'};
 return {snapshot:after,textAdjustment:{edits:evidence.edits,actual:targets},geometryEvidence:after.geometryEvidence};
};
