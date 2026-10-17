"""FNV creatures as Fallout 4 actors.

Two ways, by the creature's skeleton folder:

- **FNV's body on its FO4 counterpart** (`TEMPLATES`, nif.creature.PAIRS):
  a copy of the pair's vanilla NPC (Dogmeat for dogs) with Dogmeat's
  scripts, factions, perks and spells left out and a sandbox package; its
  skin is a copy of the vanilla skin, whose addon shows FNV's body (its
  NIFZ parts on the FO4 skeleton).
- **An FO4 stand-in** (`STAND_INS`): FO4's own kind (bloatfly, radscorpion,
  deathclaw, ghoul, brahmin, robots), else the nearest in size and role: a
  copy of the vanilla creature under FNV's name, its own body, animations
  and factions; only its scripts drop. A ported creature from the modlist
  replaces it through the replacement table.

Templated creatures and leveled creature lists become FO4 template actors,
as leveled NPCs do (npcs.py).

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
from fo4_import.spike.actor_data import CREATURE_FLAGS, with_actor_data
from fo4_import.spike.npcs import (USE_AI_DATA, USE_FACTIONS, USE_INVENTORY, USE_STATS, composed, faction_snams,
                                   with_factions)
from fo4_import.spike.statics import write_converted
from fo4_import.spike.voice import fnv_folder
from fo4_import.spike.voice_types import VoiceTypes, fnv_voice_types, with_voice
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.mesh_cache import cached_convert
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: Dogmeat's ties to his own quests and character, left out of a dog.
DOGMEAT_TIES = frozenset({b'VMAD', b'SNAM', b'PRKZ', b'PRKR', b'SPCT', b'SPLO'})
#: FNV creature skeleton folder -> the vanilla (NPC_, skin ARMO, its ARMA) a creature wearing FNV's body copies.
TEMPLATES = {'creatures\\dog': (0x1D15C, 0x1D725, 0x1D726)}
#: FNV creature skeleton folder -> the vanilla NPC_ (EditorID) standing in: FO4's own kind, else the nearest.
STAND_INS = {'creatures\\nvgecko': 'EncViciousDog01Template','creatures\\molerat': 'EncMolerat01Template',
             'creatures\\blowfly': 'EncBloatfly01Template', 'creatures\\radscorpion': 'EncRadscorpion01Template',
             'creatures\\deathclaw': 'EncDeathclaw01Template', 'creatures\\radroach': 'EncRadRoach',
             'creatures\\ghoul': 'encFeralGhoul01Template', 'creatures\\brahmin': 'EncBrahminTemplate',
             'creatures\\nvbighorner': 'EncBrahminTemplate', 'creatures\\eyebot': 'EncEyeBot',
             'creatures\\protectron': 'EncProtectron01Template', 'creatures\\nvsecuritron': 'EncProtectron01Template',
             'creatures\\nvmantis': 'EncStingwing01Template'}
#: FNV creature DATA stats as FO4 actor values (Fallout4.esm AVIF): Health, S.P.E.C.I.A.L., attack damage.
STATS = {'DATA.Health': 0x2D4, 'DATA.Strength': 0x2C2, 'DATA.Perception': 0x2C3, 'DATA.Endurance': 0x2C4,
         'DATA.Charisma': 0x2C5, 'DATA.Intelligence': 0x2C6, 'DATA.Agility': 0x2C7, 'DATA.Luck': 0x2C8,
         'DATA.AttackDamage': 0x2DF}
HEALTH = 0x2D4
#: Health FO4 adds to an NPC per level past 1 (GMST fNPCHealthLevelBonus).
LEVEL_HEALTH = 5.0
#: ACBS flag PC Level Mult: the level is a multiplier of the player's, not a number.
PC_LEVEL_MULT = 0x80
#: A stand-in's own ties a creature leaves out: scripts and its factions (FNV's go in their place).
STAND_IN_TIES = frozenset({b'VMAD', b'SNAM'})
#: Vanilla DefaultSandboxEditorLocation, the package of a converted creature none of whose FNV packages convert.
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
        wanted, names = {fid for fids in TEMPLATES.values() for fid in fids}, set(STAND_INS.values())
        self.vanilla, self.stand_ins, self.race_health = {}, {}, {}
        for rec, _ in walk(builder.fo4, b'NPC_', b'ARMO', b'ARMA', b'RACE'):
            if rec.sig == b'RACE':
                self.race_health[rec.form_id] = _health(rec.body)
                continue
            edid = (dict(subrecords(rec.body)).get(b'EDID') or b'').rstrip(b'\0').decode()
            if rec.form_id in wanted or edid in names:
                self.vanilla[rec.form_id] = rec
                self.stand_ins[edid] = rec.form_id
        self.archives = Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Meshes.ba2')
        self.fits, self.meshes, self.made = {}, {}, {}
        self.voices = VoiceTypes(builder)

    def converts(self, fnv: int) -> bool:
        """Whether FNV creature `fnv` has a pair or a stand-in (TEMPLATES, STAND_INS)."""
        rec = self.records.get(fnv)
        return rec is not None and 'Model.MODL' in rec and _folder(rec['Model.MODL']) in {*TEMPLATES, *STAND_INS}

    def base(self, fnv: int, packages: list = ()) -> int:
        """The FO4 NPC of FNV creature `fnv` (the module notes) running `packages` (else SANDBOX), made once."""
        if fnv not in self.made:
            rec = self.records[fnv]
            folder = _folder(rec['Model.MODL'])
            fid = self.builder.writer.derive_formid(SITE, f'{fnv:08X} NPC_')
            made = self._stand_in if folder in STAND_INS else self._worn
            made(fid, rec, folder, list(packages) or [SANDBOX])
            self.builder.counts['creatures'] += 1
            self.made[fnv] = fid
        return self.made[fnv]

    def _stand_in(self, fid: int, rec: dict, folder: str, packages: list) -> None:
        """Write FNV creature `rec` as a copy of its vanilla stand-in under FNV's name, scripts dropped."""
        npc = self.vanilla[self.stand_ins[STAND_INS[folder]]]
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, npc.body, npc.flags, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), STAND_IN_TIES,
            edit=composed(R.packages_edit(packages), self._actor_data(rec), self._voice(rec),
                          *self.own_parts(rec))))

    def stand_in(self, fnv: int):
        """The vanilla NPC_ record FNV creature `fnv`'s model stands in as (STAND_INS, TEMPLATES); None without."""
        folder = _folder(self.records[fnv].get('Model.MODL', ''))
        if folder in STAND_INS:
            return self.vanilla[self.stand_ins[STAND_INS[folder]]]
        return self.vanilla[TEMPLATES[folder][0]] if folder in TEMPLATES else None

    def own_parts(self, rec: dict, templated: bool = False) -> tuple:
        """Edits giving creature `rec` its stats, factions and death item: on a template actor (`templated`) only
        the parts its template does not give; on a plain copy, each from the FNV record its template chain takes
        it from."""
        if templated:
            inherited = int(rec.get('ACBS.TemplateFlags', 0)) if 'TPLT.Template' in rec else 0
            return (None if inherited & USE_STATS else with_stats(rec, self.race_health),
                    None if inherited & USE_FACTIONS else with_factions(faction_snams(rec, self.builder.factions)),
                    self._death_item({} if inherited & USE_INVENTORY else rec))
        factions = faction_snams(self.source(rec, USE_FACTIONS), self.builder.factions)
        return (with_stats(self.source(rec, USE_STATS), self.race_health), with_factions(factions),
                self._death_item(self.source(rec, USE_INVENTORY)))

    def _death_item(self, rec: dict):
        """An edit putting FNV creature `rec`'s death item (INAM) in the stand-in's place; dropped if none converts."""
        fnv = rec.get('INAM.DeathItem')
        item = self.builder.items.item(int(fnv, 16)) if fnv else None

        def edit(subs: bytes) -> bytes:
            """The subrecords with the death item replaced or left out."""
            return b''.join(pack_subrecord(tag.decode(), struct.pack('<I', item) if tag == b'INAM' else data)
                            for tag, data in subrecords(subs) if tag != b'INAM' or item)
        return edit

    def _actor_data(self, rec: dict):
        """The ACBS/AIDT edit of plain copy `rec`, each from its template chain's record."""
        return with_actor_data(self.source(rec, USE_STATS), self.source(rec, USE_AI_DATA), CREATURE_FLAGS)

    def source(self, rec: dict, flag: int) -> dict:
        """The FNV creature `rec` takes template part `flag` from: along its creature templates, else itself."""
        seen = rec
        while int(seen.get('ACBS.TemplateFlags', 0)) & flag and 'TPLT.Template' in seen:
            nxt = self.records.get(int(seen['TPLT.Template'], 16))
            if nxt is None:
                break
            seen = nxt
        return seen

    def _voice(self, rec: dict):
        """`rec`'s FNV voice type (VTCK edit) if recorded; None keeps the body's."""
        fnv = int(rec.get('VTCK.Voice', '0'), 16)
        edid = fnv_voice_types().get(fnv, ('',))[0]
        return with_voice(self.voices.of(fnv)) if edid and fnv_folder(self.export_dir, edid).is_dir() else None

    def _worn(self, fid: int, rec: dict, folder: str, packages: list) -> None:
        """Write FNV creature `rec` as a copy of its pair's vanilla NPC on a skin showing FNV's body."""
        npc, skin, addon = (self.vanilla[f] for f in TEMPLATES[folder])
        model, write = self._mesh(rec, folder), self.builder.writer
        key, edid = f'{int(rec["FormID"], 16):08X}', f'FNV_{rec["EditorID"]}'
        arma, armo = (write.derive_formid(SITE, f'{key} {part}') for part in ('ARMA', 'ARMO'))
        write.add_record('ARMA', _copy(addon, arma, f'{edid}AA', {b'MOD2': _zstr(model), b'MOD3': _zstr(model)}))
        write.add_record('ARMO', _copy(skin, armo, f'{edid}Skin', {b'MODL': struct.pack('<I', arma)}))
        edit = composed(R.packages_edit(packages), self._actor_data(rec), self._voice(rec),
                        *self.own_parts(rec))
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


def with_stats(rec: dict, race_health: dict):
    """A record edit setting PRPS's Health, S.P.E.C.I.A.L. and unarmed damage to FNV creature `rec`'s (STATS),
    the rest kept. FO4 adds the race's health (`race_health` {RACE: Health}) and a per-level bonus to the NPC's,
    so the NPC's is FNV's less those, and the creature has FNV's health in game.
    See: docs/fork/fo4_pipeline.md#creature-stats
    """
    values = {av: float(rec[key]) for key, av in STATS.items() if key in rec}

    def edit(subs: bytes) -> bytes:
        """The subrecords with PRPS updated."""
        found = dict(subrecords(subs))
        added = race_health.get(struct.unpack('<I', found[b'RNAM'])[0], 0.0) if b'RNAM' in found else 0.0
        flags, _, level = struct.unpack_from('<IhH', found[b'ACBS']) if b'ACBS' in found else (PC_LEVEL_MULT, 0, 1)
        added += 0.0 if flags & PC_LEVEL_MULT else LEVEL_HEALTH * max(level - 1, 0)
        own = {**values, HEALTH: values[HEALTH] - added} if HEALTH in values else values
        out = b''
        for tag, data in subrecords(subs):
            if tag == b'PRPS':
                pairs = {**dict(struct.unpack_from('<If', data, i) for i in range(0, len(data), 8)), **own}
                data = b''.join(struct.pack('<If', av, value) for av, value in pairs.items())
            out += pack_subrecord(tag.decode(), data)
        return out
    return edit


def _health(body: bytes) -> float:
    """A RACE's starting Health (PRPS), 0 without one."""
    data = dict(subrecords(body)).get(b'PRPS', b'')
    return dict(struct.unpack_from('<If', data, i) for i in range(0, len(data), 8)).get(HEALTH, 0.0)


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
