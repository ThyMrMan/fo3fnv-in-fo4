"""An FNV NPC's head as the face spikes read it: head mesh, face texture, head parts, and its frame on FO4's head.

The head, FaceGen and race come from the export. FNV's NPC head parts (PNAM)
and HDPT models are not exported yet, so they are read from FalloutNV.esm.
The frame maps FNV head coordinates onto the FO4 head (face.bake.align).
FNV head parts carry no type: one drawn as hair (its mesh names a hair
layer) centred below the eyes is facial hair, one above them a brow; one
not drawn as hair (FNV's Eyepatch) is worn as its own part (worn_parts).

See: docs/fork/fo4_spikes.md#spike-2-hair
"""

import struct
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np

from fo4_import.face import hair
from fo4_import.face.bake import align, surface
from fo4_import.face.fnv_head import FnvHead, coefficients, head
from fo4_import.face.texture import fnv_texture, rgb
from fo4_import.nif import fnv_file
from fo4_import.nif.convert_static import smoothness, spec_image
from fo4_import.pipeline.export_index import asset_root, export_file, export_records, plugin_sources
from fo4_import.pipeline.master_plugin import renumbered
from fo4_import.pipeline.master_space import identity
from tes5_import.base.tes5_reader import subrecords, walk

#: FNV race head part index of the left eye mesh.
FNV_EYE_PART = 6
#: FNV texture set slot of a hair layer (_hl), which only the head parts FNV draws as hair name.
HAIR_LAYER = 2
#: Per race head part key, the head texture FNV's playable races share: the skin FO4's face bases stand for.
STOCK_SKIN = {'MalePart[0]': 'characters\\male\\headhuman.dds', 'FemalePart[0]': 'characters\\female\\headhuman.dds'}


@dataclass
class Frame:
    """An FNV NPC on the FO4 head: its head, records, FNV-to-FO4 mapping and eye height range (FO4 z)."""
    fnv: FnvHead
    npc: dict
    race: dict
    part: str
    to_fo4: object
    eyes: tuple


def first(value):
    """An export value that may repeat: its first."""
    return value[0] if isinstance(value, list) else value


def record(export_dir: Path, kind: str, form_id: str) -> dict:
    """An exported record by FormID."""
    return next(r for r in export_records(export_dir, kind) if r['FormID'] == form_id)


def asset(export_dir: Path, folder: str, rel: str) -> Path:
    """An exported asset's path (lower case, forward slashes) under `folder`."""
    return export_file(export_dir, folder, rel.replace(chr(92), '/').lower())


def npc_race(export_dir: Path, edid: str) -> tuple:
    """(NPC record, race record, race head part key) of FNV NPC `edid`."""
    npc = next(r for r in export_records(export_dir, 'NPC_') if r.get('EditorID') == edid)
    race = record(export_dir, 'RACE', npc['RNAM.Race'])
    return npc, race, 'FemalePart[0]' if int(npc.get('ACBS.Flags', 0)) & 1 else 'MalePart[0]'


def npc_head(export_dir: Path, edid: str) -> tuple:
    """(FNV head, NPC record, race record, race head part key) of FNV NPC `edid`."""
    npc, race, part = npc_race(export_dir, edid)
    model = first(race[part + '.Model'])
    return head(asset_root(export_dir, 'meshes'), model, npc.get('FGGS', ''), npc.get('FGGA', '')), npc, race, part


def fnv_face(export_dir: Path, edid: str) -> tuple:
    """(FNV head, (stock skin, FaceGen colour offset, race skin minus stock skin or None)) of FNV NPC `edid`,
    from its race's head part and FaceGen; None (and the race's skin as stock) on a race using STOCK_SKIN. All
    are in the race texture's size and UV layout.
    See: docs/fork/fo4_facegen_plan.md#race-skin
    """
    fnv, npc, race, part = npc_head(export_dir, edid)
    egt = asset(export_dir, 'meshes', first(race[part + '.Model'])).with_suffix('.egt')
    texture = asset(export_dir, 'textures', first(race[part + '.Texture']))
    skin, offset = fnv_texture(texture, egt, coefficients(npc.get('FGTS', ''), 50))
    stock = asset(export_dir, 'textures', STOCK_SKIN[part])
    if stock == texture or not stock.is_file():
        return fnv, (skin, offset, None)
    stock = rgb(stock, skin.shape[:2])
    return fnv, (stock, offset, skin - stock)


def fnv_shine(export_dir: Path, edid: str) -> np.ndarray:
    """FNV NPC `edid`'s skin shine as an FO4 specular map image (spec_image, float) in its head's UVs: the alpha
    of the race head texture's normal map (else the head mesh's own) at the head material's glossiness.
    See: docs/fork/fo4_facegen_plan.md#fnv-shine
    """
    _, race, part = npc_race(export_dir, edid)
    blocks = fnv_file.read(asset(export_dir, 'meshes', first(race[part + '.Model']))).blocks
    glossiness = next(b.glossiness for b in blocks if hasattr(b, 'glossiness'))
    normal = asset(export_dir, 'textures', first(race[part + '.Texture'])[:-4] + '_n.dds')
    if not normal.is_file():
        textures = next(b.textures for b in blocks if type(b).__name__ == 'BSShaderTextureSet')
        normal = asset(export_dir, '', str(textures[1]))
    return spec_image(normal.read_bytes(), smoothness(glossiness)).astype(float)


@cache
def _esm_records(esm_path: Path, mapping: tuple, game: str) -> tuple:
    """({NPC: [PNAM head parts]}, {HDPT: (EditorID, model)}) of an FNV plugin, FormIDs through `mapping`."""
    npcs, parts, raw = {}, {}, Path(esm_path).read_bytes()
    for rec, _ in walk(renumbered(raw, mapping, game) if mapping and not identity(mapping) else raw, b'NPC_', b'HDPT'):
        subs = list(subrecords(rec.body))
        if rec.sig == b'NPC_':
            npcs[rec.form_id] = [struct.unpack('<I', d)[0] for t, d in subs if t == b'PNAM']
        else:
            fields = dict(subs)
            parts[rec.form_id] = (fields[b'EDID'].rstrip(b'\0').decode(),
                                  fields[b'MODL'].rstrip(b'\0').decode() if b'MODL' in fields else '')
    return npcs, parts


def head_parts(export_dir: Path, form_id: int) -> list:
    """Sorted [(EditorID, model)] of the NPC's owned_parts: PNAM order changes no fit.
    See: docs/fork/fo4_pipeline.md#face-fit-head-parts
    """
    return sorted((edid, model) for _, edid, model in owned_parts(export_dir, form_id))


def worn_parts(export_dir: Path, form_id: int) -> list:
    """Sorted owned_parts of the NPC not drawn as hair (hair_drawn): the eyepatch.
    See: docs/fork/fo4_spikes.md#spike-2-hair
    """
    return sorted(p for p in owned_parts(export_dir, form_id) if not hair_drawn(asset(export_dir, 'meshes', p[2])))


def owned_parts(export_dir: Path, form_id: int) -> list:
    """[(HDPT FormID, EditorID, model)] of FNV NPC `form_id`'s head parts (PNAM) that have a model, in PNAM order,
    from the newest plugin of `export_dir`'s master chain holding it (a DLC build fits its masters' NPCs too), its
    parts from any of them. FNV draws them as a set.
    See: docs/fork/fo4_pipeline.md#face-fit-head-parts
    """
    chain, parts = _head_chain(str(export_dir))
    owned = next((npcs[form_id] for npcs in chain if form_id in npcs), [])
    return [(p, *parts[p]) for p in owned if parts.get(p, ('', ''))[1]]


@cache
def _head_chain(export_dir: str) -> tuple:
    """([{NPC: [PNAM head parts]}] of `export_dir`'s master chain, newest first; {HDPT: (EditorID, model)} of the
    chain, the newest plugin's winning), once per process.
    See: docs/fork/fo4_build_speed.md#staged-first
    """
    chain = [_esm_records(*source) for source in plugin_sources(export_dir)]
    parts = {}
    for _, held in chain:
        parts = {**held, **parts}
    return [npcs for npcs, _ in chain], parts


def eye_mesh(export_dir: Path, race: dict, part: str) -> Path:
    """The FNV race's left eye mesh for the head part key `part`."""
    return asset(export_dir, 'meshes', race[part.replace('[0]', f'[{FNV_EYE_PART}]') + '.Model'])


def frame(export_dir: Path, edid: str, fo4_face: np.ndarray) -> Frame:
    """FNV NPC `edid` placed on the FO4 face `fo4_face` (its vertex positions)."""
    fnv, npc, race, part = npc_head(export_dir, edid)
    s, r, t = align(fo4_face, fnv.mean, surface(fnv.mean, fnv.triangles))
    to_fo4 = lambda p: ((p - t) @ r) / s
    eye_z = to_fo4(hair.fnv_shape(eye_mesh(export_dir, race, part))[0])[:, 2]
    return Frame(fnv, npc, race, part, to_fo4, (eye_z.min(), eye_z.max()))


@cache
def hair_drawn(mesh: Path) -> bool:
    """Whether FNV head part mesh `mesh` names a hair layer (HAIR_LAYER)."""
    sets = [b.textures for b in fnv_file.read(mesh).blocks if type(b).__name__ == 'BSShaderTextureSet']
    return any(len(t) > HAIR_LAYER and t[HAIR_LAYER] for t in sets)


def sorted_parts(export_dir: Path, at: Frame) -> tuple:
    """([facial hair mesh paths], [brow mesh paths], [unmapped EditorIDs]) of the NPC's head parts; a part not
    drawn as hair (hair_drawn) is unmapped wherever it sits.
    See: docs/fork/fo4_spikes.md#spike-2-hair
    """
    facial, brows, unmapped = [], [], []
    for edid, model in head_parts(export_dir, int(at.npc['FormID'], 16)):
        path = asset(export_dir, 'meshes', model)
        centre = at.to_fo4(hair.fnv_shape(path)[0]).mean(0)[2] if hair_drawn(path) else None
        if centre is None or at.eyes[0] <= centre <= at.eyes[1]:
            unmapped.append(edid)
        elif centre < at.eyes[0]:
            facial.append(path)
        else:
            brows.append(path)
    return facial, brows, unmapped


def hair_rgb(texture_path: Path, npc: dict) -> np.ndarray:
    """The colours FNV draws a hair texture in for `npc` (its _hl layer and HCLR), with the texture's alpha."""
    layer = texture_path.with_name(texture_path.stem + '_hl.dds')
    texture = hair.image(texture_path)
    return hair.fnv_hair_rgb(texture, hair.image(layer) if layer.exists() else texture,
                             tuple(int(npc[f'HCLR.{c}']) for c in 'RGB'))


def mesh_texture(export_dir: Path, mesh: Path) -> Path:
    """An FNV head part mesh's own base texture."""
    return asset(export_dir, '', hair.fnv_shape(mesh)[3])
