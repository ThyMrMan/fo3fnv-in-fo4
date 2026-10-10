"""An FNV NPC's head as the face spikes read it: head mesh, face texture, head parts, and its frame on FO4's head.

The head, FaceGen and race come from the export. FNV's NPC head parts (PNAM)
and HDPT models are not exported yet, so they are read from FalloutNV.esm.
The frame maps FNV head coordinates onto the FO4 head (face.bake.align).
FNV head parts carry no type: one centred below the eyes is facial hair,
one above them a brow, any other has no FO4 head part kind.

See: docs/fork/fo4_spikes.md#spike-2-hair
"""

import struct
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np

from asset_convert.sources import source_registry
from fo4_import.face import hair
from fo4_import.face.bake import align, surface
from fo4_import.face.fnv_head import FnvHead, coefficients, head
from fo4_import.face.texture import fnv_texture
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords, walk

#: FNV race head part index of the left eye mesh.
FNV_EYE_PART = 6


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
    return export_dir / folder / rel.replace(chr(92), '/').lower()


def npc_head(export_dir: Path, edid: str) -> tuple:
    """(FNV head, NPC record, race record, race head part key) of FNV NPC `edid`."""
    npc = next(r for r in export_records(export_dir, 'NPC_') if r.get('EditorID') == edid)
    race = record(export_dir, 'RACE', npc['RNAM.Race'])
    part = 'FemalePart[0]' if int(npc.get('ACBS.Flags', 0)) & 1 else 'MalePart[0]'
    model = first(race[part + '.Model'])
    return head(export_dir / 'meshes', model, npc.get('FGGS', ''), npc.get('FGGA', '')), npc, race, part


def fnv_face(export_dir: Path, edid: str) -> tuple:
    """(FNV head, (race head texture, colour offset)) of FNV NPC `edid`, from its race's head part and FaceGen."""
    fnv, npc, race, part = npc_head(export_dir, edid)
    egt = asset(export_dir, 'meshes', first(race[part + '.Model'])).with_suffix('.egt')
    texture = asset(export_dir, 'textures', first(race[part + '.Texture']))
    return fnv, fnv_texture(texture, egt, coefficients(npc.get('FGTS', ''), 50))


@cache
def _esm_records(esm_path: str) -> tuple:
    """({NPC FormID: [PNAM head part FormIDs]}, {HDPT FormID: (EditorID, model)}) of an FNV master."""
    npcs, parts = {}, {}
    for rec, _ in walk(Path(esm_path).read_bytes(), b'NPC_', b'HDPT'):
        subs = list(subrecords(rec.body))
        if rec.sig == b'NPC_':
            npcs[rec.form_id] = [struct.unpack('<I', d)[0] for t, d in subs if t == b'PNAM']
        else:
            fields = dict(subs)
            parts[rec.form_id] = (fields[b'EDID'].rstrip(b'\0').decode(),
                                  fields[b'MODL'].rstrip(b'\0').decode() if b'MODL' in fields else '')
    return npcs, parts


def head_parts(export_dir: Path, form_id: int) -> list:
    """[(EditorID, model)] of FNV NPC `form_id`'s head parts (PNAM) that have a model."""
    esm = Path(source_registry.directory_for(export_dir.parent, export_dir.name)) / export_dir.name
    npcs, parts = _esm_records(str(esm))
    return [parts[p] for p in npcs.get(form_id, []) if parts.get(p, ('', ''))[1]]


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


def sorted_parts(export_dir: Path, at: Frame) -> tuple:
    """([facial hair mesh paths], [brow mesh paths], [unmapped EditorIDs]) of the NPC's head parts."""
    facial, brows, unmapped = [], [], []
    for edid, model in head_parts(export_dir, int(at.npc['FormID'], 16)):
        path = asset(export_dir, 'meshes', model)
        centre = at.to_fo4(hair.fnv_shape(path)[0]).mean(0)[2]
        if centre < at.eyes[0]:
            facial.append(path)
        elif centre > at.eyes[1]:
            brows.append(path)
        else:
            unmapped.append(edid)
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
