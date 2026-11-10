"""Which plugins need a build: code identity, the functions that ran, a build's inputs record and the plan.

See: docs/fork/fo4_plugin_layout.md#which-builds
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.pipeline import build_inputs as BI
from fo4_import.pipeline import build_plan as BP
from fo4_import.pipeline import code_identity as CI
from fo4_import.pipeline import mod_dirs as MD
from fo4_import.pipeline import ran_code as RC
from fo4_import.pipeline import work_cache as WC
from fo4_import.pipeline.code_tag import ROOT
from tes5_import.base.writer import pack_subrecord

MODULE = '''"""A module."""
from {pkg}.other import LIMIT

SCALE = 2
UNUSED = 5


def make():
    """Docstring."""
    return [1, 2]


TABLE = make()


class Point:
    """Fields."""
    x: int = 0


def scaled(v):
    """Scale v."""
    return v * SCALE + LIMIT + len(TABLE) + Point.x


def other(v):
    return v
'''


@pytest.fixture
def package(monkeypatch):
    """A throwaway repo package `temp/ci_<id>` holding `mod.py` (MODULE) and `other.py`; identities fresh."""
    name = f'ci_{uuid.uuid4().hex[:8]}'
    root = ROOT / 'temp' / name
    root.mkdir(parents=True)
    (root / '__init__.py').write_text('', encoding='utf-8')
    (root / 'other.py').write_text('LIMIT = 10\n', encoding='utf-8')
    (root / 'mod.py').write_text(MODULE.format(pkg=f'temp.{name}'), encoding='utf-8')
    monkeypatch.setattr(CI, 'STARTED', time.time() + 3600)
    yield root, f'temp/{name}/mod.py::scaled'
    shutil.rmtree(root)


def _edit(path: Path, old: str, new: str) -> None:
    """Replace `old` with `new` in `path`, clearing the identity memo."""
    path.write_text(path.read_text(encoding='utf-8').replace(old, new), encoding='utf-8')
    CI.identity.cache_clear()


@pytest.mark.parametrize('old, new, moves', [
    ('"""Scale v."""', '"""Scale the value v."""', False),
    ('UNUSED = 5', 'UNUSED = 6', False),
    ('    return v\n', '    return v + 1\n', False),
    ('return v * SCALE', 'return v * SCALE * 1', True),
    ('SCALE = 2', 'SCALE = 3', True),
    ('x: int = 0', 'x: int = 1', True),
    ('return [1, 2]', 'return [1, 2, 3]', True),
])
def test_identity_moves_only_with_what_the_function_reads(package, old, new, moves):
    """A docstring, an unread constant or another function leave `scaled`'s identity; its body, a constant, class
    or import-time call it reads move it."""
    root, key = package
    before = CI.identity(key)
    _edit(root / 'mod.py', old, new)
    assert before is not None and (CI.identity(key) != before) == moves


def test_identity_follows_an_imported_constant(package):
    """`from .other import LIMIT`: editing LIMIT in the other module moves `scaled`'s identity."""
    root, key = package
    before = CI.identity(key)
    _edit(root / 'other.py', 'LIMIT = 10', 'LIMIT = 11')
    assert CI.identity(key) != before and CI.changed({key: before}) == key


def test_identity_is_unknown_after_an_edit_during_the_run(package, monkeypatch):
    """A file edited after this process started is not the code running: no identity, so nothing is kept."""
    root, key = package
    monkeypatch.setattr(CI, 'STARTED', time.time() - 3600)
    CI.identity.cache_clear()
    assert CI.identity(key) is None


def test_the_plan_reads_code_edited_after_it_started(package, monkeypatch):
    """The build plan runs none of the code it checks: a file edited after it started (a peer's edit during a
    multi-plugin --run) still has an identity, so a plugin built from that code is current, not rebuilt forever."""
    root, key = package
    recorded = CI.identity(key)
    monkeypatch.setattr(CI, 'STARTED', time.time() - 3600)
    CI.identity.cache_clear()
    assert CI.changed({key: recorded}) == key
    CI.rebase()
    assert CI.changed({key: recorded}) is None
    _edit(root / 'other.py', 'LIMIT = 10', 'LIMIT = 11')
    CI.rebase()
    assert CI.changed({key: recorded}) == key


def test_a_cache_entry_is_remade_only_when_code_that_made_it_changes(package, tmp_path, monkeypatch):
    """work_cache.cached keeps the functions that ran making a value: an edit to another function in the same
    module keeps the entry; an edit to a constant the maker read remakes it."""
    root, _ = package
    mod = importlib.import_module(f'temp.{root.name}.mod')
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'work')
    made = []
    make = lambda: made.append(1) or mod.scaled(1)
    assert WC.cached('site', 'unused', (b'in',), make) == 2 * 1 + 10 + 2 + 0
    _edit(root / 'mod.py', '    return v\n', '    return v + 1\n')
    WC.cached('site', 'unused', (b'in',), make)
    assert len(made) == 1
    _edit(root / 'mod.py', 'SCALE = 2', 'SCALE = 3')
    WC.cached('site', 'unused', (b'in',), make)
    assert len(made) == 2


def test_identity_is_the_same_in_every_process():
    """Names are walked in sorted order, so a process's string hash seed cannot change which definitions an
    identity takes in (a cell.py method naming many module-level names)."""
    code = ('from fo4_import.pipeline.code_identity import identity; '
            "print(identity('fo4_import/spike/cell.py::CellBuilder.__init__'))")
    seen = {subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, 'PYTHONHASHSEED': seed}).stdout for seed in ('1', '2', '3')}
    assert len(seen) == 1 and 'None' not in seen.pop()


def _helper(v: int) -> int:
    """A repo function for capture()."""
    return v + 1


def test_capture_records_the_repo_functions_that_ran():
    """capture() sees a function that already ran before it (re-armed) and nothing that did not run."""
    _helper(1)
    with RC.capture() as seen:
        _helper(2)
    assert 'tests/test_fo4_build_plan.py::_helper' in seen
    assert 'tests/test_fo4_build_plan.py::test_identity_follows_an_imported_constant' not in seen


@pytest.fixture
def recording(tmp_path, monkeypatch):
    """This process recording into a fresh record (no masters asked, no code run by earlier tests), stopped
    after."""
    monkeypatch.setattr(RC, 'RAN', set())
    RC.start()
    sys.monitoring.restart_events()
    monkeypatch.setattr(BI, '_SEEN', {k: set() for k in BI._SEEN})
    monkeypatch.setattr(BI, '_STATE', {'on': False, 'main': False})
    monkeypatch.setattr(BI, 'MASTERS', BI.MasterLog())
    monkeypatch.delenv(BI.ENV, raising=False)
    BI.start(tmp_path / 'record')
    yield tmp_path
    BI._STATE['on'] = False


def _finished(plugin: Path) -> None:
    """Write `plugin` and a finished stamp beside it."""
    plugin.parent.mkdir(parents=True, exist_ok=True)
    if not plugin.exists():
        plugin.write_bytes(b'plugin')
    plugin.with_name(plugin.name + '.build.json').write_text(json.dumps({'status': 'finished'}), encoding='utf-8')


def test_a_build_records_what_it_read_not_what_it_wrote(recording):
    """Read inputs are recorded with their bytes; a file the build wrote and read back is not; editing an input
    makes the plan say build, naming it."""
    source, data = recording / 'source.txt', recording / 'data'
    BI._STATE['on'] = False
    source.write_text('fnv', encoding='utf-8')
    BI._STATE['on'] = True
    data.mkdir()
    (data / 'out.nif').write_text('made', encoding='utf-8')
    source.read_text(encoding='utf-8')
    (data / 'out.nif').read_text(encoding='utf-8')
    _helper(3)
    plugin = data / 'Test.esm'
    _finished(plugin)
    rec = json.loads(BI.write(plugin, data, ['--export', 'x']).read_text(encoding='utf-8'))
    assert BI.norm(source) in rec['files'] and not any(p.startswith(BI.norm(data)) for p in rec['files'])
    assert 'tests/test_fo4_build_plan.py::_helper' in rec['code']
    assert BP.check(plugin) == (BP.CURRENT, '')
    source.write_text('fnv2', encoding='utf-8')
    assert BP.check(plugin) == (BP.BUILD, f'file {BI.norm(source)}')


def _mo2(root: Path, modlist: str, junk: str = '') -> None:
    """An MO2 folder at `root` selecting profile `play` (ini plus `junk`)."""
    (root / 'profiles' / 'play').mkdir(parents=True, exist_ok=True)
    (root / 'ModOrganizer.ini').write_text(f'[General]\nselected_profile=@ByteArray(play)\n{junk}', encoding='utf-8')
    (root / 'profiles' / 'play' / 'modlist.txt').write_text(modlist, encoding='utf-8')


def test_mo2_answers_stand_for_its_files(recording, monkeypatch):
    """MO2's ini and mod list are not inputs, the answers read from them are: an ini rewrite or an unrelated mod
    ticked leaves the plugin current; the file moving to a higher-priority mod makes it build.
    See: docs/fork/fo4_mod_builds.md#mo2-answers
    """
    mo2 = recording / 'mo2'
    monkeypatch.setattr(BP.creation_kit, 'MO2', mo2)
    _mo2(mo2, '+A\n')
    for mod in ('A', 'B'):
        (mo2 / 'mods' / mod).mkdir(parents=True)
    (mo2 / 'mods' / 'A' / 'x.txt').write_text('a', encoding='utf-8')
    assert BP.creation_kit.holding(Path('x.txt')) == mo2 / 'mods' / 'A' / 'x.txt'
    plugin = recording / 'data' / 'Test.esm'
    _finished(plugin)
    rec = json.loads(BI.write(plugin, recording / 'data', []).read_text(encoding='utf-8'))
    assert not any('modorganizer.ini' in p or 'modlist.txt' in p for p in rec['files'])
    _mo2(mo2, '+A\n+B\n', junk='[Settings]\ngeometry=changed\n')
    assert BP.check(plugin) == (BP.CURRENT, '')
    (mo2 / 'mods' / 'B' / 'x.txt').write_text('b', encoding='utf-8')
    _mo2(mo2, '+B\n+A\n')
    assert BP.check(plugin) == (BP.BUILD, 'mo2 holding x.txt')


def test_a_plugin_lookup_stands_for_the_mod_sources(recording, monkeypatch):
    """A replacement plugin found through the app's MO2 source is the input, not the settings, ini or mod list: an
    app setting changed, an ini rewrite or an unrelated mod ticked leave the plugin current; the plugin found in
    another mod makes it build.
    See: docs/fork/fo4_mod_builds.md#mo2-answers
    """
    mo2, app = recording / 'mo2', recording / 'fo4_app.json'
    monkeypatch.setattr(MD, 'FALLOUT4_DIR', recording / 'fo4')
    (recording / 'fo4' / 'Data').mkdir(parents=True)
    _mo2(mo2, '+A\n')
    for mod in ('A', 'B'):
        (mo2 / 'mods' / mod).mkdir(parents=True)
    (mo2 / 'mods' / 'A' / 'Guns.esp').write_bytes(b'a')
    source = {'folder': str(mo2), 'kind': 'mo2_profile', 'profile': '', 'enabled': True}
    app.write_text(json.dumps({'mod_sources': [source]}), encoding='utf-8')
    assert MD.find('Guns.esp', MD.plugin_dirs([], app)) == mo2 / 'mods' / 'A' / 'Guns.esp'
    plugin = recording / 'data' / 'Test.esm'
    _finished(plugin)
    rec = json.loads(BI.write(plugin, recording / 'data', []).read_text(encoding='utf-8'))
    assert not any(p.endswith(('modorganizer.ini', 'modlist.txt', 'fo4_app.json')) for p in rec['files'])
    app.write_text(json.dumps({'mod_sources': [source], 'work_dir': 'elsewhere'}), encoding='utf-8')
    _mo2(mo2, '+A\n+B\n', junk='[Settings]\ngeometry=changed\n')
    assert BP.check(plugin) == (BP.CURRENT, '')
    (mo2 / 'mods' / 'B' / 'Guns.esp').write_bytes(b'b')
    _mo2(mo2, '+B\n+A\n')
    verdict, reason = BP.check(plugin)
    assert verdict == BP.BUILD and reason.startswith('plugin found ["Guns.esp"')


def _game(path: Path, records: list) -> Path:
    """A built game plugin at `path` holding `records` [(signature, FormID, body)]."""
    game = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=True)
    for sig, fid, body in records:
        game.add_record(sig, pack_fo4_record(sig, fid, 0, body))
    path.parent.mkdir(parents=True, exist_ok=True)
    game.write(str(path))
    _finished(path)
    return path


def _dlc_asks(game: Path, dlc_data: Path) -> Path:
    """A DLC build that asked the game whether it holds 0x01000900 and read record 0x01000901; its plugin."""
    held = BI.Held(BP._held([game]))
    BI.MASTERS.cover('plugin', game)
    assert 0x01000900 in held
    body = BP._records([game], {0x01000901: 'FLST'})[0x01000901]
    BI.MASTERS.records[0x01000901] = body
    plugin = dlc_data / 'Dlc.esm'
    _finished(plugin)
    BI.write(plugin, dlc_data, [])
    return plugin


def test_a_dlc_is_current_after_a_game_change_it_did_not_read(recording):
    """Rebuilding the game with a new record and another record changed leaves the DLC current; changing the
    record it read, or dropping the one it asked about, makes it build."""
    game = _game(recording / 'game' / 'Game.esm', [('FLST', 0x01000900, b'a'), ('FLST', 0x01000901, b'b'),
                                                   ('FLST', 0x01000902, b'c')])
    dlc = _dlc_asks(game, recording / 'dlc')
    assert BP.check(dlc) == (BP.CURRENT, '')
    _game(game, [('FLST', 0x01000900, b'a'), ('FLST', 0x01000901, b'b'), ('FLST', 0x01000902, b'z'),
                 ('FLST', 0x01000903, b'new')])
    assert BP.check(dlc) == (BP.CURRENT, '')
    _game(game, [('FLST', 0x01000900, b'a'), ('FLST', 0x01000901, pack_subrecord('EDID', b'x\0'))])
    assert BP.check(dlc) == (BP.BUILD, 'master record 01000901')
    _game(game, [('FLST', 0x01000901, b'b')])
    assert BP.check(dlc)[1] == 'master holds 01000900'


def test_a_dlc_waits_for_a_game_that_needs_a_build(recording):
    """The plan puts the game first; a DLC whose game needs a build waits for it rather than being judged."""
    game = _game(recording / 'game' / 'Game.esm', [('FLST', 0x01000900, b'a'), ('FLST', 0x01000901, b'b')])
    dlc = _dlc_asks(game, recording / 'dlc')
    planned = BP.plan([dlc, game])
    assert [(p.name, verdict) for p, verdict, _ in planned] == [('Game.esm', BP.BUILD), ('Dlc.esm', BP.AFTER)]


@pytest.mark.parametrize('executable, args, program', [
    (None, '"C:\\Program Files\\Tool\\Caprica.exe" -o out', 'C:\\Program Files\\Tool\\Caprica.exe'),
    (None, 'cmd /c echo hi', 'cmd'),
    (None, ['Archive2.exe', 'x'], 'Archive2.exe'),
    ('C:\\py.exe', 'ignored', 'C:\\py.exe'),
])
def test_a_popen_names_its_program(executable, args, program):
    """A Popen's program: executable, else first item or command-line token."""
    assert BI._program(executable, args) == program


class _Annotated:
    """A class with an annotation: Python 3.14 runs its generated __annotate__ when the annotations are read."""
    size: int = 0


def test_generated_annotate_functions_are_not_recorded():
    """A generated __annotate__ (no source of its own) is not recorded."""
    with RC.capture() as seen:
        _Annotated.__annotations__
    assert not any(k.endswith('__annotate__') for k in seen)


def test_the_recording_itself_is_not_recorded():
    """The audit hook runs inside every capture; its file is left out, so editing it keeps every cache entry."""
    with RC.capture() as seen:
        BI._audit('open', ('x', 'r', 0))
        _helper(4)
    assert not any(k.startswith('fo4_import/pipeline/build_inputs.py') for k in seen) and seen


def test_master_scripts_follow_the_names_a_script_uses(tmp_path):
    """A DLC script naming a master script reaches it and what that one names; an unnamed one stays out."""
    master, own = tmp_path / 'master', tmp_path / 'own'
    master.mkdir()
    own.mkdir()
    (master / 'F3NV_Base.psc').write_text('ScriptName F3NV_Base extends Quest', encoding='utf-8')
    (master / 'F3NV_Packages.psc').write_text('ScriptName F3NV_Packages extends F3NV_Base', encoding='utf-8')
    (master / 'F3NV_Other.psc').write_text('ScriptName F3NV_Other', encoding='utf-8')
    (own / 'Dlc.psc').write_text('F3NV_Packages Property P Auto', encoding='utf-8')
    found = BI.master_scripts([own / 'Dlc.psc'], (master,))
    assert [p.name for p in found] == ['F3NV_Base.psc', 'F3NV_Packages.psc']
