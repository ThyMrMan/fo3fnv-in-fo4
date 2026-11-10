"""A converted FNV melee weapon mesh dressed as Fallout 4's own melee weapons.

Vanilla's (RollingPin01.nif, TireIron.nif, BaseballBat.nif, Switchblade.nif)
are one root node with: `Prn` string extra data naming the bone they hang
from (WEAPON), BSXFlags 194, attach points for weapon mods, and each shape
twice, once with its own material and once with the blood material, which
the game fades in as the weapon gets bloody. Both games hold the weapon with
its grip at the origin and its length along +Y, so FNV's geometry stays as
it is. No attach points are added: a converted weapon takes no FO4 mods.
Run after Elric (elric.finish), which replaces the Havok input with FO4
physics (elric.without_havok keeps the blocks after that input and renumbers
the references to them).
FNV moves a weapon's own parts while it is held (the switchblade's blade
slides out): held_pose reads that from the weapon type's hold animation, for
the mesh to be converted in it.

See: docs/fork/fo4_spikes.md#spike-4-melee
"""

import copy
from pathlib import Path

import numpy as np

from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import NifFormat, lighting_shader
from fo4_import.pipeline.export_index import export_file

#: Vanilla melee weapons' parent bone and BSXFlags.
PARENT, BSX = 'WEAPON', 194
BLOOD_MATERIAL = 'materials\\Blood\\BloodWeapon.BGSM'
#: Vanilla RollingPin01.nif's blood shader (env map type), its textures and its alpha (blend and test, 128).
BLOOD_SHADER = {'shader_type': 1, 'flags1': 0x8C400281, 'flags2': 0, 'grayscale_scale': 0.5, 'envmap': (0.2, 0, 0)}
BLOOD_TEXTURES = ['textures\\Blood\\BloodEdge01_d.dds', 'textures\\Blood\\BloodEdge01_n.dds', '', '',
                  'textures\\Shared\\Cubemaps\\BloodHighlightCube.dds', '', '', '', '', '']
BLOOD_ALPHA = (20547, 128)
#: FNV WEAP DNAM.FalloutAnimType -> the hold ("aim") animation under characters/_male: one- and two-handed melee.
HOLD_ANIMS = {1: '1hmaim.kf', 2: '2hmaim.kf'}
#: A pose value at or beyond this is Gamebryo's "not set" (-FLT_MAX).
UNSET = 1e30
#: NiAVObject flag Hidden: a blood copy stays hidden until the game shows it (vanilla's: 15, the shape's 14).
HIDDEN = 0x1


def _blood(nif, shape: dict) -> int:
    """Append a blood copy of `shape` (its shader, texture set and alpha after it); its index."""
    index = len(nif.blocks)
    name = nif.strings[shape['name']]
    blood = dict(copy.deepcopy(shape), name=nif.string(name.replace(':', '_Blood:', 1) if ':' in name else
                                                       name + '_Blood'),
                 flags=shape['flags'] | HIDDEN, shader=index + 1, alpha_property=index + 3, collision=NONE)
    nif.blocks.append(('BSTriShape', blood))
    nif.blocks.append(('BSLightingShaderProperty', {**lighting_shader(nif, BLOOD_MATERIAL, index + 2, 0),
                                                    **BLOOD_SHADER}))
    nif.blocks.append(('BSShaderTextureSet', {'textures': list(BLOOD_TEXTURES)}))
    nif.blocks.append(('NiAlphaProperty', {'name': NONE, 'extra': [], 'controller': NONE,
                                           'alpha_flags': BLOOD_ALPHA[0], 'threshold': BLOOD_ALPHA[1]}))
    return index


def _quaternion_rows(w: float, x: float, y: float, z: float) -> tuple:
    """A quaternion as NiMatrix3 rows: the rotation matrix transposed, as pyffi's get_scale_quat inverts."""
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                  [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                  [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
    return tuple(map(tuple, r.T.tolist()))


def _held(interp) -> tuple:
    """(translation or None, rotation rows or None) of a transform interpolator: its pose, else its first key."""
    t, q = interp.translation, interp.rotation
    data = interp.data
    trans = (t.x, t.y, t.z) if abs(t.x) < UNSET else None
    if trans is None and data and data.translations.num_keys:
        key = data.translations.keys[0].value
        trans = (key.x, key.y, key.z)
    quat = (q.w, q.x, q.y, q.z) if abs(q.w) < UNSET else None
    if quat is None and data and data.num_rotation_keys and data.quaternion_keys:
        key = data.quaternion_keys[0].value
        quat = (key.w, key.x, key.y, key.z)
    return trans, _quaternion_rows(*quat) if quat else None


def held_pose(export_dir: Path, anim_type: int) -> dict:
    """{node name: (translation, rotation rows)} of the hold animation for FNV animation type `anim_type`."""
    if anim_type not in HOLD_ANIMS:
        return {}
    data = NifFormat.Data()
    with open(export_file(export_dir, 'meshes', 'characters', '_male', HOLD_ANIMS[anim_type]), 'rb') as f:
        data.read(f)
    out = {}
    for seq in (b for b in data.roots if isinstance(b, NifFormat.NiControllerSequence)):
        for block in seq.controlled_blocks:
            if isinstance(block.interpolator, NifFormat.NiTransformInterpolator):
                out[block.get_node_name().decode('cp1252')] = _held(block.interpolator)
    return out


def dress(nif) -> None:
    """Give a converted weapon NIF vanilla's parent bone, BSXFlags and a blood copy of each lit shape."""
    root = nif.blocks[0][1]
    lit = [b for kind, b in nif.blocks if kind == 'BSTriShape'
           and nif.blocks[b['shader']][0] == 'BSLightingShaderProperty']
    root['children'] = [_blood(nif, shape) for shape in lit] + root['children']
    flags = [block for kind, block in nif.blocks if kind == 'BSXFlags']
    for block in flags:
        block['value'] = BSX
    if not flags:
        nif.blocks.append(('BSXFlags', {'name': nif.string('BSX'), 'value': BSX}))
        root['extra'].append(len(nif.blocks) - 1)
    nif_file.hang_from(nif, PARENT)


def dress_file(path) -> None:
    """dress() the NIF at `path` in place."""
    nif = nif_file.read(path.read_bytes())
    dress(nif)
    path.write_bytes(nif_file.write(nif))
