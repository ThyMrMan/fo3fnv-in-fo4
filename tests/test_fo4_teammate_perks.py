"""FNV teammate perks: the player holds the FNV perk, the named companion a gated perk of its entry points.

See: docs/fork/fo4_perks.md#teammate-perks
"""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import conditions as C
from fo4_import.spike import npcs as N
from fo4_import.spike import perks as P
from fo4_import.spike import records as R
from fo4_import.spike import teammates as T
from fo4_import.spike.type_tests import FORM_KEY as TYPE_KEYWORDS
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: FNV NPC RoseofSharonCassidy, and the FO4 NPC the stand-in build gives her.
CASS, CASS_FO4 = 0x133FDD, 0x0B000001
#: Hand of Vengeance's weapon tab as exported: GetWeaponSkillType == 41 (Guns).
GUNS_WEAPON = '000000000000803f6d00000029000000000000000000000000000000'


def _fnv_ctda(func: int, param: int, kind: int = 0) -> str:
    """An FNV export condition: `func` `param` == 1 (comparison and flags in `kind`)."""
    return struct.pack('<B3xfH2xIIII', kind, 1.0, func, param, 0, 0, 0).hex()


def _hand_of_vengeance(ability: bool = False) -> dict:
    """Hand of Vengeance as exported: Guns damage x1.15 for Cass (owner tab GetIsID), plus an ability if asked."""
    rec = {'FormID': '00163349', 'EditorID': 'HandOfVengeance', 'FULL': 'Hand of Vengeance', 'DATA.Ranks': '1',
           'EffectCount': '2' if ability else '1',
           'Effect[0].Type': 'EntryPoint', 'Effect[0].Rank': '0', 'Effect[0].EntryPoint': '0',
           'Effect[0].Function': '3', 'Effect[0].ValueType': '1', 'Effect[0].Value': struct.pack('<f', 1.15).hex(),
           'Effect[0].Tab[0].RunOn': '0', 'Effect[0].Tab[0].Condition[0].Raw': _fnv_ctda(T.GET_IS_ID, CASS),
           'Effect[0].Tab[1].RunOn': '1', 'Effect[0].Tab[1].Condition[0].Raw': GUNS_WEAPON}
    if ability:
        rec.update({'Effect[1].Type': 'Ability', 'Effect[1].Rank': '0', 'Effect[1].Ability': '00167722'})
    return rec


def _perks() -> P.Perks:
    """A Perks with a stand-in builder that writes into `written`, Cass built, no Fallout4.esm read."""
    perks = P.Perks.__new__(P.Perks)
    perks.written_records = []
    perks.builder = SimpleNamespace(counts=Counter(),
                                    writer=SimpleNamespace(add_record=lambda s, r: perks.written_records.append(r)))
    keywords = SimpleNamespace(keyword=lambda edid: 0x0B200001)
    perks.forms, perks.script_vars = {CASS: CASS_FO4, TYPE_KEYWORDS: keywords}, {}
    perks.tabs, perks.vanilla = {35: 3}, {}
    return perks


def test_only_flagged_uncommented_calls_are_teammate_perks():
    """Flagged AddPerk/RemovePerk count; no flag, a 0 flag or a comment do not."""
    text = ('Player.AddPerk CalmHeart 1\r\n\tplayer.removeperk OldVaquero, 1\r\nPlayer.AddPerk Plain\r\n'
            'Player.AddPerk Zero 0\r\n; Player.AddPerk Commented 1\r\nset x to 1 ; AddPerk Late 1')
    assert T.TEAMMATE_CALL.findall(text) == ['CalmHeart', 'OldVaquero']


def test_companions_are_the_owner_tabs_get_is_id():
    """The owner tab's GetIsID == 1 names the companion; a != test does not."""
    rec = _hand_of_vengeance()
    rec['Effect[0].Tab[0].Condition[1].Raw'] = _fnv_ctda(T.GET_IS_ID, 0x1234, kind=0x20)
    assert T.named_companions(rec) == [CASS]


def test_companion_perk_gates_fnv_entry_points_on_teammate_and_the_players_perk():
    """The companion perk keeps FNV's entry point; its owner tab adds GetPlayerTeammate == 1 and PlayerRef.HasPerk
    (the player's perk) == 1 before GetIsID; an ability is left out, counted."""
    perks = _perks()
    perks._companion_perk(_hand_of_vengeance(ability=True), 0x0B163349, (0x0B200000, [CASS]))
    subs = subrecords(perks.written_records[0][24:])
    assert dict(subs)[b'EDID'] == b'FNV_HandOfVengeance_Teammates\0'
    owner = [d for t, d in subs if t == b'CTDA'][:3]
    funcs = [struct.unpack_from('<H', d, 8)[0] for d in owner]
    assert funcs == [C.FO4.index('GetPlayerTeammate'), C.FO4.index('HasPerk'), T.GET_IS_ID]
    assert struct.unpack_from('<IIII', owner[1], 12) == (0x0B163349, 0, R.RUN_REFERENCE, T.PLAYER_REF)
    assert struct.unpack_from('<I', owner[2], 12)[0] == CASS_FO4
    assert sum(1 for t, _ in subs if t == b'PRKE') == 1
    assert perks.builder.counts['companion perk effect left out (not an entry point)'] == 1


def test_teammate_perk_naming_no_companion_writes_no_companion_perk():
    """A teammate perk naming no NPC (Calm Heart) is counted, not written."""
    perks = _perks()
    perks._companion_perk({'FormID': '0016334B', 'EditorID': 'CalmHeart'}, 1, (2, []))
    assert not perks.written_records and perks.builder.counts['teammate perk naming no companion'] == 1


def test_npc_holds_its_companion_perks_before_aidt():
    """An NPC's perks are PRKZ then a rank-1 PRKR each, placed before AIDT as vanilla orders them."""
    subs = pack_subrecord('ACBS', bytes(4)) + pack_subrecord('AIDT', bytes(4))
    tags = subrecords(N.with_perks([0x0B000010, 0x0B000020])(subs))
    assert [t for t, _ in tags] == [b'ACBS', b'PRKZ', b'PRKR', b'PRKR', b'AIDT']
    assert tags[2][1] == struct.pack('<IB', 0x0B000010, 1) and N.with_perks([]) is None


def test_held_by_lists_the_companion_perks_naming_an_npc():
    """An NPC holds the companion perks naming it, sorted as xEdit sorts PRKR."""
    teammates = T.Teammates.__new__(T.Teammates)
    teammates.perks = {1: (0x0B000020, [CASS]), 2: (0x0B000010, [CASS, 0x99]), 3: (0x0B000030, [0x99])}
    assert teammates.held_by(CASS) == [0x0B000010, 0x0B000020]
