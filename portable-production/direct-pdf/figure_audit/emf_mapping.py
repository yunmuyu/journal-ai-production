"""Bounded EMF mapping and clip state updates; unsupported operations stay unknown."""
from __future__ import annotations
import struct
from .errors import AuditInputError
from .emf_geometry import _exclude_clip, _intersect_clip, _offset_clip, _scale_extent


def apply_mapping_clip(record_type, payload, state):
    if record_type == 115:
        state['coordinate_status'] = 'unknown'
        state['clip_status'] = 'unknown'
    elif record_type == 28:
        state['meta_clip_unknown'] = True
        state['clip_status'] = 'unknown'
    elif record_type == 67:
        state['clip_status'] = 'unknown'
    elif record_type == 75:
        if len(payload) < 16:
            raise AuditInputError('truncated EMF clip region record')
        length, mode = struct.unpack('<II', payload[8:16])
        if length > len(payload)-16:
            raise AuditInputError('truncated EMF clip region data')
        if (length, mode) == (0, 5):
            state['clip_regions'] = ()
            state['clip_exclusions'] = ()
            state['clip_status'] = 'unknown' if state['meta_clip_unknown'] else 'partial'
        else:
            state['clip_status'] = 'unknown'
    elif record_type == 17:
        mode = struct.unpack('<I', payload[8:12])[0]
        if mode not in (1, 2, 3, 4, 5, 6, 8):
            raise AuditInputError('unsupported EMF mapping mode')
        if mode != state['map_mode']:
            if mode == 1:
                state['win_ext'] = (1, 1)
                state['vp_ext'] = (1, 1)
            elif mode in (2, 3, 4, 5, 6):
                factor, divisor = {2:(10,1),3:(100,1),4:(1000,254),5:(10000,254),6:(14400,254)}[mode]
                mm_x, mm_y = state['dev_mm']
                state['win_ext'] = ((mm_x*factor + divisor//2)//divisor,
                                    (mm_y*factor + divisor//2)//divisor)
                state['vp_ext'] = (state['dev'][0], -state['dev'][1])
        state['map_mode'] = mode
    elif record_type in (29, 30):
        rect = struct.unpack('<iiii', payload[8:24])
        (_exclude_clip if record_type == 29 else _intersect_clip)(state, rect)
    elif record_type == 26:
        _offset_clip(state, struct.unpack('<ii', payload[8:16]))
    elif record_type in (31, 32):
        _scale_extent(state, 'vp_ext' if record_type == 31 else 'win_ext', struct.unpack('<iiii', payload[8:24]))
    elif record_type in (9, 11):
        ex, ey = struct.unpack('<ii', payload[8:16])
        if state['map_mode'] == 8 and ex and ey:
            state['win_ext' if record_type == 9 else 'vp_ext'] = (ex, ey)
    elif record_type in (10, 12):
        state['win_org' if record_type == 10 else 'vp_org'] = struct.unpack('<ii', payload[8:16])
    else:
        return False
    return True
