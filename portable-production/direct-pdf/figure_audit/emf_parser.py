"""Partial EMF record parser."""
import struct
from .errors import AuditInputError
from .emf_geometry import IDENT, _crd, _xform, _mul, _device_point, _read_transform
from .emf_mapping import apply_mapping_clip

class Emf:
    def __init__(self, path):
        self.path = path
        from pathlib import Path
        self.data = Path(path).read_bytes()
        self.pages = []          # [(w_mm,h_mm,w_px,h_px)]
        self.texts = []
        self.polys = []
        self._validate_records()
        self._read_header()
        try:
            self._run()
        except struct.error as exc:
            raise AuditInputError('truncated or malformed EMF record payload') from exc

    def _validate_records(self):
        """Reject malformed records and retain counts for unsupported constructs."""
        d = self.data
        if len(d) < 88 or struct.unpack_from('<I', d, 0)[0] != 1 or d[40:44] != b' EMF':
            raise AuditInputError('invalid EMF header')
        supported = {1, 14, 18, 22, 24, 26, 27, 29, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 42, 43, 54, 82, 83, 84, 86, 87, 89, 3, 4, 9, 10, 11, 12, 95, 17, 30}
        self.unsupported_records = {}
        offset = 0
        eof = False
        while offset < len(d):
            if len(d) - offset < 8:
                raise AuditInputError('truncated EMF record header')
            kind, size = struct.unpack_from('<II', d, offset)
            if size < 8 or size % 4 or offset + size > len(d):
                raise AuditInputError('invalid or truncated EMF record')
            if kind not in supported:
                self.unsupported_records[kind] = self.unsupported_records.get(kind, 0) + 1
            offset += size
            if kind == 14:
                eof = True
                break
        if not eof:
            raise AuditInputError('missing EMF EOF record')

    # ---------- header ----------
    def _read_header(self):
        d = self.data
        rb = struct.unpack('<iiii', d[8:24])
        rf = struct.unpack('<iiii', d[24:40])
        self.bounds = rb
        self.frame_mm = ((rf[2] - rf[0]) / 100.0, (rf[3] - rf[1]) / 100.0)
        self.dev = struct.unpack('<ii', d[72:80])
        self.dev_mm = struct.unpack('<ii', d[80:88])
        if min(*self.dev, *self.dev_mm) <= 0:
            raise AuditInputError('invalid EMF device dimensions')
        self.kx = self.dev_mm[0] / float(self.dev[0])   # mm/px
        self.ky = self.dev_mm[1] / float(self.dev[1])
        self.nat_mm = ((rb[2] - rb[0]) * self.kx, (rb[3] - rb[1]) * self.ky)

    # ---------- main ----------
    def _run(self):
        d = self.data
        off = 0
        state = {
            'color': (0, 0, 0), 'fill': None, 'pen_w': 0.0,
            'font': None, 'tcolor': (0, 0, 0), 'align': 0, 'bkmode': 2,
            'm': IDENT, 'map_mode': 1, 'dev': self.dev, 'dev_mm': self.dev_mm, 'clip_regions': (), 'clip_exclusions': (), 'clip_status': 'partial', 'meta_clip_unknown': False, 'coordinate_status': 'partial',
        }
        stack = []
        objs = {}
        path_pts = None          # 正在录制的 path
        path_closed = False
        cur = (0.0, 0.0)
        n = len(d)
        while off + 8 <= n:
            t, sz = struct.unpack('<II', d[off:off + 8])
            if sz < 8 or off + sz > n:
                break
            p = d[off:off + sz]
            if t == 14:  # EOF
                break
            elif t == 82:  # EXTCREATEFONTINDIRECTW
                ih = struct.unpack('<I', p[8:12])[0]
                lf = p[12:12 + 92]
                h, w, esc, ori, wt = struct.unpack('<iiiii', lf[0:20])
                italic = lf[20]
                face = lf[28:28 + 64].decode('utf-16le', 'replace').split('\x00')[0]
                objs[('font', ih)] = dict(height=h, width=w, weight=wt, italic=bool(italic), face=face)
            elif t == 38:  # CREATEPEN
                ih = struct.unpack('<I', p[8:12])[0]
                style, wx, wy, col = struct.unpack('<iiii', p[12:28])
                objs[('pen', ih)] = dict(w=abs(wx), color=_crd(col), style=style)
            elif t == 95:  # EXTCREATEPEN
                ih = struct.unpack('<I', p[8:12])[0]
                style, w, bstyle, col = struct.unpack('<iiii', p[28:44])
                objs[('pen', ih)] = dict(w=w, color=_crd(col), style=style)
            elif t == 39:  # CREATEBRUSHINDIRECT
                ih = struct.unpack('<I', p[8:12])[0]
                bstyle, col, hatch = struct.unpack('<iii', p[12:24])
                objs[('brush', ih)] = dict(style=bstyle, color=_crd(col), hatch=hatch)
            elif t == 40:  # DELETEOBJECT
                ih = struct.unpack('<I', p[8:12])[0]
                objs.pop(('pen', ih), None)
                objs.pop(('brush', ih), None)
                objs.pop(('font', ih), None)
            elif t == 37:  # SELECTOBJECT
                ih = struct.unpack('<I', p[8:12])[0]
                for kind in ('pen', 'brush', 'font'):
                    if (kind, ih) in objs:
                        if kind == 'font':
                            state['font'] = objs[(kind, ih)]
                        elif kind == 'pen':
                            state['pen_w'] = objs[(kind, ih)]['w']
                            state['color'] = objs[(kind, ih)]['color']
                        else:
                            b = objs[(kind, ih)]
                            state['fill'] = b['color'] if b['style'] != 1 else None
                        break
            elif t == 24:
                state['tcolor'] = _crd(struct.unpack('<I', p[8:12])[0])
            elif t == 22:
                state['align'] = struct.unpack('<I', p[8:12])[0]
            elif t == 18:
                state['bkmode'] = struct.unpack('<I', p[8:12])[0]
            elif t == 33:
                stack.append((dict(state), cur))
            elif t == 34:
                level = struct.unpack('<i', p[8:12])[0]
                index = len(stack) + level if level < 0 else level - 1
                if level == 0 or index < 0 or index >= len(stack):
                    raise AuditInputError('invalid RestoreDC level')
                state, cur = stack[index]
                del stack[index:]
            elif t == 35:
                state['m'] = _read_transform(p[8:32])
            elif t == 36:
                xf = _read_transform(p[8:32])
                mode = struct.unpack('<I', p[32:36])[0]
                if mode == 4:
                    state['m'] = xf
                elif mode == 2:
                    state['m'] = _mul(xf, state['m'])
                elif mode == 3:
                    state['m'] = _mul(state['m'], xf)
                elif mode == 1:
                    state['m'] = IDENT
                else:
                    state['coordinate_status'] = 'unknown'
                    state['clip_status'] = 'unknown'
            elif apply_mapping_clip(t, p, state):
                pass
            elif t == 27:  # MOVETOEX
                cur = struct.unpack('<ii', p[8:16])
            elif t == 54:  # LINETO
                nx = struct.unpack('<ii', p[8:16])
                self._emit([_device_point(cur, state), _device_point(nx, state)], state, closed=False)
                cur = nx
            elif t in (86, 87, 89):  # 16-bit polygon, polyline, polyline-to
                cnt = struct.unpack('<I', p[24:28])[0]
                logical_pts = [struct.unpack('<hh', p[28 + 4 * i:32 + 4 * i]) for i in range(cnt)]
                pts = [_device_point(point, state) for point in logical_pts]
                if t == 89 and logical_pts:
                    pts.insert(0, _device_point(cur, state))
                    cur = logical_pts[-1]
                self._emit(pts, state, closed=(t == 86))
            elif t in (3, 4):  # 32-bit
                cnt = struct.unpack('<I', p[24:28])[0]
                pts = []
                for i in range(cnt):
                    x, y = struct.unpack('<ii', p[28 + 8 * i:36 + 8 * i])
                    pts.append(_device_point((x, y), state))
                self._emit(pts, state, closed=(t == 3))
            elif t in (42, 43):  # ELLIPSE / RECTANGLE
                x0, y0, x1, y1 = struct.unpack('<iiii', p[8:24])
                pts = [_device_point(c, state) for c in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
                self._emit(pts, state, closed=True, kind='ellipse' if t == 42 else 'rect')
            elif t == 84 or t == 83:
                nch = struct.unpack('<I', p[44:48])[0]
                offs = struct.unpack('<I', p[48:52])[0]
                fopt = struct.unpack('<I', p[52:56])[0]
                rcl = struct.unpack('<iiii', p[56:72])
                off_dx = struct.unpack('<I', p[72:76])[0]
                ref = struct.unpack('<ii', p[36:44])
                if 0 < nch < 4096 and offs + (nch * 2 if t == 84 else nch) <= len(p):
                    if t == 84:
                        s = p[offs:offs + nch * 2].decode('utf-16le', 'replace')
                    else:
                        s = p[offs:offs + nch].decode('gbk', 'replace')
                    f = state['font'] or dict(height=-10, weight=400, italic=False, face='')
                    h_px = abs(f['height'])
                    # 位置：ref 有效就用 ref；本批 EMF 的 ref/rcl 常被写成 0，
                    # 此时按 GDI 语义取"当前笔位"（MoveToEx + TA_UPDATECP）。
                    org = cur if state['align'] & 1 else ref
                    # 宽度：优先用 offDx 的 advances（逻辑单位，每字一个 int）
                    w_px = 0.0
                    if off_dx and off_dx + 4 * nch <= len(p):
                        adv = struct.unpack('<%di' % nch, p[off_dx:off_dx + 4 * nch])
                        if all(0 <= a < 20000 for a in adv) and sum(adv) > 0:
                            w_px = sum(adv)          # 单位就是参考设备像素，不再除 10
                    if w_px <= 0:
                        w_px = nch * h_px * 0.55
                    if rcl[2] - rcl[0] > 0:
                        bb = [_device_point((rcl[0], rcl[1]), state), _device_point((rcl[2], rcl[3]), state)]
                    else:
                        o = _device_point(org, state)
                        bb = [o, (o[0] + w_px, o[1] + h_px)]
                    self.texts.append(dict(
                        text=s, ref=_device_point(org, state), bbox=bb, fopt=fopt, clip_regions=state['clip_regions'], clip_exclusions=state['clip_exclusions'], clip_status=state['clip_status'], coordinate_status=state['coordinate_status'],
                        h_px=h_px, weight=f['weight'], italic=f['italic'],
                        face=f['face'], color=state['tcolor'], align=state['align']))
                    if state['align'] & 1:
                        state['coordinate_status'] = 'unknown'
            off += sz

    def _emit(self, pts, state, closed, kind='poly'):
        if len(pts) < 2:
            return
        self.polys.append(dict(pts=pts, closed=closed, kind=kind,
                               stroke=state['color'], width=state['pen_w'],
                               fill=state['fill'], clip_regions=state['clip_regions'], clip_exclusions=state['clip_exclusions'], clip_status=state['clip_status'], coordinate_status=state['coordinate_status']))

    # ---------- 输出 ----------
    def to_mm(self, px, py):
        x0, y0 = self.bounds[0], self.bounds[1]
        return ((px - x0) * self.kx, (py - y0) * self.ky)

    def pt_of(self, pt):
        return self.to_mm(*pt)

    def size_pt(self, h_px):
        return h_px * (self.kx * 72 / 25.4)

    def text_list(self):
        out = []
        for t in self.texts:
            if not t['text'].strip():
                continue
            (x0, y0), (x1, y1) = [self.to_mm(*p) for p in t['bbox']]
            out.append(dict(text=t['text'].replace('\ufffd', '?'), x=round(x0, 2), y=round(y0, 2),
                            w=round(x1 - x0, 2), h=round(y1 - y0, 2),
                            size=round(self.size_pt(t['h_px']), 2),
                            weight=t['weight'], italic=t['italic'], face=t['face'],
                            gray=round(sum(t['color']) / 3, 3), bbox_estimated=True, clip_status=t['clip_status'], coordinate_status=t['coordinate_status'],
                            clip_regions_mm=[[list(self.pt_of(point)) for point in region] for region in t['clip_regions']],
                            clip_exclusions_mm=[[list(self.pt_of(point)) for point in region] for region in t['clip_exclusions']]))
        return out

    def font_stats(self):
        st = {}
        for t in self.text_list():
            k = round(t['size'], 1)
            st[k] = st.get(k, 0) + len(t['text'])
        return dict(sorted(st.items()))
