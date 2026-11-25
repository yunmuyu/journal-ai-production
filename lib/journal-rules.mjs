import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function scalar(token) {
  if (token === '' || token == null) return null;
  if ((token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'"))) return token.slice(1, -1);
  if (token === 'true') return true;
  if (token === 'false') return false;
  if (token === 'null' || token === '~') return null;
  if (/^[+-]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(token)) return Number(token);
  return token;
}

export function parseYaml(text) {
  const lines = text.split(/\r?\n/).flatMap(raw => {
    if (!raw.trim() || raw.trimStart().startsWith('#')) return [];
    return [[raw.length - raw.trimStart().length, raw.trim()]];
  });
  function parseValue(i, indent) {
    if (i >= lines.length || lines[i][0] < indent) return [null, i];
    return lines[i][1].startsWith('- ') ? parseList(i, lines[i][0]) : parseMap(i, lines[i][0]);
  }
  function parseList(i, indent) {
    const items = [];
    while (i < lines.length && lines[i][0] === indent && lines[i][1].startsWith('- ')) {
      const content = lines[i][1].slice(2);
      i += 1;
      if (!content) {
        const [value, next] = parseValue(i, indent + 1);
        i = next;
        items.push(value);
        continue;
      }
      if (content.includes(':') && !content.startsWith('"') && !content.startsWith("'")) {
        const split = content.indexOf(':');
        const key = content.slice(0, split).trim();
        const rest = content.slice(split + 1).trim();
        const item = {[key]: rest ? scalar(rest) : {}};
        if (!rest) {
          const [child, next] = parseValue(i, indent + 2);
          i = next;
          item[key] = child;
        }
        while (i < lines.length && lines[i][0] > indent && !lines[i][1].startsWith('- ')) {
          const row = lines[i][1];
          const at = row.indexOf(':');
          const key2 = row.slice(0, at).trim();
          const rest2 = row.slice(at + 1).trim();
          const childIndent = lines[i][0];
          i += 1;
          if (!rest2) {
            const [child, next] = parseValue(i, childIndent + 1);
            i = next;
            item[key2] = child;
          } else item[key2] = scalar(rest2);
        }
        items.push(item);
      } else items.push(scalar(content));
    }
    return [items, i];
  }
  function parseMap(i, indent) {
    const mapping = {};
    while (i < lines.length && lines[i][0] === indent && !lines[i][1].startsWith('- ')) {
      const row = lines[i][1];
      const at = row.indexOf(':');
      const key = row.slice(0, at).trim();
      const rest = row.slice(at + 1).trim();
      i += 1;
      if (!rest) {
        const [value, next] = parseValue(i, indent + 1);
        i = next;
        mapping[key] = value;
      } else mapping[key] = scalar(rest);
    }
    return [mapping, i];
  }
  const [value, index] = parseValue(0, 0);
  if (index !== lines.length) throw Error('YAML 未解析完: ' + lines[index][1]);
  return value;
}

export function loadJournalRules() {
  const file = path.join(root, 'rules', 'journal-rules.yaml');
  const data = parseYaml(fs.readFileSync(file, 'utf8'));
  if (Number(data.normative?.scale_floor_pt) !== 6) throw Error('正文字号下限必须保持仓库既有的 6pt');
  return data;
}
