"""FormIDs across plugins: a dependent source's master byte, and a master build's ledger (base.source_ids)."""

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.base.ledger import Ledger, LedgerWriter, ledger_path
from fo4_import.base.master_overrides import drop_unchanged
from fo4_import.base.source_ids import SourceIds, built_plugins, dependent_masters, master_ledgers
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record, pack_topic
from fo4_import.spike.cell import COPY_SITE, CellBuilder
from tes5_import.base.writer import pack_subrecord

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
    assert counts == {'master record groups changed by the build alone (DIAL)': 1}


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


def test_a_game_record_naming_a_dlc_record_is_kept_whole_merged_or_dropped(tmp_path):
    """Records the DLC does not hold that now name its ammo: a gun keeping every game subrecord is an override; a
    list of every gun is the game's entries then the DLC's; a perk that lost a game entry is dropped."""
    gun, guns, perk, ammo, other = 0x03000900, 0x03000901, 0x03000902, 0x04000800, struct.pack('<I', 0x03000950)
    dlc_ref, sub = struct.pack('<I', ammo), pack_subrecord
    path = _built_game(tmp_path, FO4_MASTERS[:3], [('WEAP', gun, sub('EDID', b'G\0')),
                                                   ('FLST', guns, sub('LNAM', other)),
                                                   ('PERK', perk, sub('EDID', b'P\0') + sub('PRKE', b'a'))])
    dlc = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    for sig, fid, body in (('AMMO', ammo, b''), ('WEAP', gun, sub('EDID', b'G\0') + sub('NAM0', dlc_ref)),
                           ('FLST', guns, sub('LNAM', dlc_ref)), ('PERK', perk, sub('EDID', b'P\0') + sub('PRKE', dlc_ref))):
        dlc.add_record(sig, pack_fo4_record(sig, fid, 0, body))
    counts = drop_unchanged(dlc, [path], set())
    kept = {struct.unpack_from('<I', r, 12)[0]: r[24:] for r in dlc.top_records()}
    assert sorted(kept) == [gun, guns, ammo] and kept[guns] == sub('LNAM', other) + sub('LNAM', dlc_ref)
    assert counts == {'master records override naming DLC records (WEAP)': 1, 'master records form list merged (FLST)': 1,
                      'master records dropped: would lose master entries (PERK)': 1}
