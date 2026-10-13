JFW.arrow5={width:3.7,depth:4.4,notch:.8};
JFW.arrow5BoundaryGap=function(finalShaftMm,layoutScale){return finalShaftMm*72/25.4/layoutScale+JFW.arrow5.depth/2;};
JFW.drawArrow5=function(layer,id,points,color,strokeWidth,both){
 var cfg=JFW.arrow5,shaftPoints=[],i;for(i=0;i<points.length;i++)shaftPoints.push([points[i][0],points[i][1]]);
 var tip=points[points.length-1],previous=points[points.length-2],dx=tip[0]-previous[0],dy=tip[1]-previous[1],length=Math.sqrt(dx*dx+dy*dy);
 if(length<cfg.depth/2)throw Error('Arrow 5 terminal segment is shorter than its inset: '+id);
 var ux=dx/length,uy=dy/length,bx=tip[0]-ux*cfg.depth,by=tip[1]-uy*cfg.depth;
 shaftPoints[shaftPoints.length-1]=[tip[0]-ux*cfg.depth/2,tip[1]-uy*cfg.depth/2];
 var shaft=layer.pathItems.add();shaft.name=id;shaft.setEntirePath(shaftPoints);shaft.filled=false;shaft.stroked=true;shaft.strokeColor=color;shaft.strokeWidth=strokeWidth;shaft.strokeDashes=[];
 var head=layer.pathItems.add();head.name=id+'-head';head.setEntirePath([[bx+uy*cfg.width/2,by-ux*cfg.width/2],[bx+ux*cfg.notch,by+uy*cfg.notch],[bx-uy*cfg.width/2,by+ux*cfg.width/2],tip]);head.closed=true;head.filled=true;head.stroked=false;head.fillColor=color;
 if(both){
  var start=points[0],next=points[1],sx=next[0]-start[0],sy=next[1]-start[1],sl=Math.sqrt(sx*sx+sy*sy);
  if(sl<cfg.depth*2)throw Error('Arrow 5 bidirectional segment is too short: '+id);
  sx/=sl;sy/=sl;shaftPoints[0]=[start[0]+sx*cfg.depth/2,start[1]+sy*cfg.depth/2];shaft.setEntirePath(shaftPoints);
  var startHead=layer.pathItems.add();startHead.name=id+'-start-head';startHead.setEntirePath([[start[0]+sx*cfg.depth+sy*cfg.width/2,start[1]+sy*cfg.depth-sx*cfg.width/2],[start[0]+sx*(cfg.depth-cfg.notch),start[1]+sy*(cfg.depth-cfg.notch)],[start[0]+sx*cfg.depth-sy*cfg.width/2,start[1]+sy*cfg.depth+sx*cfg.width/2],start]);startHead.closed=true;startHead.filled=true;startHead.stroked=false;startHead.fillColor=color;
  return [shaft,head,startHead];
 }
 return [shaft,head];
};
