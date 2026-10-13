JFW.updateEditorial=function(req,stage){
 var doc=app.open(new File(req.input)),production=null,opened=null,i,j;
 function protectedItems(d){var rows=[];for(var l=0;l<d.layers.length;l++){var layer=d.layers[l];for(var p=0;p<layer.pageItems.length;p++){var ob=layer.pageItems[p];if(ob.parent.typename!=='Layer')continue;var changed=false;for(var c=0;c<req.changes.length;c++)if(layer.name==='期刊成图'&&ob.name===req.changes[c].name)changed=true;if(changed)continue;var row={layer:layer.name,name:ob.name,type:ob.typename,bounds:JFW.bounds(ob.visibleBounds),hidden:ob.hidden,locked:ob.locked,guides:ob.guides};if(ob.typename==='TextFrame')row.text=ob.contents;if(ob.typename==='GroupItem'){row.texts=[];row.paths=[];for(var t=0;t<ob.textFrames.length;t++)row.texts.push({text:ob.textFrames[t].contents,bounds:JFW.bounds(ob.textFrames[t].geometricBounds)});for(var q=0;q<ob.pathItems.length;q++){var path=ob.pathItems[q],points=[];for(var z=0;z<path.pathPoints.length;z++){var point=path.pathPoints[z];points.push([JFW.bounds([point.anchor[0],point.anchor[1],point.leftDirection[0],point.leftDirection[1]]),[point.rightDirection[0],point.rightDirection[1]]]);}row.paths.push({points:points,closed:path.closed,clipping:path.clipping,strokeWidth:path.stroked?path.strokeWidth:null});}}rows.push(row);}}return JFW.stringify(rows);}
 try{
  for(i=0;i<doc.layers.length;i++)if(doc.layers[i].name==='期刊成图'){if(production)throw Error('Duplicate production layer');production=doc.layers[i];}
  if(!production)throw Error('Missing production layer');
  var before=protectedItems(doc),changedGroups=[];
  for(i=0;i<req.changes.length;i++){
   var change=req.changes[i],placement=null,old=null;
   for(j=0;j<req.placements.length;j++)if(req.placements[j].name===change.name)placement=req.placements[j];
   if(!placement)throw Error('Unknown figure identity');
   for(j=0;j<production.groupItems.length;j++)if(production.groupItems[j].parent.typename==='Layer'&&production.groupItems[j].name===change.name){if(old)throw Error('Duplicate figure identity');old=production.groupItems[j];}
   if(!old||!old.clipped||old.locked)throw Error('Figure is missing or manually changed');
   var clip=null;for(j=0;j<old.pathItems.length;j++)if(old.pathItems[j].clipping&&old.pathItems[j].parent===old){if(clip)throw Error('Duplicate figure clip');clip=old.pathItems[j];}
   if(!clip)throw Error('Missing figure clip');var target=placement.bounds,clipBounds=clip.geometricBounds;
   for(j=0;j<4;j++)if(Math.abs(clipBounds[j]-target[j])>0.05)throw Error('Figure placement changed; explicit rebase required');
   stage('update_open_'+i);opened=app.open(new File(change.ai));var ab=JFW.bounds(opened.artboards[0].artboardRect),sourceBounds=JFW.bounds(opened.visibleBounds),width=ab[2]-ab[0],height=ab[1]-ab[3];
   if(Math.abs(width-(target[2]-target[0]))>0.1||Math.abs(height-(target[1]-target[3]))>0.1)throw Error('Figure size changed; relayout required');
   doc.activate();var group=production.groupItems.add(),copied=0;group.name=change.name;
   eval(JFW.read($.global.JFW_ADOBE_ROOT+'/editorial-copy.jsx'));var imported=JFW.copyArtwork(opened,production);group.remove();group=imported.group;group.name=change.name;copied=imported.rootCount;
   opened.close(SaveOptions.DONOTSAVECHANGES);opened=null;doc.activate();if(!copied)throw Error('Empty replacement');
   var bounds=JFW.bounds(group.visibleBounds);if(Math.abs((bounds[2]-bounds[0])-(sourceBounds[2]-sourceBounds[0]))>0.1||Math.abs((bounds[1]-bounds[3])-(sourceBounds[1]-sourceBounds[3]))>0.1)throw Error('Copy dimensions changed');
   group.translate(target[0]-(ab[0]-sourceBounds[0])-bounds[0],target[1]-(ab[1]-sourceBounds[1])-bounds[1]);
   var newClip=group.pathItems.rectangle(target[1],target[0],width,height);newClip.stroked=false;newClip.filled=false;newClip.clipping=true;newClip.move(group,ElementPlacement.PLACEATBEGINNING);group.clipped=true;
   group.move(old,ElementPlacement.PLACEBEFORE);old.remove();changedGroups.push(change.name);
  }
  if(before!==protectedItems(doc))throw Error('Untouched template or figures changed');
  stage('update_save_ai');var aio=new IllustratorSaveOptions();aio.pdfCompatible=true;doc.saveAs(new File(req.ai),aio);
  stage('update_partial_pdf');var pdo=new PDFSaveOptions();pdo.preserveEditability=true;pdo.artboardRange=req.affectedArtboards.join(',');doc.saveAs(new File(req.pdf),pdo);
  doc.artboards.setActiveArtboardIndex(req.affectedArtboards[0]-1);var png=new ExportOptionsPNG24();png.artBoardClipping=true;png.transparency=false;png.horizontalScale=300/72*100;png.verticalScale=300/72*100;doc.exportFile(new File(req.preview),ExportType.PNG24,png);
  return {doc:doc,changedGroups:changedGroups,untouchedPreserved:true,exportedArtboards:req.affectedArtboards};
 }catch(error){if(opened)opened.close(SaveOptions.DONOTSAVECHANGES);doc.close(SaveOptions.DONOTSAVECHANGES);throw error;}
};
