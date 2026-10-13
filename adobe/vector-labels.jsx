JFW.reletterGroups=function(doc,groups,fontSize){
 fontSize=fontSize===undefined?8:fontSize;var leading=fontSize===6?7:fontSize*1.2;
 var refs=[],used={},i,j,g,idx,t;
 for(i=0;i<doc.textFrames.length;i++)refs.push(doc.textFrames[i]);
 for(i=0;i<groups.length;i++)if(groups[i].font!==undefined&&groups[i].font!=='TimesNewRomanPS-ItalicMT'&&groups[i].font!=='TimesNewRomanPSMT')throw Error('Invalid group font');
 for(i=0;i<groups.length;i++){g=groups[i];if(g.frameAnchorPt!==undefined){var fa=g.frameAnchorPt;if(Object.prototype.toString.call(fa)!=='[object Array]'||fa.length!==4||fa[0]>=fa[2]||fa[1]<=fa[3])throw Error('Invalid frame anchor');for(var fi=0;fi<4;fi++)if(typeof fa[fi]!=='number'||!isFinite(fa[fi]))throw Error('Invalid frame anchor');if(g.offsetPt!==undefined||(g.align!==undefined&&g.align!=='center'))throw Error('Frame anchor requires unshifted center alignment');}if(g.align!==undefined&&g.align!=="left"&&g.align!=="center"&&g.align!=="right")throw Error("Invalid label alignment");if(g.rotation!==undefined&&g.rotation!==-90&&g.rotation!==0&&g.rotation!==90)throw Error('Invalid label rotation');if(g.offsetPt&&(Object.prototype.toString.call(g.offsetPt)!=='[object Array]'||g.offsetPt.length!==2||typeof g.offsetPt[0]!=='number'||typeof g.offsetPt[1]!=='number'||!isFinite(g.offsetPt[0])||!isFinite(g.offsetPt[1])))throw Error('Invalid label offset');if(!g.indices.length||g.indices.length!==g.expected.length||!g.text||!g.text.replace(/\s/g,''))throw Error('Invalid text group');for(j=0;j<g.indices.length;j++){idx=g.indices[j];if(idx!==Math.floor(idx)||idx<0||idx>=refs.length||used[idx])throw Error('Invalid or duplicate text index');if(refs[idx].contents!==g.expected[j])throw Error('Text identity mismatch at '+idx);used[idx]=true;}}
 for(i=0;i<groups.length;i++){
  g=groups[i];var box=null;
  for(j=0;j<g.indices.length;j++){var b=refs[g.indices[j]].geometricBounds;if(!box)box=[b[0],b[1],b[2],b[3]];else{box[0]=Math.min(box[0],b[0]);box[1]=Math.max(box[1],b[1]);box[2]=Math.max(box[2],b[2]);box[3]=Math.min(box[3],b[3]);}}
  if(g.frameAnchorPt)box=g.frameAnchorPt.slice(0);
  var lines=g.text.split(/\r\n|\r|\n/);
  if(lines.length>1&&(!g.align||g.align==='center')&&!g.rotation){
   var lineTargets=[];
   for(var li=0;li<lines.length;li++){
    t=doc.textFrames.add();if(g.recreate===true){t.opacity=100;t.blendingMode=BlendModes.NORMAL;}t.contents=lines[li];t.textRange.paragraphAttributes.justification=Justification.CENTER;
    var lineAttrs=t.textRange.characterAttributes;lineAttrs.textFont=g.font?app.textFonts.getByName(g.font):JFW.editorialFont();lineAttrs.size=fontSize;lineAttrs.autoLeading=false;lineAttrs.leading=leading;
    var lineBlack=new RGBColor();lineBlack.red=lineBlack.green=lineBlack.blue=0;lineAttrs.fillColor=lineBlack;
    var lineOutline=t.duplicate().createOutline(),lineInk=lineOutline.visibleBounds;
    t.translate((box[0]+box[2]-lineInk[0]-lineInk[2])/2,(box[1]+box[3]-lineInk[1]-lineInk[3])/2-(li-(lines.length-1)/2)*leading);
    lineTargets.push(t);lineOutline.remove();if(g.offsetPt)t.translate(g.offsetPt[0],g.offsetPt[1]);
   }
   if(g.frameAnchorPt){var whole=null;for(var ti=0;ti<lineTargets.length;ti++){var outlined=lineTargets[ti].duplicate().createOutline(),bi=outlined.visibleBounds;if(!whole)whole=[bi[0],bi[1],bi[2],bi[3]];else{whole[0]=Math.min(whole[0],bi[0]);whole[1]=Math.max(whole[1],bi[1]);whole[2]=Math.max(whole[2],bi[2]);whole[3]=Math.min(whole[3],bi[3]);}outlined.remove();}var wx=(box[0]+box[2]-whole[0]-whole[2])/2,wy=(box[1]+box[3]-whole[1]-whole[3])/2;for(var ti=0;ti<lineTargets.length;ti++)lineTargets[ti].translate(wx,wy);}
   continue;
  }
  t=g.indices.length===1&&g.rotation===undefined&&g.recreate!==true?refs[g.indices[0]].duplicate():doc.textFrames.add();if(g.recreate===true){t.opacity=100;t.blendingMode=BlendModes.NORMAL;}t.contents=g.text;t.textRange.paragraphAttributes.justification=Justification.CENTER;
  var ca=t.textRange.characterAttributes;ca.textFont=g.font?app.textFonts.getByName(g.font):JFW.editorialFont();ca.size=fontSize;ca.autoLeading=false;ca.leading=leading;var black=new RGBColor();black.red=black.green=black.blue=0;ca.fillColor=black;if(g.rotation)t.rotate(g.rotation);
  var outline=t.duplicate().createOutline(),ink=outline.visibleBounds;var dx;if(g.align==="left"){dx=box[0]-ink[0];}else if(g.align==="right"){dx=box[2]-ink[2];}else{dx=(box[0]+box[2]-ink[0]-ink[2])/2;}t.translate(dx,(box[1]+box[3]-ink[1]-ink[3])/2);outline.remove();if(g.offsetPt)t.translate(g.offsetPt[0],g.offsetPt[1]);
 }
 for(i=refs.length-1;i>=0;i--)if(used[i])refs[i].remove();
};
JFW.grayscaleArtwork=function(doc){
 function convert(c){var r,g,b;if(c.typename==='RGBColor'){r=c.red;g=c.green;b=c.blue;}else if(c.typename==='CMYKColor'){r=255*(1-c.cyan/100)*(1-c.black/100);g=255*(1-c.magenta/100)*(1-c.black/100);b=255*(1-c.yellow/100)*(1-c.black/100);}else if(c.typename==='GrayColor'||c.typename==='NoColor')return c;else throw Error('Unsupported grayscale color: '+c.typename);var out=new RGBColor();out.red=out.green=out.blue=.299*r+.587*g+.114*b;return out;}
 for(var i=0;i<doc.pathItems.length;i++){var p=doc.pathItems[i];if(p.filled)p.fillColor=convert(p.fillColor);if(p.stroked)p.strokeColor=convert(p.strokeColor);}
};
JFW.raiseEditorialText=function(doc){
 var refs=[],before=[],i,j;
 for(i=0;i<doc.textFrames.length;i++){refs.push(doc.textFrames[i]);before.push({text:doc.textFrames[i].contents,bounds:JFW.bounds?JFW.bounds(doc.textFrames[i].geometricBounds):doc.textFrames[i].geometricBounds.slice(0)});}
 if(!refs.length)return {name:null,topmost:true,textCount:0};
 var layer=doc.layers.add();layer.name='期刊文字';
 for(i=0;i<refs.length;i++){
  refs[i].move(layer,ElementPlacement.PLACEATEND);
  if(refs[i].contents!==before[i].text)throw Error('Text changed while raising layer');
  var after=refs[i].geometricBounds;for(j=0;j<4;j++)if(Math.abs(after[j]-before[i].bounds[j])>0.02)throw Error('Text moved while raising layer');
 }
 if(doc.layers[0]!==layer)throw Error('Editorial text layer is not topmost');
 return {name:layer.name,topmost:true,textCount:refs.length};
};
JFW.styleText=function(tf,styles){
 var used={},i,j,s;
 for(i=0;i<styles.length;i++){s=styles[i];if(!s||typeof s!=='object'||s instanceof Array||typeof s.start!=='number'||typeof s.length!=='number'||!isFinite(s.start)||!isFinite(s.length)||s.start!==Math.floor(s.start)||s.length!==Math.floor(s.length)||s.start<0||s.length<1||s.start+s.length>tf.contents.length||(s.font!=='TimesNewRomanPS-ItalicMT'&&s.font!=='TimesNewRomanPSMT'))throw Error('Invalid local text style');if(s.size!==undefined&&(typeof s.size!=='number'||!isFinite(s.size)||s.size<6||s.size>tf.textRange.characterAttributes.size))throw Error('Invalid local text style size');if(s.baselineShift!==undefined&&(typeof s.baselineShift!=='number'||!isFinite(s.baselineShift)||s.baselineShift< -2||s.baselineShift>0))throw Error('Invalid local text style baseline shift');if(s.script!==undefined&&s.script!=='subscript'&&s.script!=='superscript')throw Error('Invalid local text style');for(j=s.start;j<s.start+s.length;j++){if(used[j])throw Error('Overlapping local text styles');used[j]=true;}}
 for(i=0;i<styles.length;i++){s=styles[i];var font=app.textFonts.getByName(s.font);for(j=s.start;j<s.start+s.length;j++){var attributes=tf.characters[j].characterAttributes;attributes.textFont=font;if(s.size!==undefined)attributes.size=s.size;if(s.baselineShift!==undefined)attributes.baselineShift=s.baselineShift;if(s.script==='subscript')attributes.baselinePosition=FontBaselineOption.SUBSCRIPT;else if(s.script==='superscript')attributes.baselinePosition=FontBaselineOption.SUPERSCRIPT;}}
 if(styles.length)tf.note='JFW_STYLED_TEXT';
};
