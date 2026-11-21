"""An FNV creature clip's node motion, baked into a converted body part as free-running loops.

Mr. House's pod idle (`mtidle.kf`) breathes, beats his heart and slides his
helmet by moving skeleton bones; the rigid parts (helmet, heart, stomach
pump) hang on those bones by their `Prn` name. A talking machine's look is
a set of activators with no behaviour graph, so the clip's node tracks
become NiTransformControllers on the part's own nodes, looping as the idle
does: vanilla Fallout 4 moves nodes this way in 1,149 meshes with no
controller manager (`yangtzeperiscope01.nif`). A rigid part keeps the
skeleton's chain down to its `Prn` bone as nodes (hang), so it follows
every bone above it; a skinned part keeps its bones (convert's
`every_bone`).

See: docs/fork/fo4_creature_audit.md#talking-machine-clips
"""

from pathlib import Path

from fo4_import.nif import fnv_file
from fo4_import.nif.animation import add_nodes, moves, transform_interpolator, with_parents
from fo4_import.nif.convert_static import BSX_ANIMATED, NODE_FLAGS, NifFormat


def clip_tracks(kf: Path) -> list:
    """[(node name, FNV NiTransformInterpolator)] of KF `kf`'s node tracks."""
    seq = next(r for r in fnv_file.read(kf).roots if isinstance(r, NifFormat.NiControllerSequence))
    return [(cb.node_name.decode('cp1252'), cb.interpolator) for cb in seq.controlled_blocks if moves(cb)]


def hang(nif, skeleton, prn: str) -> None:
    """Put converted part `nif`'s top-level blocks (built unposed, in `prn`'s space) under copies of FNV
    `skeleton`'s nodes from its root down to bone `prn`, each with its own transform."""
    chain = with_parents(skeleton, lambda node: node.name.decode('cp1252') == prn)
    if not chain:
        return
    top = nif.blocks[0][1]
    held, top['children'] = top['children'], []
    nodes = add_nodes(nif, chain, skeleton, NODE_FLAGS)
    nif.blocks[nodes[id(chain[-1])]][1]['children'] += held


def loop(nif, tracks: list, when: dict) -> int:
    """Loop clip_tracks() `tracks` on the nodes of `nif` they name, each a free NiTransformController with
    `when`'s timing (clip_shaders.clip_channels'); the mesh is flagged animated; how many were looped."""
    named = {nif.strings[b['name']]: i for i, (kind, b) in enumerate(nif.blocks) if kind == 'NiNode' and i}
    done = 0
    for name, source in tracks:
        node = named.get(name)
        if node is None:
            continue
        interp = transform_interpolator(nif, source)
        fields = nif.blocks[node][1]
        nif.blocks.append(('NiTransformController', {**when, 'next': fields['controller'], 'target': node,
                                                     'interpolator': interp}))
        fields['controller'] = len(nif.blocks) - 1
        done += 1
    if done:
        _flag_animated(nif)
    return done


def _flag_animated(nif) -> None:
    """Set BSX_ANIMATED on `nif`'s BSXFlags, adding one to the root when it has none."""
    root = nif.blocks[0][1]
    bsx = next((i for i in root['extra'] if nif.blocks[i][0] == 'BSXFlags'), None)
    if bsx is None:
        nif.blocks.append(('BSXFlags', {'name': nif.string('BSX'), 'value': 0}))
        bsx = len(nif.blocks) - 1
        root['extra'].append(bsx)
    nif.blocks[bsx][1]['value'] |= BSX_ANIMATED
