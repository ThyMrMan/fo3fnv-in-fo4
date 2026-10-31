"""FNV's weapon poisons on Fallout 4, which cannot coat a weapon.

FNV counts an ingestible a poison when every effect is hostile (MGEF flag 0x4, JIP's AlchemyItem::IsPoison).
FalloutNV.exe's Pip-Boy (0x95E6F0) puts it on the equipped weapon only when that weapon's skill is Melee Weapons
(0x26) or Unarmed (0x2D), else shows sPoisonNoWeaponMessage, and refuses a weapon already poisoned
(sPoisonAlreadyPoisonedMessage); the weapon holds one poison (ExtraPoison, no charges) for its next hit.

Here using a poison runs F3NV_WeaponPoison on the player: with a weapon carrying FNV's Melee Weapons or Unarmed skill
keyword (type_tests) and no coat on, it gives the poison's hidden coat perk, which casts the poison's spell on the
actor hit (Apply Combat Hit Spell, the weapon tab testing those keywords); the spell is the poison's effects on the
victim (attack_spells.poison) plus F3NV_PoisonSpent, which takes the perk from the attacker, so the coat lasts one
hit. Refused, the item comes back.

See: docs/fork/fo4_pipeline.md#weapon-poisons
"""

import struct

from fo4_import.base.vmad import object_scripts
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.attack_spells import AttackSpells
from fo4_import.spike.consumable_effects import effect_pair
from fo4_import.spike.perks import DETRIMENTAL, ENTRY_POINT, PERK_DATA, pack_effect, pack_perk
from fo4_import.spike.script_effects import DELIVERY
from fo4_import.spike.type_tests import skill_keyword

#: derive_formid site (keys: '<poison EditorID> coat', 'coats').
SITE = 'FNV weapon poison'
#: The scripts applying a poison and ending its coat.
APPLY, SPENT = 'F3NV_WeaponPoison', 'F3NV_PoisonSpent'
#: FNV skills whose weapons take a poison (FalloutNV.exe 0x95E7C8: actor values 0x26 and 0x2D).
POISONABLE = ('Melee Weapons', 'Unarmed')
#: FO4 entry point Apply Combat Hit Spell, function Select Spell, its tabs (owner, weapon, target), EPFT of a spell.
HIT_SPELL, SELECT_SPELL, HIT_TABS, WEAPON_TAB, SPELL_PARAM = 51, 10, 3, 1, 5
#: The coat perk's DATA (no trait or level, one rank, unplayable, hidden).
COAT_DATA = struct.pack(PERK_DATA, 0, 0, 1, 0, 1)
#: FNV's two refusals and FalloutNV.exe's text for one FalloutNV.esm leaves at the default.
NO_WEAPON, ALREADY = 'sPoisonNoWeaponMessage', 'sPoisonAlreadyPoisonedMessage'
DEFAULTS = {ALREADY: 'The current weapon is already poisoned.'}
#: CTDA operators equal, with the OR flag.
EQUAL, OR = 0x00, 0x01


class WeaponPoisons:
    """The build's weapon poisons: each one's apply effect, coat perk and spell; the list of coats."""

    def __init__(self, builder, export_dir):
        """FNV's refusal messages, read once."""
        self.builder, self.coats, self.spells = builder, [], None
        gmst = {r.get('EditorID'): r.get('DATA.Value') for r in export_records(export_dir, 'GMST')}
        self.messages = {key: gmst.get(key) or DEFAULTS.get(key, '') for key in (NO_WEAPON, ALREADY)}
        self.list_fid = builder.writer.derive_formid(SITE, 'coats')

    def is_poison(self, rec: dict) -> bool:
        """Whether FNV ALCH `rec`'s every effect is hostile."""
        effects = self.builder.perks.fnv_effects
        keys = [rec.get(f'Effect[{i}].EFID') for i in range(int(rec.get('EffectCount', 0) or 0))]
        return bool(keys) and all(int(effects.get(k, {}).get('DATA.Flags', 0) or 0) & DETRIMENTAL for k in keys)

    def effects(self, rec: dict, item: int) -> 'bytes | None':
        """Poison `rec`'s (FO4 item `item`) ALCH effects, its coat written; None for another, or one none of whose
        effects converts."""
        if not self.is_poison(rec):
            return None
        edid, scripts = rec['EditorID'], self.builder.scripts
        coat = self.builder.writer.derive_formid(SITE, f'{edid} coat')
        spent = scripts.effects.vmad_effect(f'FNV_{edid}Spent', object_scripts([(SPENT, {'Coat': coat}, {})]),
                                            DELIVERY['Touch'])
        self.spells = self.spells or AttackSpells(self.builder)
        spell = self.spells.poison(rec, effect_pair(spent, 0.0, 0, 0))
        if not spell:
            self.builder.counts['weapon poison left out (no effect converts)'] += 1
            return None
        self._coat(coat, edid, spell)
        values = {'Poisonable': ('objects', self._keywords()), 'NoWeapon': ('string', self.messages[NO_WEAPON]),
                  'Already': ('string', self.messages[ALREADY])}
        vmad = object_scripts([(APPLY, {'Coat': coat, 'Coats': self.list_fid, 'Poison': item}, values)])
        return effect_pair(scripts.effects.vmad_effect(f'FNV_{edid}Apply', vmad, DELIVERY['Self']), 0.0, 0, 0)

    def _keywords(self) -> list:
        """The FNV skill keywords of the weapons that take a poison."""
        return [self.builder.type_keywords.keyword(skill_keyword(C.FNV_AV_NAMES.index(s))) for s in POISONABLE]

    def _coat(self, fid: int, edid: str, spell: int) -> None:
        """Write coat perk `fid` of poison `edid`: `spell` on the actor hit with a weapon that takes poison."""
        has, keywords = C.FO4.index('HasKeyword'), self._keywords()
        weapon = b''.join(R.pack_ctda(EQUAL | (OR if i < len(keywords) - 1 else 0), 1.0, has, k)
                          for i, k in enumerate(keywords))
        effect = pack_effect(ENTRY_POINT, bytes([HIT_SPELL, SELECT_SPELL, HIT_TABS]), {WEAPON_TAB: weapon},
                             [(b'EPFT', bytes([SPELL_PARAM])), (b'EPFB', struct.pack('<H', 0)),
                              (b'EPFD', struct.pack('<I', spell))])
        self.builder.writer.add_record('PERK', pack_perk(fid, (f'FNV_{edid}Coat', '', ''), b'', COAT_DATA, 0, effect))
        self.coats.append(fid)
        self.builder.counts['weapon poison'] += 1

    def write(self) -> None:
        """Write the list of every coat perk written (F3NV_WeaponPoison's Coats)."""
        self.builder.writer.add_record('FLST', R.pack_flst(self.list_fid, 'FNV_WeaponPoisonCoats', self.coats))
