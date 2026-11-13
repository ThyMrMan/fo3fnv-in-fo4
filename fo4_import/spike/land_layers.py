"""FNV LAND texture layers as Fallout 4's: per quadrant, every texture's share of each vertex, blended across borders.

FNV draws a quadrant's base texture under alpha layers painted over each
other, and switches base at a quadrant border. FO4's shares sum to at most
1 per vertex and only blend inside a quadrant, so a base change showed as a
straight seam. Here each quadrant becomes a mix of shares (the base taking
what the painted layers leave), and every vertex shared by several
quadrants, inside a cell or across cells, takes their average mix.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import hashlib
import math

import numpy as np

from fo4_import.pipeline.work_cache import cached

#: Vertices of a quadrant (17 x 17, row-major from the bottom-left).
SIDE = 17
QUAD_POINTS = SIDE * SIDE
#: A quadrant's border vertices: the ones it shares with its neighbours.
EDGE = [p for p in range(QUAD_POINTS) if p % SIDE in (0, SIDE - 1) or p // SIDE in (0, SIDE - 1)]
#: Vertices along a cell side: two quadrants of 16 steps.
CELL_STEPS = 2 * (SIDE - 1)
#: Textures a quadrant keeps: FO4 draws 4 at a time, the base first, and textures past the first 4 draw differently.
DRAWN = 4
#: The LAND fields quadrant_mix reads: the layer count and every layer's.
LAYER_FIELDS = ('LayerCount', 'Layer[')
#: The work-cache site of land_textures().
SITE = 'land textures'
#: The shares of a texture blend_borders brings to a quadrant at no vertex yet: one read-only array shared by all.
ZERO = np.zeros(QUAD_POINTS)
ZERO.setflags(write=False)


def layer_weights(layers: list) -> list:
    """FNV's alpha layers of a quadrant ({position: opacity}, painted bottom first, each over those below) as FO4's
    blend weights (vanilla's sum to at most 1, the base taking the rest): each layer's opacity times what the layers
    above it leave showing."""
    showing, out = {}, []
    for layer in reversed(layers):
        out.append({pos: op * showing.get(pos, 1.0) for pos, op in layer.items()})
        showing.update({pos: showing.get(pos, 1.0) * (1 - op) for pos, op in layer.items()})
    return out[::-1]


def quadrant_mix(rec: dict) -> dict:
    """{quadrant: {FNV LTEX FormID ('' for the default texture): QUAD_POINTS shares}} of FNV LAND `rec`: its painted
    alpha layers' shares, its base (default when missing) taking the rest."""
    base, alpha = {}, {}
    for i in range(int(rec.get('LayerCount', 0))):
        key = f'Layer[{i}]'
        if rec[f'{key}.Type'] == 'BASE':
            base.setdefault(int(rec[f'{key}.BTXT.Quadrant']), _texture(rec[f'{key}.BTXT.Texture']))
        else:
            alpha.setdefault(int(rec[f'{key}.ATXT.Quadrant']), []).append((int(rec[f'{key}.ATXT.Layer']), key))
    return {quad: _mix(rec, base.get(quad, ''), [key for _, key in sorted(alpha.get(quad, []))]) for quad in range(4)}


def _mix(rec: dict, base: str, keys: list) -> dict:
    """One quadrant's {texture: shares}: alpha layers `keys` (FNV order) over `base`."""
    shares = layer_weights([{int(rec[f'{key}.VT[{v}].Pos']): float(rec[f'{key}.VT[{v}].Opacity'])
                             for v in range(int(rec[f'{key}.VTXTCount']))} for key in keys])
    mix = {base: np.ones(QUAD_POINTS)}
    for key, weights in zip(keys, shares):
        grid = mix.setdefault(_texture(rec[f'{key}.ATXT.Texture']), np.zeros(QUAD_POINTS))
        for pos, weight in weights.items():
            grid[pos] += weight
            mix[base][pos] -= weight
    return mix


def _texture(fnv: str) -> str:
    """An FNV layer's LTEX FormID, '' for texture 0 (the default)."""
    return fnv if int(fnv, 16) else ''


def kept_textures(mix: dict, grassy: frozenset = frozenset()) -> list:
    """The DRAWN textures a quadrant `mix` keeps, heaviest first; a grassy texture past them, painted inside the
    quadrant (not only on its border, where blend_borders brings a neighbour's), replaces the lightest kept one
    that is neither the base nor grassy, so the ground still grows FNV's grass.

    See: docs/fork/fo4_look.md#grass-ground
    """
    order = sorted(mix, key=lambda t: -mix[t].sum())
    kept = order[:DRAWN]
    for texture in (t for t in order[DRAWN:] if t in grassy and np.delete(mix[t], EDGE).any()):
        spare = [i for i in range(len(kept) - 1, 0, -1) if kept[i] not in grassy]
        if spare:
            kept[spare[0]] = texture
    return kept


def limit_textures(mixes: dict, grassy: frozenset = frozenset()) -> dict:
    """{cell grid: {quadrant: [(texture, shares)], heaviest first}}: each quadrant of blend_borders' `mixes` keeps its
    kept_textures (`grassy`: the textures that grow grass); a shared vertex keeps only those every quadrant on it
    keeps, so both sides still match. Shares are renormalized per vertex.

    See: docs/fork/fo4_spikes.md#spike-4-exterior
    """
    kept = {(grid, q): kept_textures(mix, grassy) for grid, quads in mixes.items() for q, mix in quads.items()}
    totals = {(grid, q, t): mixes[grid][q][t].sum() for (grid, q), textures in kept.items() for t in textures}
    allowed = {key: [set(textures)] * QUAD_POINTS for key, textures in kept.items()}
    fill = {key: [textures[0]] * QUAD_POINTS for key, textures in kept.items()}
    for members in _shared(mixes).values():
        common = set.intersection(*(set(kept[(grid, q)]) for grid, q, _ in members))
        heaviest = max(sorted(common), key=lambda t: sum(totals[g, q, t] for g, q, _ in members), default=None)
        for grid, q, pos in members:
            allowed[(grid, q)][pos] = common or set(kept[(grid, q)])
            fill[(grid, q)][pos] = heaviest or kept[(grid, q)][0]
    out = {}
    for (grid, q), textures in kept.items():
        mix, ok = mixes[grid][q], allowed[(grid, q)]
        shares = np.array([np.where([t in ok[p] for p in range(QUAD_POINTS)], mix[t], 0.0)
                           for t in textures]).clip(0.0, 1.0)
        for p in np.flatnonzero(shares.sum(0) <= 0):
            shares[textures.index(fill[(grid, q)][p]), p] = 1.0
        out.setdefault(grid, {})[q] = list(zip(textures, _renormalized(shares, [t in grassy for t in textures])))
    return out


def _renormalized(shares: np.ndarray, grows: list) -> np.ndarray:
    """`shares` (textures x vertices, heaviest texture first) summing to 1 per vertex: grassy rows (`grows`) keep
    FNV's share, the others scale to fill the rest; where none has a share the heaviest non-grassy row takes it."""
    grows = np.array(grows, bool)
    out = shares.copy()
    if grows.all() or not grows.any():
        return out / out.sum(0)
    grass = np.minimum(out[grows].sum(0), 1.0)
    other = out[~grows].sum(0)
    out[np.flatnonzero(~grows)[0], other <= 0] = 1.0
    other = out[~grows].sum(0)
    out[~grows] *= (1.0 - grass) / other
    return out / out.sum(0)


def _shared(mixes: dict) -> dict:
    """{world vertex: [(cell grid, quadrant, position)]} for the border vertices of `mixes`' quadrants."""
    shared = {}
    for (cx, cy), quads in mixes.items():
        for quad in quads:
            for pos in EDGE:
                x = cx * CELL_STEPS + quad % 2 * (SIDE - 1) + pos % SIDE
                y = cy * CELL_STEPS + quad // 2 * (SIDE - 1) + pos // SIDE
                shared.setdefault((x, y), []).append((cx, cy, quad, pos))
    return {k: [((cx, cy), q, p) for cx, cy, q, p in v] for k, v in shared.items() if len(v) > 1}


def blend_borders(mixes: dict) -> dict:
    """Give every vertex shared by several quadrants of {cell grid: quadrant_mix} their average mix, so a texture
    change at a quadrant or cell border fades over one vertex step; `mixes` is changed and returned. A texture a
    quadrant gains with a share of +0 everywhere keeps ZERO, not an array of its own.
    See: docs/fork/fo4_build_speed.md#land-memory
    """
    for points in _shared(mixes).values():
        members = [(mixes[grid][q], pos) for grid, q, pos in points]
        textures = sorted({texture for mix, _ in members for texture in mix})
        average = {t: sum(mix[t][pos] for mix, pos in members if t in mix) / len(members) for t in textures}
        plus_zero = {t for t, share in average.items() if share == 0 and math.copysign(1.0, share) > 0}
        for mix, pos in members:
            for texture, share in average.items():
                shares = mix.setdefault(texture, ZERO)
                if shares is ZERO and texture in plus_zero:
                    continue
                if shares is ZERO:
                    shares = mix[texture] = np.zeros(QUAD_POINTS)
                shares[pos] = share
    return mixes


def land_textures(lands: dict, grassy: frozenset = frozenset()) -> dict:
    """limit_textures(blend_borders()) of the quadrant_mix of each grid's FNV LAND in `lands` ({grid: record or
    None}), kept in the work cache by the fields it reads (LAYER_FIELDS) and `grassy`.
    See: docs/fork/fo4_build_speed.md#land-cache
    """
    digest = hashlib.sha1(repr(sorted(grassy)).encode())
    for grid, land in sorted(lands.items()):
        if land:
            digest.update(repr((grid, [(k, v) for k, v in land.items() if k.startswith(LAYER_FIELDS)])).encode())
    mixes = {grid: land for grid, land in lands.items() if land}
    return cached(SITE, __name__, (digest.digest(),), lambda: limit_textures(
        blend_borders({grid: quadrant_mix(land) for grid, land in mixes.items()}), grassy))
