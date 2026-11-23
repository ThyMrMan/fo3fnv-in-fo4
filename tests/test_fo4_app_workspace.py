"""The app's work folder: the stages are pointed at it, and an older release's app-folder data moves into it."""

import os

from asset_convert import paths as data_paths
from fo4_import.app import settings as S
from fo4_import.app import workspace


def _settings(tmp_path):
    """Default settings with the work folder under `tmp_path`."""
    s = S.defaults()
    s['work_dir'] = str(tmp_path / 'work')
    return s


def _release(folder, version: str, *names: str):
    """An app folder `folder` of release `version` holding each of `names` as a folder with one file; the folder."""
    folder.mkdir(parents=True)
    (folder / 'VERSION').write_text(version + '\n', encoding='utf-8')
    for name in names:
        (folder / name).mkdir()
        (folder / name / 'kept.txt').write_text(f'{folder.name} {name}')
    return folder


def test_use_points_this_process_at_the_work_folder(tmp_path, monkeypatch):
    """use() sets the data folder later stages and data_root() read."""
    monkeypatch.delenv(data_paths.DATA_ENV, raising=False)
    assert workspace.use(_settings(tmp_path)) == tmp_path / 'work'
    assert os.environ[data_paths.DATA_ENV] == str(tmp_path / 'work') and data_paths.data_root() == tmp_path / 'work'


def test_a_release_unzipped_over_the_old_one_hands_its_data_to_the_work_folder(tmp_path):
    """export and output move; a folder the work folder already has, and anything else, stay."""
    app = _release(tmp_path / 'apps' / 'new', 'f3nv-0.4', 'export', 'output', 'replacements', 'fo4_import')
    (tmp_path / 'work' / 'replacements').mkdir(parents=True)
    lines = workspace.adopt(_settings(tmp_path), app)
    assert (tmp_path / 'work' / 'export' / 'kept.txt').read_text() == 'new export' and not (app / 'export').exists()
    assert (tmp_path / 'work' / 'output' / 'kept.txt').is_file() and len(lines) == 2
    assert (app / 'replacements' / 'kept.txt').is_file() and (app / 'fo4_import').is_dir()


def test_a_release_unzipped_beside_older_ones_takes_the_newest_ones_data(tmp_path):
    """The newest older release beside it gives its folders; a newer release's and a non-release's are left."""
    apps = tmp_path / 'apps'
    app = _release(apps / 'f3nv-0.4', 'f3nv-0.4')
    _release(apps / 'f3nv-0.2', 'f3nv-0.2', 'export', 'replacements')
    _release(apps / 'f3nv-0.3', 'f3nv-0.3', 'export')
    _release(apps / 'f3nv-0.5', 'f3nv-0.5', 'output')
    (apps / 'other' / 'output').mkdir(parents=True)
    workspace.adopt(_settings(tmp_path), app)
    assert (tmp_path / 'work' / 'export' / 'kept.txt').read_text() == 'f3nv-0.3 export'
    assert (tmp_path / 'work' / 'replacements' / 'kept.txt').read_text() == 'f3nv-0.2 replacements'
    assert not (tmp_path / 'work' / 'output').exists()


def test_a_checkout_keeps_its_own_folders(tmp_path):
    """A developer checkout (no release tag in VERSION) moves nothing."""
    app = _release(tmp_path / 'app', '$Format:%(describe)$', 'export')
    assert workspace.adopt(_settings(tmp_path), app) == [] and (app / 'export').is_dir()
