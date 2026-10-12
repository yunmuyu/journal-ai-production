JFW.aggregateEditorial=function(req,stage){
 if(req.layout==='figure-pages'){eval(JFW.read($.global.JFW_ADOBE_ROOT+'/editorial-copy.jsx'));eval(JFW.read($.global.JFW_ADOBE_ROOT+'/editorial-review-pages.jsx'));return JFW.aggregateReviewPages(req,stage);}
 var pt=72/25.4,W=490.39,H=677.48,gutter=[235.64705882353,255.41176470588],marginY=5*pt,gap=6*pt,labelGap=3*pt;
 var doc=app.open(new File(req.template)),page=0,column=0,current='',groups=[],labels=[],placements=[],opened=null,templateTexts=[],slots=[];
 for(var ti=0;ti<doc.textFrames.length;ti++)templateTexts.push(doc.textFrames[ti].contents);
 for(var bi=0;bi<doc.artboards.length;bi++){var br=doc.artboards[bi].artboardRect,busy=false;for(var pi=0;pi<doc.pageItems.length;pi++){var ob=doc.pageItems[pi];if(ob.guides||ob.hidden||ob.parent.typename!=='Layer')continue;var bb=ob.visibleBounds;if(bb[2]>br[0]&&bb[0]<br[2]&&bb[1]>br[3]&&bb[3]<br[1]){busy=true;break;}}if(!busy&&Math.abs(br[2]-br[0]-W)<0.1&&Math.abs(br[1]-br[3]-H)<0.1)slots.push(bi);}
 if(!slots.length){doc.close(SaveOptions.DONOTSAVECHANGES);throw Error('Template has no empty regular artboards');}
 var production=doc.layers.add();production.name='期刊成图';var board=doc.artboards[slots[0]].artboardRect,columnTop=board[1]-marginY,y=columnTop;
 function newPage(){page++;if(page>=slots.length)throw Error('Template empty artboards exhausted');column=0;board=doc.artboards[slots[page]].artboardRect;columnTop=board[1]-marginY;y=columnTop;}
 function nextColumn(){if(column===0){column=1;y=columnTop;}else newPage();}
 function label(author){var t=production.textFrames.add();t.contents=author;t.textRange.characterAttributes.textFont=JFW.editorialFont();t.textRange.characterAttributes.size=20;var red=new RGBColor();red.red=230;red.green=0;red.blue=0;t.textRange.characterAttributes.fillColor=red;t.left=board[0]+(column===0?0:gutter[1])+4;t.top=y;y-=t.height+labelGap;labels.push(author);}

 try{for(var k=0;k<req.items.length;k++){
  var item=req.items[k];stage('aggregate_open_'+k);opened=app.open(new File(item.ai));stage('aggregate_source_bounds_'+k);var sourceAB=JFW.bounds(opened.artboards[0].artboardRect),sourceBounds=JFW.bounds(opened.visibleBounds);doc.activate();var group=production.groupItems.add(),copied=0;group.name=item.author+'-图'+item.number;
  stage('aggregate_copy_'+k);if(req.batchCopy){eval(JFW.read($.global.JFW_ADOBE_ROOT+'/editorial-copy.jsx'));var imported=JFW.copyArtwork(opened,production);group.remove();group=imported.group;group.name=item.author+'-图'+item.number;copied=imported.rootCount;}else for(var n=opened.layers.length-1;n>=0;n--){var layer=opened.layers[n];for(var m=layer.pageItems.length-1;m>=0;m--)if(layer.pageItems[m].parent.typename==='Layer'&&!layer.pageItems[m].guides){var clone=layer.pageItems[m].duplicate(production,ElementPlacement.PLACEATBEGINNING);clone.move(group,ElementPlacement.PLACEATBEGINNING);copied++;}}
  stage('aggregate_close_'+k);opened.close(SaveOptions.DONOTSAVECHANGES);opened=null;layer=null;stage('aggregate_place_'+k);doc.activate();if(!copied)throw Error('Empty imported figure');
  var width=sourceAB[2]-sourceAB[0],height=sourceAB[1]-sourceAB[3],wide=width>80.4*pt,needLabel=item.author!==current;
  if(width>160.4*pt)throw Error('Figure exceeds double-column width');if(height>H-2*marginY-35)throw Error('Figure exceeds template height');
  if(wide&&column===1){newPage();needLabel=true;}
  if(y-height-(needLabel?34:0)<board[3]+marginY){if(wide)newPage();else nextColumn();needLabel=true;}
  if(needLabel){label(item.author);current=item.author;}
  var origin=board[0],left;if(wide)left=(W-width)/2;else if(column===0)left=(gutter[0]-width)/2;else left=gutter[1]+(W-gutter[1]-width)/2;
  var copiedBounds=JFW.bounds(group.visibleBounds);if(Math.abs((copiedBounds[2]-copiedBounds[0])-(sourceBounds[2]-sourceBounds[0]))>0.1||Math.abs((copiedBounds[1]-copiedBounds[3])-(sourceBounds[1]-sourceBounds[3]))>0.1)throw Error('Cross-document dimensions differ: '+JFW.stringify({copied:copiedBounds,source:sourceBounds}));group.translate(origin+left-(sourceAB[0]-sourceBounds[0])-copiedBounds[0],y-(sourceAB[1]-sourceBounds[1])-copiedBounds[1]);var clip=group.pathItems.rectangle(y,origin+left,width,height);clip.stroked=false;clip.filled=false;clip.clipping=true;clip.move(group,ElementPlacement.PLACEATBEGINNING);group.clipped=true;placements.push({name:group.name,page:page+1,artboardIndex:slots[page],artboardRect:JFW.bounds(board),column:wide?'double':column+1,widthMm:width/pt,bounds:[origin+left,y,origin+left+width,y-height]});y-=height+gap;groups.push(group.name);
  if(wide){column=0;columnTop=y;}
 }
 stage('aggregate_save_ai');var aiOptions=new IllustratorSaveOptions();aiOptions.pdfCompatible=true;doc.saveAs(new File(req.ai),aiOptions);
 stage('aggregate_save_pdf');var pdfOptions=new PDFSaveOptions();pdfOptions.preserveEditability=true;var used=[];for(var ui=0;ui<=page;ui++)used.push(slots[ui]+1);pdfOptions.artboardRange=used.join(',');doc.saveAs(new File(req.pdf),pdfOptions);
 stage('aggregate_export_preview');doc.artboards.setActiveArtboardIndex(slots[0]);var png=new ExportOptionsPNG24();png.artBoardClipping=true;png.transparency=false;png.horizontalScale=300/72*100;png.verticalScale=300/72*100;doc.exportFile(new File(req.preview),ExportType.PNG24,png);
 return {doc:doc,groups:groups,labels:labels,placements:placements,pages:page+1,templateTexts:templateTexts,template:{widthPt:W,heightPt:H,gutter:gutter,artboardCount:doc.artboards.length,usedArtboards:used}};
 }catch(e){if(opened)opened.close(SaveOptions.DONOTSAVECHANGES);doc.close(SaveOptions.DONOTSAVECHANGES);throw e;}
};
