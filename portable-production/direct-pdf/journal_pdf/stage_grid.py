"""Bounded measured stage columns; semantic constraints, never authored coordinates.

Direct-spec pilot only. Supports rectangle stages, plain labels, top alignment,
forward column edges and a shared merge channel immediately before its target.
"""
from __future__ import annotations

import math
from pathlib import Path

from .common import FigureError, resolve_source
from .editorial import PAD_X, PAD_Y, COMPACT_GAP, ARROW_BOUNDARY_GAP, display_content
from .scene import Scene, port


def _need(condition, message):
    if not condition:
        raise FigureError('stage_grid_unsupported', message)


def stage_grid(spec, reg, size, assets=None, root=None):
    """Measure all text, solve explicit ordering/alignment, then draw shared primitives.

    ``assets``/``root`` are only needed when a block declares an ``icon`` cropped from a
    verified source image; without icons the layout is byte-identical to before."""
    source_root = root
    columns = spec.get('columns', [])
    edges = spec.get('edges', [])
    _need(isinstance(columns, list) and 1 <= len(columns) <= 8, '阶段布局只支持1至8列')
    _need(all(isinstance(b.get('band', 1), int) and b.get('band', 1) >= 1 for b in (x for c in columns for x in c['blocks'])), 'band须为正整数')
    blocks = {}; owners = {}; ids = set(); members = {}; kid_top = {}
    allowed = {'id', 'kind', 'title', 'items', 'text', 'align_with', 'after', 'cover', 'fill', 'valign', 'vertical', 'band', 'icon', 'span', 'stretch', 'justify', 'direction', 'frame'}
    for ci, column in enumerate(columns):
        _need(set(column) <= {'id', 'blocks', 'align'} and column.get('blocks'), '每列须明确非空blocks')
        _need(column.get('align') in (None, 'top', 'center'), '列align只接受top或center')
        for block in column['blocks']:
            _need(set(block) <= allowed, '阶段块不接受坐标或未支持参数')
            identifier = block.get('id')
            _need(isinstance(identifier, str) and identifier and identifier not in ids, '重复或无效块ID')
            ids.add(identifier); blocks[identifier] = block; owners[identifier] = ci
            kind = block.get('kind')
            _need(kind in ('stage', 'node', 'label', 'group', 'note'), '只支持stage、node、label、group、note')
            if 'icon' in block:
                icon = block['icon']
                _need(kind in ('node', 'label'), '只有node或label块可放图标')
                _need(isinstance(icon, dict) and set(icon) <= {'path', 'clip', 'width_pt', 'source_kind', 'page', 'side', 'gap'},
                      '图标只接受path、clip、width_pt、source_kind、page、side、gap')
                _need(icon.get('side') in (None, 'top', 'left'), '图标side只接受top或left')
                _need(icon.get('source_kind') in (None, 'raster', 'pdf'), '图标source_kind只接受raster或pdf')
                clip = icon.get('clip')
                pdf_icon = icon.get('source_kind') == 'pdf'
                if pdf_icon:
                    _need(isinstance(clip, list) and len(clip) == 4
                          and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in clip),
                          '矢量图标clip须为四个有限数（PDF磅值）')
                else:
                    _need(isinstance(clip, list) and len(clip) == 4 and all(isinstance(v, int) and not isinstance(v, bool) for v in clip),
                          '图标clip须为四个整数像素')
                _need(clip[2] > clip[0] and clip[3] > clip[1] and min(clip) >= 0, '图标clip须为正向矩形')
                wpt = icon.get('width_pt')
                _need(isinstance(wpt, (int, float)) and not isinstance(wpt, bool) and math.isfinite(wpt) and 4 <= wpt <= 120,
                      '图标宽须为4至120pt的有限数')
                _need(isinstance(icon.get('path') or spec.get('icon_source'), str), '图标须声明源图路径或spec.icon_source')
            if 'fill' in block:
                fill = block['fill']
                _need(isinstance(fill, (int, float)) and not isinstance(fill, bool) and math.isfinite(fill) and 0 <= fill <= 1, '填充只接受有限中性灰度0至1')
            if kind == 'group':
                _need(isinstance(block.get('items'), list) and block['items'], '子框组须有items')
                _need(block.get('title') is None or isinstance(block['title'], str), '子框组标题须为字符串')
                def check_kids(kids, depth):
                    _need(depth < 4, '子框嵌套最多4层')
                    for kid in kids:
                        _need(isinstance(kid, dict) and kid.get('kind') in ('group', 'node', 'note', 'label'),
                              '子框只接受group/node/note/label')
                        _need(isinstance(kid.get('id'), str) and kid['id'] not in ids, '子框ID重复或缺失')
                        ids.add(kid['id'])
                        owners[kid['id']] = ci          # 子块可作连线端点，按所属列参与校验
                        kid_top[kid['id']] = identifier  # 记录顶层祖先，供排序时预留合流间距
                        kid.setdefault('kind', 'node')
                        if kid['kind'] == 'group':
                            _need(isinstance(kid.get('items'), list) and kid['items'], '子框组须有items')
                            check_kids(kid['items'], depth + 1)
                        else:
                            _need(isinstance(kid.get('text'), str) and kid['text'], '子框须有原文')
                check_kids(block['items'], 0)
            elif kind == 'stage':
                _need(isinstance(block.get('title'), str) and block.get('items'), '阶段须有标题和成员')
                for item in block['items']:
                    _need(set(item) == {'id', 'text'} and isinstance(item['text'], str), '成员只接受id和text')
                    _need(item['id'] not in ids, '成员ID重复')
                    ids.add(item['id'])
                    members[item['id']] = identifier
                    owners[item['id']] = ci
            else:
                _need(isinstance(block.get('text'), str) and block['text'], '节点或标签须有原文')
    _need(len(ids) <= 100, '阶段节点超出100个预算')
    edge_ids = set(); panel_edges = []
    for edge in edges:
        _need(set(edge) <= {'id', 'from', 'to', 'from_port', 'to_port', 'source_align', 'merge', 'split', 'label', 'label_vertical', 'from_panel', 'to_panel', 'straight'}, '连接不接受坐标')
        _need(edge.get('id') not in edge_ids and edge.get('id'), '连接ID重复或缺失')
        edge_ids.add(edge['id'])
        if edge.get('from_panel') or edge.get('to_panel'):
            _need(edge.get('from_panel') and edge.get('to_panel') and not edge.get('merge') and not edge.get('split'),
                  '面板连线须同时声明from_panel与to_panel，且不参与合流/扇出')
            panel_edges.append(edge)
            continue
        endpoints = {edge.get('from'), edge.get('to')}
        _need(all(e in blocks or e in members or e in kid_top for e in endpoints), '端点须绑定真实块或该块已声明的成员')
        _need(blocks.get(edge['from'], {}).get('kind') != 'label', '标签不能作为连线起点')
        _need(blocks.get(edge['to'], {}).get('kind') != 'label' or edge.get('to_port') in ('top', 'left', 'right'),
              '标签只可作为箭头终点，且须显式给端口')
        _need(edge.get('from_port') in ('left','right','top','bottom') and edge.get('to_port') in ('left','right','top','bottom'), '端口须显式声明')
        delta = owners[edge['to']] - owners[edge['from']]
        member_endpoint = bool(endpoints & set(members))
        _need((delta == 1 and edge['from_port'] == 'right' and edge['to_port'] == 'left') or
              (delta == 0 and edge['from_port'] == 'bottom' and edge['to_port'] == 'top'
               and (edge.get('merge') or not member_endpoint)),
              '仅支持相邻列右到左连接，或同列向下链；不支持反向/跨列跳接')
    scale = size / 8; px = PAD_X * scale; py = PAD_Y * scale
    panels = spec.get('panels', [])
    _need(isinstance(panels, list), 'panels须为列表')
    for panel in panels:
        _need(set(panel) <= {'id', 'title', 'blocks', 'span'} and panel.get('title') and panel.get('blocks'), '面板只接受id、title、blocks、span')
        _need(panel.get('span') in (None, 'members', 'figure'), 'span只接受members或figure')
        _need(all(isinstance(b, str) and b in blocks for b in panel['blocks']), '面板成员须为已声明块')
    gap = COMPACT_GAP * scale; arrow_gap = ARROW_BOUNDARY_GAP
    margin = 3.9
    column_gap = spec.get('policy', {}).get('column_gap', 2 * arrow_gap)
    _need(isinstance(column_gap, (int, float)) and not isinstance(column_gap, bool) and arrow_gap <= column_gap <= 40,
          'column_gap须介于箭头最小长度与40pt之间')
    icon_gap = 2.0 * scale
    node_size = {}
    justified = set()

    def measure_node(item, depth=0):
        """递归量出 group/node/note/label 的宽高；结果写进 node_size。"""
        _need(depth < 4, '子框嵌套最多4层')
        kind = item.get('kind') or 'node'
        if kind == 'group':
            kids = item['items']
            gpx = 0.0 if item.get('frame') is False else px   # 无边框组不占内边距：外沿即成员外沿
            gpy = 0.0 if item.get('frame') is False else py
            sizes = [measure_node(k, depth + 1) for k in kids]
            title = item.get('title')
            tm = reg.measure(display_content(title), size) if title else {'width': 0.0, 'height': 0.0}
            _need(item.get('direction') in (None, 'column', 'row'), 'group的direction只接受column或row')
            if item.get('direction') == 'row':
                # 横排容器：成员并排放，宽度求和、高度取最大
                w = sum(q[0] for q in sizes) + gap * (len(sizes) - 1) + 2 * gpx
                h = max(q[1] for q in sizes) + 2 * gpy + ((tm['height'] + gap) if title else 0)
                node_size[item['id']] = (w, h)
                return (w, h)
            w = max([q[0] for q in sizes] + [tm['width']]) + 2 * gpx
            h = (sum(q[1] for q in sizes) + gap * (len(sizes) - 1) + 2 * gpy
                 + ((tm['height'] + gap) if title else 0))
            if item.get('justify'):
                # 子框统一拉到容器内容宽度，和源图里「同宽嵌套」一致
                for kid in kids:
                    node_size[kid['id']] = (w - 2 * gpx, node_size[kid['id']][1])
                    justified.add(kid['id'])
            node_size[item['id']] = (w, h)
            return (w, h)
        m = reg.measure(display_content(item.get('text', '')), size)
        if kind == 'label':
            w, h = m['width'], m['height']
        elif kind == 'note':
            w, h = m['width'] + 3 * px, m['height'] + 3 * py
        else:
            w, h = m['width'] + 2 * px, m['height'] + 2 * py
        node_size[item['id']] = (w, h)
        return (w, h)
    measures = {}; widths = {}; heights = {}; item_sizes = {}; icon_wh = {}
    for identifier, block in blocks.items():
        text = block.get('title', block.get('text', ''))
        _need(block.get('vertical') in (None, True, False), 'vertical须为布尔值')
        _need(block.get('valign') in (None, 'top', 'center', 'bottom'), 'valign只接受top/center/bottom')
        _need(not block.get('vertical') or block['kind'] == 'node', '只有node块可竖排')
        if block['kind'] == 'group' and not block.get('title'):
            m = {'width': 0.0, 'height': 0.0}          # 无标题容器不参与文字测量
        else:
            m = (reg.measure_vertical(display_content(text), size) if block.get('vertical')
                 else reg.measure(display_content(text), size))
        measures[identifier] = m
        if block['kind'] == 'group':
            widths[identifier], heights[identifier] = measure_node(block)
        elif block['kind'] == 'stage':
            rows = [(item, reg.measure(display_content(item['text']), size)) for item in block['items']]
            iw = max(m['width'] for _, m in rows) + 2 * px
            item_sizes[identifier] = [(item, iw, m['height'] + 2 * py) for item, m in rows]
            widths[identifier] = max(m['width'] + 2 * px, iw + 2 * px)
            heights[identifier] = m['height'] + 4 * py + sum(h for _, _, h in item_sizes[identifier]) + gap * len(rows)
        elif block['kind'] == 'note':
            widths[identifier] = m['width'] + 3 * px
            heights[identifier] = m['height'] + 3 * py
        else:
            widths[identifier] = m['width'] + (2 * px if block['kind'] == 'node' else 0)
            heights[identifier] = m['height'] + (2 * py if block['kind'] == 'node' else 0)
        if 'icon' in block:
            icon = block['icon']; iw = icon['width_pt'] * scale
            ih = iw * (icon['clip'][3] - icon['clip'][1]) / (icon['clip'][2] - icon['clip'][0])
            icon_wh[identifier] = (iw, ih)
            padx = 2 * px if block['kind'] == 'node' else 0
            pady = 2 * py if block['kind'] == 'node' else 0
            icon_side_gap = icon.get('gap', icon_gap)
            if icon.get('side') == 'left':
                widths[identifier] = m['width'] + padx + iw + icon_side_gap
                heights[identifier] = max(m['height'] + pady, ih)
            else:
                widths[identifier] = max(widths[identifier], iw + padx)
                heights[identifier] = m['height'] + pady + ih + icon_gap
    parent = {i: i for i in blocks}
    def root(identifier):
        while parent[identifier] != identifier:
            identifier = parent[identifier]
        return identifier
    for identifier, block in blocks.items():
        if block.get('align_with'):
            other = block['align_with']; _need(other in blocks, 'align_with未知块')
            parent[root(identifier)] = root(other)
        _need(all(i in blocks for i in block.get('after', [])), 'after未知块')
        _need(all(i in blocks for i in block.get('cover', [])), 'cover未知块')
        _need(not block.get('cover') or block['kind'] == 'stage', '只有容器可cover')
    vertical = {(e.get('from'), e.get('to')) for e in edges if e.get('from_port') == 'bottom' and e.get('to_port') == 'top'}
    # 竖向合流把两段短竖线加一条横母线塞进块间距里，需要比普通箭头更多纵向空间
    merge_span = {(kid_top.get(e['from'], e['from']), kid_top.get(e['to'], e['to']))
                  for e in edges if e.get('merge') and e.get('from_port') == 'bottom'}
    band_of = {i: blocks[i].get('band', 1) for i in blocks}
    ordering = []
    for column in columns:
        members = column['blocks']
        for a, b in zip(members, members[1:]):
            if band_of[a['id']] != band_of[b['id']]:
                continue          # 换行处不串联：行内独立排布，行间由 band 堆叠
            pair = (a['id'], b['id'])
            if pair in vertical or pair in merge_span:
                distance = arrow_gap + (2.5 if pair in merge_span else 0.0)
            else:
                distance = gap
            ordering.append((a['id'], b['id'], distance))
    for identifier, block in blocks.items():
        ordering.extend((previous, identifier, arrow_gap) for previous in block.get('after', []))
    tops = {root(i): margin for i in blocks}
    for iteration in range(len(blocks) * 4 + 1):
        changed = False
        for a, b, distance in ordering:
            ra, rb = root(a), root(b)
            value = tops[ra] + heights[a] + distance
            if value > tops[rb] + 1e-6:
                tops[rb] = value; changed = True
        for identifier, block in blocks.items():
            for target in block.get('cover', []):
                value = tops[root(target)] + heights[target] + py - tops[root(identifier)]
                if value > heights[identifier] + 1e-6:
                    heights[identifier] = value; changed = True
        if not changed:
            break
    else:
        raise FigureError('stage_grid_constraints_cycle', '顶部对齐/顺序/容器约束发生循环')
    col_widths = [max(widths[b['id']] for b in col['blocks']) for col in columns]
    for panel in panels:
        want = reg.measure(display_content(panel['title']), size)['width'] + 2 * px + 6
        span_cols = sorted({owners[b] for b in panel['blocks']})
        have = sum(col_widths[ci] for ci in span_cols) + column_gap * (len(span_cols) - 1)
        if have < want:
            extra = (want - have) / len(span_cols)
            for ci in span_cols:
                col_widths[ci] += extra
    # 行（band）：块可声明 band，每行独立做列居中，行间上下堆叠；不声明即单行。
    band_ids = sorted(set(band_of.values()))
    panel_reserve = (max(reg.measure(display_content(x['title']), size)['height'] + 4 * py + 4
                         for x in panels) if panels else 0)
    spanning = {i for i, b in blocks.items() if b.get('span') or b.get('stretch')}
    band_off = {}; band_top = {}; band_bottom = {}; cursor_band = margin + panel_reserve
    for bid in band_ids:
        rows = [i for i in blocks if band_of[i] == bid and i not in spanning]
        if not rows:
            rows = [i for i in blocks if band_of[i] == bid]
        band_top[bid] = min(tops[root(i)] for i in rows)
        band_bottom[bid] = max(tops[root(i)] + heights[i] for i in rows)
        band_off[bid] = cursor_band - band_top[bid]
        cursor_band += (band_bottom[bid] - band_top[bid]) + arrow_gap * 1.5
    total_bottom = cursor_band - arrow_gap * 1.5
    col_top = {}; col_bottom = {}
    for identifier in blocks:
        if identifier in spanning:
            continue
        key = (band_of[identifier], owners[identifier])
        top = tops[root(identifier)]; bottom = top + heights[identifier]
        col_top[key] = min(col_top.get(key, top), top)
        col_bottom[key] = max(col_bottom.get(key, bottom), bottom)
    top_aligned = {ci for ci, col in enumerate(columns) if col.get('align') == 'top'}
    col_shift = {key: (0.0 if key[1] in top_aligned else
                       (band_bottom[key[0]] - band_top[key[0]] - (col_bottom[key] - col_top[key])) / 2)
                 for key in col_top}
    panel_of = {}
    for panel in panels:
        for b in panel['blocks']: panel_of[b] = panel['id']
    panel_gap = spec.get('policy', {}).get('panel_gap', 0)
    _need(isinstance(panel_gap, (int, float)) and not isinstance(panel_gap, bool) and 0 <= panel_gap <= 60, 'panel_gap须为0至60pt')
    gap_overrides = spec.get('policy', {}).get('gap_overrides', {}) or {}
    _need(isinstance(gap_overrides, dict) and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                  and arrow_gap <= v <= 60 for v in gap_overrides.values()),
          'gap_overrides须为列ID到箭头最小长度以上列距的映射')
    if spec.get('policy', {}).get('fill_width'):
        # 内容比版心窄时，把余量均分给各列：保持 8pt，又不让整幅缩在中间
        target = ((160 if spec.get('policy', {}).get('column') == 'double' else 80) * 72 / 25.4
                  - 2 * margin - 8)
        crossings = 0
        for ci in range(len(columns) - 1):
            here = {panel_of.get(b['id']) for b in columns[ci]['blocks']}
            there = {panel_of.get(b['id']) for b in columns[ci + 1]['blocks']}
            if here != there:
                crossings += 1
        used = sum(col_widths) + column_gap * (len(col_widths) - 1) + panel_gap * crossings
        if used < target:
            extra = (target - used) / len(col_widths)
            col_widths = [w + extra for w in col_widths]
    col_left = []; cursor = margin
    for ci, width in enumerate(col_widths):
        col_left.append(cursor)
        cursor += width + gap_overrides.get(columns[ci]['id'], column_gap)
        if ci + 1 < len(col_widths) and panel_gap:
            here = {panel_of.get(b['id']) for b in columns[ci]['blocks']}
            there = {panel_of.get(b['id']) for b in columns[ci + 1]['blocks']}
            if here != there: cursor += panel_gap
    icon_cache = {}
    def icon_asset(icon):
        _need(assets is not None, '图标裁取需要Assets实例，请通过compile_figure调用')
        rel = icon.get('path') or spec.get('icon_source')
        _need(source_root is not None, '图标裁取需要明确素材根目录')
        path = resolve_source(Path(source_root), rel)
        key = (str(path), tuple(icon['clip']), icon.get('source_kind'), icon.get('page', 0))
        if key not in icon_cache:
            if icon.get('source_kind') == 'pdf':
                icon_cache[key] = assets.source_icon(path, icon.get('page', 0), list(icon['clip']))
            else:
                icon_cache[key] = assets.raster(path, list(icon['clip']), gray=True)
        return icon_cache[key]
    scene = Scene(reg, size); scene.template = 'bounded-measured-stage-grid'; placed = {}
    single = {ci: sum(1 for i in blocks if owners[i] == ci and i not in spanning) <= 1 for ci in range(len(columns))}

    def draw_node(item, x, y, w, h):
        """递归落笔：group 先画外框与标题，再摆子框；note 无边框只填浅灰。"""
        kind = item.get('kind') or 'node'
        ident = item['id']
        if kind == 'group':
            frameless = item.get('frame') is False
            if frameless:
                # 无边框组：登记外沿矩形承接箭头，但不描边不填充（源图这类组合本来没有外框）
                rect = scene.shape(ident, [x, y, x + w, y + h], 'rectangle', width=.5)
                rect['invisible'] = True
                rect['container'] = True
            else:
                rect = scene.shape(ident, [x, y, x + w, y + h], container=True)
            placed[ident] = rect
            if 'fill' in item:
                rect['fill'] = item['fill']
            ipx = 0.0 if frameless else px
            ipy = 0.0 if frameless else py
            cursor_y = y + ipy
            title = item.get('title')
            if title:
                tm = reg.measure(display_content(title), size)
                scene.text(ident + ':title', title, x + w / 2, cursor_y + tm['height'] / 2, owner=ident)
                cursor_y += tm['height'] + gap
            if item.get('direction') == 'row':
                # 横排容器：成员并排，且一律拉伸到行内容高（同行等高）
                cursor_x = x + ipx
                row_bottom = y + h - ipy
                for kid in item['items']:
                    kw, kh = node_size[kid['id']]
                    if row_bottom - cursor_y > kh + 1e-6 and (kid.get('kind') or 'node') == 'node':
                        justified.add(kid['id'])   # 拉伸后的框不再等于文字测量框，改按 shape+text 绘制
                    draw_node(kid, cursor_x, cursor_y, kw, row_bottom - cursor_y)
                    cursor_x += kw + gap
                return
            for kid in item['items']:
                kw, kh = node_size[kid['id']]
                draw_node(kid, x + (w - kw) / 2, cursor_y, kw, kh)
                cursor_y += kh + gap
            return
        if kind == 'label':
            scene.text(ident, item['text'], x + w / 2, y + h / 2)
            placed[ident] = {'id': ident, 'rect': [x, y, x + w, y + h], 'container': False, 'kind': 'rectangle'}
            return
        if kind == 'note':
            if 'fill' in item:
                rect = scene.shape(ident, [x, y, x + w, y + h], 'rectangle', width=0.1)
                rect['fill'] = item['fill']
                placed[ident] = rect
            else:
                placed[ident] = {'id': ident, 'rect': [x, y, x + w, y + h], 'container': False, 'kind': 'rectangle'}
            scene.text(ident + ':text', item['text'], x + w / 2, y + h / 2)
            return
        if ident in justified:
            rect = scene.shape(ident, [x, y, x + w, y + h], 'rectangle', width=.5)
            if 'fill' in item:
                rect['fill'] = item['fill']
            scene.text(ident + ':text', item['text'], x + w / 2, y + h / 2)
            placed[ident] = rect
            return
        rect = scene.box(ident, item['text'], x, y, w, h)
        placed[ident] = rect
        if 'fill' in item:
            rect['fill'] = item['fill']

    for identifier, block in blocks.items():
        ci = owners[identifier]; width, height = widths[identifier], heights[identifier]
        band = band_of[identifier]
        x = col_left[ci] + (col_widths[ci] - width) / 2
        if block.get('span') or block.get('stretch'):
            # 跨行块拉到最后一行的底；stretch 只撑满自己那一行
            y = band_top[band] + band_off[band]
            bottom_band = band if block.get('stretch') and not block.get('span') else band_ids[-1]
            height = band_bottom[bottom_band] + band_off[bottom_band] - y
        else:
            y = tops[root(identifier)] + band_off[band] + col_shift[(band, ci)]
            if single[ci]:
                # 单块列的块级上下对齐；多块列仍整列居中，避免破坏列内顺序
                anchor = block.get('valign', 'center')
                if anchor == 'top':
                    y = tops[root(identifier)] + band_off[band] - (tops[root(identifier)] - band_top[band])
                elif anchor == 'bottom':
                    y = band_bottom[band] + band_off[band] - height
        if block['kind'] in ('group', 'note'):
            draw_node(block, x, y, width, height)
        elif block['kind'] == 'label' and 'icon' not in block:
            scene.text(identifier, block['text'], x+width/2, y+height/2)
            placed[identifier] = {'id': identifier, 'rect': [x, y, x+width, y+height], 'container': False, 'kind': 'rectangle'}
        elif block['kind'] == 'node' and block.get('vertical'):
            placed[identifier] = scene.shape(identifier, [x,y,x+width,y+height], 'rectangle', width=.5)
            scene.text(identifier+':text', block['text'], x+width/2, y+height/2, vertical=True)
            if 'fill' in block: placed[identifier]['fill'] = block['fill']
        elif block.get('frame') is False:
            # 无边框节点：只登记矩形承接箭头，不描边不填充（源图这类标注本来就没有框）
            placed[identifier] = scene.shape(identifier, [x, y, x + width, y + height], 'rectangle', width=.5)
            placed[identifier]['invisible'] = True
            if 'icon' in block:
                iw, ih = icon_wh[identifier]
                tw = measures[identifier]['width']
                if block['icon'].get('side') == 'left':
                    gap_i = block['icon'].get('gap', icon_gap)
                    left = x + (width - (iw + gap_i + tw)) / 2
                    scene.embed(identifier+':icon', icon_asset(block['icon']),
                                [left, y + (height - ih) / 2, left + iw, y + (height + ih) / 2], role='icon')
                    scene.text(identifier+':text', block['text'], left + iw + gap_i + tw / 2, y + height / 2)
                else:
                    th = measures[identifier]['height']
                    top = y + (height - (ih + icon_gap + th)) / 2
                    scene.embed(identifier+':icon', icon_asset(block['icon']),
                                [x + (width - iw) / 2, top, x + (width + iw) / 2, top + ih], role='icon')
                    scene.text(identifier+':text', block['text'], x + width / 2, top + ih + icon_gap + th / 2)
            else:
                scene.text(identifier+':text', block['text'], x + width / 2, y + height / 2)
        elif 'icon' in block:
            if block['kind'] == 'node':
                placed[identifier] = scene.shape(identifier, [x, y, x+width, y+height], 'rectangle', width=.5)
                if 'fill' in block: placed[identifier]['fill'] = block['fill']
            else:
                placed[identifier] = {'id': identifier, 'rect': [x, y, x+width, y+height], 'container': False, 'kind': 'rectangle'}
            iw, ih = icon_wh[identifier]
            text_h = measures[identifier]['height']
            if block['icon'].get('side') == 'left':
                # 图标在左、文字在右，整体在框内居中对齐
                gap_i = block['icon'].get('gap', icon_gap)
                left = x + (width - (iw + gap_i + measures[identifier]['width'])) / 2
                scene.embed(identifier+':icon', icon_asset(block['icon']),
                            [left, y + (height - ih) / 2, left + iw, y + (height + ih) / 2], role='icon')
                scene.text(identifier+':text', block['text'],
                           left + iw + gap_i + measures[identifier]['width'] / 2, y + height / 2)
            else:
                # 图标与文字作为一个整体在框内居中，避免高框里两者被拉开
                left = x + (width - iw) / 2
                block_h = ih + icon_gap + text_h
                top = y + (height - block_h) / 2
                scene.embed(identifier+':icon', icon_asset(block['icon']),
                            [left, top, left + iw, top + ih], role='icon')
                scene.text(identifier+':text', block['text'], x+width/2, top + ih + icon_gap + text_h/2)
        elif block['kind'] == 'node' and (block.get('span') or block.get('stretch')):
            # 拉高/跨行的框不再套自然尺寸契约，自身就是被拉伸的容器
            placed[identifier] = scene.shape(identifier, [x, y, x+width, y+height], 'rectangle', width=.5)
            if 'fill' in block: placed[identifier]['fill'] = block['fill']
            scene.text(identifier+':text', block['text'], x+width/2, y+height/2,
                       vertical=bool(block.get('vertical')))
        elif block['kind'] == 'node':
            placed[identifier] = scene.box(identifier, block['text'], x, y, width, height)
            if 'fill' in block: placed[identifier]['fill'] = block['fill']
        else:
            placed[identifier] = scene.shape(identifier, [x,y,x+width,y+height], container=True)
            title_h = measures[identifier]['height']
            scene.text(identifier+':title', block['title'], x+width/2,y+py+title_h/2,owner=identifier)
            separator = y+2*py+title_h
            scene.line(identifier+':separator', [[x,separator],[x+width,separator]], semantic_role='decorative')
            rows = item_sizes[identifier]; gid = identifier+':members'
            scene.measurement_groups[gid] = {'axis':'column','nodes':[item['id'] for item,_,_ in rows]}
            spare = height - (separator-y) - py - sum(h for _,_,h in rows)
            spacing = spare/len(rows)
            cursor_y = separator + spacing
            for item, iw, ih in rows:
                node = scene.box(item['id'],item['text'],x+(width-iw)/2,cursor_y,iw,ih)
                node['measurement_contract'] = {'mode':'measured-group','group':gid,'axis':'column','expected_wh':[iw,ih]}
                if 'fill' in block: node['fill'] = block['fill']
                placed[item['id']] = node
                cursor_y += ih+spacing
    figure_top = band_top[band_ids[0]] + band_off[band_ids[0]]
    figure_bottom = band_bottom[band_ids[-1]] + band_off[band_ids[-1]]
    for panel in panels:
        members = [placed[b] for b in panel['blocks']]
        tm = reg.measure(display_content(panel['title']), size)
        # 面板左右边界对齐到列栅格，而不是贴最宽成员：走道宽度才和列距一致
        cols = sorted({owners[b] for b in panel['blocks'] if b in owners})
        x0 = max(1.0, col_left[cols[0]] - px - 1.5)
        x1 = col_left[cols[-1]] + col_widths[cols[-1]] + px + 1.5
        if panel.get('span') == 'figure':
            y1 = figure_bottom + py + 3
            y0 = figure_top - tm['height'] - 4 * py - 4
        else:
            y1 = max(n['rect'][3] for n in members) + py + 3
            y0 = min(n['rect'][1] for n in members) - tm['height'] - 4 * py - 4
        scene.shape(panel['id'], [x0, y0, x1, y1], 'rectangle', width=.5)
        scene.text(panel['id']+':title', panel['title'], (x0+x1)/2, y0 + py + tm['height']/2)
        rule_y = y0 + 2 * py + tm['height']
        scene.line(panel['id']+':rule', [[x0, rule_y], [x1, rule_y]], semantic_role='decorative')
        placed[panel['id']] = scene.nodes[-1]
    def place_edge_label(edge, points):
        """Put an optional edge caption on the longest run, clear of the stroke."""
        if not edge.get('label'):
            return
        runs = list(zip(points, points[1:]))
        flat = [ab for ab in runs if abs(ab[1][0] - ab[0][0]) >= abs(ab[1][1] - ab[0][1]) and abs(ab[1][0] - ab[0][0]) > 1e-6]
        seg = max(flat, key=lambda ab: abs(ab[0][0] - ab[1][0])) if flat else max(runs, key=lambda ab: abs(ab[0][1] - ab[1][1]))
        vertical_label = bool(edge.get('label_vertical'))
        lm = (reg.measure_vertical(display_content(edge['label'], 'edge-label'), size)
              if vertical_label else reg.measure(display_content(edge['label'], 'edge-label'), size))
        if flat:
            mid_x = (seg[0][0] + seg[1][0]) / 2
            if vertical_label:
                scene.text(edge['id']+':label', edge['label'], mid_x,
                           seg[0][1] - lm['height'] / 2 - 2.6, role='edge-label', vertical=True)
            else:
                scene.text(edge['id']+':label', edge['label'], mid_x,
                           min(seg[0][1], seg[1][1]) - lm['height'] / 2 - 1.6, role='edge-label')
        else:
            # 只有竖段时才把标签贴在竖段右侧，避免压住自身的横向折段
            mid_y = (seg[0][1] + seg[1][1]) / 2
            scene.text(edge['id']+':label', edge['label'], seg[0][0] + lm['width'] / 2 + 2.2,
                       mid_y, role='edge-label', vertical=vertical_label)

    records=[]
    panel_ids = {p['id'] for p in panels}
    for edge in panel_edges:
        _need(edge['from_panel'] in panel_ids and edge['to_panel'] in panel_ids, '面板连线端点须为已声明面板')
        a = placed[edge['from_panel']]['rect']; b = placed[edge['to_panel']]['rect']
        _need(a[2] <= b[0], '面板连线只支持左面板指向右面板')
        y = (figure_top + figure_bottom) / 2
        frac_a = (y - a[1]) / (a[3] - a[1]); frac_b = (y - b[1]) / (b[3] - b[1])
        scene.line(edge['id'], [[a[2], y], [b[0], y]], arrow=True,
                   endpoint_nodes=[{'node': edge['from_panel'], 'side': 'right', 'fraction': frac_a},
                                   {'node': edge['to_panel'], 'side': 'left', 'fraction': frac_b}])
        if edge.get('label'):
            lm = (reg.measure_vertical(display_content(edge['label'], 'edge-label'), size)
                  if edge.get('label_vertical') else reg.measure(display_content(edge['label'], 'edge-label'), size))
            scene.text(edge['id']+':label', edge['label'], (a[2] + b[0]) / 2,
                       y - lm['height'] / 2 - 2.6, role='edge-label', vertical=bool(edge.get('label_vertical')))
        records.append({'edge': edge['id'], 'from': edge['from_panel'], 'to': edge['to_panel'], 'panel_edge': True})
    merge_groups={}; split_groups={}
    for edge in edges:
        if edge.get('from_panel') or edge.get('to_panel'):
            continue          # 面板级连线已在面板之后单独画出
        if edge.get('merge'):
            merge_groups.setdefault(edge['merge'], []).append(edge)
            continue
        if edge.get('split'):
            split_groups.setdefault(edge['split'], []).append(edge)
            continue
        a,b = placed[edge['from']],placed[edge['to']]
        if edge.get('straight'):
            # 直线连接：取能水平直达的那一侧高度，不做直角折
            source_rect = a['rect']; target_rect = b['rect']
            centre_a = (source_rect[1] + source_rect[3]) / 2
            centre_b = (target_rect[1] + target_rect[3]) / 2
            if target_rect[1] + .5 <= centre_a <= target_rect[3] - .5:
                y_line = centre_a
            elif source_rect[1] + .5 <= centre_b <= source_rect[3] - .5:
                y_line = centre_b
            else:
                raise FigureError('stage_grid_unsupported', '直线连接要求源或目标有一方高度覆盖另一方出口')
            start = (source_rect[2] if edge['from_port'] == 'right' else source_rect[0], y_line)
            end = (target_rect[0] if edge['to_port'] == 'left' else target_rect[2], y_line)
            frac_in = (y_line - source_rect[1]) / (source_rect[3] - source_rect[1])
            frac_out = (y_line - target_rect[1]) / (target_rect[3] - target_rect[1])
            scene.line(edge['id'], [start, end], arrow=True,
                       endpoint_nodes=[{'node': edge['from'], 'side': edge['from_port'], 'fraction': frac_in},
                                       {'node': edge['to'], 'side': edge['to_port'], 'fraction': frac_out}])
            place_edge_label(edge, [start, end])
            records.append({'edge': edge['id'], 'from': edge['from'], 'to': edge['to'], 'straight': True})
            continue
        start,end = port(a,edge['from_port']),port(b,edge['to_port'])
        if edge['from_port'] == 'bottom':
            _need(end[1] > start[1] and abs(start[0]-end[0]) < 1e-6, '同列链须向下且中心对齐')
        source_decl = edge['from']
        if edge.get('source_align'):
            _need(edge['source_align']=='target' and a['container'] and edge['from_port'] in ('left','right'), '只有容器侧端口可对齐目标')
            start[1] = end[1]
            fraction = (start[1]-a['rect'][1])/(a['rect'][3]-a['rect'][1])
            _need(0 <= fraction <= 1,'目标中心超出源容器，请声明cover')
            source_decl = {'node':edge['from'],'side':edge['from_port'],'fraction':fraction}
        points=[start,end]
        if abs(start[0]-end[0])>1e-6 and abs(start[1]-end[1])>1e-6:
            _need(edge['from_port']=='right' and edge['to_port']=='left' and start[0]<end[0], '仅支持相邻列右到左折线')
            bus=(start[0]+end[0])/2
            points=[start,[bus,start[1]],[bus,end[1]],end]
        scene.line(edge['id'],points,arrow=True,endpoint_nodes=[source_decl,edge['to']])
        place_edge_label(edge, points)
        records.append({'edge':edge['id'],'from':edge['from'],'to':edge['to']})
    for merge, members in merge_groups.items():
        if members[0].get('from_port') == 'bottom':
            # 竖向合流（括线）：各源底沿中心下行→横母线→中点下行带箭头进目标上沿
            target = members[0]['to']; target_node = placed[target]; end = port(target_node, 'top')
            _need(len(members) >= 2 and all(e['to'] == target and e['from_port'] == 'bottom' and e['to_port'] == 'top' for e in members),
                  '竖向合流须至少两条下到上边和同一目标')
            starts = [port(placed[e['from']], 'bottom') for e in members]
            _need(all(s[1] < end[1] - arrow_gap for s in starts), '竖向合流目标与源之间须留出箭头空间')
            top_start = max(s[1] for s in starts)
            # 母线优先取中点；箭头末段不得短于 ARROW_LENGTH，空间不足时母线贴近源侧
            bus_y = min((top_start + end[1]) / 2, end[1] - arrow_gap)
            xs = sorted(s[0] for s in starts)
            for edge, start in zip(members, starts):
                scene.line(edge['id'], [start, [start[0], bus_y]], shared_net=merge, semantic_role='merge-leg')
                place_edge_label(edge, [start, [start[0], bus_y]])
                records.append({'edge': edge['id'], 'from': edge['from'], 'to': edge['to'], 'shared_net': merge})
            bus_x0 = min(xs[0], end[0]); bus_x1 = max(xs[-1], end[0])
            if bus_x1 - bus_x0 > 1e-6:
                scene.line(merge + ':bus', [[bus_x0, bus_y], [bus_x1, bus_y]], shared_net=merge, semantic_role='bus')
            scene.line(merge + ':outlet', [[end[0], bus_y], end], arrow=True, endpoint_nodes=[None, target])
            continue
        target = members[0]['to']; target_node=placed[target]; end=port(target_node,'left')
        _need(len(members)>=2 and all(e['to']==target and e['from_port']=='right' and e['to_port']=='left' for e in members), '合流须至少两条右到左边和同一目标')
        starts=[port(placed[e['from']],'right') for e in members]
        # Reserve the corridor outside the widest block in the target column,
        # not merely beside a narrower target node (which can hug a later frame).
        bus=min(end[0]-(arrow_gap+0.8), col_left[owners[target]]-gap)
        _need(all(a[0]+gap<bus for a in starts),'合流通道空间不足')
        low=min([end[1]]+[a[1] for a in starts]); high=max([end[1]]+[a[1] for a in starts])
        for edge,start in zip(members,starts):
            scene.line(edge['id'],[start,[bus,start[1]]],shared_net=merge,semantic_role='merge-leg')
            place_edge_label(edge, [start, [bus, start[1]]])
            records.append({'edge':edge['id'],'from':edge['from'],'to':edge['to'],'shared_net':merge})
        if high>low:
            scene.line(merge+':bus',[[bus,low],[bus,high]],shared_net=merge,semantic_role='bus')
        scene.line(merge+':outlet',[[bus,end[1]],end],arrow=True,endpoint_nodes=[None,target])
    for split, group in split_groups.items():
        source = group[0]['from']
        _need(len(group) >= 2 and all(e_.get('from') == source and e_['from_port'] == 'right' and e_['to_port'] == 'left' for e_ in group),
              '扇出须至少两条同源右到左边')
        src_node = placed[source]; start = port(src_node, 'right')
        ends = [port(placed[e_['to']], 'left') for e_ in group]
        target_col = owners[group[0]['to']]
        # 母线贴源框右沿：腿全是水平线，与原图画法一致（不再在列间中点起扇）
        bus = start[0]
        _need(all(p[0] > bus + arrow_gap for p in ends), '扇出通道空间不足')
        if bus - start[0] > 1e-6:
            scene.line(split+':trunk',[start,[bus,start[1]]],shared_net=split,semantic_role='split-trunk')
        low = min([start[1]]+[p[1] for p in ends]); high = max([start[1]]+[p[1] for p in ends])
        src_rect = src_node['rect']
        legs_inside = all(src_rect[1] - .1 <= p[1] <= src_rect[3] + .1 for p in ends)
        if high - low > 1e-6 and not legs_inside:
            scene.line(split+':bus',[[bus,low],[bus,high]],shared_net=split,semantic_role='bus')
        src_decl = None
        if legs_inside:
            src_decl = {'node': source, 'side': 'right',
                        'fraction': (start[1] - src_rect[1]) / (src_rect[3] - src_rect[1])}
        for edge, end in zip(group, ends):
            if legs_inside:
                leg_start = (bus, end[1])
                frac = (end[1] - src_rect[1]) / (src_rect[3] - src_rect[1])
                decl = [{'node': source, 'side': 'right', 'fraction': frac}, edge['to']]
            else:
                leg_start = (bus, end[1])
                decl = [None, edge['to']]
            scene.line(edge['id'],[leg_start,end],arrow=True,endpoint_nodes=decl)
            place_edge_label(edge, [leg_start, end])
            records.append({'edge':edge['id'],'from':edge['from'],'to':edge['to'],'shared_net':split})
    scene.layout_evidence={'layout_algorithm':'bounded-measured-stage-columns','edge_bindings':records,
                           'column_widths_pt':col_widths,'column_gap_pt':column_gap,'design_font_size_pt':size,
                           'semantic_edge_count':len(edges),'agent_entry_supported':False}
    max_bottom = max(n['rect'][3] for n in placed.values()) + margin + 4
    max_right = max(n['rect'][2] for n in placed.values()) + margin
    return scene.finish(max(cursor - column_gap + margin, max_right), max(total_bottom + margin, max_bottom))
