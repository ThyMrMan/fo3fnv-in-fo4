"""The props each FNV idle shows: vanilla stand-ins (havok.anim_props), then converted FNV props (havok.fnv_props).

An FNV ANIO whose model the stand-in table does not list becomes an FO4 ANIO
on FNV's FormID and EditorID, with its mesh converted (the chain flattened)
as `<name>_prop.nif` and hung from the FO4 prop bone (CellBuilder.prop_mesh),
and the unload event vanilla's all carry. One with no mesh, or whose `Prn`
names no FNV skeleton bone, is left out.

See: docs/fork/fo4_idles.md#converted-props
"""

from collections import defaultdict

import numpy as np

from fo4_import.base.writer import pack_fo4_record
from fo4_import.havok.anim_props import UNEQUIP, AnimProps
from fo4_import.havok.fnv_props import ConvertedProp, hand_turns, prop_bone
from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.outfit import fnv_nif, prn_bone
from fo4_import.pipeline.export_index import export_file, export_records
from tes5_import.base.writer import pack_string_subrecord

#: Record flags of all 145 Fallout4.esm ANIO records.
ANIO_FLAGS = 0x200
#: A flattened chain node's pose (posed()): at its parent's origin, unturned.
FLAT = ((0.0, 0.0, 0.0), [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])


class IdleProps:
    """{FNV idle: props}, a converted prop's mesh and ANIO written once through `builder`."""

    def __init__(self, builder, export_dir, clips):
        """Props of `export_dir`'s ANIO records; `clips` (HumanClips) gives the skeletons and the hands' turns."""
        self.builder, self.export_dir = builder, export_dir
        self.vanilla, self.turns, self.bones = AnimProps(export_dir), hand_turns(clips), set(clips.fnv.index)
        self.made, self.by_idle = {}, defaultdict(list)
        for rec in export_records(export_dir, 'ANIO'):
            if rec.get('DATA.Idle') and rec.get('Model.MODL', '').lower() not in self.vanilla.models:
                self.by_idle[int(rec['DATA.Idle'], 16)].append(rec)

    def get(self, idle: int) -> tuple:
        """The props FNV idle `idle` shows, one per FO4 prop bone, a vanilla stand-in first."""
        props = {p.bone: p for p in self.vanilla.get(idle)}
        for rec in self.by_idle.get(idle, ()):
            prop = self._prop(rec)
            if prop is not None:
                props.setdefault(prop.bone, prop)
        return tuple(props.values())

    def _prop(self, rec: dict) -> 'ConvertedProp | None':
        """FNV ANIO `rec` converted (its mesh and record written), once; None (counted) when left out."""
        fid = int(rec['FormID'], 16)
        if fid not in self.made:
            path = export_file(self.export_dir, 'meshes', rec['Model.MODL'].lower())
            root = fnv_nif(path) if path.is_file() else None
            parent = prn_bone(root) if root is not None else None
            self.made[fid] = self._converted(rec, root, parent) if parent in self.bones else None
            self.builder.counts['idle prop converted' if self.made[fid] else
                                'idle prop left out (no mesh or parent bone)'] += 1
        return self.made[fid]

    def _converted(self, rec: dict, root, parent: str) -> ConvertedProp:
        """ANIO `rec` with mesh `root` hanging from FNV bone `parent`: its mesh and record written."""
        chain = chain_of(root)
        bone = prop_bone(parent)
        model, _ = self.builder.prop_mesh(rec['Model.MODL'], {name: FLAT for name, _ in chain[1:]}, bone)
        self.builder.writer.add_record('ANIO', pack_anio(self.builder.fnv_id(rec['FormID']), rec['EditorID'], model))
        return ConvertedProp(rec['EditorID'], bone, None, (), {}, parent, tuple(chain), self.turns.get(parent))


def shape_count(node) -> int:
    """How many shapes (NiGeometry) are at or below FNV node `node`."""
    return sum(isinstance(n, NifFormat.NiGeometry) for n in node.tree())


def chain_of(root) -> list:
    """[(name, unscaled rest local 4x4)] from FNV prop `root` down to the node holding all its shapes."""
    chain, node, total = [], root, shape_count(root)
    while node is not None:
        local = np.array(node.get_transform().as_list(), dtype=np.float64)
        local[:3, :3] /= node.scale or 1.0
        chain.append((node.name.decode('cp1252'), local))
        kids = [c for c in node.children if isinstance(c, NifFormat.NiNode)] if total else []
        node = next((c for c in kids if shape_count(c) == total), None)
    return chain


def pack_anio(fid: int, edid: str, model: str) -> bytes:
    """FO4 ANIO `fid`: EditorID, model under Meshes and vanilla's unload event."""
    subs = pack_string_subrecord('EDID', edid) + pack_string_subrecord('MODL', model)
    return pack_fo4_record('ANIO', fid, ANIO_FLAGS, subs + pack_string_subrecord('BNAM', UNEQUIP))
