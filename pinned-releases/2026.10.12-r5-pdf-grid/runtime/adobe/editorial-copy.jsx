JFW.copyArtwork=function(opened,production){
 opened.activate();
 var roots=[],i,j;
 for(i=opened.layers.length-1;i>=0;i--)for(j=opened.layers[i].pageItems.length-1;j>=0;j--){var item=opened.layers[i].pageItems[j];if(item.parent.typename==='Layer'&&!item.guides)roots.push(item);}
 if(!roots.length)throw Error('Empty source figure');
 var staging=opened.layers.add(),group=staging.groupItems.add();group.name='JFW_COPY_STAGING';
 for(i=0;i<roots.length;i++)roots[i].move(group,ElementPlacement.PLACEATBEGINNING);
 var clone=group.duplicate(production,ElementPlacement.PLACEATBEGINNING);
 return {group:clone,rootCount:roots.length};
};
