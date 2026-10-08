"""Fallout 4's human skeletons with a lower collision box, so the player fits FNV's doorways.

The player's movement collision is sized from the skeleton root's BSBound box
("BBX"). Vanilla's top is 128 and the controller needs about 13-17 units more
than that, so FNV doorframes (caravan doors, 130-140 high) stop the player.
A top of 115 lets the player through a 130 frame (played). Each skeleton is
read from the user's own `Fallout4 - Meshes.ba2` and written loose with only
the box's centre z and half height changed; the bottom stays at z 0.

See: docs/fork/research/fo4_target.md#player-collision
"""

import struct
from pathlib import Path

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.nif import file as nf

#: The box's top, game units (vanilla 128).
BOX_TOP = 115.0
FOLDER = ('Meshes', 'Actors', 'Character', 'CharacterAssets')
SKELETONS = ('skeleton.nif', 'skeleton_facebones.nif', 'skeleton_female_facebones.nif')
#: BSBound ends with centre (x, y, z) and half extents (x, y, z).
BOX_SIZE = 24


def lowered(raw: bytes, top: float) -> bytes:
    """`raw` with its one BSBound's top moved to `top`, the bottom kept."""
    block = next(b for kind, b in nf.read(raw).blocks if kind == 'BSBound')
    if raw.count(block) != 1:
        raise ValueError('BSBound block bytes are not unique in the skeleton')
    tail = len(block) - BOX_SIZE
    cx, cy, cz, hx, hy, hz = struct.unpack_from('<6f', block, tail)
    drop = (cz + hz - top) / 2
    new = bytearray(block)
    struct.pack_into('<6f', new, tail, cx, cy, cz - drop, hx, hy, hz - drop)
    at = raw.find(block)
    return raw[:at] + bytes(new) + raw[at + len(block):]


def write(data_dir: Path, top: float = BOX_TOP) -> int:
    """Write the lowered human skeletons into `data_dir`; how many were written."""
    archive = Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Meshes.ba2')
    folder = data_dir.joinpath(*FOLDER)
    folder.mkdir(parents=True, exist_ok=True)
    for name in SKELETONS:
        source = '\\'.join(part.lower() for part in FOLDER + (name,))
        (folder / name).write_bytes(lowered(archive.read(source), top))
    return len(SKELETONS)
