import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const recordRoot=process.env.JFW_RECORD_ROOT||'F:/2026年10月/_作图工作台';
const defaultMaps=[new URL('../office-paths.json',import.meta.url),new URL('../receive-family-20261012/office-paths.json',import.meta.url)];
const mappingFile=process.env.JFW_PATH_MAP_FILE||defaultMaps.map(fileURLToPath).find(fs.existsSync);
const mappings=mappingFile?JSON.parse(fs.readFileSync(mappingFile,'utf8')).mappings
  .map(([from,to])=>[from.replaceAll('\\','/').replace(/\/$/,''),to.replaceAll('\\','/').replace(/\/$/,'')])
  .sort((a,b)=>b[0].length-a[0].length):[];

export function resolveLocal(file){
 if(typeof file!=='string')return file;
 const normal=file.replaceAll('\\','/');
 const match=mappings.find(([from])=>normal.toLowerCase()===from.toLowerCase()||normal.toLowerCase().startsWith(from.toLowerCase()+'/'));
 return match?path.normalize(match[1]+normal.slice(match[0].length)):file;
}

export function readLocalJson(file){
 return JSON.parse(fs.readFileSync(resolveLocal(file),'utf8').replace(/^\uFEFF/,''));
}

