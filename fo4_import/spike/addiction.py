"""FNV chem addiction as FO4's: a chem whose withdrawal spell FO4 has a counterpart for takes that chem's addiction.

FNV's ENIT names a withdrawal spell and an addiction chance. FO4's chems carry
the same three parts of one addiction: ENIT's addiction spell and chance, an
`AddictionOdds*` effect raising that addiction's actor value, and an
`AddictionKeyword*` keyword. A converted chem whose withdrawal is in
COUNTERPARTS takes the counterpart chem's spell, effect and keyword, at FNV's
chance. Other withdrawals (Hydra, Turbo, Steady, tobacco, ant nectar, Quantum)
have no FO4 addiction and are left out, counted.

See: docs/fork/fo4_pipeline.md#chem-addiction
"""

import struct

from tes5_import.base.writer import pack_subrecord

#: FNV withdrawal spell -> the Fallout4.esm chem whose addiction it becomes.
COUNTERPARTS = {'WithdrawalAlcohol': 'BeerGwinnettStout_Cold', 'WithdrawalPsycho': 'Psycho', 'WithdrawalJet': 'Jet',
                'MS09WithdrawalUltrajet': 'Jet', 'WithdrawalMentats': 'Mentats', 'WithdrawalBuffout': 'Buffout',
                'WithdrawalMorphine': 'MedX'}
#: EditorID prefixes of FO4's addiction effects and keywords.
ODDS, KEYWORD = 'AddictionOdds', 'AddictionKeyword'
#: FO4 ENIT offset of the addiction spell and chance.
ADDICTION_AT = 8


class Addictions:
    """FO4 addiction parts per FNV withdrawal spell, from Fallout4.esm's counterpart chems."""

    def __init__(self, builder, chems: dict, names: dict):
        """`chems`: {EditorID: subrecords}; `names`: {FormID: EditorID}."""
        self.builder = builder
        self.parts = {w: addiction_parts(chems[chem], names) for w, chem in COUNTERPARTS.items()}

    def apply(self, withdrawal: str, chance: float) -> 'tuple | None':
        """(ENIT addiction spell and chance, keyword FormID or None, effect pair) for an FNV chem with
        `withdrawal`; None for no withdrawal, counted when FO4 has no addiction for it."""
        if not withdrawal:
            return None
        if withdrawal not in self.parts:
            self.builder.counts['ALCH addiction left out (no FO4 addiction)'] += 1
            return None
        spell, keyword, pair = self.parts[withdrawal]
        self.builder.counts['ALCH addiction (FO4 counterpart)'] += 1
        return struct.pack('<If', spell, chance), keyword, pair


def addiction_parts(subs: list, names: dict) -> tuple:
    """(addiction spell, keyword FormID or None, EFID+EFIT of the odds effect) of a Fallout4.esm chem's
    subrecords `subs`, in order."""
    found = dict(subs)
    spell = struct.unpack_from('<I', found[b'ENIT'], ADDICTION_AT)[0]
    kwda = found.get(b'KWDA', b'')
    keyword = next((k for k in struct.unpack(f'<{len(kwda) // 4}I', kwda) if names.get(k, '').startswith(KEYWORD)),
                   None)
    at = next(i for i, (t, v) in enumerate(subs)
              if t == b'EFID' and names.get(struct.unpack('<I', v)[0], '').startswith(ODDS))
    return spell, keyword, pack_subrecord('EFID', subs[at][1]) + pack_subrecord('EFIT', subs[at + 1][1])
