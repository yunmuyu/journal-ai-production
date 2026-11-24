"""Minimal YAML reader for rules/journal-rules.yaml. No extra dependency."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


def rules_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / 'rules' / 'journal-rules.yaml'
        if candidate.is_file() and (parent / 'journal.mjs').is_file():
            return candidate
    raise FileNotFoundError('rules/journal-rules.yaml')


def _scalar(token: str):
    if token == '' or token is None:
        return None
    if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
        return token[1:-1]
    if token in ('true', 'false'):
        return token == 'true'
    if token in ('null', '~'):
        return None
    try:
        if token.startswith('+') or (token.startswith('0') and token not in ('0',) and not token.startswith('0.')):
            raise ValueError
        if any(c in token for c in '.eE'):
            return float(token)
        return int(token)
    except ValueError:
        return token


def parse_yaml(text: str):
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        lines.append((indent, raw.strip()))

    def parse_value(i, indent):
        if i >= len(lines):
            return None, i
        level, content = lines[i]
        if level < indent:
            return None, i
        if content.startswith('- '):
            return parse_list(i, level)
        return parse_map(i, level)

    def parse_list(i, indent):
        items = []
        while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith('- '):
            content = lines[i][1][2:]
            i += 1
            if content == '':
                value, i = parse_value(i, indent + 1)
                items.append(value)
                continue
            if ':' in content and not content.startswith(('"', "'")):
                key, _, rest = content.partition(':')
                item = {key.strip(): _scalar(rest.strip()) if rest.strip() else {}}
                if rest.strip() == '':
                    child, i = parse_value(i, indent + 2)
                    item[key.strip()] = child
                while i < len(lines) and lines[i][0] > indent and not lines[i][1].startswith('- '):
                    key2, _, rest2 = lines[i][1].partition(':')
                    child_indent = lines[i][0]
                    i += 1
                    if rest2.strip() == '':
                        child, i = parse_value(i, child_indent + 1)
                        item[key2.strip()] = child
                    else:
                        item[key2.strip()] = _scalar(rest2.strip())
                items.append(item)
            else:
                items.append(_scalar(content))
        return items, i

    def parse_map(i, indent):
        mapping = {}
        while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith('- '):
            key, _, rest = lines[i][1].partition(':')
            i += 1
            if rest.strip() == '':
                value, i = parse_value(i, indent + 1)
                mapping[key.strip()] = value
            else:
                mapping[key.strip()] = _scalar(rest.strip())
        return mapping, i

    value, index = parse_value(0, 0)
    if index != len(lines):
        raise ValueError('YAML 未解析完: ' + lines[index][1])
    return value


@lru_cache(maxsize=1)
def load_rules():
    data = parse_yaml(rules_path().read_text(encoding='utf-8'))
    normative = data.get('normative') or {}
    required = (
        'margin_pt', 'scale_floor_pt', 'body_pt', 'stroke_pt',
        'single_column_mm', 'double_column_mm', 'simple_chart_mm',
        'grayscale_channel_delta_max',
    )
    missing = [key for key in required if key not in normative]
    if missing:
        raise ValueError('规则文件缺少字段: ' + ','.join(missing))
    if float(normative['scale_floor_pt']) != 6:
        raise ValueError('正文字号下限必须保持仓库既有的 6pt')
    return data
