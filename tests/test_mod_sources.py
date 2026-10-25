"""core.mod_sources: folder kinds, MO2 profiles, priority and case-blind lookup."""

from pathlib import Path

import pytest

from core.mod_sources import (ModSource, data_dirs, enabled_mods, find_file, from_settings, mo2_folders, plugins,
                              qsettings_value)


def _mod(root: Path, name: str, *files: str) -> Path:
    """A mod folder `name` under `root` holding empty `files`."""
    folder = root / name
    folder.mkdir(parents=True)
    for f in files:
        (folder / f).write_bytes(b'')
    return folder


def _mo2(tmp_path: Path, modlist: str, ini_extra: str = '') -> Path:
    """A fake MO2 instance with profile `Play` (modlist text `modlist`) and a game folder."""
    instance = tmp_path / 'MO2'
    (instance / 'profiles' / 'Play').mkdir(parents=True)
    (instance / 'profiles' / 'Play' / 'modlist.txt').write_text(modlist, encoding='utf-8')
    (instance / 'overwrite').mkdir()
    game = tmp_path / 'Fallout 4'
    (game / 'Data').mkdir(parents=True)
    game_ini = str(game).replace('\\', '\\\\')
    (instance / 'ModOrganizer.ini').write_text(
        f'[General]\ngameName=Fallout 4\nselected_profile=@ByteArray(Play)\ngamePath=@ByteArray({game_ini})\n'
        f'[Settings]\nstyle=x.qss\n{ini_extra}', encoding='utf-8')
    return instance


def test_folder_of_mods_later_source_wins(tmp_path):
    """A flat source listed after a folder of mods wins a plugin both have."""
    mods = tmp_path / 'mods'
    _mod(mods, 'A Guns', 'Guns.esp')
    flat = _mod(tmp_path, 'Merged', 'guns.ESP', 'Other.esm')
    sources = from_settings([{'folder': str(mods), 'kind': 'folder_of_mods'},
                             {'folder': str(flat), 'kind': 'flat'},
                             {'folder': str(tmp_path / 'off'), 'kind': 'flat', 'enabled': False}])
    assert data_dirs(sources) == [flat, mods / 'A Guns']
    found = plugins(sources)
    assert found['guns.esp'] == flat / 'guns.ESP'
    assert set(found) == {'guns.esp', 'other.esm'}


def test_mo2_profile_order_and_separators(tmp_path):
    """MO2: game Data lowest, then enabled mods bottom-up, then overwrite; disabled mods and separators left out."""
    instance = _mo2(tmp_path, '# generated\n+Top\n-Off\n-Mods_separator\n+Bottom\n*DLC: Far Harbor\n')
    assert enabled_mods(instance / 'profiles' / 'Play' / 'modlist.txt') == ['Top', 'Bottom']
    assert mo2_folders(instance) == [tmp_path / 'Fallout 4' / 'Data', instance / 'mods' / 'Bottom',
                                     instance / 'mods' / 'Top', instance / 'overwrite']


def test_mo2_moved_mods_folder(tmp_path):
    """A mod_directory setting with %BASE_DIR% is followed."""
    instance = _mo2(tmp_path, '+Only\n', 'mod_directory=%BASE_DIR%/elsewhere\n')
    assert instance / 'elsewhere' / 'Only' in mo2_folders(instance, 'Play')


def test_mo2_missing_profile(tmp_path):
    """Naming a profile the instance lacks is an error, not an empty mod list."""
    with pytest.raises(FileNotFoundError):
        mo2_folders(_mo2(tmp_path, '+A\n'), 'Nope')


def test_find_file_ignores_case(tmp_path):
    """find_file matches a name in any case and keeps folder order."""
    first, second = _mod(tmp_path, 'one'), _mod(tmp_path, 'two', 'Port.ESP')
    assert find_file('port.esp', [first, second]).name.lower() == 'port.esp'
    assert find_file('missing.esp', [first, second]) is None


def test_bad_kind():
    """An unknown kind is refused."""
    with pytest.raises(ValueError):
        ModSource(Path('.'), 'vortex')


def test_qsettings_value():
    """Byte arrays, quotes and doubled backslashes are undone."""
    assert qsettings_value('@ByteArray(C:\\\\Games\\\\Fallout 4)') == 'C:\\Games\\Fallout 4'
    assert qsettings_value('"x y"') == 'x y'
