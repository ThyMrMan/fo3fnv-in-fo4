"""An FNV creature clip's shader channels, to bake into its body as free-running loops.

FNV clips key a creature's shapes as well as its bones: the securitron's
`mtidle.kf` scrolls and scales its face screen's texture and dims its
emissive colour, and moves the static overlay. FO4 plays creature clips
through Havok, which drives bones only, so the idle clip's shader channels
become controllers in the body NIF, looping over the clip's span as the idle
does. A channel FO4 has no shader variable for (texture rotation) is left
out, as are the clips that play on events (talking, special idles).

See: docs/fork/fo4_own_rig.md#screen-clips
"""

from pathlib import Path

from fo4_import.nif import fnv_file
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import NifFormat, texel_peaks
from fo4_import.nif.shader_anim import add_running, channel, emit_multi, shapes_by_name

#: NiTimeController flags of a free loop: active, loop cycle, compute scaled time (vanilla's 72).
LOOP_FLAGS = 0x48


def clip_channels(kf: Path) -> tuple:
    """(loop timing, [(shape name, CHANNELS entry, FNV interpolator, FNV controller type)]) of the shader channels
    in KF `kf`'s sequence."""
    data = fnv_file.read(kf)
    seq = next(r for r in data.roots if isinstance(r, NifFormat.NiControllerSequence))
    when = {'flags': LOOP_FLAGS, 'frequency': float(seq.frequency), 'phase': 0.0, 'start': float(seq.start_time),
            'stop': float(seq.stop_time)}
    return when, [(cb.node_name.decode('cp1252'), channel(cb), cb.interpolator, cb.controller_type.decode('cp1252'))
                  for cb in seq.controlled_blocks if channel(cb)]


def bake(nif, fnv_root, looped: tuple, texture_root) -> int:
    """Loop clip_channels() `looped` on converted mesh `nif` (of FNV `fnv_root`, textures under `texture_root`),
    each in place of the shape's own free controller on that channel (_absorbed), as FNV's clip drives it; how
    many channels were baked.

    See: docs/fork/fo4_creature_audit.md#talking-machine-clips
    """
    when, clip = looped
    at = {'shapes': shapes_by_name(nif), 'peaks': texel_peaks(fnv_root, texture_root)}
    materials = {g.name.decode('cp1252'): next((p for p in g.get_properties()
                                                if isinstance(p, NifFormat.NiMaterialProperty)), None)
                 for g in fnv_root.tree() if isinstance(g, NifFormat.NiTriBasedGeom)}
    done = 0
    for name, entry, source, fnv_type in clip:
        start = len(nif.blocks)
        if add_running(nif, at, (name, entry, source), (fnv_type, when, emit_multi(materials.get(name)))):
            done += _absorbed(nif, start)
    return done


def _absorbed(nif, start: int) -> int:
    """Fold the controller add_running() just appended (blocks from `start`, its interpolator and data first) into
    an older one of its shader on the same channel: that one's blocks take the new contents in place and the
    appended ones go, so none is left unreferenced. When their block counts differ the shape keeps its own and
    the clip's is dropped (0); else 1."""
    new = len(nif.blocks) - 1
    kind, ctl = nif.blocks[new]
    old = _same_channel(nif, ctl['next'], kind, ctl['variable'])
    if old is None:
        return 1
    interp = nif.blocks[old][1]['interpolator']
    data = nif.blocks[interp][1].get('data', NONE) if interp >= 0 else NONE
    fresh = list(range(start, new))
    nif.blocks[ctl['target']][1]['controller'] = ctl['next']
    if interp < 0 or len(fresh) != 1 + (data >= 0):
        del nif.blocks[start:]
        return 0
    nif.blocks[interp] = (nif.blocks[fresh[0]][0], dict(nif.blocks[fresh[0]][1], data=data))
    if data >= 0:
        nif.blocks[data] = nif.blocks[fresh[1]]
    nif.blocks[old] = (kind, dict(ctl, next=nif.blocks[old][1]['next'], interpolator=interp))
    del nif.blocks[start:]
    return 1


def _same_channel(nif, first: int, kind: str, variable: int) -> 'int | None':
    """The first controller from `first` along its `next` chain of type `kind` driving `variable`; None for none."""
    while first >= 0:
        if nif.blocks[first][0] == kind and nif.blocks[first][1].get('variable') == variable:
            return first
        first = nif.blocks[first][1]['next']
    return None
