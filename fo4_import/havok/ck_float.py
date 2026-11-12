"""The Creation Kit's float32 math for AnimationOffsets root keys, in its operation order, bit for bit.

rcpps and rsqrtps are approximate instructions whose last bits differ between CPU vendors; rcp and rsqrt model
AMD Zen's (the CPU our CK runs on), from tables of the top 12 mantissa bits. hkQuaternion's sincos and slerp use the
CK's own constants.

See: docs/fork/research/anim_text_data.md#ck-math
"""

import base64
import struct
import zlib

import numpy as np

from fo4_import.havok.ck_float_tables import RCP, RSQRT_EVEN, RSQRT_ODD

F = np.float32
ZERO, HALF, ONE, TWO, THREE = F(0), F(0.5), F(1), F(2), F(3)


def _table(text: str) -> np.ndarray:
    """A result table's bits, one per top-12 mantissa bits."""
    return np.frombuffer(zlib.decompress(base64.b64decode(text)), '<u2').astype(np.uint32) * 2048 + 0x3e800000


_RCP, _RSQRT_EVEN, _RSQRT_ODD = _table(RCP), _table(RSQRT_EVEN), _table(RSQRT_ODD)


def bits(x) -> int:
    """The bits of `x` as a float32."""
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def flt(u: int):
    """The float32 with bits `u`."""
    return F(struct.unpack('<f', struct.pack('<I', int(u) & 0xFFFFFFFF))[0])


def rcp(x):
    """rcpps of a normal, finite `x` on AMD Zen."""
    u = bits(x)
    exponent = (u >> 23) & 0xFF
    return flt((int(_RCP[(u >> 11) & 0xFFF]) - ((exponent - 127) << 23)) | (u & 0x80000000))


def rsqrt(x):
    """rsqrtps of a normal, positive `x` on AMD Zen."""
    u = bits(x)
    exponent, mantissa = ((u >> 23) & 0xFF) - 127, (u >> 11) & 0xFFF
    if exponent % 2 == 0:
        return flt(int(_RSQRT_EVEN[mantissa]) - ((exponent // 2) << 23))
    return flt(int(_RSQRT_ODD[mantissa]) - (((exponent - 1) // 2) << 23))


def recip(x):
    """Havok's refined reciprocal of `x`: one Newton step on rcpps."""
    r = rcp(x)
    return (TWO - x * r) * r


def norm_factor(s):
    """Havok's refined 1/sqrt(`s`): one Newton step on rsqrtps; 0 when `s` is not positive."""
    if not s > ZERO:
        return ZERO
    r = rsqrt(s)
    return (THREE - (s * r) * r) * (r * HALF)


def hsum(v: list):
    """The CK's horizontal add of four lanes."""
    return (v[1] + v[3]) + (v[0] + v[2])


#: 4/pi and the three-part pi/4 reduction (sse_mathfun constants in the CK).
FOPI, DP1, DP2, DP3 = flt(0x3fa2f983), flt(0xbf490000), flt(0xb97da000), flt(0xb3222169)
#: The sine and cosine polynomials.
S0, S1, S2, C0, C1, C2 = (flt(u) for u in (0xb94ca1f9, 0x3c08839e, 0xbe2aaaa3, 0x37ccf5ce, 0xbab6061a, 0x3d2aaaa5))


def _reduce(x) -> tuple:
    """(octant, sine polynomial, cosine polynomial) of a non-negative `x`."""
    j = (int(np.trunc(x * FOPI)) + 1) & ~1
    y = F(j)
    x = ((DP1 * y + x) + DP2 * y) + DP3 * y
    z = x * x
    cosine = ((((C0 * z + C1) * z + C2) * z) * z - z * HALF) + ONE
    sine = ((S0 * z + S1) * z + S2) * z * x + x
    return j & 0xFFFFFFFF, sine, cosine


def _clamp(v):
    """`v` capped at 1."""
    return v if v < ONE else ONE


def _sign(octant: int) -> int:
    """The sign bit an octant's bit 2 sets."""
    return ((octant & 4) << 29) & 0xFFFFFFFF


def sincos(x) -> tuple:
    """(sin, cos) of `x` as hkQuaternion::setAxisAngle computes them."""
    sign = bits(x) & 0x80000000
    j, sine, cosine = _reduce(abs(F(x)))
    if j & 2:
        s, c = cosine + ZERO, sine + ZERO
    else:
        s, c = ZERO + sine, (sine - sine) + cosine
    return flt(bits(_clamp(s)) ^ sign ^ _sign(j)), flt(bits(_clamp(c)) ^ _sign(~(j - 2)))


def sin(x):
    """sin(`x`) as setSlerp's inline sincos computes it (a select, not an add)."""
    j, sine, cosine = _reduce(abs(x))
    return flt(bits(_clamp(cosine if j & 2 else sine)) ^ (bits(x) & 0x80000000) ^ _sign(j))


def axis_angle(axis: tuple, angle) -> tuple:
    """The quaternion (x, y, z, w) turning `angle` radians about `axis`."""
    s, c = sincos(F(angle) * HALF)
    return s * F(axis[0]), s * F(axis[1]), s * F(axis[2]), c


#: setSlerp's asin polynomial, pi/2, the dot above which it lerps (0.999), and the small-angle cut (1e-4).
ASIN = [flt(u) for u in (0x3d2cb352, 0x3cc617e3, 0x3d3a3ec7, 0x3d9980f6, 0x3e2aaae4)]
PI_2, LERP_DOT, SMALL = flt(0x3fc90fdb), flt(0x3f7fbe77), flt(0x38d1b717)


def _acos(d):
    """The angle whose cosine is `d` (|d| < 1), by setSlerp's asin polynomial."""
    x = _clamp(abs(d)) if not np.isnan(d) else d
    big = HALF < x
    z, s = ((ONE - x) * HALF, None) if big else (x * x, x)
    s = np.sqrt(z, dtype=F) if big else s
    p = ((((ASIN[0] * z + ASIN[1]) * z + ASIN[2]) * z + ASIN[3]) * z + ASIN[4]) * z
    r = p * s + s
    a = x if x < SMALL else (PI_2 - (r + r)) if big else r
    return PI_2 - flt(bits(a) ^ (bits(d) & 0x80000000))


def slerp(q0: tuple, q1: tuple, t) -> list:
    """hkQuaternion::setSlerp of `q0` to `q1` at `t`, normalized."""
    t = F(t)
    d = hsum([q1[k] * q0[k] for k in range(4)])
    flip = bits(d) & 0x80000000 if d < ZERO else 0
    d = flt(bits(d) ^ flip)
    if LERP_DOT > d:
        theta = _acos(d)
        inverse = norm_factor(ONE - d * d)
        w0, w1 = sin(theta - theta * t) * inverse, sin(theta * t) * inverse
    else:
        w0, w1 = ONE - t, t
    w1 = flt(bits(w1) ^ flip)
    v = [w1 * q1[k] + q0[k] * w0 for k in range(4)]
    n = norm_factor(hsum([c * c for c in v]))
    return [n * c for c in v]
