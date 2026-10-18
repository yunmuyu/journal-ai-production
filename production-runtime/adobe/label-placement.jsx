var JFWLabelPlacement = (function () {
    var EPS = 0.000001;
    function copy(value) {
        if (!(value instanceof Array) && Object.prototype.toString.call(value) !== '[object Array]') return value;
        var result = []; for (var i = 0; i < value.length; i++) result.push(copy(value[i])); return result;
    }
    function segments(path) {
        var points = path.points || [], result = [], count = points.length - (path.closed ? 0 : 1);
        for (var i = 0; i < count; i++) {
            var a = points[i], b = points[(i + 1) % points.length], p = a[0], q = b[0], c = a[1], d = [b[0][2], b[0][3]], previous = [p[0], p[1]];
            var straight = Math.abs(p[0] - c[0]) + Math.abs(p[1] - c[1]) + Math.abs(q[0] - d[0]) + Math.abs(q[1] - d[1]) < EPS;
            var steps = straight ? 1 : 32;
            for (var s = 1; s <= steps; s++) {
                var t = s / steps, u = 1 - t;
                var next = [u*u*u*p[0]+3*u*u*t*c[0]+3*u*t*t*d[0]+t*t*t*q[0],u*u*u*p[1]+3*u*u*t*c[1]+3*u*t*t*d[1]+t*t*t*q[1]];
                result.push([previous, next]); previous = next;
            }
        }
        return result;
    }
    function bounds(edges) {
        var b = [Infinity, -Infinity, -Infinity, Infinity];
        for (var i = 0; i < edges.length; i++) for (var j = 0; j < 2; j++) { var p = edges[i][j]; b[0]=Math.min(b[0],p[0]);b[1]=Math.max(b[1],p[1]);b[2]=Math.max(b[2],p[0]);b[3]=Math.min(b[3],p[1]); }
        return b;
    }
    function inflate(b, gap) { return [b[0]-gap,b[1]+gap,b[2]+gap,b[3]-gap]; }
    function overlap(a,b) { return a[0]<b[2]-EPS&&a[2]>b[0]+EPS&&a[3]<b[1]-EPS&&a[1]>b[3]+EPS; }
    function corners(b) { return [[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]]; }
    function inside(p, edges) {
        var yes = false;
        for (var i=0;i<edges.length;i++) { var a=edges[i][0],b=edges[i][1]; if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])yes=!yes; }
        return yes;
    }
    function crosses(a,b,rect) {
        var low=0,high=1;
        for(var axis=0;axis<2;axis++) { var delta=b[axis]-a[axis],min=axis?rect[3]:rect[0],max=axis?rect[1]:rect[2];
            if(Math.abs(delta)<EPS) { if(a[axis]<=min+EPS||a[axis]>=max-EPS)return false; }
            else {var x=(min-a[axis])/delta,y=(max-a[axis])/delta;low=Math.max(low,Math.min(x,y));high=Math.min(high,Math.max(x,y));if(low>=high-EPS)return false;}
        }
        return high>0&&low<1;
    }
    function above(a,b) {
        var x=a.paintStack,y=b.paintStack;
        if(x&&y&&x.length&&y.length) {
            for(var i=0;i<Math.min(x.length,y.length);i++) {if(typeof x[i]!=='number'||typeof y[i]!=='number'||!isFinite(x[i])||!isFinite(y[i]))return false;if(x[i]!==y[i])return x[i]<y[i];}
            return false;
        }
        return typeof a.paintOrder==='number'&&isFinite(a.paintOrder)&&typeof b.paintOrder==='number'&&isFinite(b.paintOrder)&&a.paintOrder<b.paintOrder;
    }
    function occluded(rect,item,allItems) {
        for(var i=0;i<(allItems||[]).length;i++) {
            var cover=allItems[i];
            if(cover!==item&&cover.path.opaqueFill===true&&cover.path.filled&&cover.path.closed&&above(cover.path,item.path)&&contains(rect,{edges:cover.edges,path:{stroked:false}},0))return true;
        }
        return false;
    }
    function touches(rect, item, clearance, boundaryOnly, allItems) {
        var protectedBox=inflate(rect,clearance+(item.path.stroked?(item.path.strokeWidthPt||0)/2:0)),i;
        if(occluded(protectedBox,item,allItems))return false;
        for(i=0;i<item.edges.length;i++)if(crosses(item.edges[i][0],item.edges[i][1],protectedBox))return true;
        if(!boundaryOnly&&item.path.filled&&item.path.closed) { var cs=corners(protectedBox);for(i=0;i<cs.length;i++)if(inside(cs[i],item.edges))return true; }
        return false;
    }
    function paddedContains(rect,owner,label,gap) {
        var scale=(label.fontSize||8)/8,px=Math.max(gap,4.5*scale),py=Math.max(gap,2.7*scale);
        return contains([rect[0]-(px-gap),rect[1]+(py-gap),rect[2]+(px-gap),rect[3]-(py-gap)],owner,gap);
    }
    function contains(rect,item,clearance) {
        var box=inflate(rect,clearance+(item.path.stroked?(item.path.strokeWidthPt||0)/2:0)),cs=corners(box);
        for(var i=0;i<cs.length;i++)if(!inside(cs[i],item.edges))return false;
        for(i=0;i<item.edges.length;i++)if(crosses(item.edges[i][0],item.edges[i][1],box))return false;
        return true;
    }
    function pointDistance(p,a,b) {
        var x=b[0]-a[0],y=b[1]-a[1],square=x*x+y*y,t=square?((p[0]-a[0])*x+(p[1]-a[1])*y)/square:0;t=Math.max(0,Math.min(1,t));x=p[0]-a[0]-t*x;y=p[1]-a[1]-t*y;return Math.sqrt(x*x+y*y);
    }
    function backgroundFor(item,owner) {
        if(item.path.solidObstacle||!item.path.closed||!item.path.filled)return false;
        if(!within(owner.bounds,item.bounds))return false;
        for(var i=0;i<owner.edges.length;i++) {
            var p=owner.edges[i][0];if(inside(p,item.edges))continue;
            var nearest=Infinity;for(var j=0;j<item.edges.length;j++)nearest=Math.min(nearest,pointDistance(p,item.edges[j][0],item.edges[j][1]));
            if(nearest>EPS)return false;
        }
        return true;
    }
    function distance(rect,item) {
        var cs=corners(rect),nearest=Infinity;
        for(var i=0;i<item.edges.length;i++) {var edge=item.edges[i];if(crosses(edge[0],edge[1],rect))return 0;
            for(var j=0;j<4;j++) {nearest=Math.min(nearest,pointDistance(cs[j],edge[0],edge[1]));for(var k=0;k<2;k++)nearest=Math.min(nearest,pointDistance(edge[k],cs[j],cs[(j+1)%4]));}
        }
        return nearest;
    }
    function within(rect,ab) { return rect[0]>=ab[0]-EPS&&rect[1]<=ab[1]+EPS&&rect[2]<=ab[2]+EPS&&rect[3]>=ab[3]-EPS; }
    function visible(p) { return !p.hidden&&!p.guides&&!p.clipping&&p.opacity!==0&&(p.stroked||p.filled); }
    function valid(rect) { if(!rect||rect.length!==4)return false;for(var i=0;i<4;i++)if(typeof rect[i]!=='number'||!isFinite(rect[i]))return false;return rect[0]<rect[2]&&rect[1]>rect[3]; }
    function rectangular(item) {
        if(!item.path.closed||item.path.points.length!==4||item.edges.length!==4)return false;
        var b=item.bounds;
        for(var i=0;i<item.edges.length;i++) {var a=item.edges[i][0],z=item.edges[i][1];if(Math.abs(a[0]-z[0])>EPS&&Math.abs(a[1]-z[1])>EPS)return false;if(Math.abs(a[0]-b[0])>EPS&&Math.abs(a[0]-b[2])>EPS)return false;if(Math.abs(a[1]-b[1])>EPS&&Math.abs(a[1]-b[3])>EPS)return false;}
        return true;
    }
    function solve(request) {
        var labels=request.labels||[],paths=request.paths||[],fixed=request.fixedTexts||[],ab=request.artboard,items=[],placed=[],edits=[],issues=[],ids={},i,j;
        if(!valid(ab))return {ok:false,placements:[],frameEdits:[],issues:[{type:'invalid_artboard'}]};
        for(i=0;i<paths.length;i++) {var p=paths[i];if(!visible(p))continue;var edges=segments(p);items.push({index:p.index===undefined?i:p.index,path:p,edges:edges,bounds:bounds(edges)});}
        for(i=0;i<fixed.length;i++)if(!valid(fixed[i].inkBounds))return {ok:false,placements:[],frameEdits:[],issues:[{type:'missing_fixed_ink'}]};
        function unobstructed(rect,owner,clearance,insideOwner,skipPlaced) {
            if(!within(rect,ab))return false;
            for(var pi=0;pi<items.length;pi++) {var obstacle=items[pi];if(obstacle===owner&&insideOwner)continue;
                if(touches(rect,obstacle,clearance,backgroundFor(obstacle,owner),items))return false;
            }
            for(var fi=0;fi<fixed.length;fi++)if(overlap(inflate(rect,clearance),fixed[fi].inkBounds))return false;
            for(var li=0;li<placed.length;li++)if(li!==skipPlaced&&overlap(inflate(rect,clearance),placed[li].inkBounds))return false;
            return true;
        }
        function expansion(owner,width,height,label) {
            if(!(label.allowFrameExpansionPt>0)||!owner.path.stroked||!(owner.path.strokeDashes&&owner.path.strokeDashes.length)||!rectangular(owner))return null;
            var b=owner.bounds,clearance=label.clearancePt===undefined?1.5:label.clearancePt,g=clearance+(owner.path.strokeWidthPt||0)/2;
            var scale=(label.fontSize||8)/8,gx=Math.max(clearance,4.5*scale)+(owner.path.strokeWidthPt||0)/2,gy=Math.max(clearance,2.7*scale)+(owner.path.strokeWidthPt||0)/2;
            var dx=Math.max(0,(width+2*gx-(b[2]-b[0]))/2)+EPS*4,dy=Math.max(0,(height+2*gy-(b[1]-b[3]))/2)+EPS*4;
            if(Math.max(dx,dy)>label.allowFrameExpansionPt+EPS)return null;
            var nb=[b[0]-dx,b[1]+dy,b[2]+dx,b[3]-dy],base=owner.baseBounds||b;if(Math.max(base[0]-nb[0],nb[1]-base[1],nb[2]-base[2],base[3]-nb[3])>label.allowFrameExpansionPt+EPS)return null;if(!within(inflate(nb,(owner.path.strokeWidthPt||0)/2),ab))return null;
            var strips=[[nb[0],nb[1],b[0],nb[3]],[b[2],nb[1],nb[2],nb[3]],[b[0],nb[1],b[2],b[1]],[b[0],b[3],b[2],nb[3]]];
            for(var s=0;s<strips.length;s++) {if(!valid(strips[s]))continue;
                for(var k=0;k<items.length;k++)if(items[k]!==owner&&touches(strips[s],items[k],(owner.path.strokeWidthPt||0)/2,backgroundFor(items[k],owner),items))return null;
                for(k=0;k<fixed.length;k++)if(overlap(inflate(strips[s],(owner.path.strokeWidthPt||0)/2),fixed[k].inkBounds))return null;
                for(k=0;k<placed.length;k++)if(overlap(inflate(strips[s],(owner.path.strokeWidthPt||0)/2),placed[k].inkBounds))return null;
            }
            var changed={},key;for(key in owner.path)changed[key]=owner.path[key];changed.points=copy(owner.path.points);
            for(var pp=0;pp<changed.points.length;pp++)for(var part=0;part<changed.points[pp].length;part++)for(var q=0;q<changed.points[pp][part].length;q++) {var n=changed.points[pp][part][q],shift;if(q%2){shift=-dy;if(Math.abs(n-b[1])<EPS)shift=dy;}else{shift=dx;if(Math.abs(n-b[0])<EPS)shift=-dx;}changed.points[pp][part][q]=n+shift;}
            var es=segments(changed);return {index:owner.index,path:changed,edges:es,bounds:bounds(es),baseBounds:owner.baseBounds||copy(owner.bounds)};
        }
        for(i=0;i<labels.length;i++) {
            var l=labels[i],owner=null;
            if(ids['$'+l.id]||!valid(l.inkBounds)) {issues.push({type:'invalid_label',id:l.id});continue;}ids['$'+l.id]=true;
            for(j=0;j<items.length;j++)if(items[j].index===l.ownerPathIndex)owner=items[j];
            if(!owner||!owner.path.closed) {issues.push({type:'missing_closed_owner',id:l.id});continue;}
            var ink=l.inkBounds,w=ink[2]-ink[0],h=ink[1]-ink[3],oldX=(ink[0]+ink[2])/2,oldY=(ink[1]+ink[3])/2,b=owner.bounds,cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;
            var gap=l.clearancePt===undefined?1.5:l.clearancePt,max=l.maxDistancePt===undefined?8:l.maxDistancePt,options=l.placements||['inside','left','right','above','below'],candidates=[];
            if(!(gap>=0)||!(max>=0)) {issues.push({type:'invalid_clearance',id:l.id});continue;}
            var variants=l.variants||[{inkBounds:l.inkBounds}],validVariants=variants.length>0;
            for(var vi=0;vi<variants.length;vi++)if(!valid(variants[vi].inkBounds)||(variants[vi].rotation!==undefined&&variants[vi].rotation!==0&&variants[vi].rotation!==90&&variants[vi].rotation!==-90))validVariants=false;
            if(!validVariants){issues.push({type:'invalid_variants',id:l.id});continue;}
            for(vi=0;vi<variants.length;vi++) {
                ink=variants[vi].inkBounds;w=ink[2]-ink[0];h=ink[1]-ink[3];oldX=(ink[0]+ink[2])/2;oldY=(ink[1]+ink[3])/2;
            for(j=0;j<options.length;j++) {
                var side=options[j],x=cx,y=cy,half=(owner.path.stroked?(owner.path.strokeWidthPt||0)/2:0),separation=gap+half;
                if(side==='left')x=b[0]-separation-w/2;else if(side==='right')x=b[2]+separation+w/2;else if(side==='above')y=b[1]+separation+h/2;else if(side==='below')y=b[3]-separation-h/2;else if(side!=='inside')continue;
                var ix=Math.max(0,(b[2]-b[0]-w)/2-separation-EPS*4),iy=Math.max(0,(b[1]-b[3]-h)/2-separation-EPS*4);
                var offsets;
                if(side==='inside')offsets=[[0,0],[Math.max(-ix,Math.min(ix,oldX-cx)),Math.max(-iy,Math.min(iy,oldY-cy))],[-ix,iy],[ix,iy],[-ix,-iy],[ix,-iy],[0,iy],[0,-iy],[-ix,0],[ix,0]];
                else if(side==='left'||side==='right')offsets=[[0,0],[0,Math.max(-((b[1]-b[3])/2),Math.min((b[1]-b[3])/2,oldY-cy))],[0,(b[1]-b[3])/2],[0,-(b[1]-b[3])/2]];
                else offsets=[[0,0],[Math.max(-((b[2]-b[0])/2),Math.min((b[2]-b[0])/2,oldX-cx)),0],[(b[2]-b[0])/2,0],[-(b[2]-b[0])/2,0]];
                for(var oi=0;oi<offsets.length;oi++) {var xx=x+offsets[oi][0],yy=y+offsets[oi][1],rect=[xx-w/2,yy+h/2,xx+w/2,yy-h/2];
                    if(side!=='inside'&&(separation>max+EPS||distance(rect,owner)>max+EPS))continue;
                    candidates.push({side:side,rect:rect,cost:(xx-oldX)*(xx-oldX)+(yy-oldY)*(yy-oldY),order:candidates.length,inside:side==='inside',centered:side==='inside'&&oi===0,variantIndex:vi,sourceInk:ink,rotation:variants[vi].rotation});
                }
            }
            }
            candidates.sort(function(a,z){
                if(a.inside!==z.inside){if(a.inside)return -1;return 1;}
                if(a.centered!==z.centered){if(a.centered)return -1;return 1;}
                return a.cost-z.cost||a.variantIndex-z.variantIndex||a.order-z.order;
            });
            var chosen=null,newOwner=null;
            for(j=0;j<candidates.length;j++) {var candidate=candidates[j];
                if(candidate.inside&&!paddedContains(candidate.rect,owner,l,gap))continue;
                if(unobstructed(candidate.rect,owner,gap,candidate.inside)){chosen=candidate;break;}
            }
            if(!chosen)for(vi=0;vi<variants.length&&!chosen;vi++)for(j=0;j<options.length;j++)if(options[j]==='inside') {
                ink=variants[vi].inkBounds;w=ink[2]-ink[0];h=ink[1]-ink[3];newOwner=expansion(owner,w,h,l);
                if(newOwner){var rr=[cx-w/2,cy+h/2,cx+w/2,cy-h/2];if(paddedContains(rr,newOwner,l,gap)&&unobstructed(rr,owner,gap,true)){chosen={side:'inside',rect:rr,sourceInk:ink,rotation:variants[vi].rotation};break;}newOwner=null;}
            }
            if(!chosen) {issues.push({type:'no_nearby_placement',id:l.id,ownerPathIndex:l.ownerPathIndex});continue;}
            if(newOwner) {var priorEdit=null;for(j=0;j<edits.length;j++)if(edits[j].pathIndex===owner.index)priorEdit=edits[j];if(priorEdit)priorEdit.afterPoints=copy(newOwner.path.points);else edits.push({pathIndex:owner.index,beforePoints:copy(owner.path.points),afterPoints:copy(newOwner.path.points)});for(j=0;j<items.length;j++)if(items[j]===owner)items[j]=newOwner;}
            var placement={id:l.id,dx:chosen.rect[0]-chosen.sourceInk[0],dy:chosen.rect[1]-chosen.sourceInk[1],inkBounds:chosen.rect,placement:chosen.side,ownerPathIndex:l.ownerPathIndex};
            if(chosen.rotation!==undefined)placement.rotation=chosen.rotation;
            placed.push(placement);
        }
        for(i=0;i<placed.length;i++) {
            var finalPlacement=placed[i],finalOwner=null,definition=null;
            for(j=0;j<items.length;j++)if(items[j].index===finalPlacement.ownerPathIndex)finalOwner=items[j];
            for(j=0;j<labels.length;j++)if(labels[j].id===finalPlacement.id)definition=labels[j];
            var finalGap=definition.clearancePt===undefined?1.5:definition.clearancePt,finalMax=definition.maxDistancePt===undefined?8:definition.maxDistancePt;
            var interior=finalPlacement.placement==='inside';
            if((interior&&!paddedContains(finalPlacement.inkBounds,finalOwner,definition,finalGap))||(!interior&&distance(finalPlacement.inkBounds,finalOwner)>finalMax+EPS)||!unobstructed(finalPlacement.inkBounds,finalOwner,finalGap,interior,i))issues.push({type:'placement_invalidated',id:finalPlacement.id,ownerPathIndex:finalPlacement.ownerPathIndex});
        }
        return {ok:issues.length===0,placements:placed,frameEdits:edits,issues:issues};
    }
    return {solve:solve};
}());
