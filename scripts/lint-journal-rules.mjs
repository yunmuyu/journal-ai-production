import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {loadJournalRules} from '../lib/journal-rules.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const rules = loadJournalRules();
const roles = rules.normative.font_role_labels;
const expected = {
  cn: '宋体 Regular',
  punct: '汉仪中宋简 regular',
  latin: 'Times New Roman Regular',
  latin_italic: 'Times New Roman Italic',
};
if (JSON.stringify(roles) !== JSON.stringify(expected)) {
  console.error('字体角色与 FONT-CACHE.md 的既有表述不一致');
  process.exit(1);
}
if (Number(rules.normative.scale_floor_pt) !== 6 || Number(rules.normative.margin_pt) !== 0.25) {
  console.error('6pt 下限或 0.25pt 留白被改掉了');
  process.exit(1);
}
const skip = new Set(['pinned-releases', 'production-runtime', 'candidates', 'node_modules', '.git']);
const needles = ['不得低于2pt', '留白至少2pt', 'minimum_text_margin_pt>=1.99', 'DEFAULT_PADDING_PT = 2'];
const hits = [];
function walk(dir) {
  for (const name of fs.readdirSync(dir)) {
    if (skip.has(name) || name === 'lint-journal-rules.mjs') continue;
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) walk(full);
    else if (/\.(py|mjs|md|yaml)$/.test(name)) {
      const text = fs.readFileSync(full, 'utf8');
      for (const needle of needles) if (text.includes(needle)) hits.push(`${path.relative(root, full)}: ${needle}`);
    }
  }
}
walk(root);
if (hits.length) {
  console.error(hits.join('\n'));
  process.exit(1);
}
console.log('journal rules lint ok');
