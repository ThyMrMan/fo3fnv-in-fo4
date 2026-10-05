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
