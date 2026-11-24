"""tools.release.fo4_slim_zip: which files the slim release zip takes.

See: docs/fork/fo4_plan_release.md#slim-zip
"""

import zipfile

from tools.release import fo4_slim_zip as Z


def test_data_files_follow_their_code_folder():
    """A data file comes when the nearest folder above it holding .py files holds a traced module; SKIPPED and the
    root's own data stay out, EXTRA_FOLDERS and EXTRA_FILES come."""
    files = ['pkg/__init__.py', 'pkg/a.py', 'pkg/table.json', 'pkg/movies/x.swf', 'other/__init__.py',
             'other/b.json', 'notes.txt', 'external/__init__.py', 'external/hkxcmd/hkxcmd.exe',
             'external/ffmpeg/ffmpeg.exe', 'native/build.py', 'native/dist/f3_zlib.dll',
             'native/dist/spt_engine_dump.exe', 'README.md']
    modules = {'pkg/__init__.py', 'pkg/a.py', 'external/__init__.py'}
    assert Z.slim_files(files, modules) == ['README.md', 'external/__init__.py', 'external/ffmpeg/ffmpeg.exe',
                                            'native/dist/f3_zlib.dll', 'pkg/__init__.py', 'pkg/a.py',
                                            'pkg/movies/x.swf', 'pkg/table.json']


def test_trace_reaches_the_stages_not_the_skyrim_gui():
    """The trace holds the app, every stage module and the packages above them, never the Skyrim GUI."""
    modules = Z.traced()
    assert {'fo4_app.py', 'fo4_import/__init__.py', 'fo4_import/base/papyrus.py',
            'tools/validate/fo4_install_check.py'} <= modules
    assert 'gui.py' not in modules


def test_zip_carries_the_helper_scripts():
    """Every static helper script the script stage deploys (TES4Polyfill and the rest) is in the zip."""
    files = Z.tracked()
    static = {p for p in files if p.startswith('script_convert/static_scripts/') and p.endswith('.psc')}
    assert 'script_convert/static_scripts/TES4Polyfill.psc' in static
    assert static <= set(Z.slim_files(files, Z.traced()))


def test_zip_has_one_top_folder_and_version(tmp_path, monkeypatch):
    """Every entry sits under fo3fnv-in-fo4-<version>/, VERSION holds the version, entries carry one timestamp."""
    monkeypatch.setattr(Z, 'ROOT', tmp_path)
    (tmp_path / 'a.py').write_text('x = 1\n')
    target = Z.write_zip(['a.py'], 'f3nv-9.9', tmp_path / 'out')
    with zipfile.ZipFile(target) as z:
        assert z.namelist() == ['fo3fnv-in-fo4-f3nv-9.9/a.py', 'fo3fnv-in-fo4-f3nv-9.9/VERSION']
        assert z.read('fo3fnv-in-fo4-f3nv-9.9/VERSION') == b'f3nv-9.9\n'
        assert {i.date_time for i in z.infolist()} == {Z.STAMP}
