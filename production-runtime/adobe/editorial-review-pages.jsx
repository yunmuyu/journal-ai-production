JFW.aggregateReviewPages=function(req,stage){
 if(req.layout!=='figure-pages'||!req.items||!req.items.length)throw Error('Figure pages require nonempty items');
 if(!JFW.copyArtwork)throw Error('Figure pages require JFW.copyArtwork');
 if(!req.ai||!req.pdf||!req.preview)throw Error('Review output paths required');
 for(var vi=0;vi<req.items.length;vi++)if(new File(req.items[vi].ai).fsName.toLowerCase()===new File(req.ai).fsName.toLowerCase())throw Error('Review output must not replace source AI');
 var doc=null,opened=null,retainedInputs=[],groups=[],labels=[],placements=[],used=[],cursor=0,padding=4,labelGap=4,pageGap=100;
 try{
  stage('review_pages_create');doc=app.documents.add(DocumentColorSpace.RGB,1,1);var production=doc.layers.add();production.name='期刊成图';
  for(var k=0;k<req.items.length;k++){
   var item=req.items[k];if(!item.ai||!item.author||item.number===undefined)throw Error('Incomplete review figure identity');
   stage('review_pages_open_'+k);opened=app.open(new File(item.ai));
   var sourceAB=JFW.bounds(opened.artboards[0].artboardRect),sourceBounds=JFW.bounds(opened.visibleBounds),width=sourceAB[2]-sourceAB[0],height=sourceAB[1]-sourceAB[3];
   if(width<=0||height<=0)throw Error('Invalid source artboard');
   stage('review_pages_copy_'+k);var imported=JFW.copyArtwork(opened,production),group=imported.group;group.name=item.author+'-图'+item.number;
   if(req.keepDocumentOpen===true){stage('review_pages_keep_source_'+k);retainedInputs.push(opened);}else{stage('review_pages_close_'+k);opened.close(SaveOptions.DONOTSAVECHANGES);}opened=null;doc.activate();
   if(!imported.rootCount)throw Error('Empty imported review figure');
   var copiedBounds=JFW.bounds(group.visibleBounds);
   if(Math.abs((copiedBounds[2]-copiedBounds[0])-(sourceBounds[2]-sourceBounds[0]))>0.1||Math.abs((copiedBounds[1]-copiedBounds[3])-(sourceBounds[1]-sourceBounds[3]))>0.1)throw Error('Cross-document dimensions differ');
   var badgePad=req.reviewBadges===true?3:0;
   if(req.reviewBadges===true&&item.columnLabel!=='单栏'&&item.columnLabel!=='双栏')throw Error('Review badge requires confirmed column');
   var labelText=item.author+' 图'+item.number+(req.reviewBadges===true?' · '+item.columnLabel:''),label=production.textFrames.add();label.contents=labelText;label.name='JFW_REVIEW_LABEL_'+k;
   var ca=label.textRange.characterAttributes;ca.textFont=JFW.editorialFont();ca.size=7;ca.autoLeading=false;ca.leading=8.4;var black=new RGBColor();black.red=black.green=black.blue=0;ca.fillColor=black;
   label.left=cursor+padding+badgePad;label.top=-padding-badgePad;var outline=label.duplicate().createOutline(),ink=JFW.bounds(outline.visibleBounds);outline.remove();
   var labelWidth=ink[2]-ink[0],labelHeight=ink[1]-ink[3];label.translate(cursor+padding+badgePad-ink[0],-padding-badgePad-ink[1]);
   var badgeBounds=null;if(req.reviewBadges===true){var badge=production.pathItems.rectangle(-padding,cursor+padding,labelWidth+2*badgePad,labelHeight+2*badgePad);badge.name='JFW_REVIEW_BADGE_'+k;badge.stroked=false;badge.filled=true;var lightGray=new RGBColor();lightGray.red=lightGray.green=lightGray.blue=238;badge.fillColor=lightGray;badge.move(label,ElementPlacement.PLACEAFTER);badgeBounds=[cursor+padding,-padding,cursor+padding+labelWidth+2*badgePad,-padding-labelHeight-2*badgePad];}
   var left=cursor+padding,top=-padding-labelHeight-2*badgePad-labelGap,pageWidth=Math.max(width,labelWidth+2*badgePad)+2*padding,pageHeight=height+labelHeight+2*badgePad+labelGap+2*padding;
   group.translate(left-(sourceAB[0]-sourceBounds[0])-copiedBounds[0],top-(sourceAB[1]-sourceBounds[1])-copiedBounds[1]);
   var clip=group.pathItems.rectangle(top,left,width,height);clip.stroked=false;clip.filled=false;clip.clipping=true;clip.move(group,ElementPlacement.PLACEATBEGINNING);group.clipped=true;
   var board=[cursor,0,cursor+pageWidth,-pageHeight];if(k===0)doc.artboards[0].artboardRect=board;else doc.artboards.add(board);
   groups.push(group.name);labels.push(labelText);used.push(k+1);
   placements.push({name:group.name,page:k+1,artboardIndex:k,artboardRect:JFW.bounds(board),column:'figure',widthMm:width/(72/25.4),bounds:[left,top,left+width,top-height],sourceArtboardRect:sourceAB,labelBounds:[cursor+padding+badgePad,-padding-badgePad,cursor+padding+badgePad+labelWidth,-padding-badgePad-labelHeight],badgeBounds:badgeBounds});
   cursor+=pageWidth+pageGap;
  }
  stage('review_pages_save_ai');var aiOptions=new IllustratorSaveOptions();aiOptions.pdfCompatible=true;doc.saveAs(new File(req.ai),aiOptions);
  stage('review_pages_save_pdf');var pdfOptions=new PDFSaveOptions();pdfOptions.preserveEditability=true;pdfOptions.artboardRange=used.join(',');doc.saveAs(new File(req.pdf),pdfOptions);
  stage('review_pages_export_preview');doc.artboards.setActiveArtboardIndex(0);var png=new ExportOptionsPNG24();png.artBoardClipping=true;png.transparency=false;png.horizontalScale=300/72*100;png.verticalScale=300/72*100;doc.exportFile(new File(req.preview),ExportType.PNG24,png);
  var pageSizes=[];for(var si=0;si<placements.length;si++){var ab=placements[si].artboardRect;pageSizes.push([ab[2]-ab[0],ab[1]-ab[3]]);}
  return {doc:doc,retainedInputs:retainedInputs,ownedInputsKeptOpen:retainedInputs.length,groups:groups,labels:labels,placements:placements,pages:req.items.length,templateTexts:[],template:{layout:'figure-pages',artboardCount:doc.artboards.length,usedArtboards:used,pageSizes:pageSizes}};
 }catch(e){if(req.keepDocumentOpen===true){if(opened)retainedInputs.push(opened);e.retainedInputs=retainedInputs;e.retainedDocument=doc;e.ownedInputsKeptOpen=retainedInputs.length;}else{if(opened)opened.close(SaveOptions.DONOTSAVECHANGES);if(doc)doc.close(SaveOptions.DONOTSAVECHANGES);}throw e;}
};
