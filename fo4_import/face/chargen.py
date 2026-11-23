"""An NPC's morph presets on its head parts, as the CK bakes them into the FaceGeom.

The NPC's MSDK keys name its race's presets (MPPI), each a morph (MPPM) of a
part's chargen .tri (HDPT NAM0 2, then NAM1), weighted by MSDV. The CK adds
weight times the morph's delta of .tri vertex i to the part's vertex i;
vertices past the .tri's count stay put. Morph names match without case.

See: docs/fork/fo4_facegen_plan.md#preset-morphs
"""

import struct

import numpy as np

from fo4_import.face import presets

#: HDPT NAM0: the .tri after it (NAM1) holds the part's chargen morphs.
CHARGEN = 2


def npc_weights(npc, race, female: bool) -> dict:
    """{morph name (lower case): summed weight} of the NPC record's MSDK/MSDV presets, read through `race`."""
    keys, values = npc.first(b'MSDK', b''), npc.first(b'MSDV', b'')
    names = {p.key: p.morph.lower() for p in presets.race_presets(race.subs, female)}
    out = {}
    for key, value in zip(struct.unpack(f'<{len(keys) // 4}I', keys), struct.unpack(f'<{len(values) // 4}f', values)):
        if key in names:
            out[names[key]] = out.get(names[key], 0.0) + value
    return out


def chargen_tri(part) -> str:
    """The HDPT record's chargen .tri path under Meshes, '' if it lists none."""
    kind = None
    for tag, data in part.subs:
        kind = struct.unpack('<I', data)[0] if tag == b'NAM0' else kind
        if tag == b'NAM1' and kind == CHARGEN:
            return data.rstrip(b'\0').decode('cp1252')
    return ''


def offsets(src, part, weights: dict, count: int) -> 'np.ndarray | None':
    """[count, 3] moves `weights` (npc_weights) make on a part of `count` vertices; None when nothing moves."""
    path = chargen_tri(part) if weights else ''
    if not path:
        return None
    morphs = src.tri_morphs(path)
    out = np.zeros((count, 3))
    for name, weight in weights.items():
        if name in morphs:
            n = min(count, len(morphs[name]))
            out[:n] += weight * morphs[name][:n]
    return out if out.any() else None
