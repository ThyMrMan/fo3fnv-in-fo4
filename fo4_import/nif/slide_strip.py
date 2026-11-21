"""A projector's film strip as one node per slide it stops on.

FO3/FNV projectors (vprojectorgoatslides01.nif) slide one long strip of flat
unlit slides past the screen: each sequence moves the strip node so a slide
sits at the screen while the rest of the strip hides behind the wall. FO4
draws none of such a mesh, so the strip becomes one node per stop holding
the triangles at the screen then (_window), each sequence showing its end
stop's node (scale 1) and hiding the others (scale 0).

See: docs/fork/fo4_pipeline.md#slide-strips
"""

import copy

import numpy as np

from fo4_import.nif.blocks import NONE
from fo4_import.nif.file import NifFile

#: How far a value may stray and still count as unchanged: a flat strip's depth, an axis it does not slide on.
EPSILON = 1e-3
#: Stops closer than this (game units) are one stop.
SAME_STOP = 0.1
#: The most a flat strip's vertices may differ in depth (game units): the GOAT strip's export rounding is 0.0011.
FLAT = 0.01


def restack(nif: NifFile, manager: int) -> int:
    """Rebuild each film strip node the sequences of NiControllerManager `manager` slide (_stops); how many."""
    fields = nif.blocks[manager][1]
    seqs = [nif.blocks[i][1] for i in fields['sequences']]
    palette = nif.blocks[fields['palette']][1]
    done = 0
    for name, node in list(palette['objects']):
        tracks = [(seq, block) for seq in seqs for block in seq['blocks']
                  if block['node'] >= 0 and nif.strings[block['node']] == name]
        found = _plan(nif, node, tracks)
        if found:
            _rebuild(nif, node, tracks, *found, palette)
            done += 1
    return done


def _plan(nif: NifFile, node: int, tracks: list) -> 'tuple | None':
    """({stop offset: [kept triangle mask per shape]}, the rest stop (0, 0) first; [(start stop, end stop)] per
    track) of a film strip node. A track starts at the stop showing what its first key shows, else its end stop.
    None unless every track only slides it in its flat unlit shapes' plane, they reach past the window at rest,
    every stop shows a triangle and the stops need a shape for each of the node's (_rebuild reuses every block)."""
    if node < 0 or nif.blocks[node][0] != 'NiNode':
        return None
    fields = nif.blocks[node][1]
    spans = [_span(nif, block) for _, block in tracks]
    geometry = _flat_unlit(nif, fields)
    if not tracks or None in spans or geometry is None:
        return None
    rest = np.array(fields['translation'], dtype=np.float64)
    if any(abs(key[2] - rest[2]) > EPSILON for span in spans for key in span):
        return None
    window = _window(geometry, -rest[:2])
    offsets = [[_stop(np.array(key[:2]) - rest[:2]) for key in span] for span in spans]
    plan = {offset: _masks(geometry, offset, window) for offset in dict.fromkeys([(0.0, 0.0)] + [e for _, e in offsets])}
    if window is None or all(mask.all() for mask in plan[(0.0, 0.0)]):
        return None
    used = np.array([[mask.any() for mask in masks] for masks in plan.values()])
    if not used.any(axis=1).all() or used.sum() < len(geometry):
        return None
    return plan, [(_showing(plan, _masks(geometry, start, window)) or end, end) for start, end in offsets]


def _masks(geometry: list, offset: tuple, window: 'tuple | None') -> list:
    """Each shape's _inside mask at stop `offset`."""
    return [_inside(pos, tris, offset, window) for pos, tris in geometry]


def _showing(plan: dict, masks: list) -> 'tuple | None':
    """The stop of `plan` whose masks equal `masks`; None for none."""
    return next((stop for stop, kept in plan.items() if all(map(np.array_equal, kept, masks))), None)


def _stop(offset: np.ndarray) -> tuple:
    """A stop's offset as a key: rounded to SAME_STOP."""
    return tuple(float(v) for v in np.round(offset / SAME_STOP) * SAME_STOP)


def _span(nif: NifFile, block: dict) -> 'tuple | None':
    """The first and last translation keys of a controlled block's transform track; None unless it only moves
    its node."""
    kind, interp = nif.blocks[block['interpolator']] if block['interpolator'] >= 0 else ('', {})
    if kind != 'NiTransformInterpolator' or interp['data'] < 0:
        return None
    data = nif.blocks[interp['data']][1]
    keys = data['translations']['keys']
    turns = [k[1] - 1 for k in data['rotations']] + [k[1] for g in data['xyz'] for k in g['keys']]
    grows = [k[1] - 1 for k in data['scales']['keys']]
    if not keys or any(abs(v) > EPSILON for v in turns + grows):
        return None
    return keys[0][1:4], keys[-1][1:4]


def _flat_unlit(nif: NifFile, fields: dict) -> 'list | None':
    """[(positions, triangles)] of a node holding only effect-shaded shapes in one flat plane, all blended or all
    not; None otherwise."""
    blended = {nif.blocks[c][1].get('alpha_property', NONE) >= 0 for c in fields['children']}
    if fields['scale'] != 1.0 or len(blended) != 1:
        return None
    out = []
    for child in fields['children']:
        kind, shape = nif.blocks[child]
        if kind != 'BSTriShape' or shape['shader'] < 0 or nif.blocks[shape['shader']][0] != 'BSEffectShaderProperty':
            return None
        out.append((np.array([v['position'] for v in shape['vertices']], dtype=np.float64),
                    np.array(shape['triangles'], dtype=np.int64).reshape(-1, 3)))
    depths = np.concatenate([pos[:, 2] for pos, _ in out])
    return out if depths.size and np.ptp(depths) <= FLAT else None


def _window(geometry: list, at: np.ndarray) -> 'tuple | None':
    """(low, high) corners of the triangles covering point `at` (the screen's centre, node space); None for none."""
    covering = [pos[t][:, :2] for pos, tris in geometry for t in tris if _covers(pos[t][:, :2], at)]
    if not covering:
        return None
    points = np.concatenate(covering)
    return points.min(axis=0), points.max(axis=0)


def _covers(corners: np.ndarray, at: np.ndarray) -> bool:
    """Whether 2D triangle `corners` holds point `at`, edges included."""
    a, b, c = corners
    sides = [(q[0] - p[0]) * (at[1] - p[1]) - (q[1] - p[1]) * (at[0] - p[0]) for p, q in ((a, b), (b, c), (c, a))]
    return all(s >= -EPSILON for s in sides) or all(s <= EPSILON for s in sides)


def _inside(pos: np.ndarray, tris: np.ndarray, offset: tuple, window: 'tuple | None') -> np.ndarray:
    """Mask of the triangles whose centre, moved by `offset`, lies in `window` (none without one)."""
    if window is None or not len(tris):
        return np.zeros(len(tris), dtype=bool)
    centres = pos[tris].mean(axis=1)[:, :2] + np.array(offset)
    return np.all((centres >= window[0] - EPSILON) & (centres <= window[1] + EPSILON), axis=1)


def _rebuild(nif: NifFile, node: int, tracks: list, plan: dict, moves: list, palette: dict) -> None:
    """Replace strip `node`'s shapes with its rest stop's, add a hidden node per other stop and key every track's
    sequence to go from its start stop to its end stop (`moves`)."""
    fields = nif.blocks[node][1]
    name = nif.strings[fields['name']]
    sources = [_snapshot(nif, i) for i in fields['children']]
    free = list(fields['children'])
    stops = {}
    for offset, masks in plan.items():
        shapes = [_shape(nif, src, mask, offset, free) for src, mask in zip(sources, masks) if mask.any()]
        stops[offset] = node if not stops else _stop_node(nif, node, f'{name}:{len(stops)}', shapes, palette)
        nif.blocks[stops[offset]][1]['children'] = shapes
    for (seq, block), (start, end) in zip(tracks, moves):
        _show(nif, seq, block, stops, (stops[start], stops[end]), fields['translation'])


def _snapshot(nif: NifFile, index: int) -> tuple:
    """Copies of shape `index`'s fields, its shader and its alpha block (or None)."""
    shape = copy.deepcopy(nif.blocks[index][1])
    return (shape, *(copy.deepcopy(nif.blocks[shape[k]]) if shape[k] >= 0 else None
                     for k in ('shader', 'alpha_property')))


def _shape(nif: NifFile, source: tuple, mask: np.ndarray, offset: tuple, free: list) -> int:
    """A BSTriShape of `_snapshot` `source`'s `mask` triangles moved by `offset`, with its shader and alpha, in the
    next `free` shape's blocks or new ones; its index."""
    fields, shader, alpha = source
    tris = np.array(fields['triangles'], dtype=np.int64).reshape(-1, 3)[mask]
    used, local = np.unique(tris, return_inverse=True)
    verts = [dict(fields['vertices'][i], position=_moved(fields['vertices'][i]['position'], offset)) for i in used]
    pos = np.array([v['position'] for v in verts])
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
    shape = dict(fields, vertices=verts, triangles=[tuple(map(int, t)) for t in local.reshape(-1, 3)],
                 bound=(*map(float, centre), float(np.linalg.norm(pos - centre, axis=1).max())))
    old = nif.blocks[free[0]][1] if free else {'shader': NONE, 'alpha_property': NONE}
    shape['shader'] = _put(nif, old['shader'], shader)
    shape['alpha_property'] = _put(nif, old['alpha_property'], alpha)
    if not free:
        nif.blocks.append(('BSTriShape', shape))
        return len(nif.blocks) - 1
    nif.blocks[free[0]] = ('BSTriShape', shape)
    return free.pop(0)


def _moved(position: tuple, offset: tuple) -> tuple:
    """`position` moved by 2D `offset`."""
    return position[0] + offset[0], position[1] + offset[1], position[2]


def _put(nif: NifFile, slot: int, block: 'tuple | None') -> int:
    """A copy of `block` at index `slot`, or appended when `slot` is NONE; its index (NONE for no block)."""
    if block is None:
        return NONE
    if slot < 0:
        nif.blocks.append(copy.deepcopy(block))
        return len(nif.blocks) - 1
    nif.blocks[slot] = copy.deepcopy(block)
    return slot


def _copy_block(nif: NifFile, index: int) -> int:
    """A copy of block `index` appended (NONE stays NONE); the copy's index."""
    if index < 0:
        return NONE
    nif.blocks.append(copy.deepcopy(nif.blocks[index]))
    return len(nif.blocks) - 1


def _stop_node(nif: NifFile, node: int, name: str, shapes: list, palette: dict) -> int:
    """A hidden (scale 0) copy of `node` named `name` beside it, holding `shapes`; in `palette`. Its index."""
    fields = nif.blocks[node][1]
    index = len(nif.blocks)
    nif.blocks.append(('NiNode', dict(fields, name=nif.string(name), extra=[], controller=NONE, scale=0.0,
                                      children=shapes)))
    parent = next(b for kind, b in nif.blocks if node in b.get('children', ()))
    parent['children'].insert(parent['children'].index(node) + 1, index)
    palette['objects'].append((name, index))
    return index


def _show(nif: NifFile, seq: dict, block: dict, stops: dict, shown: tuple, rest: tuple) -> None:
    """Make `seq`'s track `block` hold the strip at `rest` and add one per other stop node, each scaled from 1 at
    the sequence's start when it is `shown`'s first node to 1 at its stop when it is the second (0 otherwise)."""
    span = (seq['start'], seq['stop'])
    for index in dict.fromkeys(stops.values()):
        track = block if index == stops[(0.0, 0.0)] else _new_track(nif, block, index)
        seq['blocks'] += [] if track is block else [track]
        data = nif.blocks[nif.blocks[track['interpolator']][1]['data']][1]
        data.update(translations={'kind': 1, 'keys': [(t, *rest) for t in span]},
                    scales={'kind': 1, 'keys': [(t, float(index == at)) for t, at in zip(span, shown)]})


def _new_track(nif: NifFile, block: dict, node: int) -> dict:
    """A copy of controlled block `block` (its interpolator and data copied) driving stop node `node`, added to
    its sequence's controller targets."""
    interp = copy.deepcopy(nif.blocks[block['interpolator']])
    interp[1]['data'] = _copy_block(nif, interp[1]['data'])
    nif.blocks.append(interp)
    track = dict(block, interpolator=len(nif.blocks) - 1, node=nif.blocks[node][1]['name'])
    targets = nif.blocks[block['controller']][1]['targets']
    targets += [] if node in targets else [node]
    return track
