"""FNV creatures as Fallout 4 actors.

Two ways, by the creature's skeleton folder:

- **FNV's body on its FO4 counterpart** (`TEMPLATES`, nif.creature.PAIRS):
  a copy of the pair's vanilla NPC (Dogmeat for dogs) with Dogmeat's
  scripts, factions, perks and spells left out and a sandbox package; its
  skin is a copy of the vanilla skin, whose addon shows FNV's body (its
  NIFZ parts on the FO4 skeleton).
- **An FO4 stand-in** (`STAND_INS`) for a creature with no FO4 counterpart:
  a copy of a vanilla creature of its size and role under FNV's name, its
  own body, animations and factions; only its scripts drop. A ported
  creature from the modlist replaces it through the replacement table.

Records are hashed from the FNV creature's FormID, so none moves.

See: docs/fork/fo4_spikes.md#spike-4-creatures
"""

import struct
from pathlib import Path

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.writer import pack_fo4_record
from fo4_import.nif.creature import PAIRS, creature_fit, creature_mesh, skeleton_parents
from fo4_import.spike import records as R
from fo4_import.spike.statics import write_converted
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.mesh_cache import cached_convert
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: Dogmeat's ties to his own quests and character, left out of a dog.
DOGMEAT_TIES = frozenset({b'VMAD', b'SNAM', b'PRKZ', b'PRKR', b'SPCT', b'SPLO'})
#: FNV creature skeleton folder -> the vanilla (NPC_, skin ARMO, its ARMA) a creature wearing FNV's body copies.
TEMPLATES = {'creatures\\dog': (0x1D15C, 0x1D725, 0x1D726)}
#: FNV creature skeleton folder with no FO4 counterpart -> the vanilla NPC_ standing in (EncMolerat01Template).
STAND_INS = {'creatures\\nvgecko': 0x1D966}
#: Vanilla DefaultSandboxEditorLocation, every converted creature's package for now.
SANDBOX = 0x107AEA
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
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'CREA')}
        wanted = {fid for fids in TEMPLATES.values() for fid in fids} | set(STAND_INS.values())
        self.vanilla = {rec.form_id: rec for rec, _ in walk(builder.fo4, b'NPC_', b'ARMO', b'ARMA')
                        if rec.form_id in wanted}
        self.archives = Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Meshes.ba2')
        self.fits, self.meshes, self.made, self.count = {}, {}, {}, {}

    def placed(self, edid: str, pos: tuple, rot: tuple) -> bytes:
        """An ACHR of FNV creature `edid` at `pos`, `rot` (FormID hashed from it and its placement count)."""
        fnv = next(fid for fid, r in self.records.items() if r.get('EditorID') == edid)
        n = self.count[fnv] = self.count.get(fnv, -1) + 1
        fid = self.builder.writer.derive_formid(SITE, f'{fnv:08X} ACHR' + (f' {n}' if n else ''))
        return R.pack_achr(fid, self.base(fnv), pos, rot)

    def base(self, fnv: int) -> int:
        """The FO4 NPC of FNV creature `fnv` (the module notes), made once."""
        if fnv not in self.made:
            rec = self.records[fnv]
            folder = _folder(rec['Model.MODL'])
            fid = self.builder.writer.derive_formid(SITE, f'{fnv:08X} NPC_')
            made = self._stand_in if folder in STAND_INS else self._worn
            made(fid, rec, folder)
            self.builder.counts['creatures'] += 1
            self.made[fnv] = fid
        return self.made[fnv]

    def _stand_in(self, fid: int, rec: dict, folder: str) -> None:
        """Write FNV creature `rec` as a copy of its vanilla stand-in under FNV's name, scripts dropped."""
        npc = self.vanilla[STAND_INS[folder]]
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, npc.body, npc.flags, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), frozenset({b'VMAD'}),
            edit=R.packages_edit([SANDBOX])))

    def _worn(self, fid: int, rec: dict, folder: str) -> None:
        """Write FNV creature `rec` as a copy of its pair's vanilla NPC on a skin showing FNV's body."""
        npc, skin, addon = (self.vanilla[f] for f in TEMPLATES[folder])
        model, write = self._mesh(rec, folder), self.builder.writer
        key, edid = f'{int(rec["FormID"], 16):08X}', f'FNV_{rec["EditorID"]}'
        arma, armo = (write.derive_formid(SITE, f'{key} {part}') for part in ('ARMA', 'ARMO'))
        write.add_record('ARMA', _copy(addon, arma, f'{edid}AA', {b'MOD2': _zstr(model), b'MOD3': _zstr(model)}))
        write.add_record('ARMO', _copy(skin, armo, f'{edid}Skin', {b'MODL': struct.pack('<I', arma)}))
        edit = R.packages_edit([SANDBOX])
        write.add_record('NPC_', R.clone_npc(fid, npc.body, npc.flags, edid, rec.get('FULL', ''), DOGMEAT_TIES,
                                             edit=lambda subs: _replaced(edit(subs), {b'WNAM': struct.pack('<I', armo)})))

    def _mesh(self, rec: dict, folder: str) -> str:
        """FNV creature `rec`'s body (its NIFZ parts) on its pair's skeleton, written once; its FO4 model path."""
        names = [rec[f'NIFZ[{i}]'].lower() for i in range(int(rec.get('NIFZCount', 0)))]
        rel = f'{folder}\\{"_".join(n.rsplit(".", 1)[0] for n in names)}.nif'
        if rel not in self.meshes:
            if folder not in self.fits:
                self.fits[folder] = creature_fit(self.export_dir, folder, self.archives)
            meshes = self.export_dir / 'meshes' / folder
            parts = [(cached_convert(meshes / n, self.export_dir, animated=False), meshes / n) for n in names]
            body = creature_mesh(parts, self.fits[folder], PAIRS[folder].rig.root,
                                 skeleton_parents(meshes / 'skeleton.nif'))
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
