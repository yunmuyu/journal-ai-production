// Shared semantic layouts. Author data contains content, never Illustrator drawing commands.
JFW.drawTechnicalLayout=function(g,api,W){
 var gap=3,fs=g.fontSize,mm=72/25.4,i,j;
 function measure(s){return api.measure(s.replace(/\n/g,'\r'));}
 function text(id,s,x,y){api.text(id,s.replace(/\n/g,'\r'),x,-y);}
 function line(id,points,arrow,dash){var p=[];for(var z=0;z<points.length;z++)p.push([points[z][0],-points[z][1]]);api.line(id,p,arrow||'none',dash?'dashed':'solid');}
 function box(id,s,x,y,w,h){api.node(id,s.replace(/\n/g,'\r'),'process',x,-y,w,h);}
 function outline(id,x,y,w,h){line(id,[[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]],'none');}
 if(g.layout==='memoryMap'){
  var sizes=[],margin=0;for(i=0;i<g.boundaries.length;i++){sizes[i]=measure(g.boundaries[i].text);margin=Math.max(margin,sizes[i].w/2);}
  var left=margin+gap,width=W-2*left,top=fs*4,height=fs*4;
  if(width<=0)throw Error('Memory map width exhausted');
  for(i=0;i<g.boundaries.length;i++){
   var x=left+width*g.boundaries[i].position;text('address-'+i,g.boundaries[i].text,x,fs/2);
   if(i&&x-(left+width*g.boundaries[i-1].position)<(sizes[i].w+sizes[i-1].w)/2+gap)throw Error('Memory address labels require wider layout');
   line('boundary-'+i,[[x,fs+gap],[x,i>0&&i<g.boundaries.length-1?top+height:top]],'none',true);
  }
  outline('memory-frame',left,top,width,height);text('memory-title',g.title,left+width/2,top+height/2);
  for(i=0;i<g.regions.length;i++){
   var x0=left+width*g.boundaries[i].position,x1=left+width*g.boundaries[i+1].position,m=measure(g.regions[i]),cy=fs*2.5,cx=(x0+x1)/2;
   if(x1-x0<m.w+2*gap+4)throw Error('Memory region label requires wider layout');
   text('region-'+i,g.regions[i],cx,cy);line('range-left-'+i,[[cx-m.w/2-gap,cy],[x0,cy]],'end',true);line('range-right-'+i,[[cx+m.w/2+gap,cy],[x1,cy]],'end',true);
  }
 }else if(g.layout==='sequence'){
  gap=1.5;
  var nameWidth=0,requestWidth=0,operationWidth=0,head=[];
  for(i=0;i<g.participants.length;i++)head[i]=measure(g.participants[i]);
  for(i=0;i<g.steps.length;i++){var s=g.steps[i];nameWidth=Math.max(nameWidth,measure(s.name).w+9);requestWidth=Math.max(requestWidth,measure(s.request).w,measure(s.response).w);if(s.operation)operationWidth=Math.max(operationWidth,measure(s.operation).w);}
  var phaseInk=0;for(i=0;i<(g.phases||[]).length;i++)phaseInk=Math.max(phaseInk,measure(g.phases[i].text.split('').join('\r')).w);
  var phaseWidth=g.phases?phaseInk+3+2*gap:0,xName=phaseWidth+nameWidth/2,x0=phaseWidth+nameWidth+gap+3,x1=x0+Math.max(requestWidth+2*gap+6,g.selfMessage?12+measure(g.selfMessage).w+3:0),x2=x1+Math.max(operationWidth+2*gap+6,(head[1].w+head[2].w)/2+12);
  var needed=x2+head[2].w/2+4.5;if(needed>W)throw Error('Sequence natural width '+needed+' exceeds '+W+'; relayout or smaller font required');
  var xs=[x0,x1,x2],headerH=Math.max(head[0].h,head[1].h,head[2].h)+5.4,base=headerH+fs*3+gap,pairHeight=3*fs+4*gap+3;
  var end=base+g.steps.length*pairHeight;
  for(i=0;i<3;i++){box('participant-'+i,g.participants[i],xs[i],headerH/2,head[i].w+9,headerH);line('life-'+i,[[xs[i],headerH],[xs[i],end]],'none',true);}
  // Opaque native activation boxes sit in front of the dashed lifelines.
  box('active-client','',x0,(headerH+gap+end)/2,4,end-headerH-gap);box('active-server','',x1,(base-fs+end)/2,4,end-base+fs);
  if(g.selfMessage){var sy=headerH+gap+fs/2;line('self',[[x0+2,sy],[x0+8,sy],[x0+8,sy+fs],[x0+2,sy+fs]],'end');text('self-label',g.selfMessage,x0+12+measure(g.selfMessage).w/2,sy+fs/2);}
  for(i=0;i<g.steps.length;i++){
   var st=g.steps[i],y=base+i*pairHeight,returnY=y+fs+2*gap,cy=(y+returnY)/2,nh=measure(st.name).h+5.4;
   box('step-'+i,st.name,xName,cy,nameWidth,nh);if(i<g.steps.length-1)line('next-'+i,[[xName,cy+nh/2],[xName,cy+pairHeight-nh/2]],'end');
   text('request-'+i,st.request,(x0+x1)/2,y-fs/2-gap);line('request-line-'+i,[[x0+2,y],[x1-2,y]],'end');
   text('response-'+i,st.response,(x0+x1)/2,returnY+fs/2+gap);line('response-line-'+i,[[x1-2,returnY],[x0+2,returnY]],'end');
   if(st.operation){box('active-operation-'+i,'',x2,cy,4,fs+2*gap);line('operation-'+i,[[x1+2,cy],[x2-2,cy]],'end');var ow=measure(st.operation).w;text('operation-label-'+i,st.operation,(x1+x2)/2,cy-fs/2-gap);}
  }
  for(i=0;i<(g.phases||[]).length;i++){var ph=g.phases[i],y0=base+ph.first*pairHeight-fs,y1=base+(ph.last+1)*pairHeight-fs;line('phase-'+i,[[phaseWidth-gap,y0],[phaseWidth-2*gap,y0],[phaseWidth-2*gap,y1],[phaseWidth-gap,y1]],'none',true);text('phase-label-'+i,ph.text.split('').join('\r'),phaseInk/2,(y0+y1)/2);}
 }else if(g.layout==='photoComparison'&&g.orientation==='horizontal'){
  var count=g.panels.length,root=measure(g.title),rootW=root.w+9,rootH=root.h+5.4,photoW=0,leafW=0,labelW=0,rowH=[],groups=[],groupGap=12;
  for(i=0;i<count;i++){var panel=g.panels[i];photoW=Math.max(photoW,measure(panel.title).w,35);var heights=[];
   for(j=0;j<panel.sections.length;j++){var sec=panel.sections[j],tm=measure(sec.text),lm=measure(sec.title);leafW=Math.max(leafW,tm.w+9);labelW=Math.max(labelW,lm.w);heights.push(tm.h+5.4);}groups.push(heights);
  }
  var branchGap=9,labelLane=labelW+6,xPhoto=rootW+branchGap+photoW/2,xLeaf=rootW+branchGap+photoW+labelLane+leafW/2,total=xLeaf+leafW/2;
  if(total>W)throw Error('Horizontal photo tree requires '+total+'pt but only '+W+'pt available');
  var y=0,groupCenters=[],positions=[];
  for(i=0;i<count;i++){var yy=y,rows=[];for(j=0;j<groups[i].length;j++){var h=groups[i][j];rows.push({cy:yy+h/2,h:h});yy+=h+9;}var groupH=yy-y-9;groupCenters.push(y+groupH/2);positions.push(rows);y+=groupH+groupGap;}
  var rootY=(groupCenters[0]+groupCenters[count-1])/2;box('comparison-title',g.title,rootW/2,rootY,rootW,rootH);
  for(i=0;i<count;i++){var cy=groupCenters[i],panel=g.panels[i],cap=measure(panel.title),photoH=Math.min(44,(positions[i][positions[i].length-1].cy-positions[i][0].cy)-cap.h-3);
   line('category-'+i,[[rootW,rootY],[rootW+branchGap/2,rootY],[rootW+branchGap/2,cy],[xPhoto-photoW/2,cy]],'end');api.image('photo-'+i,panel.image.path,xPhoto,cy-photoH/2,photoW-6,photoH);text('category-label-'+i,panel.title,xPhoto,cy+photoH/2+3+cap.h/2);
   for(j=0;j<panel.sections.length;j++){var sec=panel.sections[j],row=positions[i][j],left=xLeaf-leafW/2,bus=xPhoto+photoW/2+3;
    box('section-'+i+'-'+j,sec.text,xLeaf,row.cy,leafW,row.h);line('category-link-'+i+'-'+j,[[xPhoto+photoW/2,cy],[bus,cy],[bus,row.cy],[left,row.cy]],'end');var lm=measure(sec.title);text('section-label-'+i+'-'+j,sec.title,(bus+left)/2,row.cy-lm.h/2-3);
   }
  }
 }else if(g.layout==='photoComparison'){
  var panels=g.panels,count=panels.length,lane=3*mm,width=0,root=measure(g.title),items=[],sectionH=[],titleH=0;
  for(i=0;i<count;i++){
   var p=panels[i],q={title:measure(p.title),sections:[]};titleH=Math.max(titleH,q.title.h);width=Math.max(width,q.title.w+9);
   for(j=0;j<p.sections.length;j++){var a=measure(p.sections[j].title),b=measure(p.sections[j].text);q.sections.push({title:a,text:b});width=Math.max(width,a.w+9,b.w+9);sectionH[j]=Math.max(sectionH[j]||0,a.h+gap+b.h+5.4);}
   items.push(q);
  }
  var total=count*width+(count-1)*lane+gap*2;if(total>W)throw Error('Photo comparison natural width '+total+' exceeds '+W);
  var rootH=root.h+5.4,rootY=rootH/2,centers=[];for(i=0;i<count;i++)centers[i]=gap+width/2+i*(width+lane);
  box('comparison-title',g.title,total/2,rootY,root.w+9,rootH);
  var imageTop=rootH+3*mm,imageH=21*mm,imageW=Math.min(width-6,24*mm),captionY=imageTop+imageH+gap+titleH/2;
  for(i=0;i<count;i++){var cx=centers[i];line('category-'+i,[[total/2,rootH],[total/2,rootH+1.5*mm],[cx,rootH+1.5*mm],[cx,imageTop-gap]],'end');api.image('photo-'+i,panels[i].image.path,cx,imageTop,imageW,imageH);text('category-label-'+i,panels[i].title,cx,captionY);var y=captionY+titleH/2+3*mm,laneX=cx-width/2-gap;
   for(j=0;j<panels[i].sections.length;j++){
    var sec=panels[i].sections[j],sm=items[i].sections[j],by=y+sm.title.h+gap+(sectionH[j]-sm.title.h-gap)/2,bh=sectionH[j]-sm.title.h-gap;
    text('section-label-'+i+'-'+j,sec.title,cx,y+sm.title.h/2);box('section-'+i+'-'+j,sec.text,cx,by,width,bh);
    line('category-link-'+i+'-'+j,[[cx,captionY+titleH/2+gap],[laneX,captionY+titleH/2+gap],[laneX,by],[cx-width/2,by]],'end');y+=sectionH[j]+3*mm;
   }
  }
 }else throw Error('Unknown technical layout');
};
