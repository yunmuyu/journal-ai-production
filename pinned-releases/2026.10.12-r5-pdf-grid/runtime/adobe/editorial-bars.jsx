JFW.drawEditorialBars=function(doc,p){
 var c=p.chart,fontSize=p.fontSize===undefined?8:p.fontSize,leading=fontSize===6?7:fontSize*1.2,W=p.widthMm*72/25.4,L=30,R=W-2,top=12,bottom=82,plotH=bottom-top,plotW=R-L;
 function color(g){var x=new RGBColor();x.red=x.green=x.blue=g;return x;}
 function line(a,b,gray,width,parent){var q=(parent||doc).pathItems.add();q.setEntirePath([a,b]);q.stroked=true;q.strokeWidth=width;q.strokeColor=color(gray);q.filled=false;return q;}
 function text(s,x,y,align,rotation){var t=doc.textFrames.add();t.contents=s;var a=t.textRange.characterAttributes;a.textFont=JFW.editorialFont();a.size=fontSize;a.leading=leading;a.autoLeading=false;a.fillColor=color(0);t.textRange.paragraphAttributes.justification=Justification.CENTER;if(rotation)t.rotate(rotation);app.redraw();var o=t.duplicate().createOutline(),raw=o.visibleBounds,b=[raw[0],raw[1],raw[2],raw[3]],dx;if(align==='right')dx=x-b[2];else if(align==='left')dx=x-b[0];else dx=x-(b[0]+b[2])/2;t.translate(dx,-y-(b[1]+b[3])/2);o.remove();app.redraw();o=t.duplicate().createOutline();raw=o.visibleBounds;b=[raw[0],raw[1],raw[2],raw[3]];o.remove();var actualX;if(align==='right')actualX=b[2];else if(align==='left')actualX=b[0];else actualX=(b[0]+b[2])/2;var fixX=x-actualX,fixY=-y-(b[1]+b[3])/2;if(fixX||fixY)t.translate(fixX,fixY);return t;}
 function bar(x,y,w,h,series){var group=doc.groupItems.add(),box=group.pathItems.rectangle(-y,x,w,h);box.filled=true;box.fillColor=color(series.gray===undefined?255:series.gray);box.stroked=false;
  if(series.hatch){for(var a=-h;a<w;a+=3){line([x+a,-y],[x+a+h,-y-h],0,.4,group);if(series.hatch==='cross')line([x+a,-y-h],[x+a+h,-y],90,.3,group);}var clip=group.pathItems.rectangle(-y,x,w,h);clip.filled=false;clip.stroked=false;clip.clipping=true;clip.move(group,ElementPlacement.PLACEATBEGINNING);group.clipped=true;}return group;}
 if(c.orientation==='horizontal'){
  var hL=60,hR=W-42,hTop=18,hBottom=85,hPlotW=hR-hL,hPlotH=hBottom-hTop,hRows=c.categories.length,hRowH=hPlotH/hRows,hDecimals=c.tickDecimals===undefined?2:c.tickDecimals,hValueDecimals=c.valueDecimals===undefined?1:c.valueDecimals;
  // Grouping follows the user's established formatNumber/groupInteger/groupFraction rule.
  function formatNumber(value,decimals){var parts=value.toFixed(decimals).match(/^([+-]?)(\d+)(?:\.(\d+))?$/);if(!parts)return value.toFixed(decimals);var integer=parts[2].replace(/\B(?=(\d{3})+(?!\d))/g,' '),fraction=parts[3]?parts[3].replace(/(\d{3})(?=\d)/g,'$1 '):'';return parts[1]+integer+(parts[3]!==undefined?'.'+fraction:'');}
  for(var ht=0;ht<=Math.round(c.max/c.step);ht++){var hv=ht*c.step,hx=hL+hv/c.max*hPlotW;line([hx,-hTop],[hx,-hBottom],hv?215:0,hv?.3:.5);text(formatNumber(hv,hDecimals),hx,hBottom+9,'center');}
  for(var hi=0;hi<hRows;hi++){
   var hcy=hTop+(hi+.5)*hRowH,hseries=c.series[0],hval=hseries.values[hi],hbarW=hval/c.max*hPlotW,hbox=doc.pathItems.rectangle(-hcy+hRowH*.27,hL,hbarW,hRowH*.46);
   hbox.filled=true;hbox.fillColor=color(220);hbox.stroked=true;hbox.strokeWidth=.5;hbox.strokeColor=color(0);
   text(c.categories[hi],hL-4,hcy,'right');
   if(c.valueLabels)text(formatNumber(hval,hValueDecimals),hL+hbarW+3,hcy,'left');
  }
  if(c.xLabel)text(c.xLabel,(hL+hR)/2,hBottom+23,'center');
  if(c.title&&!c.omitTitle)text(c.title,(hL+hR)/2,7,'center');
  return;
 }
 for(var y=0;y<=c.max;y+=c.step){var yp=bottom-y/c.max*plotH;line([L,-yp],[R,-yp],y?215:0,y?.3:.5);text(String(y),L-4,yp,'right');}
 var catGap=plotW/c.categories.length,count=c.series.length,barW=count===2?9:7,barGap=2;
 for(var i=0;i<c.categories.length;i++){var cx=L+(i+.5)*catGap;for(var s=0;s<count;s++){var v=c.series[s].values[i],h=v/c.max*plotH,x=cx+(s-(count-1)/2)*(barW+barGap)-barW/2;bar(x,bottom-h,barW,h,c.series[s]);if(c.valueLabels)text(v.toFixed(1),cx+(s-(count-1)/2)*18,bottom-h-5,'center');}text(c.categories[i],cx,90+(c.categories[i].split(String.fromCharCode(10)).length-1)*4.8,'center');}
 if(c.xLabel)text(c.xLabel,(L+R)/2,100,'center');if(c.yLabel)text(c.yLabel,7,(top+bottom)/2,'center',90);
 var legendX=L+4;for(var k=0;k<count;k++){bar(legendX,0,4,4,c.series[k]);var t=text(c.series[k].name,legendX+8,2,'center');var o=t.duplicate().createOutline(),b=o.visibleBounds;t.translate(legendX+8-b[0],0);legendX+=8+(b[2]-b[0])+6;o.remove();}
};
