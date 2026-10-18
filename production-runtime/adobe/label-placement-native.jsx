JFW.labelPaintMetadata = function(item,cache) {
    var current=item,stack=[],fill=item.filled?item.fillColor:null,opaque=!!fill&&item.closed&&item.opacity===100&&/^(RGBColor|GrayColor|CMYKColor)$/.test(fill.typename);
    cache=cache||[];
    while(current&&current.parent) {
        if(current.opacity!==undefined&&current.opacity!==100)opaque=false;
        if(typeof BlendModes!=='undefined'&&current.blendingMode!==undefined&&current.blendingMode!==BlendModes.NORMAL)opaque=false;
        var parent=current.parent,kind=parent.typename,entry=null;
        if(kind==='CompoundPathItem'&&parent.pathItems.length!==1)opaque=false;
        if(kind!=='Document'&&kind!=='Layer'&&kind!=='GroupItem'&&kind!=='CompoundPathItem')return {opaqueFill:false};
        for(var ci=0;ci<cache.length;ci++)if(cache[ci].kind===kind&&cache[ci].parent===parent){entry=cache[ci];break;}
        if(!entry) {
            entry={parent:parent,kind:kind,items:[]};var items;
            if(kind==='Document')items=parent.layers;
            else if(kind==='CompoundPathItem')items=parent.pathItems;
            else items=parent.pageItems;
            var itemCount=items.length;for(var si=0;si<itemCount;si++){var sibling=items[si];if(kind==='Document'||sibling.parent===parent)entry.items.push(sibling);}
            cache.push(entry);
        }
        var index=-1;
        for(var ii=0;ii<entry.items.length;ii++)if(entry.items[ii]===current){index=ii;break;}
        if(index<0&&kind==='Document')for(ii=0;ii<entry.items.length;ii++)if(entry.items[ii].name===current.name){if(index>=0)return {opaqueFill:false};index=ii;}
        if(index<0)return {opaqueFill:false,reason:'unresolved-paint-order'};stack.unshift(index);
        if(kind==='Document')break;current=parent;
    }
    return {paintStack:stack,opaqueFill:!!opaque};
};
JFW.createLabelPlacementSession = function(doc) {
    var paths=[],refs=[],initialCount=doc.pathItems.length,paintCache=[];
    function ink(frame) {
        var outline=frame.duplicate().createOutline(),b=JFW.bounds(outline.visibleBounds);
        outline.remove();return b;
    }
    function pathData(p,index) {
        var points=[],dashes=[],i,nativePoints=p.pathPoints,pointCount=nativePoints.length;
        for(i=0;i<pointCount;i++) {
            var v=nativePoints[i],anchor=v.anchor,left=v.leftDirection,right=v.rightDirection;
            points.push([[anchor[0],anchor[1],left[0],left[1]],[right[0],right[1]]]);
        }
        if(p.stroked)for(i=0;i<p.strokeDashes.length;i++)dashes.push(p.strokeDashes[i]);
        var paint=JFW.labelPaintMetadata(p,paintCache);
        return {index:index,name:p.name,points:points,closed:p.closed,clipping:p.clipping,guides:p.guides,hidden:p.hidden,opacity:p.opacity,filled:p.filled,stroked:p.stroked,strokeWidthPt:p.stroked?p.strokeWidth:0,strokeDashes:dashes,paintStack:paint.paintStack,opaqueFill:paint.opaqueFill};
    }
    for(var i=0;i<initialCount;i++){refs.push(doc.pathItems[i]);paths.push(pathData(doc.pathItems[i],i));}
    return {place:function(labels) {
        var measured=[],fixed=[],i,j,t;
        for(i=0;i<labels.length;i++) {
            var item=labels[i],layout=item.layout,label={id:item.id,fontSize:item.fontSize||8,inkBounds:ink(item.frame)};
            for(var key in layout)label[key]=layout[key];
            if(layout.rotations) {
                label.variants=[];
                var b=label.inkBounds,cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;
                for(var ri=0;ri<layout.rotations.length;ri++) {
                    var rotation=layout.rotations[ri],swapped=Math.abs(rotation-(item.rotation||0))%180!==0;
                    var w=swapped?b[1]-b[3]:b[2]-b[0],h=swapped?b[2]-b[0]:b[1]-b[3];
                    label.variants.push({rotation:rotation,inkBounds:[cx-w/2,cy+h/2,cx+w/2,cy-h/2]});
                }
            }
            measured.push(label);
        }
        for(i=0;i<doc.textFrames.length;i++) {
            t=doc.textFrames[i];var managed=false;
            for(j=0;j<labels.length;j++)if(labels[j].frame===t)managed=true;
            if(!managed&&/\S/.test(t.contents))fixed.push({inkBounds:ink(t)});
        }
        var scenePaths=paths.slice(0);
        for(i=0;i<doc.pathItems.length;i++) {
            var known=false,p=doc.pathItems[i];
            for(j=0;j<refs.length;j++)if(refs[j]===p)known=true;
            if(!known&&String(p.name||'').indexOf('JFW_EXPLICIT_TEXT_MASK_')!==0)scenePaths.push(pathData(p,scenePaths.length));
        }
        var imageSets=[doc.rasterItems||[],doc.placedItems||[]];
        for(var set=0;set<imageSets.length;set++)for(i=0;i<imageSets[set].length;i++) {
            var image=imageSets[set][i];if(image.hidden||image.opacity===0)continue;
            var ib=JFW.bounds(image.visibleBounds),parent=image.parent,visible=true;
            while(parent&&parent.typename==='GroupItem') {
                if(parent.hidden||parent.opacity===0){visible=false;break;}
                if(parent.clipped)for(j=0;j<parent.pathItems.length;j++)if(parent.pathItems[j].clipping) {
                    var cb=parent.pathItems[j].geometricBounds;
                    ib=[Math.max(ib[0],cb[0]),Math.min(ib[1],cb[1]),Math.min(ib[2],cb[2]),Math.max(ib[3],cb[3])];
                }
                parent=parent.parent;
            }
            if(visible&&ib[2]>ib[0]&&ib[1]>ib[3]) {
                var corners=[[ib[0],ib[1]],[ib[2],ib[1]],[ib[2],ib[3]],[ib[0],ib[3]]],points=[];
                for(j=0;j<4;j++)points.push([[corners[j][0],corners[j][1],corners[j][0],corners[j][1]],[corners[j][0],corners[j][1]]]);
                scenePaths.push({index:scenePaths.length,closed:true,filled:true,stroked:false,solidObstacle:true,points:points});
            }
        }
        var result=JFWLabelPlacement.solve({paths:scenePaths,labels:measured,fixedTexts:fixed,artboard:JFW.bounds(doc.artboards[0].artboardRect)});
        if(!result.ok)return result;
        for(i=0;i<result.frameEdits.length;i++) {
            var edit=result.frameEdits[i],ref=refs[edit.pathIndex];
            for(j=0;j<edit.afterPoints.length;j++) {
                var point=edit.afterPoints[j];
                ref.pathPoints[j].anchor=[point[0][0],point[0][1]];
                ref.pathPoints[j].leftDirection=[point[0][2],point[0][3]];
                ref.pathPoints[j].rightDirection=[point[1][0],point[1][1]];
            }
        }
        for(i=0;i<result.placements.length;i++) {
            var placed=result.placements[i];
            for(j=0;j<labels.length;j++)if(labels[j].id===placed.id) {
                if(placed.rotation===undefined)labels[j].frame.translate(placed.dx,placed.dy);
                else {
                    labels[j].frame.rotate(placed.rotation-(labels[j].rotation||0));
                    var rotated=ink(labels[j].frame);
                    labels[j].frame.translate(placed.inkBounds[0]-rotated[0],placed.inkBounds[1]-rotated[1]);
                }
                if(typeof placed.ownerPathIndex==='number'&&refs[placed.ownerPathIndex]) {
                    var ownerRef=refs[placed.ownerPathIndex];if(!ownerRef.name)ownerRef.name='JFW_LAYOUT_OWNER_'+placed.ownerPathIndex;
                    placed.ownerName=ownerRef.name;labels[j].frame.name='JFW_LAYOUT_TEXT_'+placed.id;
                }
                placed.actualInkBounds=ink(labels[j].frame);
                for(var bi=0;bi<4;bi++)if(Math.abs(placed.actualInkBounds[bi]-placed.inkBounds[bi])>0.05) {
                    result.ok=false;result.issues.push({type:'native_label_position_mismatch',id:placed.id,expected:placed.inkBounds,actual:placed.actualInkBounds});break;
                }
            }
        }
        return result;
    }};
};
