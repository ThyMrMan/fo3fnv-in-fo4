"""An FNV NPC's hair, facial hair, eyes and hair colour chosen among FO4's (face.hair) for its clone.

The clone loses the stand-in's eye, hair and facial hair parts and their
extras, gains the chosen ones and their extras, and takes the chosen hair
colour (HCLF, which FO4 also uses for facial hair). FNV brows become tint
layers (spike.face_fit); FNV parts of no FO4 kind are reported.

See: docs/fork/fo4_spikes.md#spike-2-hair
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from fo4_import.face import hair
from fo4_import.face.bake import positions, triangles, uvs
from fo4_import.nif import file as nif_file
from fo4_import.spike import fnv_npc
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: FO4 HDPT types whose shapes are the skull that hides hair behind it: face, head rear.
SKULL_TYPES = (1, 9)


@dataclass
class HeadChoice:
    """The FO4 parts and hair colour chosen for one FNV NPC, with their coverage distances."""
    hair: int = None
    facial_hair: int = None
    eyes: int = None
    colour: int = None
    distances: dict = field(default_factory=dict)
    unmapped: list = field(default_factory=list)


def skull(assets: hair.Fo4Assets, baseline: bytes) -> tuple:
    """(face points, head depths per view) of the baseline FaceGen NIF's face and head rear parts."""
    nif = nif_file.read(baseline)
    types = {assets.edid(f): struct.unpack('<I', s[b'PNAM'][0])[0] for f, s in assets.parts.items() if b'PNAM' in s}
    shapes = [raw for kind, raw in nif.blocks if kind in hair.SHAPES and isinstance(raw, bytes)
              and types.get(nif.strings[struct.unpack_from('<i', raw, 0)[0]]) in SKULL_TYPES]
    face = max(shapes, key=lambda raw: len(positions(raw)))
    points = np.vstack([hair.samples(positions(r), triangles(r), uvs(r))[0] for r in shapes])
    return positions(face), hair.head_depths(points)


def _drawn_coverage(mesh: Path, drawn: np.ndarray, at: fnv_npc.Frame, depths: list) -> np.ndarray:
    """Coverage of an FNV hair or facial hair mesh drawn with RGBA `drawn`."""
    points, tris, uv, _ = hair.fnv_shape(mesh)
    spread, spread_uv = hair.samples(at.to_fo4(points), tris, uv)
    return hair.coverage([(spread, hair.texels(drawn, spread_uv)[:, 3] / 255)], depths)


def _hair(choice: HeadChoice, assets, export_dir: Path, at: fnv_npc.Frame, depths: list) -> None:
    """Choose the hair and the hair colour; none for a bald NPC (no HNAM)."""
    if 'HNAM.Hair' not in at.npc:
        return
    record = fnv_npc.record(export_dir, 'HAIR', at.npc['HNAM.Hair'])
    drawn = fnv_npc.hair_rgb(fnv_npc.asset(export_dir, 'textures', record['ICON']), at.npc)
    target = _drawn_coverage(fnv_npc.asset(export_dir, 'meshes', record['Model.MODL']), drawn, at, depths)
    choice.hair, choice.distances['hair'] = hair.best_part(assets, hair.HAIR, False, target, depths)
    _, material = assets.shapes(choice.hair)[0]
    choice.colour = hair.best_hair_colour(assets, assets.texture(material['textures']['diffuse']), material,
                                          hair.fnv_hair_colour(drawn))


def choose(export_dir: Path, edid: str, assets: hair.Fo4Assets, baseline: bytes) -> HeadChoice:
    """The FO4 hair, facial hair, eyes and hair colour for FNV NPC `edid` (male HumanRace); none for a part FNV
    leaves to the race (no HNAM, no ENAM)."""
    face, depths = skull(assets, baseline)
    at = fnv_npc.frame(export_dir, edid, face)
    choice = HeadChoice()
    _hair(choice, assets, export_dir, at, depths)
    facial, _, choice.unmapped = fnv_npc.sorted_parts(export_dir, at)
    for mesh in facial:
        drawn = hair.image(fnv_npc.mesh_texture(export_dir, mesh)).astype(float)
        choice.facial_hair, choice.distances['facial hair'] = hair.best_part(
            assets, hair.FACIAL_HAIR, False, _drawn_coverage(mesh, drawn, at, depths), depths)
    if 'ENAM.Eyes' not in at.npc:
        return choice
    eye_points, eye_tris, eye_uv, _ = hair.fnv_shape(fnv_npc.eye_mesh(export_dir, at.race, at.part))
    eyes = fnv_npc.record(export_dir, 'EYES', at.npc['ENAM.Eyes'])
    texture = hair.image(fnv_npc.asset(export_dir, 'textures', eyes['ICON']))
    choice.eyes = hair.best_eyes(assets, False, hair.iris_colour(eye_points, eye_tris, eye_uv, texture))
    return choice


def head_parts_edit(choice: HeadChoice, assets: hair.Fo4Assets):
    """A clone edit swapping in the chosen eyes, hair, facial hair (with extras) and hair colour; with no eyes
    chosen (an FNV NPC on its race's) the clone keeps its own, while no hair or facial hair means none."""
    replaced = (hair.HAIR, hair.FACIAL_HAIR) + ((hair.EYES,) if choice.eyes is not None else ())
    added = [q for p in (choice.eyes, choice.hair, choice.facial_hair) if p is not None for q in [p] + assets.extras(p)]

    def edit(subs: bytes) -> bytes:
        """The clone's subrecords with its head parts and hair colour replaced."""
        own = [struct.unpack('<I', d)[0] for t, d in subrecords(subs) if t == b'PNAM']
        dropped = {q for p in own if struct.unpack('<I', assets.parts[p].get(b'PNAM', [b'\0' * 4])[0])[0] in replaced
                   for q in [p] + assets.extras(p)}
        out, placed = b'', False
        for tag, data in subrecords(subs):
            if tag == b'PNAM' and not placed:
                out += b''.join(pack_subrecord('PNAM', struct.pack('<I', p)) for p in added)
                placed = True
            if tag == b'PNAM' and struct.unpack('<I', data)[0] in dropped:
                continue
            colour = tag == b'HCLF' and choice.colour is not None
            out += pack_subrecord(tag.decode(), struct.pack('<I', choice.colour) if colour else data)
        return out
    return edit
