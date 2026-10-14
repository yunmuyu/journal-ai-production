// Include in one Adobe session with the existing JFW.drawArrow5 helper; no layout search occurs here.
JFW.applySolvedMoves=function(doc,request){
 if(request.version!==1||request.kind!=='move'||request.mustValidateBeforeMutation!==true||request.verifiedSourceSha256!==request.sourceSha256)throw Error('Bound move request required');
 function normalizedFile(p){return String(p).replace(/\\/g,'/').toLowerCase();}
 if(!doc.fullName||normalizedFile(doc.fullName.fsName)!==normalizedFile(request.sourcePath))throw Error('Active source document does not match bound source');
 var usedObjects=[],byName={},i,j,p,bindings=request.items,selected=[],arrows=[],tolerance=.03;
 for(i=0;i<doc.pageItems.length;i++){p=doc.pageItems[i];if(p.name){if(!byName[p.name])byName[p.name]=[];byName[p.name].push(p);}}
  for(var collection in request.collectionCounts)if(request.collectionCounts.hasOwnProperty(collection)&&(!doc[collection]||doc[collection].length!==request.collectionCounts[collection]))throw Error('Source collection count changed: '+collection);
 function resolve(b){var matches=b.name?byName[b.name]:doc[b.collection]?[doc[b.collection][b.index]]:null;if(!matches||matches.length!==1||!matches[0])throw Error('Source object identity ambiguous: '+(b.name||b.id));var obj=matches[0],bounds=obj.geometricBounds;for(var u=0;u<usedObjects.length;u++)if(usedObjects[u]===obj)throw Error('Source object bound twice');usedObjects.push(obj);if(obj.locked||obj.hidden)throw Error('Locked or hidden source object');for(var k=0;k<4;k++)if(Math.abs(bounds[k]-b.bounds[k])>tolerance)throw Error('Source bounds changed: '+(b.name||b.id));if(b.fontName!==undefined&&obj.textRange.characterAttributes.textFont.name!==b.fontName)throw Error('Source font changed: '+(b.name||b.id));if(b.fontSizePt!==undefined&&Math.abs(obj.textRange.characterAttributes.size-b.fontSizePt)>.001)throw Error('Source font size changed: '+(b.name||b.id));if(b.text!==undefined&&obj.contents!==b.text)throw Error('Source text changed: '+(b.name||b.id));return obj;}
 for(i=0;i<bindings.length;i++)selected.push({object:resolve(bindings[i]),binding:bindings[i]});
 for(i=0;i<selected.length;i++){var ancestor=selected[i].object.parent;while(ancestor&&ancestor!==doc){for(j=0;j<selected.length;j++)if(ancestor===selected[j].object)throw Error('Parent and child cannot both receive final moves');ancestor=ancestor.parent;}}
 for(i=0;i<request.connections.length;i++){var edge=request.connections[i],parts=[];for(j=0;j<edge.parts.length;j++)parts.push(resolve(edge.parts[j]));arrows.push({edge:edge,parts:parts});}
 if(arrows.length&&typeof JFW.drawArrow5!=='function')throw Error('Common Arrow 5 required');
 // All source identities are checked above before the first move or deletion.
 for(i=0;i<selected.length;i++){var item=selected[i];if(item.binding.dx||item.binding.dy)item.object.translate(item.binding.dx,-item.binding.dy);}
 for(i=0;i<selected.length;i++){var item=selected[i],b=item.object.geometricBounds;for(j=0;j<4;j++)if(Math.abs(b[j]-item.binding.expectedFinalBounds[j])>tolerance)throw Error('Final displacement mismatch: '+item.binding.name);}
 var black=new RGBColor();black.red=black.green=black.blue=0;
 for(i=0;i<arrows.length;i++){var a=arrows[i];for(j=0;j<a.parts.length;j++)a.parts[j].remove();JFW.drawArrow5(doc.activeLayer,a.edge.id,a.edge.points,black,.5,a.edge.both);}
 return {ok:true,moved:selected.length,replacedConnections:arrows.length,iterations:1,requiresFinalPdfVerification:true};
};
JFW.drawSolvedLayout=function(doc,request){
 if(request.kind!=='draw'||!(request.fontSizePt>=6&&request.fontSizePt<=8))throw Error('Solved drawing and supported font required');
 var black=new RGBColor();black.red=black.green=black.blue=0;
 var font=request.font==='现 宋体 1'?JFW.editorialFont():app.textFonts.getByName(request.font),i,j,prepared=[];
 // Check actual final text ink once. A stale measurement stops export instead of a new layout iteration.
 for(i=0;i<request.texts.length;i++){
  var t=request.texts[i],tf=doc.textFrames.add();tf.name='JFW_SOLVED_TEXT_'+t.id;tf.contents=t.text;
  var ca=tf.textRange.characterAttributes;ca.textFont=font;ca.size=request.fontSizePt;ca.fillColor=black;ca.autoLeading=false;ca.leading=request.fontSizePt*1.2;
  if(t.styles)JFW.styleText(tf,t.styles);
  var outline=tf.duplicate().createOutline(),b=outline.visibleBounds;var measured=[b[0],b[1],b[2],b[3]];outline.remove();
  if(Math.abs(measured[2]-measured[0]-t.expectedInk.widthPt)>.15||Math.abs(measured[1]-measured[3]-t.expectedInk.heightPt)>.15)throw Error('Final font measurement changed: '+t.id);
  tf.translate(t.x-measured[0],-t.y-measured[1]);prepared.push(tf);
 }
 for(i=0;i<request.shapes.length;i++){
  var n=request.shapes[i],p;
  if(n.shape==='rectangle')p=doc.pathItems.rectangle(-n.y,n.x,n.widthPt,n.heightPt);
  else if(n.shape==='ellipse')p=doc.pathItems.ellipse(-n.y,n.x,n.widthPt,n.heightPt);
  else if(n.shape==='diamond'){p=doc.pathItems.add();p.setEntirePath([[n.x+n.widthPt/2,-n.y],[n.x+n.widthPt,-n.y-n.heightPt/2],[n.x+n.widthPt/2,-n.y-n.heightPt],[n.x,-n.y-n.heightPt/2]]);p.closed=true;}
  else throw Error('Unsupported solved shape: '+n.shape);
  p.name='JFW_SOLVED_SHAPE_'+n.id;p.stroked=true;p.strokeWidth=.5;p.strokeColor=black;p.filled=false;
 }
 for(i=0;i<request.connections.length;i++){var e=request.connections[i],points=[];for(j=0;j<e.points.length;j++)points.push([e.points[j][0],-e.points[j][1]]);JFW.drawArrow5(doc.activeLayer,'JFW_SOLVED_EDGE_'+e.id,points,black,.5,e.both===true);}
 doc.artboards[0].artboardRect=[-.25,.25,request.canvas.widthPt-.25,-request.canvas.heightPt+.25];
 return {ok:true,texts:prepared.length,shapes:request.shapes.length,connections:request.connections.length,iterations:1,requiresFinalPdfVerification:true};
};
JFW.executeSolvedExport=function(doc,request){
 if(!request.outputAI||!request.outputPDF)throw Error('Separate AI/PDF output paths required');
 var ai=new File(request.outputAI),pdf=new File(request.outputPDF);
 if(ai.exists||pdf.exists||ai.fsName===pdf.fsName||request.sourcePath&&(ai.fsName===new File(request.sourcePath).fsName||pdf.fsName===new File(request.sourcePath).fsName))throw Error('Refuse to replace source or existing output');
 var result=request.kind==='move'?JFW.applySolvedMoves(doc,request):JFW.drawSolvedLayout(doc,request);
 var aiOptions=new IllustratorSaveOptions();aiOptions.pdfCompatible=true;doc.saveAs(ai,aiOptions);
 var pdfOptions=new PDFSaveOptions();pdfOptions.preserveEditability=true;doc.saveAs(pdf,pdfOptions);
 result.outputAI=ai.fsName;result.outputPDF=pdf.fsName;result.exported=true;return result;
};
