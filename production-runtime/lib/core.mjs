import {readLocalJson} from './local-paths.mjs';
import {validateColorPlan} from './color-policy.mjs';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, renameSync, realpathSync, existsSync, mkdirSync, appendFileSync } from 'node:fs';
import path from 'node:path';
export const sha256 = value => createHash('sha256').update(value).digest('hex');
export const fileHash = file => sha256(readFileSync(file));
export const figureId = (article, position, media) => 'f'+sha256([article,position,media].join('\0')).slice(0,20);
export const readJson = readLocalJson;
export function writeJson(file,value){mkdirSync(path.dirname(file),{recursive:true});const temp=file+'.'+process.pid+'.tmp';writeFileSync(temp,JSON.stringify(value,null,2)+'\n','utf8');renameSync(temp,file);}
export function logEvent(job,event){appendFileSync(path.join(job,'events.jsonl'),JSON.stringify({time:new Date().toISOString(),...event})+'\n','utf8');}
export function resolveInside(root,relative){
 if(typeof relative!=='string'||path.isAbsolute(relative)||/^[A-Za-z]:/.test(relative))throw Error('absolute path is not allowed');
 const base=path.resolve(root),full=path.resolve(base,relative);if(full===base||!full.startsWith(base+path.sep))throw Error('path outside job');
 if(existsSync(full)){const real=realpathSync(full),rb=realpathSync(base);if(!real.startsWith(rb+path.sep))throw Error('symlink outside job');}
 return full;
}
const finite=(v,name)=>{if(!Number.isFinite(v))throw Error(name+' must be finite');};
const rect=(r,name)=>{if(!Array.isArray(r)||r.length!==4)throw Error(name+' requires x,y,width,height');r.forEach(v=>finite(v,name));if(r[0]<0||r[1]<0||r[2]<=0||r[3]<=0||r[0]+r[2]>1.000001||r[1]+r[3]>1.000001)throw Error(name+' outside normalized image');};
export const intersects=(a,b)=>Math.min(a[0]+a[2],b[0]+b[2])>Math.max(a[0],b[0])+1e-8&&Math.min(a[1]+a[3],b[1]+b[3])>Math.max(a[1],b[1])+1e-8;
export function exportPadding(value=0.25){const values=Array.isArray(value)?value:[value,value,value,value];if(values.length!==4||values.some(v=>!Number.isFinite(v)||v<0))throw Error('invalid export padding');return values;}
function validateLocalStyles(text,styles,fontSize){
 if(!Array.isArray(styles))throw Error('invalid local text styles');
 const used=new Set(),allowed=['start','length','font','size','baselineShift','script'];
 for(const style of styles){
  if(!style||typeof style!=='object'||Array.isArray(style)||Object.keys(style).some(key=>!allowed.includes(key))||!Number.isInteger(style.start)||!Number.isInteger(style.length)||style.start<0||style.length<1||style.start+style.length>text.length||!['TimesNewRomanPS-ItalicMT','TimesNewRomanPSMT'].includes(style.font))throw Error('invalid local text style');
  if(style.script!==undefined&&!['subscript','superscript'].includes(style.script))throw Error('invalid local text style');
  if(style.size!==undefined&&(!Number.isFinite(style.size)||style.size<6||style.size>fontSize))throw Error('invalid local text style size');
  if(style.baselineShift!==undefined&&(!Number.isFinite(style.baselineShift)||style.baselineShift< -2||style.baselineShift>0))throw Error('invalid local text style baseline shift');
  for(let index=style.start;index<style.start+style.length;index++){if(used.has(index))throw Error('overlapping local text styles');used.add(index);}
 }
}
export function validatePlan(p){
 validateColorPlan(p);
 exportPadding(p.exportPaddingPt);
 if(p.version!==1||!/^f[a-zA-Z0-9_-]+$/.test(p.figureId||'')||! /^[a-f0-9]{64}$/.test(p.sourceHash||''))throw Error('invalid plan identity');
 if(!['raster-reletter','vector-reletter','rebuild','image','compose','chart-redraw'].includes(p.route))throw Error('unknown route');
 if(!Number.isFinite(p.fontSize)||p.fontSize<6||p.fontSize>8)throw Error('final typography must be 6 to 8 pt; fractional sizes are allowed');
 if(p.graph&&p.graph.fontSize!==p.fontSize)throw Error('graph font size must match plan font size');
 finite(p.widthMm,'widthMm');if(p.widthMm<10||p.widthMm>170)throw Error('unsupported width');
 if(p.crop){if(p.crop.length!==4)throw Error('crop requires l,t,r,b');p.crop.forEach(v=>finite(v,'crop'));if(p.crop.some(v=>v<0||v>=1)||p.crop[0]+p.crop[2]>=1||p.crop[1]+p.crop[3]>=1)throw Error('invalid crop');}
 for(const r of p.protectedRegions||[])rect(r,'protected region');
 for(const m of p.masks||[]){rect(m.rect,'mask');finite(m.gray,'gray');if(m.gray<0||m.gray>100)throw Error('invalid gray');if((p.protectedRegions||[]).some(r=>intersects(m.rect,r)))throw Error('mask overlaps protected region');}
 if((p.masks||[]).length&&!p.rasterEditRationale)throw Error('raster removal requires explicit rationale');
 if(p.paddingBottomPt!==undefined&&(!Number.isFinite(p.paddingBottomPt)||p.paddingBottomPt<0||p.paddingBottomPt>12))throw Error('invalid bottom label clearance');
 for(const line of p.lineSamples||[]){for(const point of [line.from,line.to])if(!Array.isArray(point)||point.length!==2||point.some(x=>!Number.isFinite(x)||x<0||x>1))throw Error('invalid legend line point');if(!['solid','dashed','dotted','dashdot'].includes(line.style))throw Error('invalid legend line style');}
 for(const t of p.texts||[]){
 if(t.gray!==undefined&&t.gray!==0)throw Error('editable text must be pure black');
 if(t.anchor!==undefined&&t.anchor!=='ink')throw Error('unsupported text anchor');
 if(t.styles!==undefined)validateLocalStyles(t.text,t.styles,p.fontSize);
 if(t.valign!==undefined&&t.valign!=='center')throw Error('invalid vertical alignment');if(t.rotation!==undefined&&![-90,0,90].includes(t.rotation))throw Error('unsupported text rotation');if(typeof t.text!=='string'||!t.text.trim())throw Error('empty text');finite(t.x,'text x');finite(t.y,'text y');if(t.x<0||t.x>1||t.y<0||t.y>1)throw Error('text outside image');if(t.align&&!['left','center','right'].includes(t.align))throw Error('invalid alignment');if(t.font&&!['SimSun','TimesNewRomanPSMT','TimesNewRomanPS-ItalicMT'].includes(t.font))throw Error('unsupported font');}
 if(p.route==='chart-redraw'){const c=p.chart;if(!c||!Array.isArray(c.categories)||!c.categories.length||!Array.isArray(c.series)||c.series.length<1||c.series.length>3||!Number.isFinite(c.max)||c.max<=0||!Number.isFinite(c.step)||c.step<=0)throw Error('Invalid bar chart');for(const s of c.series)if(s.values.length!==c.categories.length||s.values.some(v=>!Number.isFinite(v)||v<0||v>c.max))throw Error('Invalid chart values');}
 if(p.route==='rebuild'&&!p.graph)throw Error('rebuild requires graph');
 if(p.overlayFrame!==undefined&&(!['source-artboard','artwork'].includes(p.overlayFrame)||p.route!=='vector-reletter'||!p.normalizeWidth))throw Error('overlayFrame requires a normalized vector plan');
 if(p.nativeSvg!==undefined&&(typeof p.nativeSvg!=='boolean'||p.nativeSvg&&p.route!=='vector-reletter'))throw Error('nativeSvg requires a boolean on the vector route');
 if(p.route==='vector-reletter'&&!Array.isArray(p.replacements))throw Error('vector route requires explicit replacements');
 for(const group of p.textGroups||[])if(group.styles!==undefined)validateLocalStyles(group.text,group.styles,p.fontSize);
 for(const replacement of p.replacements||[])if(replacement.styles!==undefined)validateLocalStyles(replacement.text,replacement.styles,p.fontSize);
 return p;
}
export function reviewMatches(review,planHash,outputHash){return review?.decision==='pass'&&review.planHash===planHash&&review.outputHash===outputHash;}
