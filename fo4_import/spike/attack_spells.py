"""FNV creatures' unarmed attack effects (CREA EITM) as FO4 attack spells.

FNV casts a creature's unarmed attack effect on every unarmed hit; it is part
of the Actor Effect List template part (xEdit hides it under Use Actor
Effect List). FO4 casts an attack's spell (ATKD) on that attack's hit, as
Fallout4.esm's radscorpion stings carry PoisonRadscorpion. Each FNV spell
becomes one on PoisonRadscorpion's shape (fire and forget, its equip type),
magnitudes, areas and durations FNV's. FO4 casts an attack's spell on the
actor hit, whatever its delivery (a self-delivered knockdown ran on the
victim, so the player flung the deathclaws), so FNV's range decides:

- every effect FNV's Touch (poisons): the spell, by touch, on the victim;
- every effect FNV's Self (knockdowns, bursts: the script pushes its own
  combat target away): the spell self-delivered, cast on the attacker by a
  touch relay (F3NV_CastOnAttacker, on the victim, casts it on its caster).

Each effect of the spell:

- a touch value effect FNV marks detrimental is vanilla crPoisonEffect
  (damage per second) on its actor value, or StingwingPoisonEffectNPC
  (lowered, then recovered) when FNV's recovers, copied onto any other actor
  value;
- a script effect is script_effects', delivered as the spell is;
- any other, and an effect of the other range, is left out, counted; a spell
  with none is not written.

See: docs/fork/fo4_pipeline.md#attack-spells
"""

import struct

from fo4_import.base.install import plugin_walk
from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.writer import pack_subrecord
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike.consumable_effects import AV_AT, effect_pair
from fo4_import.spike.perks import ATTACK_TEMPLATES, DETRIMENTAL, RECOVER, pack_spell
from fo4_import.spike.script_effects import DELIVERY, FIRE_AND_FORGET
from tes5_import.base.tes5_reader import first_sub

SHAPE, LOWERS, RECOVERS = ATTACK_TEMPLATES
#: derive_formid site of an attack spell (key: the FNV spell's EditorID).
SITE = 'FNV attack spell'
#: FNV effect range of an effect on the caster; SPIT offset of an FO4 spell's delivery.
SELF, DELIVERY_AT = 'Self', 20
#: The touch relay's script and its property naming the self spell it casts on the attacker.
RELAY, RELAYED = 'F3NV_CastOnAttacker', 'AttackerSpell'
#: derive_formid site of an explosion's object effect (key: the FNV enchantment's EditorID).
EXPLOSION_SITE = 'FNV explosion enchantment'
#: ENIT of an explosion's object effect: Fallout4.esm's EnchPlasmaGrenadeEnergyDmg's (Fire and Forget, Touch, type 6).
ENIT_EXPLOSION = struct.pack('<IIIiII', 0, 0, 1, 0, 1, 6) + bytes(12)
#: ENIT of a weapon's object effect: Fallout4.esm's EnchCryoFreeze's (as the explosion's, flags 0x4).
ENIT_WEAPON = struct.pack('<IIIiII', 0, 4, 1, 0, 1, 6) + bytes(12)


def _keys(spell: 'dict | None') -> list:
    """FNV spell or enchantment `spell`'s effect keys (Effect[i])."""
    return [f'Effect[{i}]' for i in range(int((spell or {}).get('EffectCount', 0) or 0))]


def pack_explosion_ench(fid: int, edid: str, pairs: bytes, enit: bytes = ENIT_EXPLOSION) -> bytes:
    """An explosion's or (ENIT_WEAPON) weapon's object effect of `pairs`."""
    body = pack_subrecord('EDID', f'{edid}\0'.encode()) + pack_subrecord('OBND', bytes(12))
    return pack_fo4_record('ENCH', fid, 0, body + pack_subrecord('ENIT', enit) + pairs)


def unarmed_effects(plugin: bytes) -> dict:
    """{FNV creature FormID: its EITM spell FormID} of `plugin`'s creatures."""
    return {rec.form_id: struct.unpack('<I', data)[0] for rec, _ in plugin_walk(plugin, b'CREA')
            if (data := first_sub(rec.body, b'EITM'))}


class AttackSpells:
    """FO4 attack spells of FNV's unarmed attack effects, each written once."""

    def __init__(self, builder):
        """For `builder`'s plugin; it reads the builder's perks and script effects."""
        self.builder, self.made = builder, {}
        self.unarmed = unarmed_effects(None)

    def of(self, rec: dict) -> int:
        """The FO4 attack spell of FNV creature `rec`'s unarmed attack effect (`rec` being its Spells chain's
        record); 0 without one or when none of its effects converts."""
        fnv = self.unarmed.get(int(rec['FormID'], 16))
        if fnv and fnv not in self.made:
            self.made[fnv] = self._spell(self.builder.perks.spells.get(fnv))
        return self.made.get(fnv, 0)

    def poison(self, rec: dict, extra: bytes) -> int:
        """Poison ALCH `rec`'s spell on the actor hit, plus pairs `extra`; 0: none."""
        return self._spell(rec, (True, extra, 'Poison'))

    def _spell(self, spell: 'dict | None', poison: tuple = (False, b'', '')) -> int:
        """Write FNV spell `spell` as an attack spell, or `poison` (victim, extra pairs, EditorID prefix) as a
        poison's; its FormID, 0 when no effect converts."""
        victim, extra, prefix = poison
        keys = _keys(spell)
        on_self = not victim and bool(keys) and all(spell.get(f'{key}.Type') == SELF for key in keys)
        pairs = self.effect_pairs(spell, on_self, victim)
        if not pairs:
            return 0
        fid = self.builder.writer.derive_formid(SITE, prefix + spell['EditorID'])
        shape = self.builder.perks.vanilla[SHAPE][1]
        spit = bytearray(shape[b'SPIT'])
        struct.pack_into('<I', spit, DELIVERY_AT, DELIVERY[SELF if on_self else 'Touch'])
        self.builder.writer.add_record('SPEL', pack_spell(fid, f'FNV_{prefix}{spell["EditorID"]}', spell.get('FULL', ''),
                                                          {**shape, b'SPIT': bytes(spit)}, pairs + extra))
        self.builder.counts['SPEL (attack spell)'] += 1
        if not on_self:
            return fid
        vmad = self.builder.scripts.vmad(0, ((RELAY, {RELAYED: fid}, {}),))
        return self.builder.scripts.effects.vmad_spell(f'FNV_{spell["EditorID"]}OnHit', vmad, DELIVERY['Touch'])

    def effect_pairs(self, spell: dict, on_self: bool, victim: bool) -> bytes:
        """EFID/EFIT pairs of FNV `spell`'s effects (_effect: on the attacker when `on_self`, any range on the
        `victim`), FNV's magnitudes, areas and durations; one left out is counted."""
        pairs = b''
        for key in _keys(spell):
            effect = self._effect(spell, key, on_self, victim)
            if effect is None:
                self.builder.counts[f'attack effect left out ({spell[f"{key}.EFID"]})'] += 1
                continue
            pairs += effect_pair(effect, float(spell[f'{key}.Magnitude'] or 0), int(spell.get(f'{key}.Area') or 0),
                                 int(spell.get(f'{key}.Duration') or 0))
        return pairs

    def explosion(self, ench: dict) -> int:
        """FNV explosion enchantment `ench` as an FO4 explosion's object effect (ENCH, as Fallout4.esm's 24 explosion
        effects are): its effects on the actors caught, as a poison's; 0 when none converts, written once.
        See: docs/fork/fo4_thrown_weapons.md#effects
        """
        key = EXPLOSION_SITE, ench['EditorID']
        if key not in self.made:
            pairs = self.effect_pairs(ench, False, True)
            self.made[key] = self.builder.writer.derive_formid(*key) if pairs else 0
            if pairs:
                self.builder.writer.add_record('ENCH', pack_explosion_ench(self.made[key], f'FNV_{ench["EditorID"]}',
                                                                           pairs))
                self.builder.counts['ENCH (explosion effect)'] += 1
        return self.made[key]

    def _effect(self, spell: dict, key: str, on_self: bool, victim: bool = False) -> 'int | None':
        """The FO4 effect of FNV attack effect `key` of `spell`, on the attacker (`on_self`) or by touch; None when
        it has none or FNV gives it the other range (any range on the `victim`)."""
        perks, edid = self.builder.perks, spell[f'{key}.EFID']
        if not victim and (spell.get(f'{key}.Type') == SELF) != on_self:
            return None
        scripted = self.builder.scripts.effects.effect(edid, FIRE_AND_FORGET, DELIVERY[SELF if on_self else 'Touch'])
        flags = int(perks.fnv_effects.get(edid, {}).get('DATA.Flags', 0) or 0)
        av = int(spell.get(f'{key}.ActorValue', -1) or -1)
        name = C.fnv_av_name(av) if 0 <= av < len(C.FNV_AV_NAMES) else ''
        if scripted or on_self or not flags & DETRIMENTAL or not name or actor_value_form(name, perks.helper_index) is None:
            return scripted
        template = RECOVERS if flags & RECOVER else LOWERS
        vanilla_av = struct.unpack_from('<I', perks.vanilla[template][1][b'DATA'], AV_AT)[0]
        if actor_value_form(name, perks.helper_index) == vanilla_av:
            return perks.vanilla[template][0]
        return perks.effects.copy(template, name, 'copy', f'{template} {name}', f'FNV_{template}_{name}')
