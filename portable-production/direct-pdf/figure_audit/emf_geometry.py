"""EMF color and affine coordinate helpers."""
from .errors import AuditInputError

def _crd(color):
    """COLORREF 0x00BBGGRR → (r,g,b) 0..1"""
    r = color & 0xFF
    g = (color >> 8) & 0xFF
    b = (color >> 16) & 0xFF
    return (r / 255.0, g / 255.0, b / 255.0)


def _xform(pt, m):
    x, y = pt
    m11, m12, m21, m22, dx, dy = m
    return (m11 * x + m21 * y + dx, m12 * x + m22 * y + dy)


IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

def _device_point(pt, state):
    """Apply world-to-page followed by explicit text/anisotropic page-to-device mapping."""
    x, y = _xform(pt, state['m'])
    wx, wy = state.get('win_org', (0, 0))
    vx, vy = state.get('vp_org', (0, 0))
    if state.get('map_mode', 1) == 8:
        ex, ey = state.get('win_ext', (1, 1))
        dx, dy = state.get('vp_ext', (1, 1))
        if ex == 0 or ey == 0:
            raise AuditInputError('zero window extent')
        return ((x - wx) * dx / ex + vx, (y - wy) * dy / ey + vy)
    if state.get('map_mode', 1) != 1:
        raise AuditInputError('unsupported EMF mapping mode')
    return (x - wx + vx, y - wy + vy)


def _mul(a, b):
    """a 之后应用 b（b 左乘）"""
    a11, a12, a21, a22, adx, ady = a
    b11, b12, b21, b22, bdx, bdy = b
    return (a11 * b11 + a12 * b21, a11 * b12 + a12 * b22,
            a21 * b11 + a22 * b21, a21 * b12 + a22 * b22,
            adx * b11 + ady * b21 + bdx, adx * b12 + ady * b22 + bdy)
