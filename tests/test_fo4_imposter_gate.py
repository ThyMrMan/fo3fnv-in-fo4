"""FNV's region imposter glow cards shown only from inside a region whose imposter list names them.

See: docs/fork/fo4_look.md#route-horizon
"""
import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import imposter_gate as G
from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import subrecords

#: Two FNV regions and their watch globals; three glow cards (FNV FormIDs) and their FO4 copies.
CLOSE, MINI, CLOSE_GLOBAL, MINI_GLOBAL = 0x16ACA4, 0x172D32, 0x0A000101, 0x0A000102
CARDS = {0x1711BB: 0x0A0011BB, 0x1711BC: 0x0A0011BC, 0x1730BD: 0x0A0030BD}


def ctdas(data: bytes) -> list:
    """[(type flags, value, global)] of packed GetGlobalValue CTDAs."""
    return [struct.unpack_from('<B3xfH2xI', data, at + 6)[:2] + struct.unpack_from('<I', data, at + 18)
            for at in range(0, len(data), 38)]


def test_a_group_shows_while_one_region_holds_the_player_and_hides_while_none_does():
    """Show: an OR of the globals at 1; hide: each global at 0."""
    assert ctdas(G.shown_while([CLOSE_GLOBAL, MINI_GLOBAL], True)) == [(G.OR_NEXT, 1.0, CLOSE_GLOBAL),
                                                                        (0, 1.0, MINI_GLOBAL)]
    assert ctdas(G.shown_while([CLOSE_GLOBAL, MINI_GLOBAL], False)) == [(0, 0.0, CLOSE_GLOBAL), (0, 0.0, MINI_GLOBAL)]


def test_cards_listed_by_the_same_regions_share_one_ability_the_player_alias_gives():
    """Two cards of StripImposterClose and one of both regions: two abilities of a show, a hide and a day
    effect each, given by one start-game quest's player alias."""
    records, effects, spells = [], [], []
    builder = SimpleNamespace(
        counts=Counter(), scripts=SimpleNamespace(used=[], effects=SimpleNamespace(
            vmad_effect=lambda edid, vmad, delivery, cast: effects.append((edid, cast)) or len(effects),
            ability=lambda edid, pairs: spells.append((edid, pairs)) or 0x0A000200 + len(spells))),
        region_watch=SimpleNamespace(global_of={CLOSE: CLOSE_GLOBAL, MINI: MINI_GLOBAL}.get),
        writer=SimpleNamespace(derive_formid=lambda site, key: 0x0A000300, add_record=lambda sig, rec: records.append(rec)))
    gate = G.ImposterGate(builder)
    gate.regions = {0x1711BB: frozenset({CLOSE}), 0x1711BC: frozenset({CLOSE}), 0x1730BD: frozenset({CLOSE, MINI})}
    for fnv, fid in CARDS.items():
        gate.add(fnv, fid)
    gate.write()
    assert [e for e, _ in effects] == [f'FNV_ImposterGate_{key}_{name}' for key in ('16ACA4', '16ACA4_172D32')
                                       for name in ('Show', 'Hide', 'Day')]
    assert {cast for _, cast in effects} == {G.CONSTANT} and builder.scripts.used == [G.SCRIPT]
    alias = [struct.unpack('<I', data)[0] for tag, data in subrecords(records[0][24:]) if tag == b'ALSP']
    assert alias == [0x0A000201, 0x0A000202]


def test_alias_spells_sit_before_the_alias_end():
    """ALSP follows the forced reference and precedes ALED (xEdit's FO4 alias order)."""
    tags = [tag for tag, _ in subrecords(R.pack_qust(0x0A000001, 'Q', '', 0, [], 'Player', 0x14, spells=(5,))[24:])]
    assert tags.index(b'ALFR') < tags.index(b'ALSP') < tags.index(b'ALED')
