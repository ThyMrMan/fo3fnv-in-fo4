"""A DLC's rows merged into the game's start-game quest scripts (base.quest_merge and each script's rule)."""

from fo4_import.base.ledger import LedgerWriter
from fo4_import.base.master_overrides import drop_unchanged
from fo4_import.base.quest_merge import merged_quest
from fo4_import.base.vmad import quest_fragments, read_quest
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.spike import ammo_switch, challenges, condition
from tes5_import.base.writer import pack_subrecord

MASTERS = ['Fallout4.esm', 'FalloutHelpers.esl', 'XDI.esm', 'FalloutNV.esm']
GAME, DLC = 0x03000000, 0x04000000


def _ammo(lists: list) -> dict:
    """F3NV_AmmoSwitch values of [(list keyword, [round FormID])], each round's mod, mark and note derived from it."""
    out = {'Lists': ('objects', []), 'Starts': ('ints', []), **{c: ('objects', []) for c in ammo_switch.ROUND_COLUMNS}}
    for keyword, rounds in lists:
        out['Lists'][1].append(keyword)
        out['Starts'][1].append(len(out['Rounds'][1]))
        for r in rounds:
            for i, column in enumerate(ammo_switch.ROUND_COLUMNS):
                out[column][1].append(r + i)
    out['Starts'][1].append(len(out['Rounds'][1]))
    return out


def _quest_body(values: dict, script: str = ammo_switch.SCRIPT) -> bytes:
    """A QUST body: EDID, then the VMAD of `script` on `values` as a plain quest script."""
    vmad = quest_fragments('', [], scripts=[(script, {'Hotkey': GAME | 0x900}, values)])
    return pack_subrecord('EDID', b'FNV_AmmoSwitch\0') + pack_subrecord('VMAD', vmad)


def test_a_quest_vmad_reads_back_to_what_wrote_it():
    """Plain scripts, string, int and float arrays and an alias script read back to the same arguments."""
    scripts = [(challenges.SCRIPT, {'Fists': 7}, {'Names': ('strings', ['a', 'b']), 'Events': ('ints', [1, -1]),
                                                  'Wear': ('floats', [0.5]), 'Text': ('string', 'x')})]
    aliases = [(0, GAME | 5, [(challenges.PLAYER_SCRIPT, {}, {})])]
    vmad = quest_fragments('', [], aliases=aliases, scripts=scripts)
    assert read_quest(vmad) == (scripts, aliases)


def test_the_dlcs_new_round_joins_its_game_list_and_its_new_list_follows():
    """A round the DLC adds to a game ammo list goes after the game's rounds; a list only the DLC has comes last;
    a game list the DLC build never reached stays."""
    game = _ammo([(GAME | 1, [GAME | 0x10, GAME | 0x20]), (GAME | 2, [GAME | 0x30])])
    dlc = _ammo([(GAME | 1, [GAME | 0x10, DLC | 0x40]), (DLC | 3, [DLC | 0x50, DLC | 0x60])])
    out = ammo_switch.merge(game, dlc)
    assert out['Lists'][1] == [GAME | 1, GAME | 2, DLC | 3]
    assert out['Starts'][1] == [0, 3, 4, 6]
    assert out['Rounds'][1] == [GAME | 0x10, GAME | 0x20, DLC | 0x40, GAME | 0x30, DLC | 0x50, DLC | 0x60]
    assert out['Notes'][1][2] == DLC | 0x43


def test_a_dlc_challenge_counts_the_game_stat_group_it_shares():
    """A new DLC challenge's stat group is the game's same group; a group the game lacks is added after its own."""
    def values(rows, groups, stats):
        """F3NV_Challenges values: `rows` (FormID, group), `stats` [(name, group)]."""
        out = {k: ('objects', [0] * len(rows)) for k in ('States', *challenges.FORM_COLUMNS)}
        out.update({k: ('ints', [0] * len(rows)) for k in challenges.INT_COLUMNS})
        out.update(Rows=('objects', [r for r, _ in rows]), Names=('strings', [str(r) for r, _ in rows]),
                   Groups=('ints', groups), StatNames=('strings', [n for n, _ in stats]),
                   StatGroups=('ints', [g for _, g in stats]))
        return out
    game = values([(GAME | 1, 0), (GAME | 2, -1)], [0, -1], [('Locks Picked', 0)])
    dlc = values([(GAME | 1, 1), (DLC | 3, 1), (DLC | 4, 0)], [1, 1, 0], [('Pants Exploded', 0), ('Locks Picked', 1)])
    out = challenges.merge(game, dlc)
    assert out['Rows'][1] == [GAME | 1, GAME | 2, DLC | 3, DLC | 4]
    assert out['Groups'][1] == [0, -1, 0, 1]
    assert out['StatNames'][1] == ['Locks Picked', 'Pants Exploded'] and out['StatGroups'][1] == [0, 1]


def test_dlc_weapons_and_armor_keep_their_repair_rows_on_their_side():
    """New DLC weapons follow the game's in every weapon column and the repair rows' weapon part; new armor too,
    its tier group mapped onto the game's same eleven tiers."""
    def values(weapons, armors, tiers):
        """F3NV_ConditionPlayer values of FormIDs `weapons`, (armor, group) `armors` and tier groups `tiers`."""
        items = weapons + [a for a, _ in armors]
        return {'Weapons': ('objects', weapons), 'MaxHealth': ('floats', [1.0] * len(weapons)),
                'JamTimes': ('floats', [-1.0] * len(weapons)), 'Armors': ('objects', [a for a, _ in armors]),
                'ArmorMax': ('floats', [2.0] * len(armors)), 'ArmorGroup': ('ints', [g for _, g in armors]),
                'ArmorTiers': ('objects', [t for group in tiers for t in group]),
                'RepairLists': ('objects', [i + 1 for i in items]), 'JuryGroups': ('ints', [i & 0xFF for i in items]),
                'AmmoMarks': ('objects', []), 'AmmoWear': ('floats', []), 'WearPerks': ('objects', []),
                'WearPerkMults': ('floats', [])}
    light, heavy = tuple(range(100, 111)), tuple(range(200, 211))
    game = values([GAME | 1], [(GAME | 5, 0)], [light])
    dlc = values([GAME | 1, DLC | 2], [(DLC | 6, 1), (DLC | 7, 0)], [heavy, light])
    out = condition.merge(game, dlc)
    assert out['Weapons'][1] == [GAME | 1, DLC | 2] and out['JamTimes'][1] == [-1.0, -1.0]
    assert out['Armors'][1] == [GAME | 5, DLC | 6, DLC | 7] and out['ArmorGroup'][1] == [0, 0, 1]
    assert out['ArmorTiers'][1] == list(light + heavy)
    assert out['RepairLists'][1] == [GAME | 2, DLC | 3, GAME | 6, DLC | 7, DLC | 8]


def test_a_quest_without_a_rule_or_with_other_changes_is_not_merged():
    """A script with no rule that differs, or a changed subrecord besides the VMAD, gives no merge."""
    game, dlc = _ammo([(GAME | 1, [GAME | 0x10])]), _ammo([(GAME | 1, [DLC | 0x10])])
    assert merged_quest(_quest_body(game), _quest_body(dlc), {}) is None
    assert merged_quest(_quest_body(game), _quest_body(dlc) + pack_subrecord('FULL', b'x\0'),
                        {ammo_switch.SCRIPT: ammo_switch.merge}) is None


def test_a_game_quest_naming_dlc_rounds_is_written_merged(tmp_path):
    """The DLC build's remade ammo quest, short of a game list, is kept as the game's quest with the DLC's round."""
    quest = GAME | 0x900
    game_values = _ammo([(GAME | 1, [GAME | 0x10]), (GAME | 2, [GAME | 0x30])])
    game = FO4PluginWriter(masters=MASTERS[:3], is_esm=True)
    game.add_record('QUST', pack_fo4_record('QUST', quest, 0, _quest_body(game_values)))
    path = tmp_path / 'FalloutNV.esm'
    game.write(str(path))
    dlc = LedgerWriter(masters=MASTERS, is_esm=True)
    dlc.add_record('AMMO', pack_fo4_record('AMMO', DLC | 0x40, 0, b''))
    dlc.add_record('QUST', pack_fo4_record('QUST', quest, 0, _quest_body(_ammo([(GAME | 1, [GAME | 0x10, DLC | 0x40])]))))
    counts = drop_unchanged(dlc, [path], set(), {ammo_switch.SCRIPT: ammo_switch.merge})
    assert counts == {'master records quest rows merged (QUST)': 1}
    body = next(r for r in dlc.top_records() if r[:4] == b'QUST')[24:]
    scripts, _ = read_quest(body[body.index(b'VMAD') + 6:])
    assert scripts[0][2]['Rounds'][1] == [GAME | 0x10, DLC | 0x40, GAME | 0x30]
