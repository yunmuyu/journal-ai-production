import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {namedFigureNumber} from '../workbench/issue-manifest.mjs';

const numberPattern = /^[1-9]\d*(?:\.[1-9]\d*)?$/;

function validateArticles(articles) {
  if (!Array.isArray(articles) || !articles.length) throw Error('expected a nonempty article list');
  const folders = new Set();
  for (const {folder, author, numbers} of articles) {
    if (typeof folder !== 'string' || !folder.trim() || /[<>:"/\\|?*]|[. ]$/.test(folder) ||
        folders.has(folder.toLowerCase()) || typeof author !== 'string' || !author.trim() ||
        /[<>:"/\\|?*]/.test(author)) throw Error('invalid or duplicate article folder/author');
    if (!Array.isArray(numbers) || !numbers.length ||
        numbers.some(n => typeof n !== 'string' || !numberPattern.test(n)) ||
        new Set(numbers).size !== numbers.length ||
        numbers.some(n => n.includes('.') && numbers.includes(n.split('.')[0]))) {
      throw Error('invalid, duplicate or mixed main/subfigure numbers: ' + folder);
    }
    folders.add(folder.toLowerCase());
  }
}

export function inspectFigureInventory(root, articles) {
  validateArticles(articles);
  const folders = new Map(fs.readdirSync(root, {withFileTypes: true}).map(entry => [entry.name, entry]));
  const issues = [];
  const items = [];
  for (const {folder, author, numbers} of articles) {
    if (!folders.get(folder)?.isDirectory()) {
      issues.push({folder, kind: 'missing-folder'});
      continue;
    }
    const byNumber = new Map();
    for (const file of fs.readdirSync(path.join(root, folder), {withFileTypes: true})) {
      const number = namedFigureNumber(file.name, author);
      if (!number) continue;
      if (!file.isFile()) {
        issues.push({folder, number, kind: 'not-regular-file', name: file.name});
        continue;
      }
      if (!byNumber.has(number)) byNumber.set(number, []);
      byNumber.get(number).push(file.name);
    }
    for (const [number, names] of byNumber) {
      if (!numbers.includes(number)) issues.push({folder, number, kind: 'unexpected'});
      if (names.length > 1) issues.push({folder, number, kind: 'duplicate', names: names.sort()});
      if (number.includes('.') && byNumber.has(number.split('.')[0])) {
        issues.push({folder, number, kind: 'mixed-main-and-subfigure'});
      }
    }
    for (const number of numbers) {
      const names = byNumber.get(number);
      if (!names) {
        issues.push({folder, number, kind: 'missing'});
        continue;
      }
      if (names.length !== 1) continue;
      const relative = folder + '/' + names[0];
      const sha256 = createHash('sha256').update(fs.readFileSync(path.join(root, relative))).digest('hex');
      items.push({folder, author, number, relative, sha256});
    }
  }
  return {schema: 'jfw-local-figure-inventory-v1', complete: issues.length === 0,
    expectedCount: articles.reduce((sum, article) => sum + article.numbers.length, 0),
    issues, items: issues.length === 0 ? items : []};
}
