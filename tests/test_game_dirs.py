"""core.game_dirs: Steam libraries and app manifests read from their text files."""

from pathlib import Path

from core.game_dirs import steam_app_dir, steam_libraries


def _library(root: Path, apps: dict) -> Path:
    """A Steam library at `root` with a manifest and Data folder for each {app id: install folder}."""
    apps_dir = root / 'steamapps'
    apps_dir.mkdir(parents=True)
    for app, folder in apps.items():
        (apps_dir / f'appmanifest_{app}.acf').write_text(
            f'"AppState"\n{{\n\t"appid"\t\t"{app}"\n\t"installdir"\t\t"{folder}"\n}}\n', encoding='utf-8')
        (apps_dir / 'common' / folder / 'Data').mkdir(parents=True)
    return root


def test_second_library_from_vdf(tmp_path):
    """A game in a library that only libraryfolders.vdf names is found."""
    main = _library(tmp_path / 'Steam', {})
    other = _library(tmp_path / 'Games Lib', {377160: 'Fallout 4'})
    escaped = str(other).replace('\\', '\\\\')
    (main / 'steamapps' / 'libraryfolders.vdf').write_text(
        f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{escaped}"\n\t}}\n}}\n', encoding='utf-8')
    assert steam_libraries([main]) == [main, other]
    assert steam_app_dir((377160,), [main]) == other / 'steamapps' / 'common' / 'Fallout 4'


def test_first_app_id_wins(tmp_path):
    """Fallout 3 GOTY (22370) is preferred over the original release (22300)."""
    lib = _library(tmp_path / 'Steam', {22300: 'Fallout 3', 22370: 'Fallout 3 goty'})
    assert steam_app_dir((22370, 22300), [lib]).name == 'Fallout 3 goty'


def test_manifest_without_game_files(tmp_path):
    """A manifest whose folder has no Data (uninstalled, half-downloaded) is skipped."""
    lib = _library(tmp_path / 'Steam', {22380: 'Fallout New Vegas'})
    (lib / 'steamapps' / 'common' / 'Fallout New Vegas' / 'Data').rmdir()
    assert steam_app_dir((22380,), [lib]) is None
