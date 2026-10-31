"""Caprica ahead of FO4's compiler: the header patches and the drop-and-retry loop.

See: docs/fork/fo4_pipeline.md#caprica
"""

from fo4_import.base import caprica as CP


def test_the_header_patches_fix_what_capricas_parser_rejects():
    """Leading whitespace goes, a struct member named parent is renamed, a Var parameter loses its None default;
    other text is unchanged."""
    text = ' Scriptname X extends Y\nstruct ConnectPoint\n\tstring parent\n\tstring name\nendstruct\n' \
           'Function F(Var filter = None) native\nint parentCount\n'
    out = CP._patched(text)
    assert out.startswith('Scriptname X')
    assert '\tstring parentNode\n' in out and '\tstring name\n' in out and 'int parentCount' in out
    assert 'Function F(Var filter) native' in out


def test_a_failing_script_is_dropped_and_the_rest_compiled_again(tmp_path, monkeypatch):
    """Caprica stops at b (failing); its next run writes c; what never compiles is not reported written."""
    src, out = tmp_path / 'src', tmp_path / 'out'
    src.mkdir()
    out.mkdir()
    files = []
    for name in ('a', 'b', 'c'):
        files.append(src / f'{name}.psc')
        files[-1].write_text(f'Scriptname {name}\n')
    runs = []

    def fake_run(folder, out_dir, imports):
        """Compile in name order, stopping at b."""
        runs.append(sorted(p.stem for p in folder.glob('*.psc')))
        for path in sorted(folder.glob('*.psc')):
            if path.stem == 'b':
                return "b.psc (1, 1:2): Error: nope\nCompilation of 'b.psc' failed; 0 warnings and 1 errors"
            (out_dir / f'{path.stem}.pex').write_bytes(b'pex')
        return ''
    monkeypatch.setattr(CP, '_run', fake_run)
    monkeypatch.setattr(CP, 'caprica_imports', lambda imports: imports)
    assert CP.compile_files(files, out, 'headers') == {'a', 'c'}
    assert runs == [['a', 'b', 'c'], ['c']] and not (out / '_caprica').exists()


def test_a_failure_naming_no_script_of_the_batch_ends_the_runs(tmp_path, monkeypatch):
    """A header Caprica cannot read fails every run the same way: one run, nothing written."""
    src, out = tmp_path / 'src', tmp_path / 'out'
    src.mkdir()
    out.mkdir()
    (src / 'a.psc').write_text('Scriptname a\n')
    runs = []
    monkeypatch.setattr(CP, '_run', lambda folder, out_dir, imports: runs.append(1) or
                        'ObjectReference.psc (1212, 9:15): Fatal Error: Syntax error!')
    monkeypatch.setattr(CP, 'caprica_imports', lambda imports: imports)
    assert CP.compile_files([src / 'a.psc'], out, 'headers') == set() and len(runs) == 1


def test_only_the_known_header_folders_are_swapped_for_patched_copies(monkeypatch, tmp_path):
    """The F4SE/Base/LevelUpMenuEx entries become their safe copies; the scripts' own folders stay."""
    monkeypatch.setattr(CP, 'safe_headers', lambda folder: tmp_path / f'safe_{folder.name}')
    base = str(CP.HEADER_FOLDERS[1])
    assert CP.caprica_imports(f'{tmp_path / "mine"};{base}') == f'{tmp_path / "mine"};{tmp_path / "safe_Base"}'
