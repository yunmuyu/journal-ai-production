export function auditNativeOutput(snapshot,plan){
 const issues=[],texts=snapshot.texts||[],paths=snapshot.pathGeometry||[];
 for(const text of texts){
  const baseValid=Number.isFinite(text.size)&&text.size>=6-1e-6&&text.size<=8+1e-6;
  if(!baseValid)issues.push({type:'final_font_size',textIndex:text.index,sizePt:text.size});
  for(const [characterIndex,character] of (text.characterStyles||[]).entries()){
   const nativeScript=/^(?:FontBaselineOption\.)?(?:SUBSCRIPT|SUPERSCRIPT)$/.test(character.baselinePosition);
   const sizeValid=Number.isFinite(character.size)&&(nativeScript?baseValid&&character.size>0&&character.size<=text.size+1e-6:character.size>=6-1e-6&&character.size<=8+1e-6);
   if(!sizeValid)issues.push({type:'final_character_font_size',textIndex:text.index,characterIndex,sizePt:character.size,baseSizePt:text.size,baselinePosition:character.baselinePosition});
  }
 }
 const b=snapshot.artboard,widthMm=(b[2]-b[0])*25.4/72,limit=plan.columnConstraint==='single'||plan.widthMm<=80?80:plan.widthMm<=160?160:plan.widthMm;
 if(widthMm>limit+.001)issues.push({type:'final_column_width',actualWidthMm:widthMm,limitMm:limit});
 for(const expected of plan.strokeExpectations||[]){
  const matches=paths.filter(p=>p.name===expected.pathName&&!p.hidden&&!p.clipping&&!p.guides&&p.stroked&&p.opacity!==0);
  if(matches.length!==1){issues.push({type:'final_stroke_identity',pathName:expected.pathName,matches:matches.length});continue;}
  const actual=matches[0];
  if(expected.widthPt!==undefined&&Math.abs(actual.strokeWidthPt-expected.widthPt)>.005)issues.push({type:'final_stroke_width',pathName:expected.pathName,expectedPt:expected.widthPt,actualPt:actual.strokeWidthPt});
  const dash=Array.from(actual.strokeDashes||[]);
  if(expected.dashPt&&(dash.length!==expected.dashPt.length||dash.some((v,i)=>Math.abs(v-expected.dashPt[i])>.005)))issues.push({type:'final_dash_lengths',pathName:expected.pathName,expectedPt:expected.dashPt,actualPt:dash});
 }
 return {ok:!issues.length,issues,widthMm,minimumBaseFontPt:texts.length?Math.min(...texts.map(t=>t.size)):null,fontCoverage:texts.length?'native_text_only':'raster_or_no_text_unverified',strokeExpectationsChecked:(plan.strokeExpectations||[]).length};
}
