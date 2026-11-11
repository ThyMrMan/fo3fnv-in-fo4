"""The Fallout 4 corpus compile gate: error kinds, the summary, and the baseline comparison.

See: docs/fork/fo4_spikes.md#spike-3-gate
"""

import json
from pathlib import Path
from types import SimpleNamespace

from tools.script import compile_papyrus as CP


def test_error_kind_folds_converted_names_and_numbers_but_keeps_natives():
    """Two scripts missing the same native are one kind; the native's name stays."""
    a = CP.fo4_key('cannot cast a tes4_generickillscript to a actor, types are incompatible')
    b = CP.fo4_key('cannot cast a falloutnv_vms03script to a actor, types are incompatible')
    assert a == b == 'cannot cast a <script> to a actor, types are incompatible'
    assert CP.fo4_key('SendModEvent is not a function or does not exist').startswith('SendModEvent')
    assert CP.fo4_key('type mismatch on parameter 1') == 'type mismatch on parameter N'


def test_summary_counts_each_kind_once_per_file_and_splits_dependency_failures():
    """A file failing with no errors of its own failed through a script it uses."""
    own = {'A': ['X is not a function or does not exist', 'X is not a function or does not exist'],
           'B': ['X is not a function or does not exist'], 'Helper': ['Y is not a function or does not exist']}
    summary = CP.fo4_summary({'d'}, own, ['A', 'B', 'C', 'D'])
    assert (summary['files'], summary['compiled'], summary['own_errors'], summary['dependency_only']) == (4, 1, 2, 1)
    assert summary['kinds'] == {'X is not a function or does not exist': 2}


def test_gate_fails_on_more_failures_or_a_grown_or_new_kind(tmp_path):
    """Equal is fine; one more failing file, a grown kind or a new kind is worse."""
    base = {'files': 10, 'compiled': 8, 'kinds': {'K': 2}}
    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps(base), encoding='utf-8')
    assert CP.gate(dict(base), path) == []
    assert CP.gate(dict(base, compiled=7, kinds={'K': 3, 'New': 1}), path) == [
        'failing files 2 -> 3', '2 -> 3  K', '0 -> 1  New']


def _corpus(tmp_path, sources: dict) -> tuple:
    """(hashes, declarations, users index) of `sources` written as .psc files."""
    files = []
    for name, text in sources.items():
        (tmp_path / f'{name}.psc').write_text(text, encoding='utf-8')
        files.append(tmp_path / f'{name}.psc')
    hashes, words = CP.source_hashes(files), CP.source_words(files)
    return hashes, CP.source_declarations(files), CP.users_index(words, set(hashes)), words


CORPUS = {'Helper': 'ScriptName Helper\nInt Function Get(Int a = 1)\n  Return a\nEndFunction',
          'Mid': 'ScriptName Mid\nHelper Property H Auto', 'Top': 'ScriptName Top\nMid Property M Auto',
          'Alone': 'ScriptName Alone'}


def test_users_recompile_only_when_a_declaration_is_lost_or_changed(tmp_path):
    """A body edit, an added function or a signature no user names recompiles the helper alone; a changed header
    pulls in every user, transitively."""
    hashes, apis, users, words = _corpus(tmp_path, CORPUS)
    state = {n: {'sha': sha, 'api': apis[n], 'ok': True} for n, sha in hashes.items()}
    assert CP.needs_compile(hashes, apis, state, users, words) == set()
    body = dict(CORPUS, Helper=CORPUS['Helper'].replace('Return a', 'Return a + 1') + '\nFunction New()\nEndFunction')
    hashes, apis, users, words = _corpus(tmp_path, body)
    assert CP.needs_compile(hashes, apis, state, users, words) == {'helper'}
    hashes, apis, users, words = _corpus(tmp_path, dict(CORPUS, Helper=CORPUS['Helper'].replace('a = 1', 'a = 2')))
    assert CP.needs_compile(hashes, apis, state, users, words) == {'helper'}
    header = dict(CORPUS, Helper=CORPUS['Helper'].replace('ScriptName Helper', 'ScriptName Helper extends Quest'))
    hashes, apis, users, words = _corpus(tmp_path, header)
    assert CP.needs_compile(hashes, apis, state, users, words) == {'helper', 'mid', 'top'}
    assert CP.needs_compile(hashes, apis, {}, users, words) == set(hashes)


def test_an_added_declaration_recompiles_failing_users(tmp_path):
    """A user that failed (perhaps on the missing function) recompiles when the helper gains one."""
    hashes, apis, users, words = _corpus(tmp_path, CORPUS)
    state = {n: {'sha': sha, 'api': apis[n], 'ok': n != 'mid'} for n, sha in hashes.items()}
    hashes, apis, users, words = _corpus(tmp_path, dict(CORPUS, Helper=CORPUS['Helper'] + '\nFunction New()\nEndFunction'))
    assert CP.needs_compile(hashes, apis, state, users, words) == {'helper', 'mid'}


def test_a_failure_with_no_error_of_its_own_is_retried(tmp_path):
    """A script that failed without an error of its own (the compiler ran out of memory) compiles again on the
    next run, unchanged; one that failed on its own errors waits for a change."""
    hashes, apis, users, words = _corpus(tmp_path, CORPUS)
    state = {n: {'sha': sha, 'api': apis[n], 'ok': True} for n, sha in hashes.items()}
    state['mid'] = dict(state['mid'], ok=False, own=[])
    state['alone'] = dict(state['alone'], ok=False, own=['X is not a function or does not exist'])
    assert CP.needs_compile(hashes, apis, state, users, words) == {'mid'}


def test_declarations_join_continued_lines_and_keep_struct_members():
    """Signatures (continued over lines), properties and struct members; bodies and comments are not."""
    text = ('ScriptName S extends Quest ; note\nStruct Pair\n  Int A = 1\nEndStruct\n'
            'Int Function F(Int a, \\\n  Int b = 2) Global\n  Int local = 3\nEndFunction\nInt Property P = 4 Auto')
    assert CP.declarations(text) == ['endstruct', 'int a = 1', 'int function f(int a, int b = 2) global',
                                     'int property p = 4 auto', 'scriptname s extends quest', 'struct pair']


def test_a_lost_function_recompiles_only_users_naming_it(tmp_path):
    """Removing Get from the helper recompiles a user calling it, not one that only holds the helper."""
    sources = dict(CORPUS, Caller='ScriptName Caller\nHelper Property H Auto\nInt Function F()\n  Return H.Get()\n'
                                  'EndFunction')
    hashes, apis, users, words = _corpus(tmp_path, sources)
    state = {n: {'sha': sha, 'api': apis[n], 'ok': True} for n, sha in hashes.items()}
    gone = CORPUS['Helper'].replace('Int Function Get(Int a = 1)\n  Return a\nEndFunction', '')
    hashes, apis, users, words = _corpus(tmp_path, dict(sources, Helper=gone))
    assert CP.needs_compile(hashes, apis, state, users, words) == {'helper', 'caller'}


def _build(tmp_path, monkeypatch, sources: dict, caprica=None) -> tuple:
    """(compile_fallout4's args for a `sources` folder against a header folder holding Shared.psc, [(names FO4's
    compiler was given, its import folders)]). `caprica` stands in for Caprica's compile_files (None: no Caprica);
    the memos go under tmp_path."""
    head, src, out = tmp_path / 'head', tmp_path / 'src', tmp_path / 'out'
    for folder in (head, src, out):
        folder.mkdir()
    (head / 'Shared.psc').write_text('ScriptName Shared ; the master', encoding='utf-8')
    for name, text in sources.items():
        (src / f'{name}.psc').write_text(text, encoding='utf-8')
    batches = []

    def compile_folder(folder, out_dir, imports):
        """Every script of the batch compiles."""
        batches.append((sorted(p.stem for p in folder.glob('*.psc')), imports.split(';')))
        for psc in folder.glob('*.psc'):
            (out_dir / f'{psc.stem}.pex').write_bytes(b'pex')
        return ''
    monkeypatch.setattr(CP, 'compile_folder', compile_folder)
    monkeypatch.setattr(CP, '_STAMPS_CACHE', tmp_path / 'stamps')
    monkeypatch.setattr(CP, '_HEADER_MEMOS', tmp_path / 'stamps' / 'headers')
    monkeypatch.setattr(CP.caprica, 'available', lambda: caprica is not None)
    monkeypatch.setattr(CP.caprica, 'compile_files', caprica)
    return SimpleNamespace(src=str(src), out=str(out), headers=str(head), full=False, workers=1), batches


OVERRIDE = {'Shared': 'ScriptName Shared ; the mod', 'User': 'ScriptName User\nShared Property S Auto',
            'Alone': 'ScriptName Alone'}


def test_a_scripts_own_source_comes_before_a_masters_of_the_same_name(tmp_path, monkeypatch):
    """Both compilers get the scripts' own folder first in the import list, ahead of the master's folder holding
    a script of the same name."""
    given = []

    def caprica(files, out_dir, imports, workers):
        """Record the import list; compile nothing."""
        given.append(imports.split(';'))
        return set(), {}, 1
    args, batches = _build(tmp_path, monkeypatch, OVERRIDE, caprica)
    CP.compile_fallout4(args)
    own, master = str((tmp_path / 'src').resolve()), str(tmp_path / 'head')
    assert given == [[own, master]] and batches[0][1] == [own, master]


def test_results_saved_before_the_alias_check_are_all_compiled_again(tmp_path, monkeypatch):
    """A compile_state.json without the alias check's mark keeps no results, so every script compiles once more;
    the next run compiles nothing."""
    args, batches = _build(tmp_path, monkeypatch, OVERRIDE)
    CP.compile_fallout4(args)
    path = tmp_path / 'out' / 'compile_state.json'
    state = json.loads(path.read_text(encoding='utf-8'))
    assert state['imports'] == f"{tmp_path / 'head'};{(tmp_path / 'src').resolve()}" and state.pop(CP.CHECKED)
    path.write_text(json.dumps(state), encoding='utf-8')
    del batches[:]
    CP.compile_fallout4(args)
    assert sorted(name for names, _ in batches for name in names) == ['Alone', 'Shared', 'User']
    del batches[:]
    CP.compile_fallout4(args)
    assert batches == []


def test_capricas_source_error_is_kept_and_not_sent_to_fo4s_compiler(tmp_path, monkeypatch):
    """Caprica compiles Alone, reports Shared's own error and gets nowhere with User (a crash): only User goes to
    FO4's compiler, Shared's error is its recorded result, and the next run compiles nothing."""
    error = "Unresolved identifier 'nGone'!"

    def caprica(files, out_dir, imports, workers):
        """Alone compiles, Shared has a source error, User is in neither result."""
        (out_dir / 'alone.pex').write_bytes(b'pex')
        return {'alone'}, {'shared': [error]}, 3
    args, batches = _build(tmp_path, monkeypatch, OVERRIDE, caprica)
    compiled, own, _names = CP.compile_fallout4(args)
    assert [names for names, _ in batches] == [['User']]
    assert compiled == {'alone', 'user'} and own == {'Shared': [error]}
    assert CP.fo4_summary(compiled, own, list(OVERRIDE))['kinds'] == {error: 1}
    del batches[:]
    monkeypatch.setattr(CP.caprica, 'compile_files', lambda *a: (set(), {}, 0))
    assert CP.compile_fallout4(args)[1] == {'Shared': [error]} and batches == []


def test_header_hashes_are_kept_per_header_folder_for_every_output_folder(tmp_path, monkeypatch):
    """A second plugin (another output folder) importing the same header folder reads none of its files: the
    memo is the header folder's, not the output folder's."""
    args, _batches = _build(tmp_path, monkeypatch, OVERRIDE)
    read, plain = [], Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda path: read.append(path.parent.name) or plain(path))
    CP.compile_fallout4(args)
    assert read.count('head') == 1
    del read[:]
    (tmp_path / 'out2').mkdir()
    CP.compile_fallout4(SimpleNamespace(**{**vars(args), 'out': str(tmp_path / 'out2')}))
    assert 'head' not in read and 'src' in read
    assert [p.suffix for p in (tmp_path / 'stamps' / 'headers').iterdir()] == ['.json']


def test_a_compiled_script_whose_pex_is_gone_compiles_again(tmp_path):
    """A stopped run deleted a .pex its saved results still call compiled; failures and present .pex stay."""
    (tmp_path / 'kept.pex').write_bytes(b'')
    (tmp_path / '_chunks' / '0').mkdir(parents=True)
    state = {'kept': {'ok': True}, 'gone': {'ok': True}, 'failed': {'ok': False}}
    assert CP.missing_pex(state, tmp_path) == {'gone'} and not (tmp_path / '_chunks').exists()
