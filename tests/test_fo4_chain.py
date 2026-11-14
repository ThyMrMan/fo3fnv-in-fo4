"""The watched build chain (tools/release/fo4_chain.py) and the guards it relies on in build_plan and the faces stage:
startup checks, the per-step watchdog, faces tied to a base build, CK export completeness, hidden input leaks, the
slow-step alarm and resume. Processes, folders and clocks are fakes; nothing builds and no MO2 folder is written.

See: docs/fork/fo4_chain.md#tests
"""

import argparse
import json
import queue
from pathlib import Path

import pytest

from fo4_import.pipeline import build_plan as BP
from fo4_import.pipeline import eta
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.spike import facegen
from tools.release import fo4_chain as FC


def _config(tmp_path: Path, **over) -> FC.Config:
    """A Config whose every path exists under `tmp_path`."""
    games = tmp_path / 'games'
    fo4, mo2, nv = games / 'Fallout 4', tmp_path / 'mo2', tmp_path / 'mods' / 'F3NV - Fallout New Vegas'
    for folder in (games / 'FNV' / 'Data', fo4, mo2, nv, tmp_path / 'export' / 'FalloutNV.esm', tmp_path / 'tools'):
        folder.mkdir(parents=True, exist_ok=True)
    (fo4 / 'Fallout4.exe').write_bytes(b'')
    tool = tmp_path / 'tools' / 'CreationKit.exe'
    tool.write_bytes(b'')
    sources = tmp_path / 'export' / 'sources.json'
    sources.write_text(json.dumps({'directories': [{'label': 'Fallout New Vegas', 'path': str(games / 'FNV' / 'Data')}],
                                   'homes': {'falloutnv.esm': str(games / 'FNV' / 'Data')}}), encoding='utf-8')
    app = tmp_path / 'app' / 'fo4_app.json'
    app.parent.mkdir(exist_ok=True)
    app.write_text(json.dumps({'games': {'fallout4': str(fo4), 'fallout3': ''},
                               'mod_sources': [{'folder': str(mo2), 'enabled': True}]}), encoding='utf-8')
    fields = dict(root=tmp_path, export=tmp_path / 'export' / 'FalloutNV.esm', sources=sources, app=app, nv=nv,
                  mo2=mo2, fallout4=fo4, tools={'the Creation Kit': tool}, state=tmp_path / 'chain' / 'state.json',
                  log=tmp_path / 'chain' / 'chain.log')
    return FC.Config(**{**fields, **over})


@pytest.fixture
def no_scratch(monkeypatch):
    """No plugin reads a scratch master."""
    monkeypatch.setattr(BP, 'scratch_masters', lambda plugins: [])


def _plenty(anchor):
    """Free bytes on a roomy drive."""
    return 500 << 30


def test_a_good_setup_passes_the_startup_checks(tmp_path, no_scratch):
    """Every path present, nothing running, room to spare: no problem."""
    assert FC.startup_problems(_config(tmp_path), [], {'explorer.exe'}, _plenty) == []


def test_missing_source_folders_homes_and_tools_are_each_named(tmp_path, no_scratch):
    """The Steam move of 2026-11-12: the registry names folders that are gone; each is a line, in seconds."""
    cfg = _config(tmp_path)
    cfg.sources.write_text(json.dumps({'directories': [{'label': 'Fallout 3 goty', 'path': 'C:/gone/Data'}],
                                       'homes': {'fallout3.esm': 'C:/gone/Data'}}), encoding='utf-8')
    cfg.tools['texconv'] = tmp_path / 'tools' / 'texconv.exe'
    lines = FC.startup_problems(cfg, [], set(), _plenty)
    assert lines == ['source directory "Fallout 3 goty" (export/sources.json) is missing: C:/gone/Data',
                     'the home of fallout3.esm (export/sources.json) is missing: C:/gone/Data',
                     f'texconv is missing: {tmp_path / "tools" / "texconv.exe"}']


def test_missing_app_settings_install_and_mo2_are_named(tmp_path, no_scratch):
    """No fo4_app.json, no Fallout 4, no MO2: one line each."""
    cfg = _config(tmp_path, mo2=tmp_path / 'no_mo2', fallout4=tmp_path / 'no_fo4')
    cfg.app.unlink()
    lines = FC.startup_problems(cfg, [], set(), _plenty)
    assert lines == [f'the app settings are missing or unreadable: {cfg.app}',
                     f'the Fallout 4 install is missing: {tmp_path / "no_fo4" / "Fallout4.exe"}',
                     f'the Mod Organizer 2 instance (creation_kit.MO2) is missing: {tmp_path / "no_mo2"}']


def test_the_game_mo2_and_the_ck_must_be_closed(tmp_path, no_scratch):
    """Fallout 4, MO2 or the CK running stops the chain before it starts."""
    lines = FC.startup_problems(_config(tmp_path), [], {'fallout4.exe', 'modorganizer.exe', 'creationkit.exe'},
                                _plenty)
    assert lines == ['Fallout 4 is running (fallout4.exe): close it first',
                     'Mod Organizer 2 is running (modorganizer.exe): close it first',
                     'the Creation Kit is running (creationkit.exe): close it first']


def test_too_little_free_space_is_named(tmp_path, no_scratch):
    """A drive under the limit is a line with its free space."""
    lines = FC.startup_problems(_config(tmp_path), [], set(), lambda anchor: 12 << 30)
    assert lines == [f'drive {tmp_path.anchor} has 12.0 GB free, under 40 GB']


def test_a_master_from_a_temp_copy_stops_the_chain_and_the_run(tmp_path, monkeypatch):
    """A plugin outside temp/ whose last build read a master in it is refused by the chain and by build_plan."""
    scratch, mods = tmp_path / 'temp', tmp_path / 'mods'
    plugin, master = mods / 'Caravan' / 'CaravanPack.esm', scratch / 'profile_data' / 'FalloutNV.esm'
    monkeypatch.setattr(BP, 'SCRATCH', (scratch,))
    monkeypatch.setattr(BP, 'masters_of', lambda p: [master] if p == plugin else [])
    lines = FC.startup_problems(_config(tmp_path), [plugin], set(), _plenty)
    assert lines == [f'a master would come from a scratch copy: CaravanPack.esm: master {master}']
    monkeypatch.setattr(BP, 'rebuild', lambda *a: pytest.fail('nothing may build'))
    assert BP.run([plugin]) == BP.SCRATCH_MASTER


def test_a_scratch_build_may_read_scratch_masters(tmp_path, monkeypatch):
    """A plugin inside temp/ (a scratch build of its own) reading a temp/ master is fine."""
    scratch = tmp_path / 'temp'
    monkeypatch.setattr(BP, 'SCRATCH', (scratch,))
    monkeypatch.setattr(BP, 'masters_of', lambda p: [scratch / 'FalloutNV.esm'])
    assert BP.scratch_masters([scratch / 'DeadMoney.esm']) == []


class Feed:
    """A process's stdout fed by the test: each put() returns once the reader has taken the line."""

    def __init__(self):
        """Empty."""
        self.q, self.taken = queue.Queue(), False

    def __iter__(self):
        """Itself."""
        return self

    def __next__(self):
        """The next line, waiting for it; StopIteration at the end."""
        if self.taken:
            self.taken = False
            self.q.task_done()
        line = self.q.get()
        if line is None:
            self.q.task_done()
            raise StopIteration
        self.taken = True
        return line

    def put(self, line) -> None:
        """Give the reader `line` (None: the end) and wait until it took it."""
        self.q.put(line)
        self.q.join()


class FakeRun:
    """A fake clock driving a fake process: lines and new files appear at given seconds, the process ends at
    `exit_at`."""

    def __init__(self, lines_at=(), files_at=(), exit_at=None, code=0):
        """The script."""
        self.now = self.start = 1_000_000.0
        self.lines_at, self.files_at, self.exit_at, self.code = list(lines_at), list(files_at), exit_at, code
        self.stdout, self.returncode, self.pid = Feed(), None, 1
        self.killed = self.ck_closed = 0
        self.notes, self.out = [], []

    def poll(self):
        """The exit code once ended."""
        return self.returncode

    def sleep(self, seconds: float) -> None:
        """Advance the clock; release what is due."""
        self.now += seconds
        t = self.now - self.start
        while self.lines_at and self.lines_at[0][0] <= t:
            self.stdout.put(self.lines_at.pop(0)[1])
        if self.exit_at is not None and t >= self.exit_at and self.returncode is None:
            self.returncode = self.code
            self.stdout.put(None)

    def newest(self, folders) -> float:
        """The newest fake file's time."""
        return max((self.start + t for t in self.files_at if self.start + t <= self.now), default=0.0)

    def kill(self, proc) -> None:
        """End the process."""
        self.killed += 1
        self.returncode = -9
        self.stdout.put(None)

    def hooks(self) -> FC.Hooks:
        """Hooks driving this fake."""
        return FC.Hooks(clock=lambda: self.now, sleep=self.sleep, spawn=lambda argv, env, cwd: self,
                        newest=self.newest, kill=self.kill, close_ck=self._close_ck,
                        notify=lambda title, text: self.notes.append(title), out=self.out.append)

    def _close_ck(self) -> None:
        """Count a CK close."""
        self.ck_closed += 1


def _runner(tmp_path, fake: FakeRun, fresh=True) -> FC.Runner:
    """A Runner on `fake`, notifications on."""
    cfg = _config(tmp_path)
    return FC.Runner(cfg, FC.State(cfg.state, fresh), fake.hooks(), notify=True)


def test_a_step_that_prints_nothing_is_ended_with_a_named_error(tmp_path):
    """No output for the step's limit: STALL_NO_OUTPUT, the process tree and any CK ended, a notification."""
    fake = FakeRun(files_at=range(0, 10_000, 30))
    step = FC.Step('base', ['py', 'build'], watch=[tmp_path], no_output=600, no_file=600)
    assert _runner(tmp_path, fake).run([step]) == FC.EXIT_STALL
    assert fake.killed == 1 and fake.ck_closed == 1 and fake.notes == ['F3NV build chain stopped']
    assert any(line.startswith('===== chain stopped: STALL_NO_OUTPUT: base printed nothing for 10 min')
               for line in fake.out)
    assert json.loads((tmp_path / 'chain' / 'state.json').read_text())['steps']['base']['status'] == 'stalled'


def test_a_ck_step_writing_no_file_is_ended_with_a_named_error(tmp_path):
    """Output keeps coming but MO2's overwrite gets no new file: STALL_NO_NEW_FILE names the folder."""
    overwrite = tmp_path / 'overwrite'
    fake = FakeRun(lines_at=[(t, f'tick {t}\n') for t in range(10, 5000, 10)], files_at=[30])
    step = FC.Step('faces', ['py', 'facegen'], watch=[overwrite], no_output=600, no_file=900)
    assert _runner(tmp_path, fake).run([step]) == FC.EXIT_STALL
    stopped = [line for line in fake.out if line.startswith('===== chain stopped')]
    assert stopped == [f'===== chain stopped: STALL_NO_NEW_FILE: faces wrote no new file in {overwrite} for 15 min '
                       f'(limit 15)']


def test_a_step_that_keeps_working_passes_and_its_output_is_logged(tmp_path):
    """Lines and files keep coming until it exits 0: passed, every line in the console and the chain log."""
    fake = FakeRun(lines_at=[(t, f'line {t}\n') for t in range(5, 2000, 60)], files_at=range(0, 2000, 120),
                   exit_at=2000)
    step = FC.Step('helpers', ['py', 'helpers'], watch=[tmp_path], no_output=600, no_file=600)
    assert _runner(tmp_path, fake).run([step]) == 0
    assert 'line 1985' in fake.out and '===== helpers: exit 0 after 2000 s' in fake.out
    assert 'line 1985' in (tmp_path / 'chain' / 'chain.log').read_text(encoding='utf-8')
    assert fake.notes == ['F3NV build chain finished']


def test_a_failing_step_stops_the_chain_with_its_code(tmp_path):
    """A step exiting 7 stops the chain with 7; the next step never runs."""
    fake = FakeRun(lines_at=[(5, 'boom\n')], exit_at=10, code=7)
    later = FC.Step('later', call=lambda: pytest.fail('ran after a failure'))
    assert _runner(tmp_path, fake).run([FC.Step('base', ['py'], no_file=None), later]) == 7


def test_a_failing_preflight_does_not_stop_the_chain(tmp_path):
    """A non-fatal step's failure is reported; the chain goes on."""
    fake, ran = FakeRun(exit_at=10, code=1), []
    steps = [FC.Step('preflight', ['py'], fatal=False, no_file=None), FC.Step('kit', call=lambda: ran.append(1))]
    assert _runner(tmp_path, fake).run(steps) == 0 and ran == [1]


def _built(plugin: Path, started: str) -> None:
    """A finished build stamp for `plugin` started at `started`."""
    plugin.parent.mkdir(parents=True, exist_ok=True)
    plugin.write_bytes(b'TES4' + bytes(20))
    path = stamp_path(plugin)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'status': 'finished', 'started': started, 'ended': started + ' end'}),
                    encoding='utf-8')


def test_faces_are_stale_after_a_rebuild_of_their_plugin(tmp_path):
    """The faces stamp names the build it ran on; another build makes them stale, an unfinished stage too."""
    plugin = tmp_path / 'mod' / 'FalloutNV.esm'
    _built(plugin, '2026-11-13 01:00:00')
    assert facegen.faces_stale(plugin) is None
    facegen.write_faces_stamp(plugin, 'finished', ['--data', 'x', 'FalloutNV.esm'], tmp_path)
    assert facegen.faces_stale(plugin) is None
    _built(plugin, '2026-11-13 02:00:00')
    assert facegen.faces_stale(plugin) == ('its faces ran on build 2026-11-13 01:00:00 to 2026-11-13 01:00:00 end, '
                                           'the plugin is now build 2026-11-13 02:00:00 to 2026-11-13 02:00:00 end')
    facegen.write_faces_stamp(plugin, 'running', [], tmp_path)
    assert 'did not finish' in facegen.faces_stale(plugin)


def test_build_plan_runs_the_faces_again_right_after_a_rebuild(tmp_path, monkeypatch):
    """A base rebuild inside build_plan --run no longer resets the faces: the stage reruns with its arguments
    before anything else is planned."""
    plugin, calls = tmp_path / 'mod' / 'FalloutNV.esm', []
    _built(plugin, 'one')
    facegen.write_faces_stamp(plugin, 'finished', ['--own-facegen', 'FalloutNV.esm'], tmp_path)
    plans = iter([[(plugin, BP.BUILD, 'code x')], [(plugin, BP.CURRENT, '')]])
    monkeypatch.setattr(BP, 'plan', lambda plugins: next(plans))
    monkeypatch.setattr(BP, 'master_dirs', lambda *_: [])
    monkeypatch.setattr(BP, 'masters_of', lambda p: [])
    monkeypatch.setattr(BP, 'rebuild', lambda p, dirs: calls.append('build') or _built(p, 'two') or 0)

    def faces(argv, cwd):
        """The faces stage: record it, stamp it on the new build."""
        calls.append(argv[3:])
        facegen.write_faces_stamp(plugin, 'finished', argv[3:], tmp_path)
        return 0
    monkeypatch.setattr(BP.subprocess, 'call', faces)
    assert BP.run([plugin]) == 0
    assert calls == ['build', ['--own-facegen', 'FalloutNV.esm']]


def test_the_chain_reruns_faces_on_another_base_build(tmp_path, monkeypatch):
    """The chain's faces step is current only while its stamp names the base build on disk."""
    cfg = _config(tmp_path)
    _built(cfg.base, 'one')
    facegen.write_faces_stamp(cfg.base, 'finished', [], tmp_path)
    assert FC.faces_key(cfg).startswith('one to one end faces ')
    _built(cfg.base, 'two')
    assert FC.faces_key(cfg) is None
    with pytest.raises(FC.ChainError) as stopped:
        FC.faces_check(cfg)
    assert stopped.value.name == FC.FACES_STALE


def _nif(data: Path, stem: str) -> None:
    """A FaceGeom NIF for `stem`."""
    path = data / facegen.FACEGEN_DIRS[0] / 'p.esp' / f'{stem}.nif'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'nif')


def test_a_ck_export_missing_an_npc_fails(tmp_path, monkeypatch):
    """A CK closed after CK_QUIET mid-export: the NPCs it left without a FaceGeom are named and the stage fails."""
    monkeypatch.setattr(facegen, 'expected_faces', lambda plugin, data: {'00000800', '00000801', '00000802'})
    monkeypatch.setattr(facegen, 'collect', lambda plugin, data: [])
    _nif(tmp_path, '00000800')
    with pytest.raises(SystemExit, match=r'incomplete: 2 of 3 NPCs have no FaceGeom NIF \(00000801, 00000802\)'):
        facegen.export('p.esp', tmp_path, ck=False)
    _nif(tmp_path, '00000801')
    _nif(tmp_path, '00000802')
    assert facegen.export('p.esp', tmp_path, ck=False) == 0


def test_a_ck_fallback_missing_an_npc_fails_the_stage(tmp_path, monkeypatch):
    """The fallback expects only the failed NPCs; one it leaves without a head is a FALLBACK_FAILED line."""
    monkeypatch.setattr(facegen, 'expected_faces', lambda plugin, data: {'00000800', '00000801'})
    monkeypatch.setattr(facegen, 'run_ck', lambda plugin, data: None)
    monkeypatch.setattr(facegen, 'collect', lambda plugin, data, only: [])
    lines = facegen.fallback('p.esp', tmp_path, {0x801: 'ValueError: x'})
    assert lines[0].startswith(facegen.FALLBACK_FAILED) and '00000801' in lines[0]


def test_a_build_flipping_an_unrelated_plugin_stops_the_run(tmp_path, monkeypatch, capsys):
    """Building A makes B (which does not read A) need a build: stop and name B's changed input."""
    a, b, built = tmp_path / 'A.esm', tmp_path / 'B.esm', []
    plans = iter([[(a, BP.BUILD, 'code x'), (b, BP.CURRENT, '')],
                  [(a, BP.CURRENT, ''), (b, BP.BUILD, f'file {tmp_path / "shared.txt"}')]])
    monkeypatch.setattr(BP, 'plan', lambda plugins: next(plans))
    monkeypatch.setattr(BP, 'masters_of', lambda p: [])
    monkeypatch.setattr(BP, 'master_dirs', lambda *_: [])
    monkeypatch.setattr(BP, 'rebuild', lambda p, dirs: built.append(p.name) or 0)
    assert BP.run([a, b]) == BP.LEAKED and built == ['A.esm']
    assert f'B.esm needs a build after building A.esm, which it does not depend on (file {tmp_path / "shared.txt"})' \
           in capsys.readouterr().out


def test_a_plugin_reading_the_one_built_may_flip(tmp_path, monkeypatch):
    """B reads A as a master (through C): its flip is expected and it builds."""
    a, b, c, built = tmp_path / 'A.esm', tmp_path / 'B.esm', tmp_path / 'C.esm', []
    plans = iter([[(a, BP.BUILD, 'code x'), (c, BP.AFTER, 'A.esm'), (b, BP.CURRENT, '')],
                  [(a, BP.CURRENT, ''), (c, BP.CURRENT, ''), (b, BP.BUILD, 'master record 00000800')],
                  [(a, BP.CURRENT, ''), (c, BP.CURRENT, ''), (b, BP.CURRENT, '')]])
    monkeypatch.setattr(BP, 'plan', lambda plugins: next(plans))
    monkeypatch.setattr(BP, 'masters_of', lambda p: {c: [a], b: [c]}.get(p, []))
    monkeypatch.setattr(BP, 'master_dirs', lambda *_: [])
    monkeypatch.setattr(BP, 'rebuild', lambda p, dirs: built.append(p.name) or 0)
    assert BP.run([a, c, b]) == 0 and built == ['A.esm', 'B.esm']


def test_a_plugin_built_before_its_masters_builds_again_after_them(tmp_path, monkeypatch):
    """O had no record, so it built first; its record then names M, and M's build makes O build again."""
    o, m, built = tmp_path / 'O.esl', tmp_path / 'M.esp', []
    plans = iter([[(o, BP.BUILD, 'no record'), (m, BP.BUILD, 'code x')],
                  [(m, BP.BUILD, 'code x'), (o, BP.AFTER, 'M.esp')],
                  [(m, BP.CURRENT, ''), (o, BP.BUILD, 'file m.json')],
                  [(m, BP.CURRENT, ''), (o, BP.CURRENT, '')]])
    monkeypatch.setattr(BP, 'plan', lambda plugins: next(plans))
    monkeypatch.setattr(BP, 'masters_of', lambda p: [m] if p == o and built else [])
    monkeypatch.setattr(BP, 'master_dirs', lambda *_: [])
    monkeypatch.setattr(BP, 'rebuild', lambda p, dirs: built.append(p.name) or 0)
    assert BP.run([o, m]) == 0 and built == ['O.esl', 'M.esp', 'O.esl']


def test_a_step_past_twice_its_estimate_warns_once(tmp_path):
    """Estimate 100 s, still running at 201 s: one SLOW line and one notification; the step still passes."""
    fake = FakeRun(lines_at=[(t, 'x\n') for t in range(5, 400, 20)], exit_at=400)
    step = FC.Step('base', ['py'], estimate=lambda: (100.0, None), no_file=None)
    assert _runner(tmp_path, fake).run([step]) == 0
    slow = [line for line in fake.out if line.startswith('SLOW: base has run')]
    assert len(slow) == 1 and 'F3NV chain: base is slow' in fake.notes
    assert any('F3NV_PROFILE_STAGES' in line for line in fake.out)


def test_the_profiling_advice_names_the_stages_that_overran(tmp_path):
    """eta.overran: the slowest stage of each group past its plan, worst group first."""
    plan = {'worlds': 100.0, 'weapons': 50.0, 'people': 80.0}
    stages = {'worlds': 900.0, 'navmesh': 20.0, 'item WEAP': 120.0, 'people': 60.0}
    assert eta.overran(plan, stages) == ['worlds', 'item WEAP']


def test_a_step_without_its_own_estimate_uses_its_last_run(tmp_path):
    """The faces step has no model: twice its last passing time is the alarm."""
    fake = FakeRun(lines_at=[(t, 'x\n') for t in range(5, 100, 5)], exit_at=100)
    runner = _runner(tmp_path, fake)
    runner.state.steps['faces'] = {'status': 'passed', 'key': None, 'seconds': 40.0}
    assert runner.run([FC.Step('faces', ['py'], no_file=None)]) == 0
    assert '===== faces: py (estimate 1 min)' in fake.out
    assert any(line.startswith('SLOW: faces has run') for line in fake.out)


def test_a_restart_skips_finished_current_steps(tmp_path):
    """A passed step whose key still matches is skipped; a changed key, a failed or a keyless step runs."""
    keys, ran = {'a': 'k1', 'b': 'k1'}, []
    steps = [FC.Step(name, call=lambda name=name: ran.append(name), key=lambda name=name: keys.get(name))
             for name in ('a', 'b', 'c')]
    first = FakeRun()
    assert _runner(tmp_path, first).run(steps) == 0 and ran == ['a', 'b', 'c']
    ran.clear()
    keys['b'] = 'k2'
    again = FakeRun()
    assert _runner(tmp_path, again, fresh=False).run(steps) == 0 and ran == ['b', 'c']
    assert '===== a: current, skipped' in again.out


def test_a_failed_step_runs_again_and_fresh_forgets(tmp_path):
    """After a failure the restart runs that step; --fresh runs everything."""
    fails, ran = [True], []

    def flaky():
        """Fail once."""
        ran.append('x')
        if fails.pop() if fails else False:
            raise RuntimeError('broke')
    steps = [FC.Step('x', call=flaky, key=lambda: 'k')]
    assert _runner(tmp_path, FakeRun()).run(steps) == 1
    assert _runner(tmp_path, FakeRun(), fresh=False).run(steps) == 0
    assert _runner(tmp_path, FakeRun(), fresh=False).run(steps) == 0
    assert ran == ['x', 'x']
    assert _runner(tmp_path, FakeRun(), fresh=True).run(steps) == 0 and ran == ['x', 'x', 'x']


def test_the_chain_keeps_the_scratch_chains_order(tmp_path, monkeypatch):
    """base, faces, helpers, dll, plan, others (The Frontier left out), faces check, preflight, then the kit."""
    cfg = _config(tmp_path)
    for mod, name in (('F3NV - Dead Money', 'DeadMoney.esm'), ('F3NV - The Frontier', 'TheFrontier.esm')):
        _built(cfg.nv.parent / mod / name, 'one')
    monkeypatch.setattr(FC, '_ck_output', lambda: [])
    args = argparse.Namespace(profile_stages=FC.PROFILE_STAGES, kit=tmp_path / 'kit.esl', kit_mod=tmp_path / 'kit')
    steps = FC.chain_steps(cfg, args)
    assert [s.name for s in steps] == ['base', 'faces', 'helpers', 'dll', 'plan', 'others', 'faces check',
                                       'preflight', 'test plugin']
    others = [str(a) for a in steps[5].argv]
    assert others[-1] == '--run' and str(cfg.nv.parent / 'F3NV - Dead Money' / 'DeadMoney.esm') in others
    assert not any('Frontier' in a for a in others)
    assert steps[0].env['F3NV_PROFILE_STAGES'] == 'worlds,item WEAP'
    assert '--own-facegen' in steps[1].argv
