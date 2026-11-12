"""Light (ESL-flagged) converted plugins: the light id range and its ledger, light masters read through their
ledgers, the per-mod opt-in and its lock, override-only plugins flagged light, and the app's arguments."""

import json
import struct
from pathlib import Path

import pytest

from fo4_import.app import light_plugins
from fo4_import.base.ledger import ID, LIGHT_SPAN, ONE_TO_ONE, Ledger, LedgerWriter, LightFull, ledger_path
from fo4_import.base.source_ids import SourceIds, is_light, key_light, master_ledgers
from fo4_import.base.writer import FLAG_ESL, FO4PluginWriter, pack_fo4_record
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.pipeline.light_choice import STAMP_KEY, Choice, choose, finish_flag, own_ids
from tes5_import.base.writer import pack_subrecord

MASTERS = ['Fallout4.esm', 'FalloutHelpers.esl', 'FalloutNV.esm']
KEYS = [('FNV type keyword', f'FNV_Key{n}') for n in range(300)]


def _light(ledger: 'Ledger | None' = None) -> LedgerWriter:
    """A light writer on MASTERS keeping `ledger` (an empty one by default)."""
    writer = LedgerWriter(masters=MASTERS, is_esm=False)
    writer.make_light()
    writer.use_ledger(ledger or Ledger())
    return writer


def _plugin(path: Path, masters: list, ids: list, light: bool = False) -> Path:
    """A plugin at `path` with a keyword record for each FormID of `ids`, ESL-flagged when `light`."""
    writer = FO4PluginWriter(masters=masters, is_esm=path.suffix == '.esm', is_esl=light)
    for fid in ids:
        writer.add_record('KYWD', pack_fo4_record('KYWD', fid, 0, b''))
    writer.write(str(path))
    return path


def test_light_ids_are_in_range_the_same_for_the_same_keys_and_kept_by_the_ledger(tmp_path):
    """Two fresh light writers give the same ids in 0x001-0xFFF; a rebuild with the saved ledger keeps them even
    when a new key comes first; 1:1 records are kept under ONE_TO_ONE by their source object id."""
    first, second = _light(), _light()
    ids = [first.derive_formid(*k) for k in KEYS]
    assert ids == [second.derive_formid(*k) for k in KEYS]
    assert len(set(ids)) == len(KEYS) and all(fid >> 24 == 3 and 0x001 <= fid & 0xFFFFFF <= 0xFFF for fid in ids)
    one = first.one_to_one(0x00ABCD)
    assert first.one_to_one(0x00ABCD) == one and first.ledger.get(ID, ONE_TO_ONE, '00ABCD') == one & 0xFFFFFF
    first.ledger.path = ledger_path(tmp_path / 'Mod.esp')
    first.ledger.save()
    again = _light(Ledger(ledger_path(tmp_path / 'Mod.esp')))
    newcomer = again.derive_formid('FNV type keyword', 'FNV_New')
    assert [again.derive_formid(*k) for k in KEYS] == ids and newcomer not in ids
    assert again.one_to_one(0x00ABCD) == one


def test_a_full_ledger_writer_hashes_exactly_as_before():
    """No drift: a full LedgerWriter gives the plain writer's ids for the same keys."""
    plain, full = FO4PluginWriter(masters=MASTERS), LedgerWriter(masters=MASTERS)
    assert [full.derive_formid(*k) for k in KEYS] == [plain.derive_formid(*k) for k in KEYS]
    assert not full.light and not full.is_esl


def test_a_light_plugin_stops_when_every_light_id_is_taken():
    """With 4,095 ids kept, a new key raises LightFull; the uncapped probe still places the last free id."""
    ledger = Ledger()
    for oid in range(1, LIGHT_SPAN):
        ledger.put(ID, 'old', oid, oid)
    writer = _light(ledger)
    last = writer.derive_formid('FNV type keyword', 'FNV_Last')
    assert last & 0xFFFFFF == 0xFFF
    with pytest.raises(LightFull):
        writer.derive_formid('FNV type keyword', 'FNV_OneTooMany')


def test_a_light_plugin_is_written_with_the_flag_and_its_next_id(tmp_path):
    """The header has ESL beside ESM, and the next object id is one above the highest own id."""
    writer = _light()
    writer.is_esm = True
    ids = [writer.derive_formid(*k) for k in KEYS[:20]]
    for fid in ids:
        writer.add_record('KYWD', pack_fo4_record('KYWD', fid, 0, b''))
    out = tmp_path / 'Mod.esm'
    writer.write(str(out))
    raw = out.read_bytes()
    assert struct.unpack_from('<I', raw, 8)[0] & (FLAG_ESL | 1) == FLAG_ESL | 1 and is_light(out)
    assert struct.unpack_from('<I', raw, 24 + 6 + 8)[0] == max(f & 0xFFFFFF for f in ids) + 1
    assert own_ids(out) == {f & 0xFFFFFF for f in ids}


def test_a_dependent_reads_a_light_masters_records_through_its_ledger(tmp_path):
    """A light master's 1:1 record is found by its source object id in the master's ledger; a record it never
    built is None (held) and an error (fo4); a full master's passes its object id through."""
    master = _light()
    one = master.one_to_one(0x001234)
    master.ledger.path = ledger_path(tmp_path / 'Light.esm')
    master.ledger.save()
    _plugin(tmp_path / 'Light.esm', MASTERS, [one], light=True)
    _plugin(tmp_path / 'Full.esm', MASTERS, [0x03001234])
    masters = MASTERS + ['Light.esm', 'Full.esm']
    writer = LedgerWriter(masters=masters, is_esm=False)
    ids = SourceIds(['FalloutNV.esm', 'Light.esm', 'Full.esm'], masters, writer.own_index)
    ledgers = master_ledgers(masters, (tmp_path,))
    key_light(ids, writer, [tmp_path / 'Light.esm', tmp_path / 'Full.esm'], masters, ledgers)
    assert ids.fo4(0x01001234) == 3 << 24 | one & 0xFFFFFF
    assert ids.held(0x01009999) is None
    with pytest.raises(KeyError):
        ids.fo4(0x01009999)
    assert ids.fo4(0x02001234) == 0x04001234 and ids.fo4(0x03000800) == 0x05000800
    with pytest.raises(SystemExit, match='no ledger'):
        key_light(ids, writer, [tmp_path / 'Light.esm'], masters, {})


def test_the_choice_is_free_before_the_first_build_and_locked_after_it(tmp_path):
    """First build: as asked. Built full: asking light stops with the count unless the switch is confirmed, which
    drops the ledger ids; the stamp's opt-in wins over the plugin's flag."""
    plugin = tmp_path / 'Mod.esp'
    assert choose(plugin, True) == Choice(True) and choose(plugin, False) == Choice(False)
    _plugin(plugin, MASTERS, [0x03000800, 0x03000801])
    assert choose(plugin, False) == Choice(False)
    with pytest.raises(SystemExit, match='moves 2 FormIDs'):
        choose(plugin, True)
    assert choose(plugin, True, switch=True) == Choice(True, True)
    stamp_path(plugin).parent.mkdir(parents=True, exist_ok=True)
    stamp_path(plugin).write_text(json.dumps({STAMP_KEY: True}), encoding='utf-8')
    with pytest.raises(SystemExit, match='no ledger'):
        choose(plugin, True)


def test_a_light_build_refuses_ids_its_ledger_does_not_hold_and_a_full_one_a_plugin_made_light(tmp_path):
    """A plugin renumbered outside the converter is never rebuilt over."""
    plugin = tmp_path / 'Mod.esp'
    ledger = Ledger(ledger_path(plugin))
    ledger.put(ID, ONE_TO_ONE, '000800', 0x001)
    ledger.save()
    _plugin(plugin, MASTERS, [0x03000001])
    assert choose(plugin, True) == Choice(True)
    _plugin(plugin, MASTERS, [0x03000002], light=True)
    with pytest.raises(SystemExit, match='not in its ledger'):
        choose(plugin, True)
    full = _plugin(tmp_path / 'Other.esp', MASTERS, [0x03000801], light=True)
    with pytest.raises(SystemExit, match='made light outside'):
        choose(full, False)


def test_a_plugin_with_no_new_records_is_light_and_a_light_one_carries_no_precombines():
    """finish_flag: no own record flags a full writer light; own records keep it full; a light writer's own cell
    with precombine data stops the build."""
    writer = LedgerWriter(masters=MASTERS)
    writer.add_record('KYWD', pack_fo4_record('KYWD', 0x02000800, 0, b''))
    assert finish_flag(writer) == 'light (no new records)' and writer.is_esl
    writer = LedgerWriter(masters=MASTERS)
    writer.add_record('KYWD', pack_fo4_record('KYWD', 0x03000800, 0, b''))
    assert finish_flag(writer) == 'full' and not writer.is_esl
    light = _light()
    light.add_record('CELL', pack_fo4_record('CELL', light.one_to_one(0x000900), 0, pack_subrecord('XCRI', b'\0' * 8)))
    with pytest.raises(SystemExit, match='precombine'):
        finish_flag(light)


def test_the_app_passes_the_opt_in_and_the_switch_only_once_confirmed(tmp_path):
    """--light follows the entry; --switch-plugin-type only when a built type differs and the user confirmed it."""
    settings = {'per_source': {'falloutnv': {'addons': []}}}
    plugin = tmp_path / 'Mod.esp'
    light_plugins.choose(settings, 'falloutnv', 'Mod.esp', True)
    assert light_plugins.arguments(settings, 'falloutnv', 'Mod.esp', plugin) == ['--light']
    _plugin(plugin, MASTERS, [0x03000800])
    assert light_plugins.needs_confirming(plugin, True) and light_plugins.own_count(plugin) == 1
    assert light_plugins.arguments(settings, 'falloutnv', 'Mod.esp', plugin) == ['--light']
    light_plugins.choose(settings, 'falloutnv', 'Mod.esp', True, confirmed=True)
    assert light_plugins.arguments(settings, 'falloutnv', 'Mod.esp', plugin) == ['--light', '--switch-plugin-type']
    light_plugins.choose(settings, 'falloutnv', 'Mod.esp', False)
    assert light_plugins.arguments(settings, 'falloutnv', 'Mod.esp', plugin) == []
