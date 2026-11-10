"""FNV's Hardcore mode on Fallout 4: script rows, need effects, conditions, stages.

See: docs/fork/fo4_hardcore.md#built
"""

import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.spike import conditions as C
from fo4_import.spike import consumable_effects as CE
from fo4_import.spike import hardcore as H
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV, fallout4_actor_values

#: FalloutNV.esm's IsHardcore == 1 and == 0 conditions, as its stimpak carries them.
IS_HARDCORE = '000000000000803F4A02000000000000000000000000000000000000'
NOT_HARDCORE = '00000000000000004A02000000000000000000000000000000000000'
EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
#: FNV points per game hour: 120 real seconds per hour over 10, 25 and 50 seconds per point.
PER_HOUR = [12.0, 4.8, 2.4]
GLOBAL = 0x05000A00


def _convert(monkeypatch, body: str) -> str:
    """A one-block FNV script as its Fallout 4 conversion."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    src = f'scn T\nshort x\nbegin GameMode\n{body}\nend\n'
    return ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'ObjectReference', 'T')


def test_scripts_read_and_set_hardcore_through_its_quest(monkeypatch):
    """IsHardcore, IsAlwaysHardcore (FNV's short name behemoth) and SetHardcore call the Hardcore quest."""
    out = _convert(monkeypatch, 'if player.IsHardcore\n  set x to 1\nendif\nif player.behemoth == 1\n  set x to 2\n'
                                'endif\nSetHardcore 1\nSetHardcore 0')
    assert 'TES4Hardcore.IsOn()' in out and 'TES4Hardcore.IsAlways()' in out
    assert 'TES4Hardcore.SetHardcore(true)' in out and 'TES4Hardcore.SetHardcore(false)' in out
    assert 'F3NV_Hardcore Property TES4Hardcore' in out and 'TODO' not in out


def test_needs_are_helper_actor_values_under_fnvs_spellings():
    """The needs are helper actor values, under FNV's spellings too."""
    avs = fallout4_actor_values()
    assert avs['sleepdeprevation'] == avs['sleepdeprivation'] and avs['starvation'] == avs['hunger']
    assert {avs[n][2] for n in ('dehydration', 'hunger', 'sleepdeprivation')} == {0x823, 0x824, 0x825}


def _rec(*effects) -> dict:
    """An FNV export ALCH with (EFID, magnitude, conditions) effects."""
    rec = {'EditorID': 'Test', 'EffectCount': str(len(effects))}
    for i, (edid, magnitude, conds) in enumerate(effects):
        key = f'Effect[{i}]'
        rec.update({f'{key}.EFID': edid, f'{key}.Magnitude': str(magnitude), f'{key}.Area': '0',
                    f'{key}.Duration': '0', f'{key}.ActorValue': '73', f'{key}.ConditionCount': str(len(conds))})
        rec.update({f'{key}.Condition[{j}].Raw': raw for j, raw in enumerate(conds)})
    return rec


def test_hardcore_variants_are_kept_with_their_test():
    """Both of the stimpak's variants are kept, each with its IsHardcore test."""
    rec = _rec(('RestoreHealth', 5, [IS_HARDCORE]), ('RestoreHealthStimpak', 30, [NOT_HARDCORE]))
    effects = CE.fnv_effects(rec)
    assert [e[0] for e in effects] == ['RestoreHealth', 'RestoreHealthStimpak']
    assert [[C.compare(c, 1.0) for c in e[6]] for e in effects] == [[True], [False]]


def test_an_isHardcore_test_reads_the_global():
    """The test is FO4's GetGlobalValue on the Hardcore global, its comparison kept."""
    hardcore = SimpleNamespace(on=GLOBAL)
    ctda = H.Hardcore.test(hardcore, C.parse(IS_HARDCORE))
    op, value, func, p1 = struct.unpack_from('<B3xfH2xI', ctda, 6)
    assert (op, value, func, p1) == (0x00, 1.0, C.FO4.index('GetGlobalValue'), GLOBAL)


def _hardcore(monkeypatch) -> tuple:
    """A Hardcore on stand-in records, and the [(edid, VMAD)] of the effects it writes."""
    written = []
    monkeypatch.setattr(H, 'hotkey_effect', lambda b, fid, edid, name, vmad: written.append((edid, vmad)))
    builder = SimpleNamespace(counts=Counter(), scripts=SimpleNamespace(used=[]),
                              writer=SimpleNamespace(derive_formid=lambda site, key: hash(key) & 0xFFFFFF))
    hardcore = H.Hardcore.__new__(H.Hardcore)
    hardcore.builder, hardcore.quest, hardcore.made = builder, 0x123, {}
    return hardcore, written


def test_need_effects_carry_fnvs_own_amount(monkeypatch):
    """One effect per FNV effect and amount, the amount FNV's own; lowering a need is negative."""
    hardcore, written = _hardcore(monkeypatch)
    assert hardcore.need_effects('RestoreDehydrationLevel', 50)[0][1] == 50.0
    hardcore.need_effects('RestoreDehydrationLevel', 50)
    hardcore.need_effects('DamageDehydrationLevel', 25)
    hardcore.need_effects('RestoreSleepDeprivationLevel', 15)
    assert len(written) == 3 and hardcore.builder.scripts.used == [H.NEED_SCRIPT] * 3
    vmads = dict(written)
    assert struct.pack('<f', -50.0) in vmads['FNV_Hardcore_RestoreDehydrationLevel_50']
    assert struct.pack('<f', 25.0) in vmads['FNV_Hardcore_DamageDehydrationLevel_25']


def test_a_stage_holds_while_its_need_is_in_range():
    """A stage's effects run from its threshold to the next one's."""
    tests = H.range_tests(0x823, 200, 400)
    ops = [struct.unpack_from('<B3xf', tests, 6 + i * 38) for i in range(2)]
    assert ops == [(0x60, 200.0), (0x80, 400.0)]


@pytest.mark.skipif(not (EXPORT / 'GMST.txt').exists(), reason='needs the FalloutNV.esm export')
def test_fnv_rates_come_from_its_settings_and_timescale():
    """The exe's 10 s thirst, the ESM's 25 s hunger and 50 s sleep, TimeScale 30."""
    assert H.per_hour(EXPORT) == pytest.approx(PER_HOUR)
