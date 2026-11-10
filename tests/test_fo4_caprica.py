"""Caprica ahead of FO4's compiler: the header patches, the drop-and-retry runs, and which failures are the
script's own.

See: docs/fork/fo4_pipeline.md#caprica
"""

from fo4_import.base import caprica as CP

UNRESOLVED = "Unresolved identifier 'nGone'!"


def test_the_header_patches_fix_what_capricas_parser_rejects():
    """Leading whitespace goes, a struct member named parent is renamed, a Var parameter loses its None default;
    other text is unchanged."""
    text = ' Scriptname X extends Y\nstruct ConnectPoint\n\tstring parent\n\tstring name\nendstruct\n' \
           'Function F(Var filter = None) native\nint parentCount\n'
    out = CP._patched(text)
    assert out.startswith('Scriptname X')
    assert '\tstring parentNode\n' in out and '\tstring name\n' in out and 'int parentCount' in out
    assert 'Function F(Var filter) native' in out


def _sources(tmp_path, names: str, monkeypatch) -> tuple:
    """(the .psc paths of `names`, an empty output folder); the import list and memory check are passed through."""
    src, out = tmp_path / 'src', tmp_path / 'out'
    src.mkdir()
    out.mkdir()
    for name in names:
        (src / f'{name}.psc').write_text(f'Scriptname {name}\nEvent OnBogus()\nEndEvent\n')
    monkeypatch.setattr(CP, 'caprica_imports', lambda imports: imports)
    monkeypatch.setattr(CP, 'memory_workers', lambda wanted, each, spare: wanted)
    return [src / f'{name}.psc' for name in names], out


def _stops_at(failing: dict, runs: list):
    """A _run stand-in compiling in name order and stopping at the first script of `failing` {name: message}."""
    def fake_run(folder, out_dir, imports):
        """(1, the failing script's error line) at the first failing script, else (0, '')."""
        runs.append(sorted(p.stem for p in folder.glob('*.psc')))
        for path in sorted(folder.glob('*.psc')):
            if path.stem in failing:
                return 1, f"{path.stem}.psc (2, 1:2): Error: {failing[path.stem]}\nCompilation of '{path.stem}.psc' failed"
            (out_dir / f'{path.stem}.pex').write_bytes(b'pex')
        return 0, ''
    return fake_run


def test_a_source_error_is_the_scripts_own_and_any_other_failure_is_left_to_fo4(tmp_path, monkeypatch):
    """b fails on an unresolved name: its error is kept. d fails on a message not known to be a source error: it
    is in neither result. Each is dropped and the rest run again."""
    files, out = _sources(tmp_path, 'abcde', monkeypatch)
    runs = []
    monkeypatch.setattr(CP, '_run', _stops_at({'b': UNRESOLVED, 'd': "Cannot initialize a 'var' value with a 'None'!"}, runs))
    assert CP.compile_files(files, out, 'headers') == ({'a', 'c', 'e'}, {'b': [UNRESOLVED]}, 3)
    assert runs == [['a', 'b', 'c', 'd', 'e'], ['c', 'd', 'e'], ['e']] and not (out / '_caprica').exists()


def test_a_crash_a_timeout_or_an_unreadable_header_leaves_the_folder_to_fo4(tmp_path, monkeypatch):
    """A run naming no script of the folder ends it after one run with no error recorded; a crash's and a
    timeout's .pex are deleted, as one may be half written."""
    files, out = _sources(tmp_path, 'ab', monkeypatch)
    for code, text in ((0xC0000409, ''), (None, ''), (1, 'ObjectReference.psc (1212, 9:15): Fatal Error: Syntax error!')):
        runs = []

        def fake_run(folder, out_dir, imports, code=code, text=text, runs=runs):
            """Write a.pex, then end as the case says."""
            runs.append(1)
            (out_dir / 'a.pex').write_bytes(b'half')
            return code, text
        monkeypatch.setattr(CP, '_run', fake_run)
        assert CP.compile_files(files, out, 'headers') == (set(), {}, 1) and len(runs) == 1
        assert not (out / 'a.pex').exists()


def test_the_scripts_are_dealt_into_folders_run_at_once(tmp_path, monkeypatch):
    """With two workers, five scripts go into two folders; each folder's failing script costs that folder one more
    run, and the group folder leads its import list."""
    files, out = _sources(tmp_path, 'abcde', monkeypatch)
    runs, imports = [], []

    def fake_run(folder, out_dir, given):
        """Record the import list, then compile as _stops_at does."""
        imports.append(given.split(';'))
        return _stops_at({'a': UNRESOLVED, 'b': UNRESOLVED}, runs)(folder, out_dir, given)
    monkeypatch.setattr(CP, '_run', fake_run)
    written, errors, count = CP.compile_files(files, out, 'own;headers', workers=2)
    assert (written, set(errors), count) == ({'c', 'd', 'e'}, {'a', 'b'}, 4)
    assert sorted(runs) == [['a', 'c', 'e'], ['b', 'd'], ['c', 'e'], ['d']]
    assert all(given[0].endswith(('0', '1')) and given[1:] == ['own', 'headers'] for given in imports)


def test_source_errors_take_fo4s_wording_where_it_has_one():
    """A missing function, an impossible cast and a new event read as FO4's compiler words them; an unresolved
    name stays in Caprica's words; a message not known to be a source error is None."""
    assert CP.source_error("Unresolved function name 'IsCompleted'!", '') == \
        'IsCompleted is not a function or does not exist'
    assert CP.source_error("Cannot convert from 'FALLOUTNV_GloveScript' to 'Actor'!", '') == \
        'cannot cast a falloutnv_glovescript to a actor, types are incompatible'
    assert CP.source_error(CP.NEW_EVENT, 'Event OnDeath(Actor akKiller)') == \
        'new event ondeath cannot be defined because the script is not flagged as native'
    assert CP.source_error(UNRESOLVED, '') == UNRESOLVED
    assert CP.source_error("Cannot initialize a 'var' value with a 'None'!", '') is None
    assert CP.source_error('Syntax error!', '') is None


def test_only_the_known_header_folders_are_swapped_for_patched_copies(monkeypatch, tmp_path):
    """The known header folders become their safe copies; the scripts' own stay."""
    monkeypatch.setattr(CP, 'safe_headers', lambda folder: tmp_path / f'safe_{folder.name}')
    base = str(CP.HEADER_FOLDERS[1])
    assert CP.caprica_imports(f'{tmp_path / "mine"};{base}') == f'{tmp_path / "mine"};{tmp_path / "safe_Base"}'
