"""The hidden perk carrying the source game's combat rules: random critical hits (criticals), weapon skills'
damage and spread (weapon_skills), sneak attacks (sneak_attacks). The player holds it (F3NV_NewGame, on a new game
and every load); every NPC and creature record the build writes is given it before the plugin is written (a
templated actor's comes from its template).

See: docs/fork/fo4_pipeline.md#random-criticals
See: docs/fork/fo4_pipeline.md#weapon-skills
See: docs/fork/fo4_pipeline.md#sneak-attacks
"""

import struct

from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike.combat_styles import fnv_settings
from fo4_import.spike.criticals import Criticals
from fo4_import.spike.perks import ENTRY_POINT, PERK_DATA, pack_effect, pack_perk
from fo4_import.spike.requirement_spread import RequirementSpread
from fo4_import.spike.sneak_attacks import SneakAttacks
from fo4_import.spike.weapon_skills import WeaponSkills
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: The perk: EditorID and FormID key, DATA (no trait or level, one rank, unplayable, hidden).
EDID, KEY, DATA = 'FNV_CombatRules', 'PERK combat rules', struct.pack(PERK_DATA, 0, 0, 1, 0, 1)
#: FO4 NPC_ subrecords before its perk list (xEdit wbDefinitionsFO4); PRKZ counts the PRKR entries after them.
BEFORE_PERKS = frozenset({b'EDID', b'VMAD', b'OBND', b'PTRN', b'STCP', b'ACBS', b'SNAM', b'INAM', b'VTCK', b'TPLT',
                          b'LTPT', b'LTPC', b'TPTA', b'RNAM', b'SPCT', b'SPLO', b'DEST', b'DAMC', b'DSTD', b'DSTA',
                          b'DMDL', b'DMDT', b'DMDC', b'DMDS', b'DSTF', b'WNAM', b'ANAM', b'ATKR', b'ATKD', b'ATKE',
                          b'ATKW', b'ATKS', b'ATKT', b'SPOR', b'OCOR', b'GWOR', b'ECOR', b'FCPL', b'RCLR'})
HEADER = 24


def with_perk(record: bytes, perk: int) -> bytes:
    """FO4 NPC_ `record` holding `perk` at rank 1 too: PRKR after its perks (PRKZ counting it), else a new list."""
    subs = list(subrecords(record[HEADER:]))
    if any(tag == b'PRKR' and struct.unpack_from('<I', data)[0] == perk for tag, data in subs):
        return record
    tags, entry = [tag for tag, _ in subs], (b'PRKR', struct.pack('<IB', perk, 1))
    if b'PRKZ' in tags:
        subs = [(t, struct.pack('<I', struct.unpack('<I', d)[0] + 1) if t == b'PRKZ' else d) for t, d in subs]
        subs.insert(max(i for i, t in enumerate(tags) if t in (b'PRKZ', b'PRKR')) + 1, entry)
    else:
        at = next((i for i, t in enumerate(tags) if t not in BEFORE_PERKS), len(subs))
        subs[at:at] = [(b'PRKZ', struct.pack('<I', 1)), entry]
    body = b''.join(pack_subrecord(tag.decode(), data) for tag, data in subs)
    return record[:4] + struct.pack('<I', len(body)) + record[8:HEADER] + body


def combat_rules(builder, helper_index: int) -> tuple:
    """(Criticals, CombatPerk) of `builder`'s build, on FNV's settings read once."""
    settings = fnv_settings(builder.export_dir)
    criticals = Criticals(builder, settings, helper_index)
    perk = CombatPerk(builder, (criticals, WeaponSkills(builder, settings, helper_index), SneakAttacks(builder, settings),
                                RequirementSpread(builder, settings, helper_index)))
    perk.damage_rules, perk.settings = damage_rules(settings, helper_index), settings
    return criticals, perk


def damage_rules(settings: dict, helper_index: int) -> tuple:
    """({property: FormID}, {property: (kind, value)}) F3NV_NewGame hands F3NV_Damage.SetRules: FNV's floor and DR
    cap, the actor values of FNV's DR (the helper's), its DT (FO4's DamageResist) and FO4's EnergyResist.
    See: docs/fork/fo4_pipeline.md#damage-threshold
    """
    forms = {'DamageResist': actor_value_form('DamageResist', helper_index),
             'DamageThreshold': actor_value_form('DamageThreshold', helper_index),
             'EnergyResist': actor_value_form('EnergyResist', helper_index)}
    return forms, {'MinDamage': ('float', settings.get('fMinDamMultiplier', 0.2)),
                   'MaxResist': ('float', settings.get('fMaxArmorRating', 85.0) / 100.0)}


class CombatPerk:
    """The combat rules perk of one build; its entries come from `parts` (each with entries())."""

    def __init__(self, builder, parts: tuple):
        """Its FormID, fixed before anything names it."""
        self.builder, self.parts, self.damage_rules, self.settings = builder, parts, ({}, {}), {}
        self.fid = builder.writer.derive_formid(KEY, EDID)

    def write(self) -> None:
        """Write the perk and give it to every NPC and creature record the build wrote."""
        effects = b''
        for n, (data, tabs, params) in enumerate(e for part in self.parts for e in part.entries()):
            effects += pack_effect(ENTRY_POINT, data, tabs, params[:1] + [(b'EPFB', struct.pack('<H', n))] + params[1:])
        self.builder.writer.add_record('PERK', pack_perk(self.fid, (EDID, '', ''), b'', DATA, 0, effects))
        self.builder.counts['NPC_ given FNV_CombatRules'] = self.builder.writer.patch_records(
            'NPC_', lambda rec: with_perk(rec, self.fid))
