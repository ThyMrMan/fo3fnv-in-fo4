"""FormIDs across plugins: a dependent source's master byte, and a master build's ledger (base.source_ids)."""

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.base.ledger import Ledger, LedgerWriter, ledger_path
from fo4_import.base.master_overrides import added_perk_entries, drop_unchanged, master_records
from fo4_import.base.source_ids import SourceIds, built_plugins, dependent_masters, master_ledgers
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record, pack_quest, pack_topic
from fo4_import.spike import list_adds
from fo4_import.spike.cell import COPY_SITE, CellBuilder
from fo4_import.spike.say_once import SayOnce
from script_convert.pipeline import pack_wstring
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_group, pack_subrecord

FO4_MASTERS = ['Fallout4.esm', 'FalloutHelpers.esl', 'XDI.esm', 'FalloutNV.esm']
SITE, KEY = 'FNV type keyword', 'FNV_WeaponSkillGuns'


def test_a_dlc_record_on_its_master_is_the_game_plugins_and_its_own_the_builds():
    """DeadMoney's 00xxxxxx (FalloutNV.esm's) is FalloutNV.esm's FO4 index; its 01xxxxxx the build's own."""
    ids = SourceIds(['FalloutNV.esm'], FO4_MASTERS, len(FO4_MASTERS))
    assert ids.fo4(0x00123456) == 0x03123456 and not ids.is_own(0x00123456)
    assert ids.fo4(0x01000800) == 0x04000800 and ids.is_own(0x01000800)
    alone = SourceIds([], FO4_MASTERS[:3], 3)
    assert alone.fo4(0x00123456) == 0x03123456 and alone.is_own(0x00123456)
    with pytest.raises(ValueError, match='FalloutNV.esm'):
        SourceIds(['FalloutNV.esm'], FO4_MASTERS[:3], 3)


def test_a_generated_record_the_master_holds_is_the_masters_and_not_written_again(tmp_path):
    """The game build keeps its keyword in its ledger; a DLC build reads it: the same object id at the game
    plugin's index, its record left out; a key the master lacks is the DLC's own."""
    game = LedgerWriter(masters=['Fallout4.esm'], is_esm=True)
    game.use_ledger(Ledger(ledger_path(tmp_path / 'FalloutNV.esm')))
    keyword = game.derive_formid(SITE, KEY)
    game.ledger.save()
    dlc = LedgerWriter(masters=['Fallout4.esm', 'FalloutNV.esm'], is_esm=True)
    dlc.use_master_ledgers(master_ledgers(['Fallout4.esm', 'FalloutNV.esm'], (tmp_path,)))
    shared = dlc.derive_formid(SITE, KEY)
    assert shared == 0x01 << 24 | keyword & 0xFFFFFF
    dlc.add_record('KYWD', pack_fo4_record('KYWD', shared, 0, b''))
    assert dlc.left_to_masters == 1 and not list(dlc.top_records())
    own = dlc.derive_formid(SITE, 'FNV_DeadMoneyOnly')
    assert own >> 24 == dlc.own_index
    dlc.add_record('KYWD', pack_fo4_record('KYWD', own, 0, b''))
    assert [struct.unpack_from('<I', r, 12)[0] for r in dlc.top_records()] == [own]


def test_a_master_ledger_id_its_master_no_longer_holds_is_the_dlcs_own(tmp_path):
    """A game ledger id the built game plugin holds is the game's; one it no longer holds hashes to the DLC's own
    copy; without the held set (a masterless build) the ledger alone decides."""
    game = LedgerWriter(masters=['Fallout4.esm'], is_esm=True)
    game.use_ledger(Ledger(ledger_path(tmp_path / 'FalloutNV.esm')))
    held, stale = game.derive_formid(SITE, KEY), game.derive_formid(SITE, 'FNV_GoneFromTheGame')
    game.ledger.save()
    ledgers = master_ledgers(['Fallout4.esm', 'FalloutNV.esm'], (tmp_path,))
    for hold, expect_stale in ((frozenset({0x01 << 24 | held & 0xFFFFFF}), None), (None, 0x01 << 24 | stale & 0xFFFFFF)):
        dlc = LedgerWriter(masters=['Fallout4.esm', 'FalloutNV.esm'], is_esm=True)
        dlc.use_master_ledgers(ledgers, hold)
        assert dlc.derive_formid(SITE, KEY) == 0x01 << 24 | held & 0xFFFFFF
        copy = dlc.derive_formid(SITE, 'FNV_GoneFromTheGame')
        assert copy == expect_stale if expect_stale else copy >> 24 == dlc.own_index


def _world(refs: list) -> bytes:
    """A top WRLD group: worldspace 0x03000A00, its cell 0x03000B00, and REFRs `refs` [(FormID, body)] as its
    temporary children."""
    temporary = pack_group(9, struct.pack('<I', 0x03000B00), b''.join(pack_fo4_record('REFR', f, 0, b) for f, b in refs))
    cell = pack_fo4_record('CELL', 0x03000B00, 0, pack_subrecord('DATA', b'\x00\x00'))
    world = pack_group(1, struct.pack('<I', 0x03000A00), cell + pack_group(6, struct.pack('<I', 0x03000B00), temporary))
    return pack_group(0, b'WRLD', pack_fo4_record('WRLD', 0x03000A00, 0, pack_subrecord('EDID', b'W\0')) + world)


def test_a_dlc_drops_game_refs_in_its_worldspace_groups_that_change_nothing(tmp_path):
    """Placed refs in a pre-built WRLD group: one identical to the game's goes; one the DLC changes stays under the
    game's cell and worldspace (their own copies), which therefore stay too."""
    same, moved = (0x03000C01, pack_subrecord('NAME', bytes(4))), (0x03000C02, pack_subrecord('NAME', bytes(4)))
    game = FO4PluginWriter(masters=FO4_MASTERS[:3], is_esm=True)
    game.add_raw_group('WRLD', _world([same, moved]))
    path = tmp_path / 'FalloutNV.esm'
    game.write(str(path))
    dlc = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    dlc.add_raw_group('WRLD', _world([same, (moved[0], pack_subrecord('NAME', b'\x01\0\0\0'))]))
    counts = drop_unchanged(dlc, [path], {moved[0]})
    left = [rec.form_id for blob in dlc.raw_groups() for rec, _ in walk(blob, bodies=(), span=(0, len(blob)))]
    assert left == [0x03000A00, 0x03000B00, moved[0]]
    assert counts['master records same as master (REFR)'] == 1 and counts['master records override (REFR)'] == 1


def _built_game(tmp_path, masters: list, records: list) -> Path:
    """Write the built game plugin FalloutNV.esm with `masters` and `records` [(signature, FormID, body)]."""
    game = FO4PluginWriter(masters=masters, is_esm=True)
    for sig, fid, body in records:
        game.add_record(sig, pack_fo4_record(sig, fid, 0, body))
    path = tmp_path / 'FalloutNV.esm'
    game.write(str(path))
    return path


def test_a_dlc_build_lists_the_game_plugins_masters_first_and_needs_it_built(tmp_path):
    """The game's masters and the game lead a DLC's masters, its own replacement mod after; unbuilt raises."""
    with pytest.raises(SystemExit, match='FalloutNV.esm'):
        built_plugins(['FalloutNV.esm'], (tmp_path,))
    _built_game(tmp_path, FO4_MASTERS[:3] + ['GameMod.esp'], [])
    built = built_plugins(['FalloutNV.esm'], (tmp_path,))
    assert dependent_masters(built, ['DlcMod.esp', 'GameMod.esp'], FO4_MASTERS[:3]) == [
        *FO4_MASTERS[:3], 'GameMod.esp', 'FalloutNV.esm', 'DlcMod.esp']
    assert dependent_masters([], ['GameMod.esp'], FO4_MASTERS[:3]) == FO4_MASTERS[:3] + ['GameMod.esp']


def test_a_dlc_keeps_only_master_records_that_change_the_game_plugins(tmp_path):
    """Same as the game's: dropped; changed and held by the DLC: an override; changed but not held: dropped; the
    game never built it: dropped; a Fallout4.esm record the game left alone: a new override; the DLC's own: kept."""
    same, changed, unbuilt, fo4, own, drifted = 0x03000900, 0x03000901, 0x03000902, 0x00012345, 0x04000800, 0x03000903
    path = _built_game(tmp_path, FO4_MASTERS[:3], [('FLST', same, b'a'), ('FLST', changed, b'b'),
                                                   ('FLST', drifted, b'g')])
    dlc = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    for fid, body in ((same, b'a'), (changed, b'c'), (unbuilt, b'd'), (fo4, b'e'), (own, b'f'), (drifted, b'h')):
        dlc.add_record('FLST', pack_fo4_record('FLST', fid, 0, body))
    counts = drop_unchanged(dlc, [path], {changed, own})
    assert sorted(struct.unpack_from('<I', r, 12)[0] for r in dlc.top_records()) == [fo4, changed, own]
    assert counts == {'master records same as master (FLST)': 1, 'master records override (FLST)': 1,
                      'master records not in its master (FLST)': 1, 'master records new override (FLST)': 1,
                      'master records changed by the build alone (FLST)': 1}


def test_a_master_topic_the_dlc_does_not_hold_goes_unless_it_carries_a_dlc_line(tmp_path):
    """A game topic and its lines remade by the DLC build: dropped; one carrying a DLC line: kept."""
    path = _built_game(tmp_path, FO4_MASTERS[:3], [])
    dlc = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    for dial, info in ((0x03000A00, 0x03000A01), (0x03000B00, 0x04000801)):
        dlc.add_record('DIAL', pack_topic(pack_fo4_record('DIAL', dial, 0, b''), dial,
                                          [pack_fo4_record('INFO', info, 0, b'')]))
    counts = drop_unchanged(dlc, [path], set())
    assert [struct.unpack_from('<I', r, 12)[0] for r in dlc.top_records()] == [0x03000B00]
    assert counts == {'master records not in its master (DIAL)': 2, 'master records not in its master (INFO)': 1}


def test_a_game_quest_holding_a_dlc_line_keeps_only_it_under_the_games_own_quest_and_topic(tmp_path):
    """A game quest the DLC build remade around one DLC line: the quest and topic stay as the game's bytes, the
    game's identical line and the scene the build changed alone go; a game topic with no DLC line goes whole."""
    quest, topic, bare, line, scene, mine = 0x03000C00, 0x03000C01, 0x03000C02, 0x03000C03, 0x03000C04, 0x04000802
    sub = pack_subrecord
    path = _built_game(tmp_path, FO4_MASTERS[:3], [('QUST', quest, sub('EDID', b'Q\0')), ('DIAL', topic, sub('TIFC', b'\1\0\0\0')),
                                                   ('DIAL', bare, b''), ('INFO', line, b'i'), ('SCEN', scene, b's')])
    dlc = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    topics = [pack_topic(pack_fo4_record('DIAL', topic, 0, sub('TIFC', b'\2\0\0\0')), topic,
                         [pack_fo4_record('INFO', line, 0, b'i'), pack_fo4_record('INFO', mine, 0, b'm')]),
              pack_topic(pack_fo4_record('DIAL', bare, 0, b''), bare, [pack_fo4_record('INFO', line + 9, 0, b'')])]
    dlc.add_record('QUST', pack_quest(pack_fo4_record('QUST', quest, 0, sub('EDID', b'Q\0') + sub('FNAM', b'x')),
                                      quest, topics=topics, scenes=[pack_fo4_record('SCEN', scene, 0, b't')]))
    counts = drop_unchanged(dlc, [path], set())
    expected = pack_quest(pack_fo4_record('QUST', quest, 0, sub('EDID', b'Q\0')), quest, topics=[pack_topic(
        pack_fo4_record('DIAL', topic, 0, sub('TIFC', b'\1\0\0\0')), topic, [pack_fo4_record('INFO', mine, 0, b'm')])])
    assert list(dlc.top_records()) == [expected]
    assert counts['master records same as master (INFO)'] == 1 and counts['master records same as master (DIAL)'] == 1
    assert counts['master records changed by the build alone (SCEN)'] == 1


def test_a_game_record_the_built_game_left_out_is_the_dlcs_own_copy():
    """In a DLC build: the DLC's record keeps its object id; a game record the built game plugin holds is the
    game's; one it left out is the DLC's own copy, hashed from the FNV FormID, the same id every build."""
    writer = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    ids = SourceIds(['FalloutNV.esm'], FO4_MASTERS, writer.own_index)
    builder = SimpleNamespace(ids=ids, writer=writer, top=0, in_masters=frozenset({0x03000900}))
    copy = CellBuilder.fnv_id(builder, '00000901')
    assert CellBuilder.fnv_id(builder, 0x01000850) == 0x04000850 and builder.top == 0x851
    assert CellBuilder.fnv_id(builder, 0x00000900) == 0x03000900
    assert copy >> 24 == writer.own_index and copy == writer.derive_formid(COPY_SITE, '00000901')


def test_a_game_record_naming_a_dlc_record_is_kept_added_to_at_run_time_or_dropped(tmp_path):
    """Records the DLC does not hold that now name its ammo: a gun keeping every game subrecord is an override; a
    list of every gun is not overridden, its new entry added at run time; a perk losing a game entry is dropped."""
    gun, guns, perk, ammo, other = 0x03000900, 0x03000901, 0x03000902, 0x04000800, struct.pack('<I', 0x03000950)
    dlc_ref, sub = struct.pack('<I', ammo), pack_subrecord
    path = _built_game(tmp_path, FO4_MASTERS[:3], [('WEAP', gun, sub('EDID', b'G\0')),
                                                   ('FLST', guns, sub('LNAM', other)),
                                                   ('PERK', perk, sub('EDID', b'P\0') + sub('PRKE', b'a'))])
    dlc = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    for sig, fid, body in (('AMMO', ammo, b''), ('WEAP', gun, sub('EDID', b'G\0') + sub('NAM0', dlc_ref)),
                           ('FLST', guns, sub('LNAM', dlc_ref)), ('PERK', perk, sub('EDID', b'P\0') + sub('PRKE', dlc_ref))):
        dlc.add_record(sig, pack_fo4_record(sig, fid, 0, body))
    adds = {}
    counts = drop_unchanged(dlc, [path], set(), adds)
    assert sorted(struct.unpack_from('<I', r, 12)[0] for r in dlc.top_records()) == [gun, ammo]
    assert adds == {guns: (b'FLST', '', [ammo])}
    assert counts == {'master records override naming DLC records (WEAP)': 1,
                      'master records list entries added at run time (FLST)': 1,
                      'master records dropped: would lose master entries (PERK)': 1}


def test_a_game_list_held_by_the_dlc_is_added_to_and_an_unwritten_entry_left_out(tmp_path):
    """A game form list the DLC overrides in its source, adding a written DLC record and one never written: not
    overridden either, only the written record added at run time."""
    guns, ammo, ghost, sub = 0x03000901, 0x04000800, 0x04000801, pack_subrecord
    path = _built_game(tmp_path, FO4_MASTERS[:3], [('FLST', guns, sub('LNAM', struct.pack('<I', 0x03000950)))])
    dlc = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    dlc.add_record('AMMO', pack_fo4_record('AMMO', ammo, 0, b''))
    dlc.add_record('FLST', pack_fo4_record('FLST', guns, 0, b''.join(
        sub('LNAM', struct.pack('<I', f)) for f in (ammo, ghost))))
    adds = {}
    drop_unchanged(dlc, [path], {guns}, adds)
    assert adds == {guns: (b'FLST', '', [ammo])} and [r[:4] for r in dlc.top_records()] == [b'AMMO']


def test_a_dlcs_say_once_lines_mark_a_quest_of_its_own():
    """SayOnce: the game's marker quest when this plugin owns it; a DLC whose master holds it gets its own."""
    class Writer:
        """A writer stand-in: own index 4; a key with 'plugin' in it is the plugin's own, the rest the master's."""
        own_index = 4

        @staticmethod
        def derive_formid(site: str, key: str) -> int:
            """FormID of `key`: 0x04000801 for a plugin key, else 0x03000800."""
            return 0x04000801 if 'plugin' in key else 0x03000800
    once = SayOnce(Writer())
    assert once.quest == 0x04000801 and once.edid == 'FNV_TES4SayOnce_000801'




def test_a_dlcs_form_list_additions_become_one_quest_adding_them_at_run_time():
    """list_adds.write: one F3NV_FormListAdds quest, Lists and Forms parallel (a list once per form); none without
    additions."""
    written = []
    builder = SimpleNamespace(export_dir=Path('HonestHearts.esm'), writer=SimpleNamespace(
        derive_formid=lambda site, key: 0x04000900, add_record=lambda sig, rec: written.append((sig, rec))))
    assert list_adds.write(builder, {}) == 0 and not written
    assert list_adds.write(builder, {0x03000901: (b'FLST', 'A', [0x04000800, 0x04000801]),
                                     0x03000902: (b'FLST', 'B', [0x04000802])}) == 3
    (sig, quest), = written
    assert sig == 'QUST' and b'FNV_FormListAdds_HonestHearts\0' in quest and pack_wstring(list_adds.SCRIPT) in quest
    assert all(struct.pack('<I', f) in quest for f in (0x04000800, 0x04000801, 0x04000802, 0x03000901, 0x03000902))
    assert quest.count(struct.pack('<I', 0x03000901)) == 2


def test_a_game_perk_the_dlc_only_adds_entries_to_becomes_its_own_gated_perk(tmp_path):
    """A DLC's copy of a game perk adding an entry: not overridden; the entry goes on the DLC's own hidden perk,
    gated on the game perk (HasPerk first in a new perk-owner tab), which its quest gives the player."""
    perk, sub = 0x03000902, pack_subrecord
    head = sub('EDID', b'FNV_Ninja\0') + sub('DATA', bytes(5))
    old = sub('PRKE', b'\x02\x00\x00') + sub('DATA', b'\x01\x05\x03') + sub('PRKF', b'')
    new = sub('PRKE', b'\x02\x00\x00') + sub('DATA', b'\x02\x05\x03') + sub('PRKF', b'')
    path = _built_game(tmp_path, FO4_MASTERS[:3], [('PERK', perk, head + old)])
    dlc = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    dlc.add_record('PERK', pack_fo4_record('PERK', perk, 0, head + old + new))
    adds = {}
    counts = drop_unchanged(dlc, [path], set(), adds)
    assert not list(dlc.top_records()) and counts == {"master records perk entries moved to the plugin's own perk (PERK)": 1}
    assert adds == {perk: (b'PERK', 'FNV_Ninja', [((b'PRKE', b'\x02\x00\x00'), (b'DATA', b'\x02\x05\x03'), (b'PRKF', b''))])}
    written = []
    builder = SimpleNamespace(export_dir=Path('HonestHearts.esm'), writer=SimpleNamespace(
        derive_formid=lambda site, key: 0x04000900 if key == 'quest' else 0x04000901,
        add_record=lambda sig, rec: written.append((sig, rec))))
    assert list_adds.write(builder, adds) == 1
    (_, own), (_, quest) = written
    subs = list(subrecords(own[24:]))
    assert subs[:2] == [(b'EDID', b'FNV_Ninja_HonestHearts\0'), (b'DATA', list_adds.HIDDEN_PERK)]
    tags = [tag for tag, _ in subs]
    assert tags[2:] == [b'PRKE', b'DATA', b'PRKC', b'CTDA', b'PRKF']
    ctda = dict(subs)[b'CTDA']
    assert struct.unpack_from('<H', ctda, 8)[0] == 448 and struct.unpack_from('<I', ctda, 12)[0] == perk
    assert struct.pack('<I', 0x04000901) in quest


def test_a_masters_topic_nested_in_its_quests_children_group_is_found(tmp_path):
    """master_records finds a DIAL inside a quest's children group (type 10), where a signature-filtered walk does
    not look, so drop_unchanged judges a DLC's copy against it."""
    quest, topic, sub = 0x03000900, 0x03000901, pack_subrecord
    children = pack_group(10, struct.pack('<I', quest), pack_fo4_record('DIAL', topic, 0, sub('EDID', b'T\0')))
    game = FO4PluginWriter(masters=FO4_MASTERS[:3], is_esm=True)
    game.add_raw_group('QUST', pack_group(0, b'QUST', pack_fo4_record('QUST', quest, 0, sub('EDID', b'Q\0')) + children))
    path = tmp_path / 'FalloutNV.esm'
    game.write(str(path))
    assert master_records([path], {topic: b'DIAL'}, FO4_MASTERS)[topic][1] == sub('EDID', b'T\0')


def test_a_perk_entry_renumbered_by_the_dlcs_additions_is_still_the_masters():
    """added_perk_entries matches entries ignoring EPFB (the entry's number, shifted when entries are added): a game
    entry renumbered 55 to 57 is not lost, and only the new entry is added."""
    sub = pack_subrecord
    head = sub('EDID', b'P\0') + sub('DATA', bytes(5))

    def entry(point: int, number: int) -> bytes:
        """A perk entry for entry point `point`, numbered `number`."""
        return sub('PRKE', b'\x02\x00\x00') + sub('DATA', bytes([point, 5, 3])) + sub('EPFT', b'\x08') + \
            sub('EPFB', struct.pack('<H', number)) + sub('PRKF', b'')
    added = added_perk_entries(head + entry(1, 57) + entry(2, 58), head + entry(1, 55))
    assert [dict(e)[b'DATA'][0] for e in added] == [2]
