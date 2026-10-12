import {readFileSync} from 'node:fs';
import path from 'node:path';

const windowsAbsolute = value => typeof value === 'string' && /^[A-Za-z]:/.test(value) && (value[2] === '/' || value.charCodeAt(2) === 92);
const normalized = value => { let result = value.replaceAll(String.fromCharCode(92), '/'); while (result.endsWith('/')) result = result.slice(0, -1); return result; };

let cachedFile;
let cachedEntries;
function loadMappings(mappingFile) {
 if (cachedFile === mappingFile) return cachedEntries;
 const config = JSON.parse(readFileSync(mappingFile, 'utf8'));
 if (!Array.isArray(config.mappings)) throw Error('JFW_PATH_MAP_FILE requires mappings array');
 const entries = config.mappings.map(entry => {
  if (!Array.isArray(entry) || entry.length !== 2 || !windowsAbsolute(entry[0]) || typeof entry[1] !== 'string' || !path.isAbsolute(entry[1])) throw Error('Invalid JFW path mapping');
  return [normalized(entry[0]), entry[1]];
 }).sort((left, right) => right[0].length - left[0].length);
 cachedFile = mappingFile;
 cachedEntries = entries;
 return entries;
}

export function mapLocalPath(value, mappingFile = process.env.JFW_PATH_MAP_FILE) {
 if (!mappingFile || !windowsAbsolute(value)) return value;
 const source = normalized(value);
 const entries = loadMappings(mappingFile);
 for (const [from, to] of entries) {
  if (source.toLowerCase() === from.toLowerCase()) return to;
  if (source.toLowerCase().startsWith(from.toLowerCase() + '/')) return path.join(to, ...source.slice(from.length + 1).split('/'));
 }
 return value;
}

export function readLocalJson(file) {
 const input = mapLocalPath(file);
 return JSON.parse(readFileSync(input, 'utf8').replace(/^﻿/, ''), (_key, value) => mapLocalPath(value));
}
