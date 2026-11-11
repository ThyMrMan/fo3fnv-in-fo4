"""FNV creatures as Fallout 4 actors.

Each creature takes the replacement table's creature entry for its
EditorID, else the rule for an ability of its own (`_rules.ability`), else
the rule for its skeleton folder (`_rules.creature`), in one of three modes:

- **`fnv`, FNV's body on its FO4 counterpart** (only where nif.creature.PAIRS
  has the folder): a copy of the target NPC (Dogmeat for dogs, the super
  mutant template for super mutants) with its scripts and factions left out,
  a unique one's perks and spells too, and a sandbox package; its skin is a
  copy of the target's skin (WNAM), whose addon (the skin's first MODL) shows
  FNV's body (its NIFZ parts on the FO4 skeleton), head included. A pair worn
  over FO4's own body (super mutants) lists FO4's body addon first, tinted to
  FNV's skin (creature_tint, an MSWP), then FNV's head and armor.
- **`stats`, an FO4 stand-in**: FO4's own kind (bloatfly, radscorpion,
  deathclaw, ghoul, brahmin, robots), else the nearest in size and role: a
  copy of the target creature under FNV's name, its own body, animations
  and factions; only its scripts drop.
- **`item`, the target as it is** (a DLC's or a mod's creature, or a
  Fallout4.esm one): nothing is written; its references and lists name it.

Templated creatures and leveled creature lists become FO4 template actors,
as leveled NPCs do (npcs.py).

Records are hashed from the FNV creature's FormID, so none moves.

See: docs/fork/fo4_spikes.md#spike-4-creatures
"""

import functools
import struct
from pathlib import Path

from fo4_import.helpers_plugin import form_id
from fo4_import.spike.type_tests import keywords_edit
from script_convert.constants import FALLOUT4_HELPER_CREATURE_KEYWORD
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.source_fault import without_fault
from fo4_import.nif.creature import PAIRS, creature_fit, creature_mesh, skeleton_parents, skin_texture
from fo4_import.spike import records as R
from fo4_import.spike.actor_data import (ACBS_ALLOW_PC_DIALOGUE, BASE_DATA_FLAGS, CREATURE_FLAGS, UNIQUE, hit_proof,
                                        with_actor_data)
from fo4_import.spike.creature_sounds import USE_MODEL, CreatureSounds
from fo4_import.spike.creature_tint import tinted, tinted_materials
from fo4_import.spike.npc_skills import with_creature_skills
from fo4_import.spike.attack_spells import AttackSpells
from fo4_import.spike.creature_attacks import attack_list, fnv_groups, race_attacks, with_attacks
from fo4_import.rig.build import Rigs
from fo4_import.rig.gun_mods import GunMods
from fo4_import.rig.table import rigs
from fo4_import.spike.creature_speed import Fo4Speeds, fnv_run_speed, heights, with_height, with_speed_mult
from fo4_import.spike.replacements import CREATURE_TYPES, creature_entry, targets
from fo4_import.spike.npcs import (USE_AI_DATA, USE_BASE_DATA, USE_FACTIONS, USE_INVENTORY, USE_SCRIPT, USE_STATS,
                                   USE_TRAITS, composed, faction_snams, script_of, template_source, vendor_snam,
                                   with_factions, with_inventory, with_script)
from fo4_import.spike.entry_condition import condition_of
from fo4_import.spike.stand_in_fields import checked
from fo4_import.spike.statics import write_converted
from fo4_import.spike.talking_machines import TalkingMachines
from fo4_import.spike.voice import fnv_folders, recorded
from fo4_import.spike.void_actors import copy_record
from fo4_import.spike.voice_types import VoiceTypes, fnv_voice_types, with_voice
from fo4_import.pipeline.export_index import asset_root, export_records
from fo4_import.pipeline.mesh_cache import cached_convert
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: A unique target's (Dogmeat's) ties to its own quests and character, left out of an `fnv` creature.
CHARACTER_TIES = frozenset({b'VMAD', b'SNAM', b'PRKZ', b'PRKR', b'SPCT', b'SPLO'})
#: BOD2 bit of slot 61 (FX), FNV's armor addon's own slot over FO4's body addon (fo4_spikes.md#spike-4-creatures).
FX_SLOT = 0x80000000
#: FNV creature DATA stats as FO4 actor values (Fallout4.esm AVIF): Health, S.P.E.C.I.A.L., attack damage.
STATS = {'DATA.Health': 0x2D4, 'DATA.Strength': 0x2C2, 'DATA.Perception': 0x2C3, 'DATA.Endurance': 0x2C4,
         'DATA.Charisma': 0x2C5, 'DATA.Intelligence': 0x2C6, 'DATA.Agility': 0x2C7, 'DATA.Luck': 0x2C8,
         'DATA.AttackDamage': 0x2DF}
HEALTH = 0x2D4
#: Health FO4 adds to an NPC per level past 1 (GMST fNPCHealthLevelBonus).
LEVEL_HEALTH = 5.0
#: FNV template flag Use Actor Effect List.
USE_SPELLS = 0x8
#: ACBS flag PC Level Mult: the level is a multiplier of the player's, not a number.
PC_LEVEL_MULT = 0x80
#: A stand-in's own ties a creature leaves out: scripts, factions (FNV's go in their place), short name (FNV has none).
STAND_IN_TIES = frozenset({b'VMAD', b'SNAM', b'SHRT', b'LTPT', b'LTPC'})
#: Vanilla DefaultSandboxEditorLocation, the package of a converted creature none of whose FNV packages convert.
SANDBOX = 0x107AEA
#: Fallout4.esm races whose graphs tunnel in combat: MoleratRace, RadScorpionRace, MirelurkHunterRace.
TUNNELING_RACES = frozenset({0x1D810, 0x636AB, 0x64C60})
#: Fallout4.esm DisableTunnelingKeyword (default object KeywordDisableTunneling_DO), as on LvlMoleratBomb.
DISABLE_TUNNELING = 0x22FC80
#: Fallout4.esm Protectron, Handy, SentryBot, Deathclaw, SupermutantBehemoth, MirelurkKing races (helpers_races).
GATED_RACES = frozenset({0xDFB33, 0x359F4, 0xAE0B7, 0x1DB4A, 0xBB7D9, 0xB7F91})
SITE = 'FNV CREA'
#: A model's texture hash lists (MODT and the addon's MO2T-MO5T), which name the vanilla model's textures.
MODEL_TEXTURES = frozenset({b'MODT', b'MO2T', b'MO3T', b'MO4T', b'MO5T'})
#: An addon's model -> its material swap (MSWP) subrecord, which follows it.
SWAPS = {b'MOD2': b'MO2S', b'MOD3': b'MO3S'}
#: FO4 items a stand-in fights with (non-playable, record flag 0x4: WeapEyebot, MirelurkShield; not its loot lists).
GEAR, NON_PLAYABLE = frozenset({b'WEAP', b'AMMO', b'ARMO'}), 0x4
#: A ranged rig's ammo per gun when its FNV record lists none of the gun's own, as Fallout4.esm's EncEyeBot carries.
ARMED_AMMO = 100
#: FNV WEAP DNAM Flags1 Embedded Weapon (0x20) and Non-Playable (0x80); FNV AMMO DATA Non-Playable (0x2).
FNV_WEAPON_GEAR, FNV_AMMO_NON_PLAYABLE = 0x20 | 0x80, 0x2
#: FO4 WEAP DNAM animation type byte and its first ranged type (Bow; then Staff, Gun, Grenade, Mine).
FO4_ANIM_TYPE, FO4_FIRST_RANGED = 54, 7
#: FNV WEAP DNAM animation type of its first ranged weapon (one-handed pistol; 0-2 are hand to hand and melee).
FNV_FIRST_RANGED = 3


def fnv_ranged(sig: 'str | None', rec: dict) -> bool:
    """Whether FNV item `rec` is a ranged weapon."""
    return sig == 'WEAP' and int(rec.get('DNAM.FalloutAnimType', 0) or 0) >= FNV_FIRST_RANGED


def fnv_gear(sig: 'str | None', rec: dict) -> bool:
    """Whether FNV item `rec` is attack gear (non-playable weapon or ammo)."""
    if sig == 'WEAP':
        return bool(int(rec.get('DNAM.Flags1', 0) or 0) & FNV_WEAPON_GEAR)
    return sig == 'AMMO' and bool(int(rec.get('DATA.Flags', 0) or 0) & FNV_AMMO_NON_PLAYABLE)


def skeleton_folder(model: str) -> str:
    """The folder holding FNV skeleton `model` (`creatures\\dog`); a bare name as is."""
    parts = model.replace('/', '\\').lower().split('\\')
    return '\\'.join(parts[:-1] or parts)


class Creatures:
    """Makes FO4 actors of FNV creatures for one plugin."""

    def __init__(self, builder, export_dir: Path, data_dir: Path):
        """For `builder`'s plugin (its writer and Fallout4.esm bytes), FNV export `export_dir`, into `data_dir`."""
        self.builder, self.export_dir, self.data_dir = builder, export_dir, data_dir
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'CREA')}
        table = builder.table
        keyed = {**table.rules.creature, **table.rules.ability, **table.creatures}
        self.npcs, self.worn, self.race_health, self.gear, self.ranged = self._index(builder.fo4, keyed)
        self.as_is = targets({k: e for k, e in keyed.items() if e.mode == 'item'}, builder.fo4, builder.masters,
                             builder.plugin_dirs, CREATURE_TYPES)
        self.archives = Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Meshes.ba2')
        self.fits, self.meshes, self.made, self.sized, self.skins = {}, {}, {}, {}, {}
        self.tint_archives, self.tinted, self.faces, self.face_sets = None, {}, {}, None
        self.rigs = None
        self.voices, self.race_attacks = VoiceTypes(builder), race_attacks(builder.fo4)
        self.speeds = Fo4Speeds(builder.fo4)
        self.sounds = CreatureSounds(builder, self.records)
        self.attack_spells, self.gun_mods = AttackSpells(builder), GunMods(builder)
        self.talking = TalkingMachines(builder, export_dir, data_dir)

    @staticmethod
    def _index(fo4: bytes, keyed: dict) -> tuple:
        """({EditorID lowercased: NPC_} of the Fallout4.esm targets in `keyed`, {EditorID: (NPC_, skin ARMO,
        addon ARMA)} of its `fnv` targets, {RACE: starting Health}, {its non-playable WEAP, AMMO, ARMO}, {its
        non-playable ranged WEAP: the AMMO it fires, 0 for none})."""
        wanted = {e.edid.lower() for e in keyed.values() if e.base}
        npcs, armor, race_health, gear, ranged = {}, {}, {}, set(), {}
        for rec, _ in walk(fo4, b'NPC_', b'ARMO', b'ARMA', b'RACE', b'WEAP', b'AMMO'):
            gear.update({rec.form_id} if rec.sig in GEAR and rec.flags & NON_PLAYABLE else set())
            ranged.update(_ranged_gear(rec) if rec.sig == b'WEAP' and rec.flags & NON_PLAYABLE else {})
            if rec.sig == b'RACE':
                race_health[rec.form_id] = _health(rec.body)
            elif rec.sig in (b'ARMO', b'ARMA'):
                armor[rec.form_id] = rec
            elif rec.sig == b'NPC_':
                edid = (dict(subrecords(rec.body)).get(b'EDID') or b'').rstrip(b'\0').decode().lower()
                npcs.update({edid: rec} if edid in wanted else {})
        worn = {}
        for edid in {e.edid.lower() for e in keyed.values() if e.base and e.mode == 'fnv'} & set(npcs):
            skin = armor[_form(npcs[edid], b'WNAM')]
            worn[edid] = (npcs[edid], skin, armor[_form(skin, b'MODL')])
        return npcs, worn, race_health, gear, ranged

    def inventory(self, rec: dict, body, outfit: bool, armed: bool = False):
        """The inventory edit of FNV creature `rec` on clone `body`: the body's attack gear (its non-playable
        items; its ranged weapon and ammo only when `rec` has a ranged weapon of its own) and the playable items of
        `rec`'s Inventory chain (its FNV guns too when `armed`: a ranged rig); the body's default outfit only when
        `outfit` (stats mode, which keeps FO4's look).
        See: docs/fork/fo4_creature_audit.md#inventory, docs/fork/fo4_creature_audit.md#deathclaws
        """
        found = list(subrecords(body.body))
        source = self.source(rec, USE_INVENTORY)
        dropped = set() if self._shoots(source) else {*self.ranged, *self.ranged.values()}
        gear = [(*struct.unpack_from('<Ii', d), None) for t, d in found
                if t == b'CNTO' and struct.unpack_from('<I', d)[0] in self.gear - dropped]
        doft = next((struct.unpack('<I', d)[0] for t, d in found if t == b'DOFT'), 0)
        return with_inventory(doft if outfit else 0, gear + self._carried(source, armed))

    def _shoots(self, rec: dict) -> bool:
        """Whether FNV creature `rec`'s inventory holds a ranged weapon (fnv_ranged)."""
        items = self.builder.items.records
        return any(fnv_ranged(*items.get(int(rec[f'Item[{i}].FormID'], 16), (None, {})))
                   for i in range(int(rec.get('ItemCount', 0) or 0)))

    def _carried(self, rec: dict, armed: bool = False) -> list:
        """[(FO4 item, count, condition)] of FNV creature `rec`'s items that convert, its attack gear (FNV's
        non-playable weapons and ammo: fnv_gear) left out; when `armed`, its guns kept, each with its FO4 ammo
        (_ammo), a creature gun copy left to its forced-inventory mod (_guns)."""
        out, items = [], self.builder.items
        for i in range(int(rec.get('ItemCount', 0) or 0)):
            fnv = int(rec[f'Item[{i}].FormID'], 16)
            sig, item = items.records.get(fnv, (None, {}))
            gun = armed and sig == 'WEAP'
            made = None if fnv_gear(sig, item) and not gun else items.item(fnv)
            out += self._ammo(rec, fnv, item) if made and gun else []
            self.builder.counts['creature item' if made else 'creature item left out (gear or not converted)'] += 1
            kept = made and not (gun and fnv in self.builder.equipment.creature_guns)
            out += [(made, int(rec[f'Item[{i}].Count']), condition_of(int(rec['FormID'], 16), i))] if kept else []
        return out

    def _guns(self, rec: dict) -> list:
        """[(FNV FormID, FO4 gun, equip slot)] of the creature gun copies in FNV creature `rec`'s inventory."""
        items, guns = self.builder.items, self.builder.equipment.creature_guns
        fnvs = [int(rec[f'Item[{i}].FormID'], 16) for i in range(int(rec.get('ItemCount', 0) or 0))]
        made = [(fnv, items.item(fnv)) for fnv in fnvs if items.records.get(fnv, (None,))[0] == 'WEAP']
        return [(fnv, gun, guns[fnv]) for fnv, gun in made if gun and fnv in guns]

    def own_guns(self, rec: dict) -> tuple:
        """(armed, gun-mod edit or None): whether `rec`'s own items hold creature guns."""
        guns = self._guns(rec) if self.source(rec, USE_INVENTORY) is rec else []
        return bool(guns), self.gun_mods.edit(guns) if guns else None

    def _ammo(self, rec: dict, fnv: int, gun: dict) -> list:
        """[(FO4 ammo, count, None)] for FNV creature `rec`'s gun `fnv` (`gun`): its FO4 copy's ammo, as many as `rec`
        carries of the gun's FNV ammo, else ARMED_AMMO; [] when the copy has none."""
        ammo = self.builder.equipment.weapon_ammo.get(fnv)
        own = [int(rec[f'Item[{i}].Count']) for i in range(int(rec.get('ItemCount', 0) or 0))
               if rec[f'Item[{i}].FormID'] == gun.get('NAM0')]
        return [(ammo, own[0] if own else ARMED_AMMO, None)] if ammo else []

    def _entry(self, rec: dict) -> tuple:
        """(entry, key) of FNV creature `rec` (replacements.creature_entry)."""
        return creature_entry(self.builder.table, rec, skeleton_folder(rec.get('Model.MODL', '')),
                              self.builder.perks.spell_names)[:2]

    def converts(self, fnv: int) -> bool:
        """Whether FNV creature `fnv` has an entry whose target is there (and, for `fnv`, a rig pair)."""
        rec = self.records.get(fnv)
        entry, key = self._entry(rec) if rec is not None else (None, '')
        if entry is None:
            return False
        if entry.mode == 'item':
            return key in self.as_is
        if entry.mode == 'fnv':
            return entry.edid.lower() in self.worn and skeleton_folder(rec.get('Model.MODL', '')) in PAIRS
        if entry.mode == 'rig' and skeleton_folder(rec.get('Model.MODL', '')) not in rigs():
            return False
        return entry.edid.lower() in self.npcs

    def base(self, fnv: int, packages: list = (), stats: dict = None) -> int:
        """The FO4 NPC of FNV creature `fnv` (the module notes) running `packages` (else SANDBOX), made once;
        with `stats` (stats and rig modes), a copy sized and sped as that FNV record's Stats give (traits_variant),
        kept apart from `made` ({FNV creature: its base}, which other stages read)."""
        made = self.sized if stats else self.made
        made_key = stats['FormID'] if stats else fnv
        if made_key not in made:
            rec = self.records[fnv]
            entry, key = self._entry(rec)
            if entry.mode == 'item':
                self.builder.counts['creatures (target as is)'] += 1
                made[made_key] = self.as_is[key]
                return made[made_key]
            fid = self.builder.writer.derive_formid(SITE, f'{fnv:08X} NPC_' + (f' size {made_key}' if stats else ''))
            rec = {**rec, 'EditorID': f'{stats["EditorID"]}Traits'} if stats else rec
            write = {'stats': self._stand_in, 'fnv': self._worn, 'rig': self._own_rig,
                     'speaker': self._speaker}[entry.mode]
            made[made_key] = fid
            write(fid, rec, entry, list(packages) or [SANDBOX], stats)
            self.builder.counts['creatures' if not stats else 'creature traits sized as a template actor'] += 1
        return made[made_key]

    def traits_variant(self, rec: dict) -> 'int | None':
        """For template actor `rec` whose own Stats size it apart from its traits creature: that creature's base
        at `rec`'s size, for its Traits slot (FO4 keeps height under Traits, FNV base scale under Stats); else
        None.
        See: docs/fork/fo4_creature_audit.md#own-size
        """
        traits, left = template_source(self.records, rec, USE_TRAITS)
        if left or int(rec.get('ACBS.TemplateFlags', 0)) & USE_STATS or self._base_scale(rec) == self._base_scale(traits):
            return None
        fnv, entry = int(traits['FormID'], 16), self._entry(traits)[0]
        if not self.converts(fnv) or entry.mode not in ('stats', 'fnv', 'rig'):
            return None
        return self.base(fnv, (), self.source(rec, USE_STATS))

    def _stand_in(self, fid: int, rec: dict, entry, packages: list, stats: dict = None) -> None:
        """Write FNV creature `rec` as a copy of its entry's target under FNV's name, the target's scripts dropped."""
        npc = self.npcs[entry.edid.lower()]
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, npc.body, npc.flags, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), STAND_IN_TIES,
            edit=checked(self.builder.counts, npc.body, rec['EditorID'], composed(
                R.packages_edit(packages), self._actor_data(rec), self._voice(rec), self._keywords(rec),
                self._combat_style(rec), self._attacks(rec, npc), *self.own_parts(rec),
                *self._sized(rec, npc, stats), self.inventory(rec, npc, True)))))

    def _speaker(self, fid: int, rec: dict, entry, packages: list, stats: dict = None) -> None:
        """Write FNV talking machine `rec` as an unseen speaker: a stand-in copy on the speaker race in its empty
        skin (talking_machines); its look is placed beside it (speaker_look)."""
        npc = self.npcs[entry.edid.lower()]
        race, skin = self.talking.race()
        edit = composed(R.packages_edit(packages), self._actor_data(rec), self._voice(rec), self._keywords(rec),
                        self._combat_style(rec), *self.own_parts(rec), self.inventory(rec, npc, False))
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, npc.body, npc.flags, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), STAND_IN_TIES,
            edit=checked(self.builder.counts, npc.body, rec['EditorID'],
                         lambda subs: _on_race(R.without_object_templates(edit(subs)), race, skin))))

    def speaker_look(self, fnv: int, achr: int, ref_key: str, placed: tuple) -> bytes:
        """Talking machine `fnv`'s look beside speaker `achr`; b'' otherwise."""
        rec = self.records.get(fnv)
        entry = self._entry(rec)[0] if rec is not None else None
        return self.talking.look(achr, rec, ref_key, placed) if entry is not None and entry.mode == 'speaker' else b''

    def screen_armor(self, face: str, expression: str) -> int:
        """Rigs.screen_armor: a securitron face's screen armor (0 without one)."""
        return self.own_rigs().screen_armor(face, expression)

    def own_rigs(self) -> Rigs:
        """The build's own-rig writer, made on first use."""
        self.rigs = self.rigs or Rigs(self.builder, self.export_dir, self.data_dir)
        return self.rigs

    def _own_rig(self, fid: int, rec: dict, entry, packages: list, stats: dict = None) -> None:
        """Write FNV creature `rec` on its own rig (fo4_import.rig): a copy of its entry's target NPC under FNV's
        name on the rig's race, wearing its own body's skin, at FNV's speed (the rig's movement type moves at
        FNV's clip speeds) and FNV's size (FNV's own mesh: height = base scale / the race's height, the race being
        the template's copy); its race's attacks are its own, in a list of its own casting its FNV attack spell
        when it has one (Rigs.attacks).
        See: docs/fork/fo4_own_rig.md#modules
        """
        self.own_rigs()
        rig = rigs()[skeleton_folder(rec['Model.MODL'])]
        members = [r for r in self.records.values() if skeleton_folder(r.get('Model.MODL', '')) == rig.folder]
        style = self.builder.combat_styles.record(self.source(rec, USE_TRAITS))
        talks = any(int(r.get('ACBS.Flags', 0) or 0) & ACBS_ALLOW_PC_DIALOGUE for r in members)
        race = self.rigs.race(rig, rec, style, self.sounds.rig(rig, members), talks)
        spell = self.attack_spells.of(self.source(rec, USE_SPELLS))
        skin = self.rigs.skin(rig, rec)
        npc = self.npcs[entry.edid.lower()]
        stats = stats or self.source(rec, USE_STATS)
        speed = float(stats.get('ACBS.SpeedMultiplier', 100) or 100)
        template_race = self.rigs.templates.get(b'RACE', rig.template['race'])[0].form_id
        height = self._base_scale(rec, stats) / self.speeds.race_height(template_race)
        edit = composed(R.packages_edit(packages), self._actor_data(rec), self._voice(rec), self._keywords(rec),
                        self._combat_style(rec), *self.own_parts(rec), with_speed_mult(speed),
                        with_height(height, height), self.inventory(rec, npc, False, bool(rig.guns)),
                        self.gun_mods.edit(self._guns(self.source(rec, USE_INVENTORY))) if rig.guns else None,
                        self.rigs.attacks(rig, race, style, spell) if spell else None)
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, npc.body, npc.flags, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), STAND_IN_TIES,
            edit=checked(self.builder.counts, npc.body, rec['EditorID'], lambda subs: _on_race(edit(subs), race, skin))))

    def _combat_style(self, rec: dict):
        """The ZNAM edit of plain copy `rec`: its traits source's FNV style, converted."""
        return self.builder.combat_styles.edit(self.source(rec, USE_TRAITS))

    def _attacks(self, rec: dict, npc):
        """The attack-list edit of FNV creature `rec` on stand-in NPC `npc` (creature_attacks); None when the
        stand-in's attack race has no attacks.
        See: docs/fork/fo4_pipeline.md#creature-attacks
        """
        found = dict(subrecords(npc.body))
        race = struct.unpack('<I', found.get(b'ATKR') or found[b'RNAM'])[0]
        attacks = self.race_attacks.get(race)
        if not attacks:
            return None
        style = self.builder.combat_styles.record(self.source(rec, USE_TRAITS))
        groups = fnv_groups(self.export_dir, skeleton_folder(rec.get('Model.MODL', '')))
        subs, count = attack_list(attacks, groups, style, self.attack_spells.of(self.source(rec, USE_SPELLS)))
        self.builder.counts['creature attacks kept'] += count
        self.builder.counts['creature attacks disabled'] += len(attacks) - count
        return with_attacks(race, subs)

    def _base_scale(self, rec: dict, stats: dict = None) -> float:
        """`rec`'s base scale: BNAM of `stats`, else its Stats chain's; 1 if none."""
        return float((stats or self.source(rec, USE_STATS)).get('BNAM.BaseScale', 1.0) or 1.0)

    def _sized(self, rec: dict, npc, stats: dict = None) -> tuple:
        """(height edit, SpeedMult edit) of FNV creature `rec` on stand-in `npc`: the stand-in's height range times
        FNV's base scale (the stand-in's body is sized for itself, so FNV's scale applies relative to it), and the
        SpeedMult giving FNV's run at that size; both from `stats` (else `rec`'s Stats chain); the SpeedMult edit
        None when either speed is unknown.
        See: docs/fork/fo4_pipeline.md#creature-speed
        """
        stats = stats or self.source(rec, USE_STATS)
        scale, subs = self._base_scale(rec, stats), dict(subrecords(npc.body))
        low, high = (h * scale for h in heights(subs))
        sized = {**subs, b'NAM6': struct.pack('<f', low), b'NAM4': struct.pack('<f', high)}
        fnv = fnv_run_speed(self.export_dir, skeleton_folder(rec.get('Model.MODL', '')), stats, scale)
        value = self.speeds.speed_mult(sized, fnv)
        self.builder.counts['creature speeds' if value else 'creature speeds unknown'] += 1
        return with_height(low, high), with_speed_mult(round(value, 1)) if value else None

    def _keywords(self, rec: dict):
        """FNV creature `rec`'s type keyword and its _race_keywords."""
        return keywords_edit(self.builder.type_keywords.of(int(rec['FormID'], 16)) + self._race_keywords(rec))

    def _race_keywords(self, rec: dict) -> list:
        """The keywords turning FO4-only race behaviour off for `rec`'s traits creature: DisableTunnelingKeyword on
        a tunneling race, the helper creature keyword on a race whose ability helpers_races gates.
        See: docs/fork/fo4_creature_audit.md#molerat-burrowing, docs/fork/fo4_creature_audit.md#race-abilities
        """
        entry = self._entry(self.source(rec, USE_TRAITS))[0]
        npc = self.npcs.get(entry.edid.lower()) if entry is not None and entry.mode != 'speaker' else None
        found = dict(subrecords(npc.body)) if npc is not None else {}
        race = struct.unpack('<I', found[b'RNAM'])[0] if b'RNAM' in found else 0
        gated = form_id(FALLOUT4_HELPER_CREATURE_KEYWORD, self.builder.scripts.helper_index)
        return [DISABLE_TUNNELING] if race in TUNNELING_RACES else [gated] if race in GATED_RACES else []

    def label(self, fnv: int) -> str:
        """FNV creature `fnv`'s skeleton folder, else its EditorID."""
        rec = self.records[fnv]
        return skeleton_folder(rec['Model.MODL']) if 'Model.MODL' in rec else rec.get('EditorID', f'{fnv:08X}')

    def keeps_look(self, fnv: int) -> bool:
        """Whether FNV creature `fnv` keeps its stand-in's look (mode `stats`)."""
        entry = self._entry(self.records[fnv])[0]
        return entry is not None and entry.mode == 'stats'

    def stand_in(self, fnv: int):
        """The Fallout4.esm NPC_ FNV creature `fnv`'s entry targets, or None."""
        entry = self._entry(self.records[fnv])[0]
        return self.npcs.get(entry.edid.lower()) if entry is not None and entry.base else None

    def _own_speed(self, rec: dict):
        """The SpeedMult edit of template actor `rec` with its own Stats: its FNV run at its own size on its traits
        creature's stand-in (the rig: FNV's SpeedMult itself); None when its traits come from a list or do not
        convert.
        See: docs/fork/fo4_creature_audit.md#own-size
        """
        traits, left = template_source(self.records, rec, USE_TRAITS)
        entry = None if left else self._entry(traits)[0]
        if entry is None or entry.mode not in ('stats', 'fnv', 'rig') or not self.converts(int(traits['FormID'], 16)):
            return None
        stats = self.source(rec, USE_STATS)
        if entry.mode == 'rig':
            return with_speed_mult(float(stats.get('ACBS.SpeedMultiplier', 100) or 100))
        return self._sized(traits, self.npcs[entry.edid.lower()], stats)[1]

    def own_parts(self, rec: dict, templated: bool = False) -> tuple:
        """Edits giving creature `rec` its stats and combat skill, factions (its vendor one too), death item, sounds
        and abilities: on a template actor (`templated`) only the parts its template does not give (its script:
        Npcs._template_script); on a plain copy, each from the FNV record its template chain takes it from, its
        script too."""
        vendor = vendor_snam(self.builder, int(rec['FormID'], 16))
        if templated:
            inherited = int(rec.get('ACBS.TemplateFlags', 0)) if 'TPLT.Template' in rec else 0
            factions = faction_snams(rec, self.builder.factions) + vendor
            return (None if inherited & USE_STATS else with_stats(rec, self.race_health),
                    None if inherited & USE_STATS else self._combat_skill(rec),
                    None if inherited & USE_STATS else self._own_speed(rec),
                    None if inherited & USE_FACTIONS else with_factions(factions),
                    self._death_item({} if inherited & USE_TRAITS else rec),
                    self.sounds.edit(rec) if self.sounds.source(rec) or not inherited & USE_MODEL else None,
                    None if inherited & USE_SPELLS else self._spells(rec),
                    None if template_source(self.records, rec, USE_TRAITS)[1] else self._keywords(rec))
        factions = faction_snams(self.source(rec, USE_FACTIONS), self.builder.factions) + vendor
        return (with_stats(self.source(rec, USE_STATS), self.race_health), self._combat_skill(self.source(rec, USE_STATS)),
                with_factions(factions),
                self._death_item(self.source(rec, USE_TRAITS)), self.sounds.edit(rec),
                self._spells(self.source(rec, USE_SPELLS)),
                with_script(self.builder.scripts, script_of(self.source(rec, USE_SCRIPT))))

    def _combat_skill(self, rec: dict):
        """FNV creature `rec`'s Combat Skill edit (npc_skills); None without."""
        return with_creature_skills(int(rec['FormID'], 16), self.builder.scripts.helper_index)

    def _spells(self, rec: dict):
        """An edit adding `rec`'s abilities (Perks.ability); None without any."""
        found = (self.builder.perks.ability(int(rec[f'Spell[{i}]'], 16)) for i in range(int(rec.get('SpellCount', 0))))
        spells = [fid for fid in found if fid]
        return with_spells(spells) if spells else None

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
        """The ACBS/AIDT edit of plain copy `rec`, each from its template chain's record: the level band and PC
        Level Mult from Stats, Essential, Respawn, Is Ghost and Invulnerable from Base Data.
        See: docs/fork/fo4_creature_audit.md#base-data
        """
        stats, base = self.source(rec, USE_STATS), self.source(rec, USE_BASE_DATA)
        flags = int(stats.get('ACBS.Flags', 0) or 0) & ~BASE_DATA_FLAGS
        flags |= int(base.get('ACBS.Flags', 0) or 0) & BASE_DATA_FLAGS
        return self.actor_data(rec, {**stats, 'ACBS.Flags': str(flags)}, self.source(rec, USE_AI_DATA))

    def actor_data(self, rec: dict, stats: dict, ai: dict):
        """with_actor_data of creature `rec` from `stats` and `ai` (hit_proof)."""
        return with_actor_data(stats, ai, CREATURE_FLAGS, hit_proof(self.export_dir, self.source(rec, USE_SCRIPT)))

    def source(self, rec: dict, flag: int) -> dict:
        """The creature `rec` takes part `flag` from (template_source)."""
        return template_source(self.records, rec, flag)[0]

    def _voice(self, rec: dict):
        """`rec`'s FNV voice type (VTCK edit) if recorded; None keeps the body's."""
        fnv = int(rec.get('VTCK.Voice', '0'), 16)
        edid = fnv_voice_types().get(fnv, ('',))[0]
        return with_voice(self.voices.of(fnv)) if edid and recorded(fnv_folders(self.export_dir, edid)) else None

    def _own_voice(self, rec: dict):
        """`rec`'s or its sound set's FNV voice type (VTCK edit), recorded or not."""
        voiced = rec if 'VTCK.Voice' in rec else self.sounds.source(rec) or {}
        fnv = int(voiced.get('VTCK.Voice', '0'), 16)
        return with_voice(self.voices.of(fnv)) if fnv in fnv_voice_types() else None

    def _worn(self, fid: int, rec: dict, entry, packages: list, stats: dict = None) -> None:
        """Write FNV creature `rec` as a copy of its entry's target NPC on a skin showing FNV's body; on FO4's human
        (Pair.human) it speaks with FNV's voice type (_own_voice) and holds its guns."""
        npc, write, edid = self.worn[entry.edid.lower()][0], self.builder.writer, f'FNV_{rec["EditorID"]}'
        armo = self._skin(int(rec['FormID'], 16), entry)
        face = self.faces.get(int(rec['FormID'], 16))
        human = PAIRS[skeleton_folder(rec['Model.MODL'])].human
        edit = composed(R.packages_edit(packages), self._actor_data(rec),
                        self._own_voice(rec) if human else self._voice(rec), self._keywords(rec),
                        self._combat_style(rec), self._attacks(rec, npc), *self.own_parts(rec),
                        *self._sized(rec, npc, stats), self.inventory(rec, npc, False, human),
                        R.with_face(face) if face else None)
        unique = struct.unpack_from('<I', dict(subrecords(npc.body))[b'ACBS'])[0] & UNIQUE
        write.add_record('NPC_', R.clone_npc(fid, npc.body, npc.flags, edid, rec.get('FULL', ''),
                                             CHARACTER_TIES if unique else STAND_IN_TIES,
                                             edit=checked(self.builder.counts, npc.body, edid, lambda subs: _replaced(
                                                 edit(subs), {b'WNAM': struct.pack('<I', armo)} if armo else {}))))

    def _skin(self, fnv: int, entry) -> 'int | None':
        """The skin (ARMO) showing FNV creature `fnv`'s body: a copy of its entry's target's skin and addon, also
        covering the head slot (_with_slot), unless the pair wears FO4's body (_fo4_body, listed first) and head
        (its face set tinted in self.faces): FNV's addon then covers FX_SLOT; written once, as sized copies share it.
        None, the target's own skin kept as a stand-in's is, when FNV's body has a source fault (counted)."""
        if fnv not in self.skins:
            rec, (npc, skin, addon), write = self.records[fnv], self.worn[entry.edid.lower()], self.builder.writer
            folder, edid = skeleton_folder(rec['Model.MODL']), f'FNV_{rec["EditorID"]}'
            made = without_fault(self._mesh, rec, folder)
            if made is None:
                self.builder.counts["creatures on their target's skin (a source fault)"] += 1
                self.skins[fnv] = None
                return None
            model, bare = made
            head = functools.partial(_with_slot, slot=FX_SLOT if bare else PAIRS[folder].head_slots)
            arma, armo = (write.derive_formid(SITE, f'{fnv:08X} {part}') for part in ('ARMA', 'ARMO'))
            write.add_record('ARMA', copy_record(addon, arma, f'{edid}AA', {
                b'MOD2': _zstr(model), b'MOD3': _zstr(model), **head(addon)}, MODEL_TEXTURES))
            addons = ([self._fo4_body(addon, folder, bare)] if bare else []) + [arma]
            self.faces.update({fnv: self._face(npc, bare)} if bare else {})
            models = b''.join(pack_subrecord('INDX', bytes(2)) + pack_subrecord('MODL', struct.pack('<I', a))
                              for a in addons)
            write.add_record('ARMO', copy_record(skin, armo, f'{edid}Skin', head(skin), MODEL_TEXTURES | {b'INDX'},
                                                 lambda tag, data: models if tag == b'MODL' else
                                                 pack_subrecord(tag.decode(), data)))
            self.skins[fnv] = armo
        return self.skins[fnv]

    def _fo4_body(self, addon, folder: str, bare: str) -> int:
        """FO4's own body addon `addon` in FNV bare skin `bare`'s color (creature_tint, a copy wearing an MSWP), made
        once per folder and skin."""
        key = f'{folder} {bare} body'
        if key not in self.tinted:
            write, name = self.builder.writer, f'FNV_{Path(bare).stem}'
            if self.tint_archives is None:
                self.tint_archives = Archives(FALLOUT4_DIR / 'Data')
            pairs = tinted(self.tint_archives, self.export_dir, self.data_dir, PAIRS[folder].body, bare)
            swap, arma = write.derive_formid(SITE, f'{key} MSWP'), write.derive_formid(SITE, f'{key} ARMA')
            write.add_record('MSWP', R.pack_mswp(swap, f'{name}_BodySwap', pairs))
            ms = struct.pack('<I', swap)
            write.add_record('ARMA', copy_record(addon, arma, f'{name}_BodyAA', drop=MODEL_TEXTURES, edit=lambda tag, data: (
                pack_subrecord(tag.decode(), data) + (pack_subrecord(SWAPS[tag].decode(), ms) if tag in SWAPS else b''))))
            self.tinted[key] = arma
        return self.tinted[key]

    def _face(self, npc, bare: str) -> int:
        """A copy of target NPC `npc`'s race's default face set (DFTM) wearing its material in FNV bare skin
        `bare`'s color (tinted_materials), made once per skin."""
        key = f'{bare} face'
        if key not in self.tinted:
            if self.face_sets is None:
                self.face_sets = {r.form_id: r for r, _ in walk(self.builder.fo4, b'RACE', b'TXST')}
            race = self.face_sets[_form(npc, b'RNAM')]
            txst = self.face_sets[_form(race, b'DFTM')]
            material = 'materials\\' + dict(subrecords(txst.body))[b'MNAM'].rstrip(b'\0').decode().lower()
            (_, copy), = tinted_materials(self.tint_archives, self.export_dir, self.data_dir, [material], bare)
            fid, write = self.builder.writer.derive_formid(SITE, f'{key} TXST'), self.builder.writer
            write.add_record('TXST', copy_record(txst, fid, f'FNV_{Path(bare).stem}_Face', {b'MNAM': _zstr(copy)}))
            self.tinted[key] = fid
        return self.tinted[key]

    def _mesh(self, rec: dict, folder: str) -> tuple:
        """FNV creature `rec`'s body (its NIFZ parts) on its pair's skeleton, written once: (its FO4 model path, FNV's
        bare skin texture when it is worn over FO4's body, else None: a pair that doesn't, or a skin that is its
        armor too)."""
        names = [rec[f'NIFZ[{i}]'].lower() for i in range(int(rec.get('NIFZCount', 0)))]
        rel = f'{folder}\\{"_".join(n.rsplit(".", 1)[0] for n in names)}.nif'
        if rel not in self.meshes:
            if folder not in self.fits:
                self.fits[folder] = creature_fit(self.export_dir, folder, self.archives)
            meshes = asset_root(self.export_dir, 'meshes', folder)
            parts = [(cached_convert(meshes / n, self.export_dir, animated=False), meshes / n) for n in names]
            bare = (skin_texture([meshes / n for n in names]) or None) if PAIRS[folder].fo4_body else None
            body = creature_mesh(parts, self.fits[folder], PAIRS[folder].rig.root,
                                 skeleton_parents(meshes / 'skeleton.nif'), bare)
            self.meshes[rel] = write_converted(self.export_dir, body, rel, self.data_dir)[0], bare
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


def with_spells(spells: list):
    """An NPC edit adding `spells` to its spell list (SPCT, SPLO), which FO4 keeps right after RNAM."""
    def edit(subs: bytes) -> bytes:
        """The subrecords with the spells added."""
        found = list(subrecords(subs))
        have = [struct.unpack('<I', d)[0] for t, d in found if t == b'SPLO']
        ids = have + [s for s in spells if s not in have]
        block = pack_subrecord('SPCT', struct.pack('<I', len(ids))) + b''.join(
            pack_subrecord('SPLO', struct.pack('<I', s)) for s in ids)
        return b''.join(pack_subrecord(t.decode(), d) + (block if t == b'RNAM' else b'')
                        for t, d in found if t not in (b'SPCT', b'SPLO'))
    return edit


def _ranged_gear(rec) -> dict:
    """{WEAP `rec`: its AMMO (0: none)} for a ranged animation type; else {}."""
    dnam = dict(subrecords(rec.body)).get(b'DNAM', b'')
    ranged = len(dnam) > FO4_ANIM_TYPE and dnam[FO4_ANIM_TYPE] >= FO4_FIRST_RANGED
    return {rec.form_id: struct.unpack_from('<I', dnam)[0]} if ranged else {}


def _health(body: bytes) -> float:
    """A RACE's starting Health (PRPS), 0 without one."""
    data = dict(subrecords(body)).get(b'PRPS', b'')
    return dict(struct.unpack_from('<If', data, i) for i in range(0, len(data), 8)).get(HEALTH, 0.0)


def _form(rec, tag: bytes) -> int:
    """The FormID in record `rec`'s first `tag` subrecord."""
    return struct.unpack('<I', dict(subrecords(rec.body))[tag][:4])[0]


def _zstr(text: str) -> bytes:
    """A NUL-ended cp1252 string's bytes."""
    return text.encode('cp1252') + b'\0'


def _on_race(subs: bytes, race: int, skin: int) -> bytes:
    """NPC_ subrecords `subs` on race `race` (RNAM, ATKR) wearing skin `skin` (WNAM, after RNAM and any spells,
    before ATKR, where FO4's NPC_ keeps it)."""
    out, placed = b'', False
    for tag, data in subrecords(subs):
        if tag in (b'ATKR', b'ANAM', b'PRKZ') and not placed:
            out += pack_subrecord('WNAM', struct.pack('<I', skin))
            placed = True
        if tag == b'WNAM':
            continue
        out += pack_subrecord(tag.decode(), struct.pack('<I', race) if tag in (b'RNAM', b'ATKR') else data)
    return out if placed else out + pack_subrecord('WNAM', struct.pack('<I', skin))


def _with_slot(rec, slot: int) -> dict:
    """{BOD2: skin or addon `rec`'s slots plus `slot` (bits)}."""
    data = dict(subrecords(rec.body))[b'BOD2']
    return {b'BOD2': struct.pack('<I', struct.unpack_from('<I', data)[0] | slot) + data[4:]}


def _replaced(subs: bytes, values: dict) -> bytes:
    """Subrecords `subs` with each tag in `values` given that data."""
    return b''.join(pack_subrecord(t.decode(), values.get(t, d)) for t, d in subrecords(subs))
