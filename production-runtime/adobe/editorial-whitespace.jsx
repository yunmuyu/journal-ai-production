// Collapse explicitly verified empty horizontal bands without scaling glyphs or images.
JFW.compressVerticalWhitespace=function(doc,bands){
 function mapped(y){var down=-y,removed=0;for(var i=0;i<bands.length;i++){var a=bands[i][0],b=bands[i][1];if(down>=b)removed+=b-a;else if(down>a)removed+=down-a;}return y+removed;}
 var i,j,p,b,oldY;
 for(i=0;i<doc.pathItems.length;i++){p=doc.pathItems[i];for(j=0;j<p.pathPoints.length;j++){var q=p.pathPoints[j],a=q.anchor,l=q.leftDirection,r=q.rightDirection;q.anchor=[a[0],mapped(a[1])];q.leftDirection=[l[0],mapped(l[1])];q.rightDirection=[r[0],mapped(r[1])];}}
 for(i=0;i<doc.textFrames.length;i++){p=doc.textFrames[i];b=p.visibleBounds;oldY=(b[1]+b[3])/2;p.translate(0,mapped(oldY)-oldY);}
 for(i=0;i<doc.rasterItems.length;i++){p=doc.rasterItems[i];oldY=p.top-p.height/2;p.translate(0,mapped(oldY)-oldY);}
 for(i=0;i<doc.placedItems.length;i++){p=doc.placedItems[i];oldY=p.top-p.height/2;p.translate(0,mapped(oldY)-oldY);}
};
