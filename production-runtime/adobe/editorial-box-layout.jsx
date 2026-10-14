JFW.drawBoxLayout=function(doc,spec,fontSize,targetWidthMm){
 var metrics=JFW.layoutMetrics,font=app.textFonts.getByName('ATC-73b000205b8b4f530020*1'),gap=metrics.compactGap,padX=metrics.padX,padY=metrics.padY,framePad=metrics.framePad;
 var black=new RGBColor();black.red=black.green=black.blue=0;
 var texts=[],boxes=[],frames=[],groups={},ids={},sections=spec.sections;
 if(!sections||!sections.length)throw Error('Box layout sections required');
 function label(id,value){
  if(ids[id])throw Error('Duplicate box layout ID: '+id);ids[id]=true;
  var tf=doc.textFrames.add();tf.name='JFW_BOX_TEXT_'+id;tf.contents=value;
  var ca=tf.textRange.characterAttributes;ca.textFont=font;ca.size=fontSize;ca.autoLeading=false;ca.leading=fontSize*1.2;ca.fillColor=black;
  for(var i=0;i<tf.paragraphs.length;i++)tf.paragraphs[i].paragraphAttributes.justification=Justification.CENTER;
  app.redraw();var outline=tf.duplicate().createOutline(),b=JFW.bounds(outline.visibleBounds);outline.remove();
  var item={id:id,text:value,tf:tf,inkWidth:b[2]-b[0],inkHeight:b[1]-b[3]};texts.push(item);return item;
 }
 function prepare(n){
  if(n.kind==='box'){
   n.label=label(n.id,n.text);n.w=n.label.inkWidth+2*padX;n.h=n.label.inkHeight+2*padY;
   if(n.widthGroup)groups[n.widthGroup]=Math.max(groups[n.widthGroup]||0,n.w);
  }else if(n.kind==='frame'){n.label=label(n.id+'-title',n.title);prepare(n.content);}
  else if(n.kind==='row'||n.kind==='column'){if(!n.children||!n.children.length)throw Error('Empty layout group');for(var i=0;i<n.children.length;i++)prepare(n.children[i]);}
  else throw Error('Unsupported box layout kind '+n.kind);
 }
 function measure(n){
  if(n.kind==='box'){if(n.widthGroup)n.w=groups[n.widthGroup];return;}
  if(n.kind==='frame'){measure(n.content);n.w=Math.max(n.content.w,n.label.inkWidth)+2*framePad;n.h=n.content.h+n.label.inkHeight+gap+2*framePad;if(n.widthGroup){n.w=Math.max(n.w,groups[n.widthGroup]||0);groups[n.widthGroup]=n.w;}return;}
  var sum=0,max=0;for(var i=0;i<n.children.length;i++){var c=n.children[i];measure(c);if(n.kind==='row'){sum+=c.w;max=Math.max(max,c.h);}else{sum+=c.h;max=Math.max(max,c.w);}}
  if(n.kind==='row'){n.w=sum+gap*(n.children.length-1);n.h=max;}else{n.w=max;n.h=sum+gap*(n.children.length-1);}
 }
 function positionText(t,x,y,w,h){
  app.redraw();var outline=t.tf.duplicate().createOutline(),b=JFW.bounds(outline.visibleBounds);outline.remove();
  t.tf.translate(x+w/2-(b[0]+b[2])/2,-y-h/2-(b[1]+b[3])/2);
 }
 function rect(id,x,y,w,h){var p=doc.pathItems.rectangle(-y,x,w,h);p.name='JFW_BOX_FRAME_'+id;p.filled=false;p.stroked=true;p.strokeWidth=.5;p.strokeColor=black;p.strokeDashes=[];return p;}
 function place(n,x,y,w,h){
  if(w<n.w-.01||h<n.h-.01)throw Error('Layout allocated less than measured content: '+n.id);
  if(n.kind==='box'){var drawn=rect(n.id,x,y,w,h);positionText(n.label,x,y,w,h);boxes.push({id:n.id,text:n.text,bounds:JFW.bounds(drawn.geometricBounds),minimumPadding:[padX,padY,padX,padY]});return;}
  if(n.kind==='frame'){
   rect(n.id,x,y,w,h);positionText(n.label,x+framePad,y+framePad,w-2*framePad,n.label.inkHeight);
   place(n.content,x+framePad,y+framePad+n.label.inkHeight+gap,w-2*framePad,n.content.h);
   frames.push({id:n.id,bounds:[x,-y,x+w,-y-h]});return;
  }
  var cursor=0,i,c,extra=0;
  if(n.kind==='row'){
   if(n.stretch!==false)extra=(w-n.w)/n.children.length;
   for(i=0;i<n.children.length;i++){c=n.children[i];place(c,x+cursor,y,c.w+extra,h);cursor+=c.w+extra+gap;}
  }else{
   for(i=0;i<n.children.length;i++){c=n.children[i];place(c,x,y+cursor,w,c.h);cursor+=c.h+gap;}
  }
 }
 var labelBand=0,contentWidth=0,i;
 for(i=0;i<sections.length;i++){var s=sections[i];s.label=label('section-'+s.id,s.title);labelBand=Math.max(labelBand,s.label.inkWidth);prepare(s.content);}
 for(i=0;i<sections.length;i++)measure(sections[i].content);
 for(i=0;i<sections.length;i++){measure(sections[i].content);contentWidth=Math.max(contentWidth,sections[i].content.w);}
 var y=0,separators=[],layerFrames=spec.sectionFrames===true;
 function layerArrow(x,top,bottom,both,id){
  JFW.drawArrow5(doc.activeLayer,'JFW_LAYER_ARROW_'+id,[[x,-bottom],[x,-top]],black,.5,both);
 }
 for(i=0;i<sections.length;i++){
  var s=sections[i],inset=layerFrames?Math.max(framePad,padX):0,height=s.content.h+2*inset;
  if(layerFrames)rect('section-'+s.id,0,y,labelBand+gap+contentWidth+2*inset,height);
  positionText(s.label,inset,y+inset,labelBand,s.content.h);place(s.content,inset+labelBand+gap,y+inset,contentWidth,s.content.h);y+=height;
  if(i<sections.length-1){
   if(layerFrames){
    var links=s.linksAfter||[],distance=metrics.arrowLength;for(var al=0;al<links.length;al++)if(links[al].both)distance=Math.max(distance,2*JFW.arrow5.depth+4);
    if(links.length)for(var li=0;li<links.length;li++){var link=links[li];if(!(link.position>=0&&link.position<=1))throw Error('Invalid layer arrow position');layerArrow(inset+labelBand+gap+contentWidth*link.position,y,y+distance,link.both===true,s.id+'-'+li);}
    y+=distance;
   }else{
    var line=doc.pathItems.add();line.name='JFW_BOX_SEPARATOR_'+s.id;line.setEntirePath([[0,-y-gap/2],[labelBand+gap+contentWidth,-y-gap/2]]);line.filled=false;line.stroked=true;line.strokeWidth=.5;line.strokeColor=black;line.strokeDashes=[4,3];separators.push(s.id);y+=gap;
   }
  }
 }
 app.redraw();var scale=1,naturalBounds=JFW.bounds(doc.visibleBounds),naturalWidthMm=(naturalBounds[2]-naturalBounds[0]+.5)*25.4/72;
 if(targetWidthMm!==undefined){
  if(!(targetWidthMm>0))throw Error('Target width must be positive');
  if(naturalWidthMm>targetWidthMm){
   scale=(targetWidthMm*72/25.4-.5)/(naturalBounds[2]-naturalBounds[0]);
   if(fontSize*scale<6-0.000001)throw Error('LAYOUT_REFLOW_REQUIRED: final font '+(fontSize*scale)+' pt is below 6 pt; wrap long labels or rearrange the layout before considering double column');
   var objects=[],layer=doc.activeLayer;
   for(i=0;i<layer.pageItems.length;i++)if(layer.pageItems[i].parent===layer)objects.push(layer.pageItems[i]);
   var artwork=layer.groupItems.add();artwork.name='JFW_BOX_LAYOUT_SCALED';
   for(i=0;i<objects.length;i++)objects[i].move(artwork,ElementPlacement.PLACEATEND);
   artwork.resize(scale*100,scale*100,true,true,true,true,scale*100);
   app.redraw();
  }
 }
 if(fontSize*scale<6-0.000001)throw Error('LAYOUT_REFLOW_REQUIRED: final font below 6 pt');
 var measured=[],issues=[],minimum=[Infinity,Infinity,Infinity,Infinity];
 for(i=0;i<boxes.length;i++)for(var pi=0;pi<doc.pathItems.length;pi++)if(doc.pathItems[pi].name==='JFW_BOX_FRAME_'+boxes[i].id){boxes[i].bounds=JFW.bounds(doc.pathItems[pi].geometricBounds);boxes[i].minimumPadding=[padX*scale,padY*scale,padX*scale,padY*scale];}
 for(i=0;i<frames.length;i++)for(var pi=0;pi<doc.pathItems.length;pi++)if(doc.pathItems[pi].name==='JFW_BOX_FRAME_'+frames[i].id)frames[i].bounds=JFW.bounds(doc.pathItems[pi].geometricBounds);
 for(i=0;i<texts.length;i++){
  var t=texts[i],outline=t.tf.duplicate().createOutline(),ink=JFW.bounds(outline.visibleBounds);outline.remove();
  measured.push({id:t.id,text:t.text,size:t.tf.textRange.characterAttributes.size,font:font.name,inkBounds:ink,layoutScale:scale});
  for(var j=0;j<boxes.length;j++)if(boxes[j].id===t.id){
   var box=boxes[j],b=box.bounds,padding=[ink[0]-b[0],b[1]-ink[1],b[2]-ink[2],ink[3]-b[3]];box.paddingPt=padding;
   for(var k=0;k<4;k++){minimum[k]=Math.min(minimum[k],padding[k]);if(padding[k]<box.minimumPadding[k]-.01)issues.push({type:'node_text_padding',nodeId:t.id,side:k,actualPt:padding[k],requiredPt:box.minimumPadding[k]});}
  }
 }
 var vb=JFW.bounds(doc.visibleBounds);doc.artboards[0].artboardRect=[vb[0]-.25,vb[1]+.25,vb[2]+.25,vb[3]-.25];
 return {texts:measured,boxes:boxes,frames:frames,separators:separators,minimumPaddingPt:minimum,basePaddingPt:[padX,padY,padX,padY],gapPt:gap*scale,baseGapPt:gap,baseFontSize:fontSize,scale:scale,naturalWidthMm:naturalWidthMm,artboard:JFW.bounds(doc.artboards[0].artboardRect),mechanicalIssues:issues};
};
