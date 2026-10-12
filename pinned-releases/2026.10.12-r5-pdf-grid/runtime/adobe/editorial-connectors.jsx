JFW.arrow5={width:3.7,depth:4.4,notch:.8};
JFW.arrow5BoundaryGap=function(finalShaftMm,layoutScale){return finalShaftMm*72/25.4/layoutScale+JFW.arrow5.depth/2;};
JFW.drawArrow5=function(layer,id,points,color,strokeWidth){
 var cfg=JFW.arrow5,shaftPoints=[],i;for(i=0;i<points.length;i++)shaftPoints.push([points[i][0],points[i][1]]);
 var tip=points[points.length-1],previous=points[points.length-2],dx=tip[0]-previous[0],dy=tip[1]-previous[1],length=Math.sqrt(dx*dx+dy*dy);
 if(length<cfg.depth/2)throw Error('Arrow 5 terminal segment is shorter than its inset: '+id);
 var ux=dx/length,uy=dy/length,bx=tip[0]-ux*cfg.depth,by=tip[1]-uy*cfg.depth;
 shaftPoints[shaftPoints.length-1]=[tip[0]-ux*cfg.depth/2,tip[1]-uy*cfg.depth/2];
 var shaft=layer.pathItems.add();shaft.name=id;shaft.setEntirePath(shaftPoints);shaft.filled=false;shaft.stroked=true;shaft.strokeColor=color;shaft.strokeWidth=strokeWidth;shaft.strokeDashes=[];
 var head=layer.pathItems.add();head.name=id+'-head';head.setEntirePath([[bx+uy*cfg.width/2,by-ux*cfg.width/2],[bx+ux*cfg.notch,by+uy*cfg.notch],[bx-uy*cfg.width/2,by+ux*cfg.width/2],tip]);head.closed=true;head.filled=true;head.stroked=false;head.fillColor=color;
 return [shaft,head];
};
