"""An FNV consumable effect no table lists, routed by its archetype, actor value and kind (consumable_effects)."""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import conditions as C
from fo4_import.spike import consumable_effects as CE
from fo4_import.spike import script_effects as SE

#: FO4 AVIF FormIDs the tests' actor values resolve to.
FO4_AVS = {'Health': 0x2D4, 'Guns': 0x0B000900}
HEALTH, GUNS = C.FNV_AV_NAMES.index('Health'), C.FNV_AV_NAMES.index('Guns')


def _fo4_effect(edid: str, flags: int, archetype: int = 0, cast: tuple = CE.CONSUMED, extra: tuple = ()) -> dict:
    """{tag: data} of a Fallout4.esm MGEF on Health with `flags`, `archetype`, `cast` and `extra` empty tags."""
    data = bytearray(0x60)
    struct.pack_into('<I', data, 0, flags)
    struct.pack_into('<II', data, CE.ARCHETYPE_AT, archetype, FO4_AVS['Health'])
    struct.pack_into('<II', data, CE.CAST_AT, *cast)
    return {b'EDID': edid.encode() + b'\0', b'DATA': bytes(data), **dict.fromkeys(extra, b'')}


def test_value_key_takes_only_a_plain_shown_value_effect_a_consumable_casts():
    """A fire-and-forget self Value/Peak Value Modifier keys by (actor value, lowers, recovers); others are None."""
    assert CE.value_key(_fo4_effect('DamageHealth', CE.DETRIMENTAL)) == (0x2D4, True, False)
    assert CE.value_key(_fo4_effect('FortifyHealth', CE.RECOVER, 34)) == (0x2D4, False, True)
    assert CE.value_key(_fo4_effect('FortifyHealthChem', CE.RECOVER, 34, extra=(b'KWDA',))) is None
    assert CE.value_key(_fo4_effect('FortifyHealthHIDDEN', CE.RECOVER | CE.HIDDEN, 34)) is None
    assert CE.value_key(_fo4_effect('AbFortifyHealth', CE.RECOVER, 34, (0, 0))) is None
    assert CE.value_key(_fo4_effect('DamageHealthAimed', CE.DETRIMENTAL, 0, (2, 2))) is None
    assert CE.value_key(_fo4_effect('FortifyHealthScript', 0, 1)) is None


def _effects(monkeypatch, fnv: dict) -> CE.Effects:
    """Effects knowing FNV effects `fnv` and Fallout4.esm's DamageHealth (0x55); copies are recorded, not written."""
    monkeypatch.setattr(CE, 'actor_value_form', lambda name, index: FO4_AVS.get(name))
    effects = CE.Effects(SimpleNamespace(counts=Counter()), 0xFE, {}, values={(0x2D4, True, False): 0x55})
    effects.fnv_values, effects.made = fnv, []
    effects.copy = lambda *args: effects.made.append(args) or 0x77
    return effects


def test_an_unlisted_value_effect_is_fo4s_of_its_actor_value_and_kind_else_a_copy(monkeypatch):
    """FNV's damage of Health is Fallout4.esm's; a damage of a skill FO4 has no effect on copies DamageHealth."""
    effects = _effects(monkeypatch, {'Tremble': (CE.VALUE_MODIFIER, HEALTH, CE.DETRIMENTAL | 0x71),
                                     'DamageSkillGuns': (CE.VALUE_MODIFIER, GUNS, CE.DETRIMENTAL)})
    assert effects.by_value('Tremble', HEALTH) == [0x55] and effects.by_value('Tremble', -1) == [0x55]
    assert effects.by_value('DamageSkillGuns', GUNS) == [0x77]
    assert effects.made == [('DamageHealth', 'Guns', 'copy', 'DamageHealth Guns', 'FNV_DamageHealth_Guns')]


def test_an_effect_of_another_archetype_or_actor_value_is_left_out_with_why(monkeypatch):
    """A script effect whose script did not convert, a value FO4 lacks, an unknown effect: [] and the reason."""
    effects = _effects(monkeypatch, {'Steady': (1, -1, 0), 'Odd': (CE.VALUE_MODIFIER, 0, 0), 'Lock': (16, -1, 0)})
    assert effects.by_value('Steady', -1) == effects.by_value('Odd', 0) == effects.by_value('Gone', -1) == []
    reasons = [effects.drop_reason(e) for e in ('Steady', 'Odd', 'Lock', 'Gone', 'RestoreDehydrationLevel')]
    assert reasons == ['script did not convert', 'actor value FO4 lacks', 'archetype 16', 'no record', 'Hardcore off']


def test_an_addiction_spell_is_never_a_consumables_fire_and_forget_spell():
    """A withdrawal (FNV Addiction) of value effects is left out; an Actor Effect of them goes to _plain_spell."""
    effects = SE.ScriptEffects.__new__(SE.ScriptEffects)
    effects.effects, plain = {}, []
    effects.builder = SimpleNamespace(counts=Counter(), consumables=SimpleNamespace(
        effects=SimpleNamespace(pairs=lambda rec: plain.append(rec['EditorID']) or b'')))
    spell = {'EffectCount': '1', 'Effect[0].EFID': 'AddictRedAGJet', 'Effect[0].ConditionCount': '0'}
    assert effects._spell({**spell, 'EditorID': 'WithdrawalJet', 'SPIT.Type': str(SE.ADDICTION)}) is None
    assert effects._spell({**spell, 'EditorID': 'Burn', 'SPIT.Type': '0'}) is None and plain == ['Burn']


def test_a_listed_effect_keeps_its_table_entry(monkeypatch):
    """EFFECTS first: FNV's RestoreHealth stays RestoreHealthFood."""
    effects = _effects(monkeypatch, {'RestoreHealth': (CE.VALUE_MODIFIER, HEALTH, CE.DETRIMENTAL)})
    effects.vanilla = {'RestoreHealthFood': (0x99, {})}
    assert effects._fo4('RestoreHealth', HEALTH) == [0x99]
