"""Converted guns' third-person AnimTextData copied from vanilla: ids, which entries are copied, the files, the
persistent list.

See: docs/fork/research/anim_text_data.md#writer
"""

import struct

from fo4_import.havok import gun_anim_text as GAT
from fo4_import.havok.gun_clips import entry_subrecords

GRAPH = 'Actors\\Character\\Behaviors\\WeaponBehavior.hkx'
FIRST = 'Actors\\Character\\_1stPerson\\Behaviors\\GunBehavior.hkx'
VANILLA = ['Actors\\Character\\Animations\\Weapon\\PipeRiflePistol', 'Actors\\Character\\Animations']
FNV = 'Actors\\FNV\\Character\\Animations\\Weap10mmPistol'


def _str(text: str) -> bytes:
    """AnimTextData's string: a u8 length counting the NUL, the bytes, the NUL."""
    return bytes([len(text) + 1]) + text.encode('cp1252') + b'\0'


def _offsets(graph: str, clips: dict) -> bytes:
    """An AnimationOffsets file: `clips` {name: path}, each with one still key at 1 s and no events."""
    body = b'V4\n' + _str(graph) + struct.pack('<I', len(clips))
    body += b''.join(_str(name) + _str(path) for name, path in clips.items()) + struct.pack('<I', len(clips))
    still = struct.pack('<fI4fI5fI', 1.0, 1, 1.0, 0, 0, 0, 1, 1.0, 0, 0, 0, 1, 0)
    return body + b''.join(_str(path) + still for path in clips.values())


def _race(*entries) -> bytes:
    """A packed RACE holding `entries` ({graph, paths}) as weapon subgraph entries."""
    subs = [s for e in entries for s in entry_subrecords(
        {'actor': [], 'graph': e['graph'], 'paths': e['paths'], 'target': [1], 'flags': b'\x01\0\0\0'})]
    body = b''.join(sig + struct.pack('<H', len(data)) + data for sig, data in subs)
    return b'RACE' + struct.pack('<I', len(body)) + bytes(16) + body


def _file_data(tmp_path, entry: int, clips: list) -> None:
    """gun_clips' AnimationFileData for `entry`, listing clip paths `clips`."""
    path = tmp_path / GAT.ANIM_TEXT / 'AnimationFileData' / f'{entry}.txt'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\r\n'.join(['3', '1', str(entry), str(len(clips)), *clips]) + '\r\n', encoding='cp1252')


def _vanilla(template: int, persistent=()) -> GAT.Vanilla:
    """Vanilla holding `template`'s offsets (clips Idle and Fire on GRAPH), speed info and dynamic idle data."""
    offsets = _offsets(GRAPH, {'Idle': VANILLA[0] + '\\Idle', 'Fire': VANILLA[0] + '\\Fire'})
    files = {('animationoffsets', template): lambda: offsets, ('animationspeedinfo', template): lambda: b'speed',
             ('dynamicidledata', template): lambda: b'Version 1\n'}
    return GAT.Vanilla({GRAPH.lower(): {'idle', 'fire'}}, set(persistent), files)


def test_entry_ids_keep_a_single_folders_case_and_lower_several():
    """Ids the Creation Kit wrote for our build: one folder in its own case, several lower-cased."""
    assert GAT.entry_id(['Actors\\FNVGecko\\Animations'],
                        'Actors\\FNVGecko\\Behaviors\\FNVGeckoRootBehavior.hkx') == 536022380439387835
    assert GAT.entry_id(['Actors\\Character\\_1stPerson\\Animations\\Paired',
                         'Actors\\FNV\\Character\\_1stPerson\\Animations\\WeapBBGun',
                         'Actors\\Character\\_1stPerson\\Animations\\PipeRifle',
                         'Actors\\Character\\_1stPerson\\Animations\\HandmadeRevolver',
                         'Actors\\Character\\_1stPerson\\Animations\\Common'], FIRST) == 16966350897748940951


def test_clip_names_read_the_offsets_header():
    """The graph and its clip names, lower case."""
    assert GAT.clip_names(_offsets(GRAPH, {'Idle': 'A\\Idle', 'FireB': 'A\\FireB'})) == (GRAPH.lower(), ['idle', 'fireb'])


def test_only_third_person_entries_playing_no_fnv_clip_are_copied(tmp_path):
    """Copied: FNV folder clips the graph never names. Left: an FNV clip it names, first person, FNV folders only."""
    plain, plays = [FNV, *VANILLA], [FNV + '\\Pistol', *VANILLA]
    template = GAT.entry_id(VANILLA, GRAPH)
    _file_data(tmp_path, GAT.entry_id(plain, GRAPH), [FNV + '\\WPNAssemblyPose.hkx', VANILLA[0] + '\\Idle.hkx'])
    _file_data(tmp_path, GAT.entry_id(plays, GRAPH), [FNV + '\\Pistol\\Fire.hkx'])
    _file_data(tmp_path, GAT.entry_id(plain, FIRST), [VANILLA[0] + '\\Idle.hkx'])
    races = [_race({'graph': GRAPH, 'paths': plain}, {'graph': GRAPH, 'paths': plays},
                   {'graph': FIRST, 'paths': plain}, {'graph': GRAPH, 'paths': [FNV]})]
    assert GAT.copied_entries(races, tmp_path, _vanilla(template)) == {GAT.entry_id(plain, GRAPH): template}


def test_written_files_are_the_templates_and_the_persistent_list_grows(tmp_path):
    """Each kind the template has, byte for byte; the entry listed beside the list's own ids, once."""
    template, entry = GAT.entry_id(VANILLA, GRAPH), GAT.entry_id([FNV, *VANILLA], GRAPH)
    vanilla = _vanilla(template, persistent={template, 7})
    written = GAT.write(tmp_path, {entry: template}, vanilla)
    assert sorted(p.parent.name for p in written) == ['AnimationOffsets', 'AnimationSpeedInfo', 'DynamicIdleData']
    assert (tmp_path / GAT.ANIM_TEXT / 'AnimationSpeedInfo' / f'{entry}.txt').read_bytes() == b'speed'
    (tmp_path / GAT.PERSISTENT).write_text('5.txt\n7.txt\n', encoding='cp1252')
    assert GAT.merge_persistent(tmp_path, {entry: template}, vanilla) == 1
    assert GAT.merge_persistent(tmp_path, {entry: template}, vanilla) == 0
    assert (tmp_path / GAT.PERSISTENT).read_text(encoding='cp1252').split() == ['5.txt', '7.txt', f'{entry}.txt']


def test_persistent_list_keeps_a_master_builds_ids(tmp_path):
    """A DLC build's list (loose, hiding the master's) carries the master build's ids too."""
    master, own = tmp_path / 'master', tmp_path / 'dlc'
    (master / GAT.PERSISTENT).parent.mkdir(parents=True)
    (master / GAT.PERSISTENT).write_text('5.txt\n99.txt\n', encoding='cp1252')
    assert GAT.merge_persistent(own, {}, _vanilla(1, persistent={5}), [master, tmp_path / 'none']) == 1
    assert GAT.persistent_ids((own / GAT.PERSISTENT).read_text(encoding='cp1252')) == {5, 99}


def test_persistent_list_starts_from_vanillas_without_one(tmp_path):
    """No list in the data folder: vanilla's ids and the entry, sorted by number."""
    template, entry = GAT.entry_id(VANILLA, GRAPH), GAT.entry_id([FNV, *VANILLA], GRAPH)
    GAT.merge_persistent(tmp_path, {entry: template}, _vanilla(template, persistent={template, 12}))
    assert GAT.persistent_ids((tmp_path / GAT.PERSISTENT).read_text(encoding='cp1252')) == {12, template, entry}
