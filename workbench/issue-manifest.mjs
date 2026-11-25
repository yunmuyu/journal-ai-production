import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {pathToFileURL} from 'node:url';

const WORD = /\.docx?$/i;
const OUTPUT = /\.(pdf|jpe?g)$/i;
const NAMED = /^(.+)-图([1-9]\d*(?:\.[1-9]\d*)?)\.(pdf|jpe?g)$/i;

export function loadNovemberData(file) {
  const context = {window: {}};
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), context);
  const data = context.window.NOVEMBER_DATA;
  if (!data || !Array.isArray(data.authors)) throw Error('november-data.js 缺少 window.NOVEMBER_DATA.authors');
  return data;
}

function remember(authors, author) {
  if (!authors.has(author)) authors.set(author, {author, words: [], files: []});
  return authors.get(author);
}

export function scanIssueFolder(root) {
  const authors = new Map();
  const visit = (author, file) => {
    const row = remember(authors, author);
    const base = path.basename(file);
    if (base.startsWith('~$') || base.startsWith('.')) return;
    if (WORD.test(base)) row.words.push(file);
    else if (OUTPUT.test(base)) {
      const named = base.match(NAMED);
      if (named && named[1] === author) row.files.push({number: named[2], url: pathToFileURL(file).href});
    }
  };
  for (const entry of fs.readdirSync(root, {withFileTypes: true})) {
    if (entry.name.startsWith('.') || entry.name.startsWith('~$')) continue;
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) {
      for (const name of fs.readdirSync(full)) visit(entry.name, path.join(full, name));
    } else if (WORD.test(entry.name)) {
      visit(entry.name.replace(/\.docx?$/i, ''), full);
    }
  }
  return {
    authors: [...authors.values()].map(row => ({
      author: row.author,
      main: new Set(row.files.map(file => file.number.split('.')[0])).size,
      words: row.words,
      files: row.files,
    })),
  };
}

export function loadWorkbenchInventory({workbenchRoot, issueRoot} = {}) {
  const november = workbenchRoot && path.join(workbenchRoot, 'november-data.js');
  if (november && fs.existsSync(november)) return {source: 'november-data.js', data: loadNovemberData(november)};
  const manifest = issueRoot && path.join(issueRoot, 'issue-manifest.json');
  if (manifest && fs.existsSync(manifest)) {
    return {source: 'issue-manifest.json', data: JSON.parse(fs.readFileSync(manifest, 'utf8').replace(/^\uFEFF/, ''))};
  }
  if (issueRoot && fs.existsSync(issueRoot)) return {source: 'scan', data: scanIssueFolder(issueRoot)};
  return null;
}
