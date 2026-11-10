"""FNV chem addiction onto FO4's counterpart chems, else its own addictions (spike.addiction)."""

import struct
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.spike import addiction as A
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

JET_SPELL, ODDS, KEYWORD, OTHER = 0x4BAE1, 0x245F06, 0x245F04, 0x96720
CA_EFFECT, COUNT, AGILITY = 0x2A74C, 0x1EB997, 0x17E601
NAMES = {ODDS: 'AddictionOddsJet', KEYWORD: 'AddictionKeywordJet', OTHER: 'ObjectTypeChem', 0x248900: 'Slow',
         CA_EFFECT: 'CA_AddictionEffect', COUNT: 'abAddictionCount', AGILITY: 'abReduceAgilityAddiction'}
JET = [(b'EDID', b'Jet\0'), (b'KWDA', struct.pack('<II', OTHER, KEYWORD)),
       (b'ENIT', struct.pack('<iIIfI', 50, 3, JET_SPELL, 0.1, 0)),
       (b'EFID', struct.pack('<I', 0x248900)), (b'EFIT', b'a' * 12),
       (b'EFID', struct.pack('<I', ODDS)), (b'EFIT', b'b' * 12)]
SHAPES = {'AbAddictionJet': [(b'ETYP', b'e' * 4), (b'SPIT', b's' * 36),
                             (b'EFID', struct.pack('<I', AGILITY)), (b'EFIT', b'x' * 12),
                             (b'EFID', struct.pack('<I', CA_EFFECT)), (b'EFIT', b'c' * 12),
                             (b'EFID', struct.pack('<I', COUNT)), (b'EFIT', b'n' * 12)],
          'AddictionJet': [(b'NAM0', struct.pack('<f', -70.0)), (b'AVFL', b'f' * 4), (b'NAM1', struct.pack('<I', 8))],
          'AddictionOddsJet': [(b'DATA', bytes(0x50)), (b'DNAM', bytes(4))]}
CTDA = pack_subrecord('CTDA', b't' * 32)
#: FNV's withdrawal test GetActorValue IgnoreCrippledLimbs == 0 (an actor value FO4 lacks), and one failing at 0.
IGNORES, IGNORED = ('00000000000000000E00000048000000000000000000000000000000',
                    '000000000000803F0E00000048000000000000000000000000000000')
#: FNV's Hydra withdrawal: Endurance -3 under a condition, and FNV's marker effect.
HYDRA = {'EditorID': 'WithdrawalHydra', 'FULL': 'Hydra Withdrawal', 'SPIT.Type': '10', 'EffectCount': '2',
         'Effect[0].EFID': 'AddictRedENHydra', 'Effect[0].ConditionCount': '1', 'Effect[0].Condition[0].Raw': IGNORES,
         'Effect[1].EFID': 'AddictionEFFECT'}


def _addictions(monkeypatch, written: list) -> 'A.Addictions':
    """Addictions over JET for every counterpart, FNV's Hydra withdrawal and SHAPES; records go to `written`."""
    monkeypatch.setattr(A, 'export_records', lambda folder, sig: (HYDRA, {'EditorID': 'Fireball', 'SPIT.Type': '0'}))
    perks = SimpleNamespace(helper_index=1, constant_effect=lambda rec, key: (pack_subrecord('EFID', struct.pack('<I', 0xE11))
                                                              + pack_subrecord('EFIT', b'h' * 12), CTDA))
    builder = SimpleNamespace(counts=Counter(), export_dir='x', perks=perks, writer=SimpleNamespace(
        derive_formid=lambda site, key: {'SPEL': 0x100, 'AVIF': 0x101, 'MGEF': 0x102, 'KYWD': 0x103}[key.split()[0]],
        add_record=lambda sig, data: written.append((sig, list(subrecords(data[24:]))))))
    return A.Addictions(builder, {chem: JET for chem in set(A.COUNTERPARTS.values())}, NAMES, SHAPES)


def test_a_vanilla_chem_gives_its_addiction_spell_keyword_and_odds_effect():
    """ENIT's spell, the AddictionKeyword, the AddictionOdds pair and its EFIT."""
    spell, keyword, pair = A.addiction_parts(JET, NAMES)
    assert (spell, keyword) == (JET_SPELL, KEYWORD)
    assert pair.endswith(b'b' * 12) and struct.pack('<I', ODDS) in pair


def test_a_withdrawal_takes_its_counterparts_addiction_at_fnvs_chance_else_none(monkeypatch):
    """Ultrajet's is Jet's at FNV's 0.2; a withdrawal naming no FNV addiction spell is counted; none, nothing."""
    found = _addictions(monkeypatch, [])
    enit, keyword, _ = found.apply('MS09WithdrawalUltrajet', 0.2)
    assert struct.unpack('<If', enit) == (JET_SPELL, struct.unpack('<f', struct.pack('<f', 0.2))[0])
    assert keyword == KEYWORD and found.apply('Fireball', 0.1) is None and found.apply('', 0.0) is None
    assert found.builder.counts['ALCH addiction left out (no withdrawal spell)'] == 1


def test_a_withdrawal_names_its_fo4_addiction_spell_for_a_cure_script(monkeypatch):
    """Jet's is FO4's Jet addiction, Hydra's its own; another spell none.
    See: docs/fork/fo4_pipeline.md#chem-addiction"""
    found = _addictions(monkeypatch, [])
    assert found.spell('WithdrawalJet') == JET_SPELL and found.spell('WithdrawalHydra') == 0x100
    assert found.spell('Fireball') is None


def test_hydra_gets_an_fo4_style_addiction_of_its_own(monkeypatch):
    """Hydra's chem takes its own spell, keyword and an odds effect at Jet's EFIT; the actor value, odds effect
    (raising it) and keyword are written once, the withdrawal spell after perks: Jet's SPIT, FNV's effects with
    conditions, FO4's two marker effects for FNV's marker."""
    written = []
    found = _addictions(monkeypatch, written)
    enit, keyword, pair = found.apply('WithdrawalHydra', 0.1)
    assert found.apply('WithdrawalHydra', 0.1)[0] == enit and struct.unpack_from('<I', enit)[0] == 0x100
    assert keyword == 0x103 and pair == pack_subrecord('EFID', struct.pack('<I', 0x102)) + pack_subrecord(
        'EFIT', b'b' * 12)
    assert [s for s, _ in written] == ['AVIF', 'MGEF', 'KYWD']
    avif, mgef = dict(written[0][1]), dict(written[1][1])
    assert avif[b'EDID'] == b'FNV_AddictionHydra\0' and avif[b'NAM0'] == struct.pack('<f', -70.0)
    assert struct.unpack_from('<I', mgef[b'DATA'], A.AV_AT)[0] == 0x101
    found.write_spells()
    sig, spell = written[3]
    effects = [struct.unpack('<I', b)[0] for s, b in spell if s == b'EFID']
    assert sig == 'SPEL' and dict(spell)[b'SPIT'] == b's' * 36 and effects == [0xE11, CA_EFFECT, COUNT]
    assert spell[spell.index((b'EFID', struct.pack('<I', 0xE11))) + 2] == (b'CTDA', b't' * 32)
    assert found.builder.counts['ALCH addiction (own)'] == 2 and found.builder.counts['addiction (own)'] == 1


@pytest.mark.parametrize('withdrawal', ['WithdrawalHydra'])
def test_an_own_addiction_made_after_perks_is_written_at_once(monkeypatch, withdrawal):
    """Once write_spells ran, a newly made addiction's spell is written with it."""
    written = []
    found = _addictions(monkeypatch, written)
    found.write_spells()
    found.spell(withdrawal)
    assert [s for s, _ in written] == ['AVIF', 'MGEF', 'KYWD', 'SPEL']


def test_a_withdrawal_test_of_an_actor_value_fo4_lacks_reads_0(monkeypatch):
    """IgnoreCrippledLimbs == 0 passes and is left out; == 1 never passes, so the effect is dropped."""
    found = _addictions(monkeypatch, [])
    settled = found._settled(HYDRA, 'Effect[0]')
    assert settled['Effect[0].ConditionCount'] == '0' and 'Effect[0].Condition[0].Raw' not in settled
    assert found._settled({**HYDRA, 'Effect[0].Condition[0].Raw': IGNORED}, 'Effect[0]') is None
