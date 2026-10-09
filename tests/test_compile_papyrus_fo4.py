"""The Fallout 4 corpus compile gate: error kinds, the summary, and the baseline comparison.

See: docs/fork/fo4_spikes.md#spike-3-gate
"""

import json

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
    hashes = CP.source_hashes(files)
    return hashes, CP.source_declarations(files), CP.users_index(files, set(hashes))


CORPUS = {'Helper': 'ScriptName Helper\nInt Function Get(Int a = 1)\n  Return a\nEndFunction',
          'Mid': 'ScriptName Mid\nHelper Property H Auto', 'Top': 'ScriptName Top\nMid Property M Auto',
          'Alone': 'ScriptName Alone'}


def test_users_recompile_only_when_a_declaration_is_lost_or_changed(tmp_path):
    """A body edit or an added function recompiles the helper alone; a changed signature pulls in its users."""
    hashes, apis, users = _corpus(tmp_path, CORPUS)
    state = {n: {'sha': sha, 'api': apis[n], 'ok': True} for n, sha in hashes.items()}
    assert CP.needs_compile(hashes, apis, state, users) == set()
    body = dict(CORPUS, Helper=CORPUS['Helper'].replace('Return a', 'Return a + 1') + '\nFunction New()\nEndFunction')
    hashes, apis, users = _corpus(tmp_path, body)
    assert CP.needs_compile(hashes, apis, state, users) == {'helper'}
    hashes, apis, users = _corpus(tmp_path, dict(CORPUS, Helper=CORPUS['Helper'].replace('a = 1', 'a = 2')))
    assert CP.needs_compile(hashes, apis, state, users) == {'helper', 'mid', 'top'}
    assert CP.needs_compile(hashes, apis, {}, users) == set(hashes)


def test_an_added_declaration_recompiles_failing_users(tmp_path):
    """A user that failed (perhaps on the missing function) recompiles when the helper gains one."""
    hashes, apis, users = _corpus(tmp_path, CORPUS)
    state = {n: {'sha': sha, 'api': apis[n], 'ok': n != 'mid'} for n, sha in hashes.items()}
    hashes, apis, users = _corpus(tmp_path, dict(CORPUS, Helper=CORPUS['Helper'] + '\nFunction New()\nEndFunction'))
    assert CP.needs_compile(hashes, apis, state, users) == {'helper', 'mid'}


def test_declarations_join_continued_lines_and_keep_struct_members():
    """Signatures (continued over lines), properties and struct members; bodies and comments are not."""
    text = ('ScriptName S extends Quest ; note\nStruct Pair\n  Int A = 1\nEndStruct\n'
            'Int Function F(Int a, \\\n  Int b = 2) Global\n  Int local = 3\nEndFunction\nInt Property P = 4 Auto')
    assert CP.declarations(text) == ['endstruct', 'int a = 1', 'int function f(int a, int b = 2) global',
                                     'int property p = 4 auto', 'scriptname s extends quest', 'struct pair']
