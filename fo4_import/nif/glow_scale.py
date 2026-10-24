"""FNV glow multipliers as Fallout 4's: each kind of glow ranked within vanilla's own range for that kind.

FNV and FO4 light glows differently, so FNV's numbers are not carried as
values. Each kind maps by a power curve through both games' median and 90th
percentile, clamped to vanilla's full range: FO4 = median_fo4 x
(FNV / median_fnv)^s. A neon overlay (an alpha-tested glow drawn as an
additive effect) follows vanilla's additive glow materials; a lit glow
surface (a window) follows vanilla's lit glow materials. FO4's bloom then
makes the bright ones glow.

See: docs/fork/fo4_look.md#emissive
"""

import math

#: Per kind: (FNV median, FNV 90th percentile, FO4 median, FO4 90th, FO4 min, FO4 max). FNV: 14,909 meshes' shapes
#: (1,224 alpha-tested glows, 1,853 lit glows); FO4 + DLC: 24 additive and 150 lit glow material families.
CURVES = {'neon': (1.1, 2.0, 1.8, 5.0, 0.39, 9.0),
          'lit': (1.0, 10.0, 0.8, 1.7, 0.05, 10.0)}


def fo4_glow(kind: str, fnv: float) -> float:
    """FO4's multiplier for FNV glow multiplier `fnv` of `kind` ('neon' or 'lit'); 0 stays 0."""
    if fnv <= 0:
        return 0.0
    fnv_mid, fnv_high, mid, high, low, top = CURVES[kind]
    power = math.log(high / mid) / math.log(fnv_high / fnv_mid)
    return min(top, max(low, mid * (fnv / fnv_mid) ** power))


def slope(kind: str, fnv: float) -> float:
    """d fo4_glow / d fnv at `fnv` (by a small step), for a key's tangents."""
    step = max(1e-3, fnv * 1e-3)
    return (fo4_glow(kind, fnv + step) - fo4_glow(kind, max(0.0, fnv - step))) / (step + min(step, fnv))


def map_keys(nif, interp: int, kind: str, peak: float = 1.0) -> None:
    """Map float interpolator `interp`'s keys (values, and quadratic tangents) through fo4_glow, divided by the
    shape's brightest texel `peak`, so the curve's value is what that texel shows (as a white one would)."""
    if interp < 0 or nif.blocks[interp][1].get('data', -1) < 0:
        return
    group = nif.blocks[nif.blocks[interp][1]['data']][1]['keys']
    scale = 1.0 / max(peak, 0.05)
    out = []
    for key in group['keys']:
        rest = list(key[2:])
        if group['kind'] == 2:
            rest = [scale * slope(kind, key[1]) * t for t in rest]
        out.append((key[0], scale * fo4_glow(kind, key[1]), *rest))
    group['keys'] = out
