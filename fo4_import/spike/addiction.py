"""FNV chem addiction as FO4's: a counterpart chem's addiction, else one of its own built as vanilla's are.

FNV's ENIT names a withdrawal spell and an addiction chance. FO4's chems carry
the same three parts of one addiction: ENIT's addiction spell and chance, an
`AddictionOdds*` effect raising that addiction's actor value, and an
`AddictionKeyword*` keyword. A converted chem whose withdrawal is in
COUNTERPARTS takes the counterpart chem's spell, effect and keyword, at FNV's
chance. Any other FNV withdrawal (Hydra, Turbo, Steady, tobacco, ant nectar,
Quantum) gets its own on Jet's shapes (SHAPES): an actor value, an odds effect
raising it, a keyword, and an Addiction-type withdrawal spell of FNV's effects
(perks.constant_effect) with FO4's MARKERS in place of FNV's FNV_MARKER,
written after perks (write_spells).

See: docs/fork/fo4_pipeline.md#chem-addiction
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike.consumable_effects import AV_AT
from fo4_import.spike.perks import pack_spell
from fo4_import.spike.records import pack_kywd
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: FNV withdrawal spell -> the Fallout4.esm chem whose addiction it becomes.
COUNTERPARTS = {'WithdrawalAlcohol': 'BeerGwinnettStout_Cold', 'WithdrawalPsycho': 'Psycho', 'WithdrawalJet': 'Jet',
                'MS09WithdrawalUltrajet': 'Jet', 'WithdrawalMentats': 'Mentats', 'WithdrawalBuffout': 'Buffout',
                'WithdrawalMorphine': 'MedX'}
#: EditorID prefixes of FO4's addiction effects and keywords.
ODDS, KEYWORD = 'AddictionOdds', 'AddictionKeyword'
#: FO4 ENIT offset of the addiction spell and chance.
ADDICTION_AT = 8
#: Fallout4.esm's Jet addiction an own one is shaped on: its chem, withdrawal spell, actor value and odds effect.
SHAPE_CHEM, SHAPES = 'Jet', ('AbAddictionJet', 'AddictionJet', 'AddictionOddsJet')
#: Vanilla withdrawal spell effects beside the stat losses: the companions' reaction and the addictions count.
MARKERS = ('CA_AddictionEffect', 'abAddictionCount')
#: FNV's withdrawal marker effect (MARKERS stand in for it); FNV spell type Addiction.
FNV_MARKER, FNV_ADDICTION = 'AddictionEFFECT', '10'
#: derive_formid site of an own addiction's parts (key: the part's record type and the FNV withdrawal's EditorID).
SITE = 'FNV addiction'
#: AVIF subrecords copied from AddictionJet: default, flags, type.
AVIF_KEPT = (b'NAM0', b'AVFL', b'NAM1')
#: Bytes of an EFID subrecord (header and FormID), which an effect pair starts with.
EFID_SIZE = 10
#: The FNV condition function reading an actor value.
AV_TEST = 'GetActorValue'


class Addictions:
    """FO4 addiction parts per FNV withdrawal spell: Fallout4.esm's counterpart chems', else own ones."""

    def __init__(self, builder, chems: dict, names: dict, shapes: dict):
        """`chems`: {EditorID: subrecords} (COUNTERPARTS' and SHAPE_CHEM); `names`: {FormID: EditorID};
        `shapes`: {EditorID: subrecords} of SHAPES."""
        self.builder, self.names, self.shapes = builder, names, shapes
        self.parts = {w: addiction_parts(chems[chem], names) for w, chem in COUNTERPARTS.items()}
        self.jet = addiction_parts(chems[SHAPE_CHEM], names)
        self.withdrawals = {r['EditorID']: r for r in export_records(builder.export_dir, 'SPEL')
                            if r.get('SPIT.Type') == FNV_ADDICTION}
        self.unwritten, self.perks_written = [], False

    def spell(self, withdrawal: str) -> 'int | None':
        """FO4 addiction spell of FNV withdrawal `withdrawal` (EditorID); None for none.
        See: docs/fork/fo4_pipeline.md#chem-addiction
        """
        return self.parts[withdrawal][0] if withdrawal in self.parts or self._own(withdrawal) else None

    def apply(self, withdrawal: str, chance: float) -> 'tuple | None':
        """(ENIT addiction spell and chance, keyword FormID or None, effect pair) for an FNV chem with
        `withdrawal`; None for no withdrawal, counted when it names no FNV addiction spell."""
        if not withdrawal:
            return None
        own = withdrawal not in COUNTERPARTS
        if withdrawal not in self.parts and not self._own(withdrawal):
            self.builder.counts['ALCH addiction left out (no withdrawal spell)'] += 1
            return None
        spell, keyword, pair = self.parts[withdrawal]
        self.builder.counts['ALCH addiction (own)' if own else 'ALCH addiction (FO4 counterpart)'] += 1
        return struct.pack('<If', spell, chance), keyword, pair

    def _own(self, withdrawal: str) -> bool:
        """Make FNV withdrawal `withdrawal`'s own addiction: write its actor value, odds effect and keyword, queue
        its spell (write_spells); False when it names no FNV addiction spell."""
        rec = self.withdrawals.get(withdrawal)
        if rec is None:
            return False
        name, writer = withdrawal.replace('Withdrawal', ''), self.builder.writer
        ids = {sig: writer.derive_formid(SITE, f'{sig} {withdrawal}') for sig in ('SPEL', 'AVIF', 'MGEF', 'KYWD')}
        avif, odds = (dict(self.shapes[s]) for s in SHAPES[1:])
        av = pack_string_subrecord('EDID', f'FNV_Addiction{name}') + pack_string_subrecord('FULL', rec.get('FULL', ''))
        av += pack_string_subrecord('DESC', '') + b''.join(pack_subrecord(s.decode(), avif[s]) for s in AVIF_KEPT)
        writer.add_record('AVIF', pack_fo4_record('AVIF', ids['AVIF'], 0, av))
        writer.add_record('MGEF', pack_odds(ids['MGEF'], f'FNV_{ODDS}{name}', odds, ids['AVIF']))
        writer.add_record('KYWD', pack_kywd(ids['KYWD'], f'FNV_{KEYWORD}{name}', 0))
        self.builder.counts['addiction (own)'] += 1
        self.parts[withdrawal] = (ids['SPEL'], ids['KYWD'],
                                  pack_subrecord('EFID', struct.pack('<I', ids['MGEF'])) + self.jet[2][EFID_SIZE:])
        self.unwritten.append((ids['SPEL'], rec))
        if self.perks_written:
            self.write_spells()
        return True

    def write_spells(self) -> None:
        """Write the own withdrawal spells _own queued, and from now on each as it is made; after perks.write,
        whose form map their effects' conditions read (perks.constant_effect)."""
        self.perks_written, shape = True, self.shapes[SHAPES[0]]
        markers = b''.join(pack_subrecord('EFID', b) + pack_subrecord('EFIT', shape[i + 1][1])
                           for i, (s, b) in enumerate(shape)
                           if s == b'EFID' and self.names.get(struct.unpack('<I', b)[0]) in MARKERS)
        for fid, rec in self.unwritten:
            self.builder.writer.add_record('SPEL', pack_spell(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''),
                                                              dict(shape), self._effects(rec) + markers))
        self.unwritten.clear()

    def _effects(self, rec: dict) -> bytes:
        """EFID/EFIT pairs and conditions of FNV withdrawal `rec`'s effects but FNV_MARKER; one left out, counted."""
        out = b''
        for key in (f'Effect[{i}]' for i in range(int(rec.get('EffectCount', 0) or 0))):
            if rec[f'{key}.EFID'] == FNV_MARKER:
                continue
            settled = self._settled(rec, key)
            made = settled and self.builder.perks.constant_effect(settled, key)
            self.builder.counts['withdrawal effect' if made else f'withdrawal effect left out ({rec[f"{key}.EFID"]})'] += 1
            out += made[0] + made[1] if made else b''
        return out

    def _settled(self, rec: dict, key: str) -> 'dict | None':
        """`rec` with effect `key`'s tests of an actor value FO4 lacks settled: nothing sets one, so it reads 0
        (withdrawals test IgnoreCrippledLimbs == 0); a passing test is left out, None when one fails."""
        raws = [rec[f'{key}.Condition[{j}].Raw'] for j in range(int(rec.get(f'{key}.ConditionCount', 0) or 0))]
        kept = []
        for raw in raws:
            cond = C.parse(raw)
            other = cond['func'] != AV_TEST or not 0 <= cond['p1'] < len(C.FNV_AV_NAMES)
            if other or actor_value_form(C.fnv_av_name(cond['p1']), self.builder.perks.helper_index) is not None:
                kept.append(raw)
            elif not C.compare(cond, 0.0):
                return None
        out = {k: v for k, v in rec.items() if not k.startswith(f'{key}.Condition')}
        return {**out, f'{key}.ConditionCount': str(len(kept)), **{f'{key}.Condition[{j}].Raw': raw
                                                                  for j, raw in enumerate(kept)}}


def pack_odds(fid: int, edid: str, shape: dict, av: int) -> bytes:
    """An addiction odds effect: `shape`'s (AddictionOddsJet) raising actor value `av`."""
    data = bytearray(shape[b'DATA'])
    struct.pack_into('<I', data, AV_AT, av)
    subs = pack_string_subrecord('EDID', edid) + pack_subrecord('DATA', bytes(data))
    return pack_fo4_record('MGEF', fid, 0, subs + pack_subrecord('SNDD', b'') + pack_subrecord('DNAM', shape[b'DNAM']))


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
