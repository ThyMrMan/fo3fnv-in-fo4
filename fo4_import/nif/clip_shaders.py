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
from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.shader_anim import channel

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
