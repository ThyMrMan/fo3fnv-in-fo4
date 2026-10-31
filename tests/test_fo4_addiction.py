"""FNV chem addiction onto FO4's counterpart chems (spike.addiction)."""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import addiction as A

JET_SPELL, ODDS, KEYWORD, OTHER = 0x4BAE1, 0x245F06, 0x245F04, 0x96720
NAMES = {ODDS: 'AddictionOddsJet', KEYWORD: 'AddictionKeywordJet', OTHER: 'ObjectTypeChem', 0x248900: 'Slow'}
JET = [(b'EDID', b'Jet\0'), (b'KWDA', struct.pack('<II', OTHER, KEYWORD)),
       (b'ENIT', struct.pack('<iIIfI', 50, 3, JET_SPELL, 0.1, 0)),
       (b'EFID', struct.pack('<I', 0x248900)), (b'EFIT', b'a' * 12),
       (b'EFID', struct.pack('<I', ODDS)), (b'EFIT', b'b' * 12)]


def test_a_vanilla_chem_gives_its_addiction_spell_keyword_and_odds_effect():
    """ENIT's spell, the AddictionKeyword, the AddictionOdds pair and its EFIT."""
    spell, keyword, pair = A.addiction_parts(JET, NAMES)
    assert (spell, keyword) == (JET_SPELL, KEYWORD)
    assert pair.endswith(b'b' * 12) and struct.pack('<I', ODDS) in pair


def test_a_withdrawal_takes_its_counterparts_addiction_at_fnvs_chance_else_none():
    """Ultrajet's is Jet's at FNV's 0.2; Hydra's has no FO4 addiction (counted); no withdrawal, nothing."""
    builder = SimpleNamespace(counts=Counter())
    found = A.Addictions(builder, {chem: JET for chem in set(A.COUNTERPARTS.values())}, NAMES)
    enit, keyword, _ = found.apply('MS09WithdrawalUltrajet', 0.2)
    assert struct.unpack('<If', enit) == (JET_SPELL, struct.unpack('<f', struct.pack('<f', 0.2))[0])
    assert keyword == KEYWORD and found.apply('WithdrawalHydra', 0.1) is None and found.apply('', 0.0) is None
    assert builder.counts['ALCH addiction left out (no FO4 addiction)'] == 1
