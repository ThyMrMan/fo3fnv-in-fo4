"""FNV creatures as Fallout 4 actors: the FO4 counterpart's NPC and race, wearing FNV's body.

A creature whose skeleton folder has an FO4 pair (nif.creature.PAIRS) is a
copy of the pair's vanilla NPC (Dogmeat for dogs) with its scripts,
factions, perks, spells and packages left out and a sandbox package; its
skin is a copy of the vanilla skin, whose addon shows FNV's body (its NIFZ
parts on the FO4 skeleton). Records are hashed from the FNV creature's
FormID, so none moves.

See: docs/fork/fo4_spikes.md#spike-4-creatures
"""

import struct
from pathlib import Path

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.writer import pack_fo4_record
from fo4_import.nif.convert_static import convert
from fo4_import.nif.creature import PAIRS, creature_fit, creature_mesh, skeleton_parents
from fo4_import.spike import records as R
from fo4_import.spike.statics import write_converted
from tes5_import.base.text_reader import parse_export_file
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: FNV creature skeleton folder -> the vanilla (NPC_, skin ARMO, its ARMA) a converted creature copies.
TEMPLATES = {'creatures\\dog': (0x1D15C, 0x1D725, 0x1D726)}
#: Vanilla DefaultSandboxEditorLocation, every converted creature's package for now.
SANDBOX = 0x107AEA
#: The vanilla NPC's ties to its own quests and character, left out of the copy.
DROPPED = frozenset({b'VMAD', b'SNAM', b'PRKZ', b'PRKR', b'SPCT', b'SPLO'})
SITE = 'FNV CREA'
#: A model's texture hash lists (MODT and the addon's MO2T-MO5T), which name the vanilla model's textures.
MODEL_TEXTURES = frozenset({b'MODT', b'MO2T', b'MO3T', b'MO4T', b'MO5T'})


def _folder(model: str) -> str:
    """An FNV creature model path's skeleton folder (`creatures\\dog`)."""
    return '\\'.join(model.replace('/', '\\').lower().split('\\')[:2])


class Creatures:
    """Makes FO4 actors of FNV creatures for one plugin."""

    def __init__(self, builder, export_dir: Path, data_dir: Path):
        """For `builder`'s plugin (its writer and Fallout4.esm bytes), FNV export `export_dir`, into `data_dir`."""
        self.builder, self.export_dir, self.data_dir = builder, export_dir, data_dir
        self.records = {int(r['FormID'], 16): r for r in parse_export_file(str(export_dir / 'CREA.txt'))}
        wanted = {fid for fids in TEMPLATES.values() for fid in fids}
        self.vanilla = {rec.form_id: rec for rec, _ in walk(builder.fo4, b'NPC_', b'ARMO', b'ARMA')
                        if rec.form_id in wanted}
        self.archives = Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Meshes.ba2')
        self.fits, self.meshes, self.made = {}, {}, {}

    def placed(self, edid: str, pos: tuple, rot: tuple) -> bytes:
        """An ACHR of FNV creature `edid` at `pos`, `rot` (hashed FormID)."""
        fnv = next(fid for fid, r in self.records.items() if r.get('EditorID') == edid)
        fid = self.builder.writer.derive_formid(SITE, f'{fnv:08X} ACHR')
        return R.pack_achr(fid, self.base(fnv), pos, rot)

    def base(self, fnv: int) -> int:
        """The FO4 NPC of FNV creature `fnv`: the pair's vanilla NPC copied, on a skin showing FNV's body."""
        if fnv in self.made:
            return self.made[fnv]
        rec = self.records[fnv]
        folder = _folder(rec['Model.MODL'])
        npc, skin, addon = (self.vanilla[f] for f in TEMPLATES[folder])
        model = self._mesh(rec, folder)
        key, write = f'{fnv:08X}', self.builder.writer
        arma, armo, fid = (write.derive_formid(SITE, f'{key} {part}') for part in ('ARMA', 'ARMO', 'NPC_'))
        edid = f'FNV_{rec["EditorID"]}'
        write.add_record('ARMA', _copy(addon, arma, f'{edid}AA', {b'MOD2': _zstr(model), b'MOD3': _zstr(model)}))
        write.add_record('ARMO', _copy(skin, armo, f'{edid}Skin', {b'MODL': struct.pack('<I', arma)}))
        edit = R.packages_edit([SANDBOX])
        write.add_record('NPC_', R.clone_npc(fid, npc.body, npc.flags, edid, rec.get('FULL', ''), DROPPED,
                                             edit=lambda subs: _replaced(edit(subs), {b'WNAM': struct.pack('<I', armo)})))
        self.builder.counts['creatures'] += 1
        self.made[fnv] = fid
        return fid

    def _mesh(self, rec: dict, folder: str) -> str:
        """FNV creature `rec`'s body (its NIFZ parts) on its pair's skeleton, written once; its FO4 model path."""
        names = [rec[f'NIFZ[{i}]'].lower() for i in range(int(rec.get('NIFZCount', 0)))]
        rel = f'{folder}\\{"_".join(n.rsplit(".", 1)[0] for n in names)}.nif'
        if rel not in self.meshes:
            if folder not in self.fits:
                self.fits[folder] = creature_fit(self.export_dir, folder, self.archives)
            fit = self.fits[folder]
            meshes = self.export_dir / 'meshes' / folder
            parts = [(convert(str(meshes / n), self.export_dir, animated=False), meshes / n) for n in names]
            body = creature_mesh(parts, fit, PAIRS[folder].rig.root, skeleton_parents(meshes / 'skeleton.nif'))
            self.meshes[rel] = write_converted(self.export_dir, body, rel, self.data_dir)[0]
        return self.meshes[rel]


def _zstr(text: str) -> bytes:
    """A NUL-ended cp1252 string's bytes."""
    return text.encode('cp1252') + b'\0'


def _replaced(subs: bytes, values: dict) -> bytes:
    """Subrecords `subs` with each tag in `values` given that data."""
    return b''.join(pack_subrecord(t.decode(), values.get(t, d)) for t, d in subrecords(subs))


def _copy(vanilla, fid: int, edid: str, values: dict) -> bytes:
    """Vanilla record `vanilla` as `fid` with EditorID `edid`, the subrecords in `values` replaced and the
    model texture lists (MODEL_TEXTURES, the vanilla model's) left out."""
    subs = _replaced(vanilla.body, values)
    subs = b''.join(pack_string_subrecord('EDID', edid) if t == b'EDID' else pack_subrecord(t.decode(), d)
                    for t, d in subrecords(subs) if t not in MODEL_TEXTURES)
    return pack_fo4_record(vanilla.sig.decode(), fid, vanilla.flags, subs)
