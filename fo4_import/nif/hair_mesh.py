"""A mod's own FNV hair mesh, worn on FO4's head (nif.headgear), as an FO4 hair head part's mesh.

Vanilla FO4 hairs split their triangles into two sub-segments: slot 30
(hair top, hidden under a hat) first, then slot 31 (the rest). A converted
hair's triangles take the split of the vanilla hair triangles nearest them
(majority of FIELD_NEIGHBOURS centres, both sexes' hairs pooled; 90.5%
agreement leaving each vanilla hair out in turn). The shapes take vanilla
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


def as_hair(worn: bytes, field: tuple, material: str) -> bytes:
    """Worn head item NIF `worn` (headgear.worn) as a hair mesh: each shape's triangles split top first by
    `field` (hat_field) into HAIR_TOP and HAIR_REST sub-segments, HAIR_ALPHA, its shader on `material`."""
    nif = nif_file.read(worn)
    name = nif.string(material)
    for index, (kind, raw) in enumerate(list(nif.blocks)):
        if kind != 'BSSubIndexTriShape':
            continue
        shape, _ = sub_segments(raw)
        points, _, _, tris = shape_arrays(shape)
        top = in_top(field, points[tris].mean(1))
        shape['triangles'] = [tuple(int(i) for i in t) for t in tris[np.argsort(~top, kind='stable')]]
        parts = [(slot, int(n)) for slot, n in ((HAIR_TOP, top.sum()), (HAIR_REST, (~top).sum())) if n]
        nif.blocks[shape['shader']][1]['name'] = name
        nif.blocks.append(('NiAlphaProperty', {'name': NONE, 'extra': [], 'controller': NONE,
                                               'alpha_flags': HAIR_ALPHA[0], 'threshold': HAIR_ALPHA[1]}))
        shape['alpha_property'] = len(nif.blocks) - 1
        nif.blocks[index] = (kind, pack_tri_shape(shape) + segments(parts))
    return nif_file.write(nif)
