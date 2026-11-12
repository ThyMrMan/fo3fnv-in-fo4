"""An NPC's FaceGen head (FaceGeom NIF) assembled from its head part meshes, as the Creation Kit exports it.

Each part's shape, skin and bone data are copied from its own mesh, its vertices moved by the NPC's sculpt
regions (face_bones); the shader is the mesh's, filled in from its
material, texture set and the NPC (hair colour, skin tone); the bone nodes stand at the race skeleton's bind
positions scaled by the race's height. Scratch only: nothing in the build calls this yet.

See: docs/fork/fo4_facegen_plan.md#phase-1-our-own-facegeom
"""

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.face.bake import positions, with_positions
from fo4_import.face.face_bones import Sculpt
from fo4_import.nif import bgem, bgsm
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import SHADER_DEFAULT, SHADER_ENVMAP, SHADER_FACEGEN, SHADER_GLOW, SHADER_HAIR_TINT
from fo4_import.nif.blocks import SHADER_SKIN_TINT, Reader, pack_av, pack_tri_shape, read_av
from tes5_import.base.tes5_reader import masters, subrecords, walk

#: Record types a FaceGeom draws on.
SIGS = (b'NPC_', b'RACE', b'HDPT', b'TXST', b'CLFM', b'ARMO', b'ARMA')
#: HDPT DATA flags: an extra part (drawn only through its parent's HNAM); its textures are the body's.
EXTRA_PART, USES_BODY_TEXTURE = 0x08, 0x20
#: ACBS flags bit Female.
FEMALE = 0x1
#: ACBS template flags (u16 at TEMPLATE_FLAGS_AT) bit Use Traits; RACE DATA flags (u32 at RACE_FLAGS_AT) FaceGen Head.
USE_TRAITS, TEMPLATE_FLAGS_AT, FACEGEN_HEAD, RACE_FLAGS_AT = 0x1, 14, 0x2, 32
#: Extra data a part's mesh carries into the FaceGeom (from its root or its shape).
FACE_EXTRAS = ('BSClothExtraData', 'BSEyeCenterExtraData')
#: Cloth data stores no name, but the engine names it 'CED' and the CK's string table lists that.
CLOTH, CLOTH_NAME = 'BSClothExtraData', 'CED'
#: HDPT types of the face and the eyes, and the race's default face texture set per sex (female?).
FACE_PART, EYES_PART, FACE_SETS = 1, 2, {False: b'DFTM', True: b'DFTF'}
#: NiNode flags of the root, the FaceGen node and each bone node, as the CK writes them.
ROOT_FLAGS, FACEGEN_FLAGS, BONE_FLAGS = 536887310, 536870926, 14
FACEGEN_NODE = 'BSFaceGenNiNodeSkinned'
SHAPES = ('BSSubIndexTriShape', 'BSTriShape')
#: BSVertexDesc eye-data offset nibble, and the offset the CK sets on a shape that has none.
EYE_DATA_SHIFT, EYE_DATA = 36, 1 << 37
#: Shader flags1 Eye_Environment_Mapping, which the CK clears.
EYE_ENVIRONMENT = 1 << 17
#: Shader flags2 Transform_Changed, set on every FaceGeom shader.
TRANSFORM_CHANGED = 0x80
#: Shader flag bits the CK takes from the material: (flags word, bit, material field).
MATERIAL_BITS = (('flags1', 0, 'specular'), ('flags1', 7, 'env_mapping'), ('flags1', 18, 'hair'),
                 ('flags2', 6, 'glowmap'), ('flags2', 22, 'skew_specular_alpha'))
#: The skin addon whose texture set a body-textured part takes: BOD2 slot 33 (Body).
BODY_SLOT = 1 << 3
#: What the CK writes per bone in a BSSkin::Instance's trailing vector list.
BONE_VECTOR = (0.0, 1.0, 1.0)
#: Wetness the CK writes when neither the material nor its root material sets it.
WETNESS = (0.8, 0.7, 0.3, 1.0, 1.2, 0.1)
#: BSShaderTextureSet slot of each BGSM texture.
SLOTS = {'diffuse': 0, 'normal': 1, 'glow': 2, 'greyscale': 3, 'envmap': 4, 'wrinkles': 5, 'smooth_spec': 7}
#: BSEffectShaderProperty field of each BGEM texture.
EFFECT_TEXTURES = {'base': 'source_texture', 'grayscale': 'greyscale', 'envmap': 'env_map', 'normal': 'normal',
                   'env_mask': 'env_mask'}
#: The face's own textures (FaceCustomization) by slot.
FACE_TEXTURES = {0: '_d', 1: '_msn', 7: '_s'}
#: Lighting shader fields copied from the material: (shader field, material field).
FROM_MATERIAL = (('smoothness', 'smoothness'), ('specular_strength', 'specular_mult'),
                 ('fresnel_power', 'fresnel_power'), ('backlight_power', 'backlight_power'), ('alpha', 'alpha'), ('emissive_multiple', 'emittance_mult'))
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _form(data: bytes) -> int:
    """A subrecord's FormID."""
    return struct.unpack_from('<I', data)[0]


def zstr(data: bytes) -> str:
    """A zero-terminated string subrecord."""
    return data.rstrip(b'\0').decode('cp1252')


@dataclass(eq=False)
class Rec:
    """One record: the plugin it is read from, its signature and subrecords [(tag, data)]."""
    owner: str
    sig: bytes
    subs: list

    def first(self, tag: bytes, default=None):
        """The first `tag` subrecord's data."""
        return next((d for t, d in self.subs if t == tag), default)


class Sources:
    """A plugin, its masters and the game: records by (owner, local id), files loose first, then archives."""

    def __init__(self, plugin: Path, dirs: list, load_order=()):
        """Index the plugins of `load_order` (names, in order, as the CK loads a profile's), then `plugin`, each
        with its masters (found in `dirs`, then the game's Data), a later one's records over an earlier's; files
        from `dirs`' loose folders and BA2s (first wins), then the game's archives."""
        self.dirs = [Path(d) for d in dirs]
        self.records, self.masters, self.seen = {}, {}, set()
        self.archives = Archives(FALLOUT4_DIR / 'Data')
        for d in reversed(self.dirs):
            self.archives.by_name.update(Archives(d, '*.ba2').by_name)
        for name in [*load_order, Path(plugin).name]:
            if name.lower() not in self.masters:
                self._load(self._find(name) if name in load_order else Path(plugin))

    def _load(self, path: Path) -> None:
        """Index one plugin's records (masters first)."""
        data = path.read_bytes()
        own = masters(data)
        for name in own:
            if name not in self.masters:
                self._load(self._find(name))
        self.masters[path.name.lower()] = own
        for rec, _ in walk(data, *SIGS):
            owner = own[rec.form_id >> 24] if rec.form_id >> 24 < len(own) else path.name.lower()
            self.records[owner, rec.form_id & 0xFFFFFF] = Rec(path.name.lower(), rec.sig, list(subrecords(rec.body)))

    def _find(self, name: str) -> Path:
        """A master's file in `dirs` or the game's Data."""
        for d in self.dirs + [FALLOUT4_DIR / 'Data']:
            if (d / name).exists():
                return d / name
        raise FileNotFoundError(f'master {name} not in {self.dirs} or the game\'s Data')

    def record(self, owner: str, form_id: int) -> 'Rec | None':
        """The record (owner, local id), noted in `seen` (facegen_own's cache check)."""
        self.seen.add((owner, form_id))
        return self.records.get((owner, form_id))

    def get(self, rec: Rec, data: bytes) -> 'Rec | None':
        """The record the FormID in `data` (a field of `rec`) names."""
        fid, own = _form(data), self.masters[rec.owner]
        return self.record(own[fid >> 24] if fid >> 24 < len(own) else rec.owner, fid & 0xFFFFFF)

    def read(self, path: str) -> bytes:
        """A file under Data, noted in `seen` (as record())."""
        rel = path.replace('/', '\\')
        self.seen.add(rel)
        return self.stored(rel)

    def stored(self, rel: str) -> bytes:
        """File `rel` under Data, loose in `dirs` first, then the archives; not noted."""
        hit = next((d / rel for d in self.dirs if (d / rel).is_file()), None)
        return hit.read_bytes() if hit else self.archives.read(rel)

    def material(self, name: str) -> dict:
        """A BGSM or BGEM by the name a shader gives."""
        raw = self.read(name if name.lower().startswith('materials') else 'materials\\' + name)
        return (bgem if raw[:4] == bgem.MAGIC else bgsm).read(raw)


def part_type(part: Rec) -> int:
    """A head part's type (HDPT PNAM)."""
    return _form(part.first(b'PNAM', b'\xff\xff\xff\xff'))


def sex_section(race: Rec, female: bool) -> list:
    """The race's subrecords [(tag, data)] in its male (empty MNAM) or female (empty FNAM) sections."""
    marker, sex, out = b'FNAM' if female else b'MNAM', None, []
    for t, data in race.subs:
        sex = t if t in (b'MNAM', b'FNAM') and not data else sex
        out += [(t, data)] if sex == marker else []
    return out


def _by_sex(race: Rec, female: bool, tag: bytes) -> list:
    """The race's `tag` subrecords in its male (MNAM) or female (FNAM) sections."""
    return [data for t, data in sex_section(race, female) if t == tag]


def _with_extras(src: Sources, part: Rec) -> list:
    """A head part led by its extra parts (HNAM order, each led by its own)."""
    out = []
    for data in (d for t, d in part.subs if t == b'HNAM'):
        extra = src.get(part, data)
        out += _with_extras(src, extra) if extra and extra.first(b'MODL') else []
    return out + [part]


def head_parts(src: Sources, npc: Rec, race: Rec, female: bool) -> list:
    """The parts the CK draws, in its order: race defaults for types the NPC lacks (last first), then the NPC's own
    (last first), each led by its extras."""
    own = [p for p in (src.get(npc, d) for t, d in npc.subs if t == b'PNAM')
           if p and not p.first(b'DATA')[0] & EXTRA_PART]
    types, defaults = {part_type(p) for p in own}, []
    for part in (src.get(race, d) for d in _by_sex(race, female, b'HEAD')):
        if part and part_type(part) not in types:
            defaults.append(part)
            types.add(part_type(part))
    return [x for p in defaults[::-1] + own[::-1] if p.first(b'MODL') for x in _with_extras(src, p)]


def skeleton_nodes(src: Sources, race: Rec, female: bool) -> dict:
    """{bone (lowercase): position} of the race's skeleton for one sex, at its height."""
    skeleton = nif_file.read(src.read('meshes\\' + zstr(_by_sex(race, female, b'ANAM')[0])))
    worlds = world32(skeleton, race_height(race, female))
    return {name.lower(): tuple(float(x) for x in pos) for name, pos in worlds.items()}


def race_height(race: Rec, female: bool) -> float:
    """The race's height for one sex (DATA)."""
    return struct.unpack_from('<2f', race.first(b'DATA'))[1 if female else 0]


def world32(skeleton, height: float) -> dict:
    """{name: world position} of a skeleton NIF's nodes, its root scaled by `height`, composed as the CK does: in
    float32, rotate (sums left to right), then scale, then translate."""
    f4 = np.float32
    parent = {c: i for i, (_, b) in enumerate(skeleton.blocks) if isinstance(b, dict) and 'children' in b
              for c in b['children']}
    world = {}

    def place(i):
        """(world rotation rows, position, scale) of node `i`."""
        if i not in world:
            b = skeleton.blocks[i][1]
            rot = [[f4(x) for x in b['rotation'][r * 3:r * 3 + 3]] for r in range(3)]
            pos, scale = [f4(x) for x in b['translation']], f4(b['scale'])
            if i in parent:
                ur, up, us = place(parent[i])
                pos = [(ur[r][0] * pos[0] + ur[r][1] * pos[1] + ur[r][2] * pos[2]) * us + up[r] for r in range(3)]
                rot = [[ur[r][0] * rot[0][c] + ur[r][1] * rot[1][c] + ur[r][2] * rot[2][c] for c in range(3)]
                       for r in range(3)]
                scale = us * scale
            else:
                pos, scale = [p * f4(height) for p in pos], scale * f4(height)
            world[i] = rot, pos, scale
        return world[i]

    return {skeleton.strings[b['name']]: place(i)[1] for i, (_, b) in enumerate(skeleton.blocks)
            if isinstance(b, dict) and 'children' in b}


def _skin_bones(raw: bytes) -> list:
    """The bone node indices of a BSSkin::Instance."""
    n = struct.unpack_from('<I', raw, 8)[0]
    return list(struct.unpack_from(f'<{n}i', raw, 12))


def _pack_skin_instance(root: int, data: int, bones: list) -> bytes:
    """A BSSkin::Instance with BONE_VECTOR per bone."""
    out = struct.pack(f'<iiI{len(bones)}i', root, data, len(bones), *bones)
    return out + struct.pack('<I', len(bones)) + struct.pack('<3f', *BONE_VECTOR) * len(bones)


def shader_type(mat: dict) -> int:
    """The lighting shader type the CK gives a BGSM."""
    for field, kind in (('glowmap', SHADER_GLOW), ('facegen', SHADER_FACEGEN), ('skin_tint', SHADER_SKIN_TINT),
                        ('hair', SHADER_HAIR_TINT), ('env_mapping', SHADER_ENVMAP)):
        if mat.get(field):
            return kind
    return SHADER_DEFAULT


def _wetness(src: Sources, mat: dict) -> tuple:
    """The material's wetness, else its root material's, else the CK's default."""
    keys = ('wet_spec_scale', 'wet_spec_power', 'wet_spec_minvar', 'wet_env_map_scale', 'wet_fresnel', 'wet_metalness')
    for m in (mat, src.material(mat['root_material']) if mat.get('root_material') else {}):
        if m and m[keys[0]] != -1.0:
            return tuple(m[k] for k in keys)
    return WETNESS


@dataclass
class Npc:
    """What the CK takes from the NPC: plugin and id (its face texture names), hair colour, skin tone, the skin's
    texture set, and the face material (its face texture set's, else the race's default)."""
    plugin: str
    form_id: int
    grayscale: float
    tone: tuple
    body_textures: list
    face_material: str


def set_flags(sh: dict, mat: dict) -> None:
    """Set the material's flag bits and Transform_Changed on shader `sh`."""
    for word, bit, field in MATERIAL_BITS:
        sh[word] = sh[word] | 1 << bit if mat.get(field) else sh[word] & ~(1 << bit)
    sh['flags1'] &= ~EYE_ENVIRONMENT
    sh['flags2'] |= TRANSFORM_CHANGED


def _textures(src: Sources, part: Rec, mat: dict, npc: Npc) -> list:
    """The ten texture slots: the material's, the part's texture set over them (the body's when it uses the body
    texture), the face's own for a FaceGen material."""
    slots = [''] * 10
    for name, slot in SLOTS.items():
        slots[slot] = mat['textures'].get(name, '')
    txst = src.get(part, part.first(b'TNAM')) if part.first(b'TNAM') else None
    sets = npc.body_textures if part.first(b'DATA')[0] & USES_BODY_TEXTURE else _txst_paths(txst)[:1]
    for slot, path in enumerate(sets):
        slots[slot] = path or slots[slot]
    for slot, suffix in FACE_TEXTURES.items() if mat.get('facegen') else ():
        slots[slot] = face_texture(npc, suffix)
    return slots


def face_texture(npc: Npc, suffix: str) -> str:
    """The NPC's own face texture path as the CK writes it (`suffix`: _d, _msn or _s)."""
    return f'Data\\Textures\\Actors\\Character\\FaceCustomization\\{npc.plugin}\\{npc.form_id:08X}{suffix}.dds'


def _txst_paths(txst: 'Rec | None') -> list:
    """A TXST's TX00..TX07 paths ('' where absent)."""
    if txst is None:
        return []
    found = {t: zstr(d) for t, d in txst.subs if t[:2] == b'TX'}
    return [found.get(b'TX%02d' % i, '') for i in range(8)]


def lighting(src: Sources, part: Rec, sh: dict, mat: dict, npc: Npc) -> tuple:
    """(the CK's lighting shader from the mesh's `sh` and its material `mat`, texture paths)."""
    sh = dict(sh, shader_type=shader_type(mat), grayscale_scale=npc.grayscale, wetness=_wetness(src, mat))
    set_flags(sh, dict(mat, specular=bool(mat['specular'] and mat['specular_mult'])))
    sh.update({field: mat[key] for field, key in FROM_MATERIAL if field in sh})
    sh['uv_offset'], sh['uv_scale'] = tuple(mat['uv_offset']), tuple(mat['uv_scale'])
    sh['specular_color'] = tuple(mat['specular_color'])
    sh.pop('envmap', None), sh.pop('skin_tint', None), sh.pop('hair_tint', None)
    if sh['shader_type'] == SHADER_ENVMAP:
        sh['envmap'] = (mat['env_mask_scale'], 0, 0)
    elif sh['shader_type'] == SHADER_SKIN_TINT:
        sh['skin_tint'] = npc.tone
    elif sh['shader_type'] == SHADER_HAIR_TINT:
        sh['hair_tint'] = tuple(mat['hair_tint'])
    return sh, _textures(src, part, mat, npc)


def effect(sh: dict, mat: dict) -> dict:
    """The CK's effect shader from the mesh's `sh` and its BGEM `mat`."""
    sh = dict(sh, base_color=(*mat['base_color'], mat['alpha']), base_color_scale=mat['base_color_scale'],
              falloff=tuple(mat[k] for k in ('falloff_start_angle', 'falloff_stop_angle', 'falloff_start_opacity',
                                             'falloff_stop_opacity')),
              soft_depth=mat['soft_depth'], env_min_lod=mat['env_min_lod'], env_map_scale=mat['env_mask_scale'],
              lighting_influence=round(mat['lighting_influence'] * 255),
              uv_offset=tuple(mat['uv_offset']), uv_scale=tuple(mat['uv_scale']))
    for name, field in EFFECT_TEXTURES.items():
        sh[field] = mat['textures'][name]
    sh['flags2'] |= TRANSFORM_CHANGED
    return sh


def body_addon(src: Sources, npc: Rec, race: Rec) -> 'Rec | None':
    """The skin's (the NPC's WNAM, else the race's) body addon (ARMA on the body slot)."""
    owner = npc if npc.first(b'WNAM') else race
    skin = src.get(owner, owner.first(b'WNAM')) if owner.first(b'WNAM') else None
    addons = (src.get(skin, d) for t, d in (skin.subs if skin else []) if t == b'MODL')
    return next((a for a in addons if a and _form(a.first(b'BOD2', b'\0' * 4)) & BODY_SLOT), None)


def body_textures(src: Sources, npc: Rec, race: Rec, female: bool) -> list:
    """The skin's body addon's skin texture set for one sex."""
    addon = body_addon(src, npc, race)
    txst = addon.first(b'NAM1' if female else b'NAM0') if addon else None
    return txst_slots(src, src.get(addon, txst)) if txst else []


def txst_slots(src: Sources, txst: Rec) -> list:
    """A TXST's texture slots: its material's (MNAM), its own paths (TX00..TX07) over them."""
    slots = [''] * 10
    material = zstr(txst.first(b'MNAM', b'\0'))
    for name, slot in SLOTS.items() if material else ():
        slots[slot] = src.material(material)['textures'].get(name, '')
    for slot, path in enumerate(_txst_paths(txst)):
        slots[slot] = path or slots[slot]
    return slots


def npc_face(src: Sources, plugin: str, form_id: int) -> tuple:
    """(NPC record, its race, female, Npc) for the NPC `form_id` (local id) of `plugin`."""
    npc = src.record(plugin.lower(), form_id & 0xFFFFFF)
    race, female = src.get(npc, npc.first(b'RNAM')), bool(struct.unpack_from('<I', npc.first(b'ACBS'))[0] & FEMALE)
    colour = src.get(npc, npc.first(b'HCLF')) if npc.first(b'HCLF') else None
    grayscale = struct.unpack('<f', colour.first(b'CNAM'))[0] if colour else 1.0
    tone = tuple(float(np.float32(round(c * 255)) * np.float32(1 / 255))
                 for c in struct.unpack('<4f', npc.first(b'QNAM', b'\0' * 16)))
    face = Npc(plugin, form_id & 0xFFFFFF, grayscale, tone, body_textures(src, npc, race, female),
               _face_material(src, npc, race, female))
    return npc, race, female, face


def exported(npc: Rec, race: Rec) -> bool:
    """Whether the CK exports FaceGen for `npc`: it takes no traits from a template and its race has a FaceGen head.
    See: docs/fork/fo4_facegen_plan.md#own-stage
    """
    traits = npc.first(b'TPLT') and struct.unpack_from('<H', npc.first(b'ACBS'), TEMPLATE_FLAGS_AT)[0] & USE_TRAITS
    data = race.first(b'DATA', b'')
    return not traits and len(data) >= RACE_FLAGS_AT + 4 and bool(
        struct.unpack_from('<I', data, RACE_FLAGS_AT)[0] & FACEGEN_HEAD)


def _face_material(src: Sources, npc: Rec, race: Rec, female: bool) -> str:
    """The material of the NPC's face set (FTST), else the race's default."""
    owner, tag = (npc, b'FTST') if npc.first(b'FTST') else (race, FACE_SETS[female])
    txst = src.get(owner, owner.first(tag)) if owner.first(tag) else None
    return zstr(txst.first(b'MNAM', b'\0')) if txst else ''


@dataclass
class Shape:
    """A part mesh's first shape: its NiAVObject fields, references, vertex descriptor and the bytes after it
    (vertices, triangles, segments), kept as they are."""
    kind: str
    av: dict
    skin: int
    shader: int
    alpha: int
    desc: int
    body: bytes

    @classmethod
    def of(cls, mesh) -> 'Shape':
        """The first BSTriShape or BSSubIndexTriShape of `mesh`."""
        index = next(i for i, (kind, _) in enumerate(mesh.blocks) if kind in SHAPES)
        block = mesh.blocks[index][1]
        r = Reader(block if isinstance(block, bytes) else pack_tri_shape(block))
        av = {}
        read_av(r, av)
        r.take('4f')
        skin, shader, alpha = r.take('3i')
        return cls(mesh.blocks[index][0], av, skin, shader, alpha, r.take('Q'), r.data[r.pos:])

    def pack(self) -> bytes:
        """The shape's bytes with a zero bound, as every skinned part has."""
        return pack_av(self.av) + struct.pack('<4f3iQ', 0.0, 0.0, 0.0, 0.0, self.skin, self.shader, self.alpha,
                                              self.desc) + self.body

    def sculpt(self, sculpt: Sculpt, model: str) -> None:
        """Move the vertices by the NPC's sculpt regions, where the part has a twin they move."""
        packed = self.pack()
        points = sculpt.positions(model, len(positions(packed)))
        if points is not None:
            self.body = with_positions(packed, points)[len(packed) - len(self.body):]


def _bone_names(mesh, shape: Shape) -> list:
    """The bone names a mesh's shape is skinned to."""
    return [mesh.strings[mesh.blocks[b][1]['name']] for b in _skin_bones(mesh.blocks[shape.skin][1])]


def eye_data(desc: int) -> int:
    """The vertex descriptor with the CK's eye-data offset where the shape has none."""
    return desc if desc >> EYE_DATA_SHIFT & 0xF else desc | EYE_DATA


class FaceGeom:
    """A FaceGeom NIF being assembled: root, bone nodes, FaceGen node, then each part's blocks."""

    def __init__(self, src: Sources, npc: Npc, bones: list):
        """Root, `bones` [(name, position)] as nodes, and the FaceGen node."""
        self.src, self.npc = src, npc
        self.nif = nif_file.NifFile()
        empty = self.nif.empty_string()
        self.nif.blocks.append(('BSFadeNode', self._node(empty, ROOT_FLAGS, (0.0, 0.0, 0.0))))
        self.nodes = {}
        for bone, pos in bones:
            self.nodes[bone.lower()] = len(self.nif.blocks)
            self.nif.blocks.append(('NiNode', self._node(self.nif.string(bone), BONE_FLAGS, pos)))
        self.facegen = len(self.nif.blocks)
        self.nif.blocks.append(('NiNode', self._node(self.nif.string(FACEGEN_NODE), FACEGEN_FLAGS, (0.0, 0.0, 0.0))))
        self.nif.blocks[0][1]['children'] = list(range(1, self.facegen + 1))

    def _text(self, text: str) -> int:
        """The string table index of `text`, '' included."""
        return self.nif.string(text) if text else self.nif.empty_string()

    @staticmethod
    def _node(name: int, flags: int, pos: tuple) -> dict:
        """A NiNode at `pos`, unrotated, with no children."""
        return {'name': name, 'extra': [], 'controller': -1, 'flags': flags, 'translation': tuple(pos),
                'rotation': IDENTITY, 'scale': 1.0, 'collision': -1, 'children': []}

    def _named(self, mesh, block: dict) -> dict:
        """A mesh's block with its name moved to this file's string table."""
        name = block['name']
        return dict(block, name=-1 if name < 0 else self._text(mesh.strings[name]))

    def _extra(self, mesh, index: int) -> tuple:
        """A mesh's raw extra data block, its name moved to this file."""
        kind, raw = mesh.blocks[index]
        if kind == CLOTH:
            self.nif.string(CLOTH_NAME)
            return kind, raw
        name = struct.unpack_from('<i', raw)[0]
        return kind, struct.pack('<i', -1 if name < 0 else self._text(mesh.strings[name])) + raw[4:]

    def add(self, part: Rec, mesh, shape: Shape) -> None:
        """One part's shape, extra data, skin, bone data, shader, texture set and alpha from its mesh."""
        at, blocks = len(self.nif.blocks), self.nif.blocks
        own = [e for e in shape.av['extra'] if mesh.blocks[e][0] in FACE_EXTRAS]
        name = self.nif.string(zstr(part.first(b'EDID')))
        found = list(dict.fromkeys(e for e in mesh.blocks[0][1]['extra'] + own if mesh.blocks[e][0] in FACE_EXTRAS))
        extras = [self._extra(mesh, e) for e in found]
        skin = at + 1 + len(extras)
        bones = [self.nodes[b.lower()] for b in _bone_names(mesh, shape)]
        data = mesh.blocks[_skin_data(mesh.blocks[shape.skin][1])][1]
        kind, sh = mesh.blocks[shape.shader]
        face = part_type(part) == FACE_PART and self.npc.face_material
        mat = self.src.material(face or mesh.strings[sh['name']])
        blocks += [(shape.kind, b''), *extras, ('BSSkin::Instance', _pack_skin_instance(self.facegen, skin + 1, bones)),
                   ('BSSkin::BoneData', data)]
        if kind == 'BSLightingShaderProperty':
            sh, textures = lighting(self.src, part, sh, mat, self.npc)
            blocks += [(kind, dict(sh, name=0, root_material=0, texture_set=skin + 3)),
                       ('BSShaderTextureSet', {'textures': textures})]
        else:
            blocks.append((kind, dict(effect(sh, mat), name=0)))
        if shape.alpha >= 0:
            blocks.append(('NiAlphaProperty', self._named(mesh, mesh.blocks[shape.alpha][1])))
        moved = dict(zip(found, range(at + 1, skin)))
        shape.av.update(name=name, extra=[moved[e] for e in own + found])
        shape.skin, shape.shader, shape.desc = skin, skin + 2, eye_data(shape.desc)
        shape.alpha = len(blocks) - 1 if shape.alpha >= 0 else -1
        blocks[at] = (shape.kind, shape.pack())
        blocks[self.facegen][1]['children'].append(at)


def _skin_data(raw: bytes) -> int:
    """The BoneData index of a BSSkin::Instance."""
    return struct.unpack_from('<i', raw, 4)[0]


def bone_nodes(parts: list, skeleton: dict, height: float) -> list:
    """[(name, position)] of every bone the parts are skinned to, first seen first: the skeleton's position, else
    (a bone only the part has, such as hair cloth) the part mesh's own, scaled by `height`."""
    out = {}
    for _, mesh, shape in parts:
        own = None
        for name in _bone_names(mesh, shape):
            if name.lower() not in out:
                own = own or (None if name.lower() in skeleton else world32(mesh, height))
                pos = skeleton.get(name.lower()) or tuple(float(x) for x in own[name])
                out[name.lower()] = (name, pos)
    return list(out.values())


def build(src: Sources, plugin: str, form_id: int) -> bytes:
    """The FaceGeom NIF bytes of NPC `form_id` (local id) of `plugin`."""
    npc, race, female, face = npc_face(src, plugin, form_id)
    sculpt, parts = Sculpt(src, npc, female), []
    for part in head_parts(src, npc, race, female):
        model = zstr(part.first(b'MODL'))
        mesh = nif_file.read(src.read('meshes\\' + model))
        shape = Shape.of(mesh)
        shape.sculpt(sculpt, model)
        parts.append((part, mesh, shape))
    geom = FaceGeom(src, face, bone_nodes(parts, skeleton_nodes(src, race, female), race_height(race, female)))
    for part, mesh, shape in parts:
        geom.add(part, mesh, shape)
    return nif_file.write(geom.nif)


def main(argv=None) -> None:
    """Write one NPC's FaceGeom NIF to --out (scratch use: nothing in the build reads it)."""
    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument('--plugin', type=Path, required=True, help='the NPC\'s plugin (its masters are found in --dirs)')
    p.add_argument('--dirs', type=Path, nargs='*', default=[], help='folders holding masters, loose files and BA2s')
    p.add_argument('--npc', required=True, help='the NPC\'s FormID (hex; the plugin\'s own index is ignored)')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    src = Sources(args.plugin, [args.plugin.parent] + args.dirs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(build(src, args.plugin.name, int(args.npc, 16)))
    print('wrote', args.out)


if __name__ == '__main__':
    main()
