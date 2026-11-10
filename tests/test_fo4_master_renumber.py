"""A master read behind a plugin with several masters is renumbered into that plugin's FormID space: its export
records by the key table, its plugin bytes by the xEdit-derived subrecord table, unions by their selector field.

See: docs/fork/fo4_plugin_layout.md#multi-master
"""

import struct
import zlib
from pathlib import Path

import pytest

from fo4_import.base.master_overrides import built_bytes, held_by
from fo4_import.base.vmad import info_fragments, object_scripts, quest_fragments, read_entry, read_quest
from fo4_import.base.vmad import terminal_fragments
from script_convert.pipeline import pack_wstring
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.pipeline import master_space
from fo4_import.pipeline.master_plugin import offsets, renumbered
from fo4_import.pipeline.master_space import byte_map, identity, renumber, renumber_record
from tes5_import.base.tes5_reader import FLAG_COMPRESSED, subrecords, walk
from tes5_import.base.writer import pack_subrecord
from tools.generators.gen_fnv_subrecord_formids import build

#: Honest Hearts (masters: FalloutNV.esm) read behind a mod listing Dead Money before it.
CHILD = ['FalloutNV.esm', 'DeadMoney.esm', 'HonestHearts.esm']
MAP = (0, 2)
#: A built DLC (own index 04) read behind a mod listing two other DLCs before it.
MOVED = (0, 1, 2, 3, 6)
FNV_DEFS = Path('references/xEdit/Core/wbDefinitionsFNV.pas')


def sub(tag: bytes, data: bytes) -> bytes:
    """One subrecord."""
    return tag + struct.pack('<H', len(data)) + data


def record(sig: bytes, fid: int, body: bytes, flags: int = 0) -> bytes:
    """One record (FNV header: 24 bytes)."""
    return sig + struct.pack('<III', len(body), flags, fid) + bytes(8) + body


def group(label: int, kind: int, inner: bytes) -> bytes:
    """One GRUP."""
    return b'GRUP' + struct.pack('<IIi', 24 + len(inner), label, kind) + bytes(8) + inner


def plugin(*groups: bytes) -> bytes:
    """A plugin: an empty TES4 header, then `groups`."""
    return record(b'TES4', 0, b'') + b''.join(groups)


def fids(raw: bytes, sig: bytes, tag: bytes) -> list:
    """Every `tag` subrecord's u32 values in `sig` records, in file order."""
    out = []
    for rec, _ in walk(raw, sig):
        out += [struct.unpack(f'<{len(d) // 4}I', d[:len(d) // 4 * 4]) for t, d in subrecords(rec.body) if t == tag]
    return out


def test_byte_map_follows_the_child_list():
    """A master's own index and its masters' move to the child's; one master is the identity."""
    assert byte_map(CHILD, 'HonestHearts.esm', ['FalloutNV.esm']) == MAP
    assert identity(byte_map(['FalloutNV.esm', 'HonestHearts.esm'], 'HonestHearts.esm', ['FalloutNV.esm']))
    assert renumber(0x01001234, MAP) == 0x02001234 and renumber(0x00001234, MAP) == 0x00001234
    with pytest.raises(SystemExit):
        byte_map(['FalloutNV.esm'], 'HonestHearts.esm', ['FalloutNV.esm', 'DeadMoney.esm'])


def test_export_record_keys():
    """FormID keys and condition params move; a known non-FormID hex value stays."""
    ctda = struct.pack('<B3xIH2xIIII', 0, 0, 72, 0x01000800, 0, 2, 0x01000900).hex()
    rec = renumber_record({'FormID': '01000100', 'Condition[0].Raw': ctda}, MAP, 'fnv')
    assert rec['FormID'] == '02000100'
    raw = bytes.fromhex(rec['Condition[0].Raw'])
    assert struct.unpack_from('<I', raw, 12)[0] == 0x02000800 and struct.unpack_from('<I', raw, 24)[0] == 0x02000900


def test_package_location_by_its_type():
    """PLDT's location is a FormID for a reference, cell or object ID, an object type number otherwise."""
    near_ref = sub(b'PLDT', struct.pack('<iIi', 0, 0x01000500, 100))
    obj_type = sub(b'PLDT', struct.pack('<iIi', 5, 0x01000005, 100))
    out = renumbered(plugin(group(0x4B434150, 0, record(b'PACK', 0x01000010, near_ref + obj_type))), MAP, 'fnv')
    assert [v[1] for v in fids(out, b'PACK', b'PLDT')] == [0x02000500, 0x01000005]


def test_perk_header_data_before_its_effect_selector():
    """A perk's header DATA (before any PRKE) stays; an effect's DATA after PRKE type 1 (ability) moves."""
    body = sub(b'DATA', bytes([0, 1, 1, 1, 0])) + sub(b'PRKE', bytes([1, 0, 0])) + sub(b'DATA', b'\x00\x05\x00\x01')
    out = renumbered(plugin(group(0x4B524550, 0, record(b'PERK', 0x01000020, body))), MAP, 'fnv')
    datas = [d for rec, _ in walk(out, b'PERK') for t, d in subrecords(rec.body) if t == b'DATA']
    assert datas == [bytes([0, 1, 1, 1, 0]), struct.pack('<I', 0x02000500)]


def test_selector_value_picks_cases():
    """A case applies for its listed values only, never before its selector."""
    layout = {'at': [], 'select': {'sub': 'EPFT', 'at': 0, 'size': 1}, 'cases': [{'in': [3], 'at': [0]}]}
    assert offsets(layout, b'', {b'EPFT': b'\x03'}) == [0]
    assert offsets(layout, b'', {b'EPFT': b'\x01'}) == [] and offsets(layout, b'', {}) == []


def test_ownership_compressed_and_group_label():
    """COED's owner and global move; a compressed record is written inflated; a cell's child group label moves."""
    body = sub(b'COED', struct.pack('<IIf', 0x01000600, 0x01000700, 1.0))
    packed = struct.pack('<I', len(body)) + zlib.compress(body)
    conts = group(0x544E4F43, 0, record(b'CONT', 0x01000040, packed, FLAG_COMPRESSED))
    out = renumbered(plugin(conts, group(0x01000030, 6, b'')), MAP, 'fnv')
    assert fids(out, b'CONT', b'COED') == [(0x02000600, 0x02000700, struct.unpack('<I', struct.pack('<f', 1.0))[0])]
    cell_children = out.rindex(b'GRUP')
    assert struct.unpack_from('<I', out, cell_children + 8)[0] == 0x02000030
    assert not struct.unpack_from('<I', out, 48 + 8)[0] & FLAG_COMPRESSED


def test_generated_table_has_no_complex_subrecord():
    """xEdit's FNV definitions place every FormID: decider unions as selector cases, none left complex."""
    if not FNV_DEFS.is_file():
        pytest.skip('xEdit definitions not present')
    table = build(FNV_DEFS, 'fnv')
    assert not [f'{r}.{s}' for r, subs in table.items() for s, v in subs.items() if v == 'complex']
    assert table['PACK']['PTDT']['select'] == {'at': 0, 'size': 4}
    assert table['REFR']['XPOD'] == {'at': [0, 4]}


def test_a_built_dlc_reads_in_a_mods_numbering(tmp_path):
    """A built DLC (own index 04) read behind another DLC moves to 05, its FormIDs too; its own list is as is."""
    own = ['Fallout4.esm', 'FalloutHelpers.esl', 'XDI.esm', 'FalloutNV.esm']
    dlc = FO4PluginWriter(masters=own, is_esm=True)
    dlc.add_record('NPC_', pack_fo4_record('NPC_', 0x04000801, 0, pack_subrecord('RNAM', struct.pack('<I', 0x04000802))))
    path = tmp_path / 'HonestHearts.esm'
    dlc.write(str(path))
    assert built_bytes(path, own + ['HonestHearts.esm']) == path.read_bytes()
    mod = own + ['DeadMoney.esm', 'HonestHearts.esm']
    assert fids(built_bytes(path, mod), b'NPC_', b'RNAM') == [(0x05000802,)]
    assert 0x05000801 in held_by([path], mod) and 0x04000801 not in held_by([path], mod)


def scripted(sig: bytes, vmad: bytes) -> bytes:
    """A plugin of one `sig` record (index 04) carrying script data `vmad`."""
    return plugin(group(int.from_bytes(sig, 'little'), 0, record(sig, 0x04000010, sub(b'VMAD', vmad))))


def vmad_of(raw: bytes, sig: bytes) -> bytes:
    """The script data of the one `sig` record in plugin `raw`."""
    return next(d for rec, _ in walk(raw, sig) for t, d in subrecords(rec.body) if t == b'VMAD')


def test_script_properties_move():
    """An object property and an object array move with their plugin; another master's object, None and an int
    that looks like a FormID stay."""
    values = {'Many': ('objects', [0x04000333, 0]), 'Number': ('int', 0x04000444)}
    raw = scripted(b'ACTI', object_scripts([('S', {'One': 0x04000111, 'Game': 0x03000222}, values)]))
    moved = {'Many': ('objects', [0x06000333, 0]), 'Number': ('int', 0x04000444)}
    out = vmad_of(renumbered(raw, MOVED, 'fo4'), b'ACTI')
    assert read_entry(out, 6)[0] == ('S', {'One': 0x06000111, 'Game': 0x03000222}, moved)
    assert renumbered(raw, (0, 1, 2, 3, 4), 'fo4') == raw and not master_space.UNCLASSIFIED


def test_quest_alias_and_fragment_scripts_move():
    """A quest's own script, its alias's quest and alias script, and an INFO's and a PERK's fragment script move."""
    alias = (3, 0x04000010, [('A', {'Ref': 0x04000555}, None)])
    quest = quest_fragments('', [], aliases=[alias], scripts=[('Q', {'Own': 0x04000666}, None)])
    out = vmad_of(renumbered(scripted(b'QUST', quest), MOVED, 'fo4'), b'QUST')
    assert read_quest(out) == ([('Q', {'Own': 0x06000666}, {})], [(3, 0x06000010, [('A', {'Ref': 0x06000555}, {})])])
    info = vmad_of(renumbered(scripted(b'INFO', info_fragments('F', {'Line': 0x04000777})), MOVED, 'fo4'), b'INFO')
    assert read_entry(info, 8)[0] == ('F', {'Line': 0x06000777}, {})
    perk = vmad_of(renumbered(scripted(b'PERK', terminal_fragments('P', [], {'Perk': 0x04000888})), MOVED, 'fo4'),
                   b'PERK')
    assert read_entry(perk, 7)[0] == ('P', {'Perk': 0x06000888}, {}) and not master_space.UNCLASSIFIED


def test_struct_member_in_object_format_1():
    """A struct's object member moves, read FormID first under object format 1."""
    member = pack_wstring('M') + struct.pack('<BBIhH', 1, 1, 0x04000999, -1, 0)
    prop = pack_wstring('P') + struct.pack('<BBI', 7, 1, 1) + member
    vmad = struct.pack('<hhH', 6, 1, 1) + pack_wstring('S') + struct.pack('<BH', 0, 1) + prop
    out = vmad_of(renumbered(scripted(b'ACTI', vmad), MOVED, 'fo4'), b'ACTI')
    assert out == vmad.replace(struct.pack('<I', 0x04000999), struct.pack('<I', 0x06000999)) != vmad


def test_unwalkable_script_data_is_kept_and_counted():
    """A property type the walker does not know, and data cut short, are returned as they are and counted."""
    prop = pack_wstring('P') + struct.pack('<BBHhI', 9, 1, 0, -1, 0x04000111)
    vmad = struct.pack('<hhH', 6, 2, 1) + pack_wstring('S') + struct.pack('<BH', 0, 1) + prop
    cut = object_scripts([('S', {'One': 0x04000111}, None)])[:-2]
    for data in (vmad, cut):
        raw = scripted(b'ACTI', data)
        assert renumbered(raw, MOVED, 'fo4')[-len(data):] == data
    assert master_space.UNCLASSIFIED == {'ACTI.VMAD (script data not walked)': 2}


@pytest.fixture(autouse=True)
def _clear_unclassified():
    """Each test starts with no unclassified counts."""
    master_space.UNCLASSIFIED.clear()
