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

from fo4_import.base.install import source_esm
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike.consumable_effects import AV_AT, effect_pair
from fo4_import.spike.perks import ATTACK_TEMPLATES, DETRIMENTAL, RECOVER, pack_spell
from fo4_import.spike.script_effects import DELIVERY, FIRE_AND_FORGET
from tes5_import.base.tes5_reader import first_sub, walk

SHAPE, LOWERS, RECOVERS = ATTACK_TEMPLATES
#: derive_formid site of an attack spell (key: the FNV spell's EditorID).
SITE = 'FNV attack spell'
#: FNV effect range of an effect on the caster; SPIT offset of an FO4 spell's delivery.
SELF, DELIVERY_AT = 'Self', 20
#: The touch relay's script and its property naming the self spell it casts on the attacker.
RELAY, RELAYED = 'F3NV_CastOnAttacker', 'AttackerSpell'


def unarmed_effects(plugin: bytes) -> dict:
    """{FNV creature FormID: its EITM spell FormID} of `plugin`'s creatures."""
    return {rec.form_id: struct.unpack('<I', data)[0] for rec, _ in walk(plugin, b'CREA')
            if (data := first_sub(rec.body, b'EITM'))}


class AttackSpells:
    """FO4 attack spells of FNV's unarmed attack effects, each written once."""

    def __init__(self, builder):
        """For `builder`'s plugin; it reads the builder's perks and script effects."""
        self.builder, self.made = builder, {}
        self.unarmed = unarmed_effects(source_esm())

    def of(self, rec: dict) -> int:
        """The FO4 attack spell of FNV creature `rec`'s unarmed attack effect (`rec` being its Spells chain's
        record); 0 without one or when none of its effects converts."""
        fnv = self.unarmed.get(int(rec['FormID'], 16))
        if fnv and fnv not in self.made:
            self.made[fnv] = self._spell(self.builder.perks.spells.get(fnv))
        return self.made.get(fnv, 0)

    def _spell(self, spell: 'dict | None') -> int:
        """Write FNV spell `spell` as an attack spell; its FormID, 0 when no effect converts."""
        keys = [f'Effect[{i}]' for i in range(int((spell or {}).get('EffectCount', 0) or 0))]
        on_self = bool(keys) and all(spell.get(f'{key}.Type') == SELF for key in keys)
        pairs = b''
        for key in keys:
            effect = self._effect(spell, key, on_self)
            if effect is None:
                self.builder.counts[f'attack effect left out ({spell[f"{key}.EFID"]})'] += 1
                continue
            pairs += effect_pair(effect, float(spell[f'{key}.Magnitude'] or 0), int(spell.get(f'{key}.Area') or 0),
                                 int(spell.get(f'{key}.Duration') or 0))
        if not pairs:
            return 0
        fid = self.builder.writer.derive_formid(SITE, spell['EditorID'])
        shape = self.builder.perks.vanilla[SHAPE][1]
        spit = bytearray(shape[b'SPIT'])
        struct.pack_into('<I', spit, DELIVERY_AT, DELIVERY[SELF if on_self else 'Touch'])
        self.builder.writer.add_record('SPEL', pack_spell(fid, f'FNV_{spell["EditorID"]}', spell.get('FULL', ''),
                                                          {**shape, b'SPIT': bytes(spit)}, pairs))
        self.builder.counts['SPEL (attack spell)'] += 1
        if not on_self:
            return fid
        vmad = self.builder.scripts.vmad(0, ((RELAY, {RELAYED: fid}, {}),))
        return self.builder.scripts.effects.vmad_spell(f'FNV_{spell["EditorID"]}OnHit', vmad, DELIVERY['Touch'])

    def _effect(self, spell: dict, key: str, on_self: bool) -> 'int | None':
        """The FO4 effect of FNV attack effect `key` of `spell`, on the attacker (`on_self`) or by touch; None when
        it has none or FNV gives it the other range."""
        perks, edid = self.builder.perks, spell[f'{key}.EFID']
        if (spell.get(f'{key}.Type') == SELF) != on_self:
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
