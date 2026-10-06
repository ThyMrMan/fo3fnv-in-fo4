"""The duplicate script name guard: a name written twice with different text stops the run.

See: docs/fork/fo4_spikes.md#spike-3-names
"""

import pytest

from script_convert.pipeline import DuplicateScriptName, refuse_duplicate_names


def test_one_write_per_name_passes():
    """Distinct names never trip the guard."""
    refuse_duplicate_names(['A', 'B'], [('A', 'SrcA', '1'), ('B', 'SrcB', '2')])


def test_the_same_text_twice_is_harmless():
    """A name rewritten with identical text replaced nothing."""
    refuse_duplicate_names(['A', 'a'], [('A', 'SrcA', '1'), ('a', 'SrcA', '1')])


def test_different_text_under_one_name_names_both_sources():
    """Case-insensitive, as Papyrus names are; the message names each source."""
    with pytest.raises(DuplicateScriptName, match='SrcA / SrcB'):
        refuse_duplicate_names(['A', 'a'], [('A', 'SrcA', '1'), ('a', 'SrcB', '2')])


def test_a_converted_script_named_like_a_static_helper_is_refused():
    """A static helper has no recorded origin, so sharing its name counts as different."""
    with pytest.raises(DuplicateScriptName, match='tes4polyfill'):
        refuse_duplicate_names(['TES4Polyfill', 'TES4Polyfill'], [('TES4Polyfill', 'SomeScript', '1')])
