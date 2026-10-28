"""FNV creatures' unarmed attack effects as FO4 attack spells.

See: docs/fork/fo4_pipeline.md#attack-spells
"""

from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import attack_spells as AS
from fo4_import.spike import creature_attacks as CA
from fo4_import.spike import perks as P
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

HEALTH, AGILITY = 0x2D4, 0x2C7
#: FNV detrimental (Poison, Reduce) and beneficial magic effects' flags.
EFFECTS = {'Poison': {'DATA.Flags': str(P.DETRIMENTAL)}, 'ReduceAgility': {'DATA.Flags': str(P.DETRIMENTAL | P.RECOVER)},
           'RestoreHealth': {'DATA.Flags': '0'}}


def _spells(scripted: dict = None) -> AS.AttackSpells:
    """AttackSpells over stand-in perks: crPoisonEffect on Health, the recovering one on Agility, copies logged."""
    copies = []
    data = bytearray(0x60)
    perks = SimpleNamespace(
        fnv_effects=EFFECTS, helper_index=0,
        vanilla={AS.LOWERS: (0x100, {b'DATA': bytes(data[:0x44]) + HEALTH.to_bytes(4, 'little') + bytes(0x18)}),
                 AS.RECOVERS: (0x200, {b'DATA': bytes(data[:0x44]) + AGILITY.to_bytes(4, 'little') + bytes(0x18)})},
        effects=SimpleNamespace(copy=lambda template, av, *_: copies.append((template, av)) or 0x300 + len(copies)))
    spells = AS.AttackSpells.__new__(AS.AttackSpells)
    spells.builder = SimpleNamespace(perks=perks, counts=Counter(), scripts=SimpleNamespace(
        effects=SimpleNamespace(effect=lambda edid, cast, delivery: (scripted or {}).get(edid))))
    spells.copies = copies
    return spells


def test_value_effects_are_vanillas_touch_effects_or_copies(monkeypatch):
    """Poison on Health is crPoisonEffect; a recovering Reduce on Agility the recovering one; others are copies."""
    monkeypatch.setattr(AS, 'actor_value_form', lambda name, index: {'Health': HEALTH, 'Agility': AGILITY,
                                                                     'Perception': 0x2C3}.get(name))
    spells = _spells()
    effect = lambda efid, av: spells._effect({'e.EFID': efid, 'e.ActorValue': str(av), 'e.Type': 'Touch'}, 'e', False)
    assert effect('Poison', 16) == 0x100 and effect('ReduceAgility', 10) == 0x200
    assert effect('Poison', 6) == 0x301 and spells.copies == [(AS.LOWERS, 'Perception')]
    assert effect('RestoreHealth', 16) is None


def test_a_script_effect_is_script_effects_in_fnvs_range():
    """A script effect is script_effects' on its own range (touch, or self for a knockdown); the other is out."""
    spells = _spells({'CazadorPoisonEffect': 0x400, 'DeathclawKnockdownEffect': 0x500})
    touch = {'e.EFID': 'CazadorPoisonEffect', 'e.ActorValue': '-1', 'e.Type': 'Touch'}
    own = {'e.EFID': 'DeathclawKnockdownEffect', 'e.ActorValue': '-1', 'e.Type': 'Self'}
    assert spells._effect(touch, 'e', False) == 0x400 and spells._effect(own, 'e', True) == 0x500
    assert spells._effect(touch, 'e', True) is None


def test_every_attack_casts_fnvs_spell_not_the_stand_ins():
    """Every attack casts the given spell in place of the stand-in's."""
    stand_in = CA.ATKD.pack(2.0, 1.0, 0x999, 0, 0.0, 35.0, 0.0, 0.0, 0.0, 1.0, 0)
    subs, _ = CA.attack_list([(stand_in, b'sting\0', b'')], frozenset({'attackleft'}), {}, 0x1234)
    assert [CA.ATKD.unpack(d)[2] for t, d in subrecords(subs) if t == b'ATKD'] == [0x1234]


def test_a_self_spell_is_cast_on_the_attacker_by_a_touch_relay():
    """A knockdown (every effect Self) is written self-delivered; the attack carries a touch relay casting it."""
    spells = _spells({'DeathclawKnockdownEffect': 0x500})
    written, relays = [], []
    spells.builder.perks.vanilla[AS.SHAPE] = (0x600, {b'ETYP': bytes(4), b'SPIT': bytes(36)})
    spells.builder.writer = SimpleNamespace(derive_formid=lambda site, key: 0x700, add_record=lambda s, r: written.append(r))
    spells.builder.scripts.vmad = lambda scpt, extra: extra
    spells.builder.scripts.effects.vmad_spell = lambda edid, vmad, delivery: relays.append((edid, vmad, delivery)) or 0x800
    knock = {'EditorID': 'DeathClawKnockback', 'EffectCount': '1', 'Effect[0].EFID': 'DeathclawKnockdownEffect',
             'Effect[0].Type': 'Self', 'Effect[0].Magnitude': '0', 'Effect[0].ActorValue': '-1'}
    assert spells._spell(knock) == 0x800 and len(written) == 1
    assert relays == [('FNV_DeathClawKnockbackOnHit', ((AS.RELAY, {AS.RELAYED: 0x700}, {}),), 1)]


def test_with_spell_sets_every_attacks_spell():
    """An own rig's list (no stand-in list to filter) gets the spell on every ATKD, the rest untouched."""
    atkd = CA.ATKD.pack(1.0, 1.0, 0, 0, 0.0, 35.0, 0.0, 0.0, 0.0, 1.0, 0)
    subs = CA.with_spell(pack_subrecord('ATKD', atkd) + pack_subrecord('ATKE', b'bite\0'), 0x1234)
    assert [CA.ATKD.unpack(d)[2] for t, d in subrecords(subs) if t == b'ATKD'] == [0x1234]
    assert dict(subrecords(subs))[b'ATKE'] == b'bite\0'
