"""A mod's own FNV hair mesh, worn on FO4's head (nif.headgear), as an FO4 hair head part's mesh.

Vanilla FO4 hairs split their triangles into two sub-segments: slot 30
(hair top, hidden under a hat) first, then slot 31 (the rest). A converted
hair's triangles take the split of the vanilla hair triangles nearest them
(majority of FIELD_NEIGHBOURS centres, both sexes' hairs pooled; 90.5%
agreement leaving each vanilla hair out in turn). An FNV hair authored with a
NoHat and a Hat shape (what FNV draws bareheaded and under a hat) needs no vote:
both become one shape, NoHat the top, Hat the rest. The shapes take vanilla
hair's commonest NiAlphaProperty (alpha-tested, 62 of its 92) and the hair material
made for the NPC's colour.

See: docs/fork/fo4_facegen_plan.md#own-heads
"""

import struct
from functools import cache

import numpy as np
from scipy.spatial import cKDTree

from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE, Reader, pack_tri_shape, read_tri_shape
from fo4_import.nif.headgear import segments, shape_arrays

#: Vanilla hair meshes, and names marking ones that are no head hair (FaceBones copies, hairlines, beards).
HAIR_FOLDER = 'meshes\\actors\\character\\characterassets\\hair\\'
NOT_HAIR = ('facebones', 'hairline', 'beard')
#: Slots of a hair's top (hidden under hats) and the rest; vanilla hair centres a converted triangle polls.
HAIR_TOP, HAIR_REST, FIELD_NEIGHBOURS = 30, 31, 25
#: Vanilla hair's commonest NiAlphaProperty (flags, threshold).
HAIR_ALPHA = (4844, 90)
#: FNV hair's shapes drawn bareheaded and under a hat (lowercase); most vertices one shape indexes.
NO_HAT, HAT, MAX_VERTICES = 'nohat', 'hat', 0xFFFF


def sub_segments(raw: bytes) -> tuple:
    """(shape, [(first triangle, triangles, slot)]) of a BSSubIndexTriShape block's sub-segments; [] when its
    shared data has cuts (not a plain head item)."""
    reader = Reader(raw)
    shape = read_tri_shape(reader)
    tail = raw[reader.pos:]
    _, n_segments, _ = struct.unpack_from('<3I', tail, 0)
    pos, subs = 12, []
    for _ in range(n_segments):
        n_sub = struct.unpack_from('<4I', tail, pos)[3]
        subs += [struct.unpack_from('<2I', tail, pos + 16 + 16 * i) for i in range(n_sub)]
        pos += 16 + 16 * n_sub
    n_shared, total = struct.unpack_from('<2I', tail, pos)
    data = [struct.unpack_from('<3I', tail, pos + 8 + 4 * n_shared + 12 * i) for i in range(total)]
    if any(cuts for _, _, cuts in data):
        return shape, []
    return shape, [(start // 3, count, slot) for (start, count), (slot, _, _) in zip(subs, data[n_shared:])]


@cache
def hat_field(archives) -> tuple:
    """(tree over vanilla hair triangle centres, whether each is in the hair top) of `archives`' split hairs."""
    centres, top = [], []
    for name in archives.names(HAIR_FOLDER):
        if not name.endswith('.nif') or any(word in name for word in NOT_HAIR):
            continue
        for kind, raw in nif_file.read(archives.read(name)).blocks:
            shape, subs = sub_segments(raw) if kind == 'BSSubIndexTriShape' else (None, [])
            if {slot for _, _, slot in subs} != {HAIR_TOP, HAIR_REST}:
                continue
            points, _, _, tris = shape_arrays(shape)
            flags = np.zeros(len(tris), bool)
            for first, count, slot in subs:
                flags[first:first + count] = slot == HAIR_TOP
            centres.append(points[tris].mean(1))
            top.append(flags)
    return cKDTree(np.vstack(centres)), np.concatenate(top)


def in_top(field: tuple, centres: np.ndarray) -> np.ndarray:
    """Whether each triangle centre is in the hair top: its vanilla neighbours' vote."""
    tree, top = field
    _, near = tree.query(centres, k=FIELD_NEIGHBOURS)
    return top[near].mean(1) > 0.5


def _voted(shape: dict, field: tuple) -> list:
    """`shape`'s triangles reordered top first by `field`'s vote (in_top); its [(slot, triangles)]."""
    points, _, _, tris = shape_arrays(shape)
    top = in_top(field, points[tris].mean(1))
    shape['triangles'] = [tuple(int(i) for i in t) for t in tris[np.argsort(~top, kind='stable')]]
    return [(slot, int(n)) for slot, n in ((HAIR_TOP, top.sum()), (HAIR_REST, (~top).sum())) if n]


def enclosing(a: tuple, b: tuple) -> tuple:
    """The smallest sphere (x, y, z, radius) holding spheres `a` and `b`."""
    ca, cb = np.array(a[:3]), np.array(b[:3])
    gap = float(np.linalg.norm(cb - ca))
    if gap + b[3] <= a[3] or gap + a[3] <= b[3]:
        return tuple(a) if a[3] >= b[3] else tuple(b)
    radius = (gap + a[3] + b[3]) / 2
    return (*map(float, ca + (cb - ca) * (radius - a[3]) / gap), radius)


def _with_hat(nif, shape: dict, hat_index: int) -> list:
    """FNV's NoHat `shape` with its Hat variant (block `hat_index`) appended, their bounds merged: NoHat's
    triangles the top a hat hides, Hat's the rest; its [(slot, triangles)].
    See: docs/fork/fo4_facegen_plan.md#own-hair-hat
    """
    hat, _ = sub_segments(nif.blocks[hat_index][1])
    count = len(shape['vertices'])
    parts = [(HAIR_TOP, len(shape['triangles'])), (HAIR_REST, len(hat['triangles']))]
    shape['vertices'] = shape['vertices'] + hat['vertices']
    shape['triangles'] = shape['triangles'] + [tuple(i + count for i in t) for t in hat['triangles']]
    shape['bound'] = enclosing(shape['bound'], hat['bound'])
    data, other = _bone_data(nif, shape), nif.blocks[_bone_data(nif, hat)][1]
    raw = bytearray(nif.blocks[data][1])
    struct.pack_into('<4f', raw, 4, *enclosing(struct.unpack_from('<4f', raw, 4), struct.unpack_from('<4f', other, 4)))
    nif.blocks[data] = (nif.blocks[data][0], bytes(raw))
    return parts


def _bone_data(nif, shape: dict) -> int:
    """Skinned `shape`'s BSSkin::BoneData block (its one bone's sphere at byte 4)."""
    return struct.unpack_from('<i', nif.blocks[shape['skin']][1], 4)[0]


def hat_variant(nif) -> tuple:
    """(NoHat's block, Hat's block) of a worn FNV hair's root shapes, both fitting in one shape; (None, None)
    without that pair."""
    named = {}
    for index in nif.blocks[0][1]['children']:
        kind, raw = nif.blocks[index]
        if kind == 'BSSubIndexTriShape':
            shape = read_tri_shape(Reader(raw))
            named[nif.strings[shape['name']].lower()] = (index, len(shape['vertices']))
    no_hat, hat = named.get(NO_HAT), named.get(HAT)
    if no_hat and hat and no_hat[1] + hat[1] <= MAX_VERTICES:
        return no_hat[0], hat[0]
    return None, None


def as_hair(worn: bytes, field: tuple, material: str) -> bytes:
    """Worn head item NIF `worn` (headgear.worn) as a hair mesh: FNV's NoHat and Hat shapes as one (_with_hat), or
    each shape's triangles split top first by `field` (hat_field) into HAIR_TOP and HAIR_REST sub-segments;
    HAIR_ALPHA, its shader on `material`."""
    nif = nif_file.read(worn)
    name = nif.string(material)
    no_hat, hat = hat_variant(nif)
    if hat is not None:
        nif.blocks[0][1]['children'].remove(hat)
    for index, (kind, raw) in enumerate(list(nif.blocks)):
        if kind != 'BSSubIndexTriShape' or index == hat:
            continue
        shape, _ = sub_segments(raw)
        parts = _with_hat(nif, shape, hat) if index == no_hat else _voted(shape, field)
        nif.blocks[shape['shader']][1]['name'] = name
        nif.blocks.append(('NiAlphaProperty', {'name': NONE, 'extra': [], 'controller': NONE,
                                               'alpha_flags': HAIR_ALPHA[0], 'threshold': HAIR_ALPHA[1]}))
        shape['alpha_property'] = len(nif.blocks) - 1
        nif.blocks[index] = (kind, pack_tri_shape(shape) + segments(parts))
    return nif_file.write(nif)
