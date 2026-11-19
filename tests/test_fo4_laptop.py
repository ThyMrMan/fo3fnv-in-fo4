"""The test-machine runner's parts that need no second machine."""
import io
import json
import os

from tools.live import fo4_laptop as L
from tools.live import fo4_test_instance as T


def _files(root, names):
    """Writes each of `names` under `root` with its own name as content."""
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding='utf-8')


def test_send_sends_changed_and_removes_stale(tmp_path, monkeypatch):
    """A file the test machine lacks or holds older is sent; one only it has, under a pushed folder, goes."""
    _files(tmp_path, ['Mod/a.esm', 'Mod/b.ba2'])
    os.utime(tmp_path / 'Mod/a.esm', (2_000_000_000, 2_000_000_000))
    asked, sent = [], []

    def fake_ask(_cfg, payload, *args):
        """The test machine: a.esm older there, b.ba2 the same, gone.txt only there."""
        asked.append((args[0], payload))
        same = L.stats(tmp_path, ['Mod/b.ba2'])['Mod/b.ba2']
        return {'Mod/a.esm': [9, 1], 'Mod/b.ba2': same, 'Mod/gone.txt': [1, 1]} if args[0] == 'stat' else 1

    class FakePopen:
        """Stands in for the local tar, recording what it would send."""

        def __init__(self, cmd, stdout):
            sent.append(open(cmd[-1], encoding='utf-8').read().split())
            self.stdout = io.BytesIO()

        def wait(self):
            return 0

    monkeypatch.setattr(L, 'ask', fake_ask)
    monkeypatch.setattr(L.subprocess, 'Popen', FakePopen)
    monkeypatch.setattr(L.subprocess, 'run', lambda *a, **k: type('Done', (), {'returncode': 0})())
    L.send({'host': 'h'}, tmp_path, 'D:\\mods', L.tree(tmp_path, ['Mod']), ('Mod',))
    assert asked[1] == ('remove', ['Mod/gone.txt'])
    assert sent == [['Mod/a.esm']]


def test_stat_command_lists_named_files_and_folders(tmp_path, monkeypatch, capsys):
    """The test machine answers the named files plus everything under the named folders."""
    _files(tmp_path, ['repo/x.py', 'Mod/one.esm', 'Mod/sub/two.dds'])
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps({'files': ['repo/x.py', 'repo/missing.py'],
                                                             'under': ['Mod', 'NotThere']})))
    L.stat_command(tmp_path)
    assert sorted(json.loads(capsys.readouterr().out)) == ['Mod/one.esm', 'Mod/sub/two.dds', 'repo/x.py']


def test_local_run_builds_then_runs_visible_cases(tmp_path, monkeypatch):
    """The story-case task builds the instance, then runs the cases visibly, each only if the last passed."""
    started = {}
    monkeypatch.setattr(L, 'start_task', lambda folder, commands: started.update(commands=commands) or 0)
    L.local_run('D:\\MO2', 'Fallout 3', ['tests/story/fo3_opening', '--set', 'SEX=male'])
    build, cases = started['commands']
    assert 'fo4_test_instance build --mo2 D:\\MO2 --profile "Fallout 3"' in build
    assert 'fo4_story_cases --visible tests/story/fo3_opening --set SEX=male' in cases
    text = L.task_script(tmp_path, started['commands']).read_text()
    assert text.count('if not errorlevel 1') == 2 and 'run.done' in text
    assert T.Instance(1, visible=True).desktop == 'Default'


def test_local_record_runs_the_recorder(monkeypatch):
    """The recording task runs fo3_record on the given install, writing the timeline beside its log."""
    started = {}
    monkeypatch.setattr(L, 'start_task', lambda folder, commands: started.update(folder=folder, commands=commands))
    L.local_record('C:\\Games\\Fallout 3', ['--seconds', '60'])
    (command,) = started['commands']
    assert 'tools.live.fo3_record --fallout3 "C:\\Games\\Fallout 3"' in command and '--seconds 60' in command
    assert str(started['folder'] / 'f3_timeline.log') in command


def test_cmdline_quotes_what_cmd_would_split():
    """Spaces, pipes and semicolons are quoted for cmd; plain words are not."""
    assert L.cmdline(['--until', r'\|stage\|5$', 'coc X;say', 'plain']) == r'--until "\|stage\|5$" "coc X;say" plain'


def test_record_arguments_pass_through():
    """`record -- --seconds 60` hands the options after `--` to the recorder."""
    args = L.parse_args(['record', '--', '--seconds', '60', '--menu', 'coc X'])
    assert [a for a in args.case_args if a != '--'] == ['--seconds', '60', '--menu', 'coc X']
