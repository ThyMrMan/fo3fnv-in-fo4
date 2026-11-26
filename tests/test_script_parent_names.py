"""Converted names that collide with Fallout 4's native parents, and GetIsReference's typed comparison.

See: docs/commentary/script_convert.md#getisreference-not-an-actor-test
"""

from script_convert.command_rows import COMMAND_ROWS
from script_convert.constants import safe_property_name, source_name
from script_convert.target import FALLOUT4, SKYRIM, TARGET_ENV


def test_a_variable_named_for_a_parent_property_is_renamed_on_fallout4_only(monkeypatch):
    """ObjectReference's X/Y/Z: `x` becomes myX for Fallout 4; Skyrim's ObjectReference has none, so it stays."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    assert [safe_property_name(n) for n in ('x', 'Y', 'Motion_Fixed', 'xPos')] == ['myX', 'myY', 'myMotion_Fixed',
                                                                                 'xPos']
    monkeypatch.setenv(TARGET_ENV, SKYRIM)
    assert safe_property_name('x') == 'x'


def test_the_fo4_build_names_variables_as_the_scripts_do(monkeypatch):
    """With no target set, fallout4=True still renames x and maps it back."""
    monkeypatch.delenv(TARGET_ENV, raising=False)
    assert safe_property_name('x', fallout4=True) == 'myX' and source_name('myX', fallout4=True) == 'X'
    assert source_name('myX') == 'myX'


def test_get_is_reference_compares_as_object_references():
    """Self and another script's type compare as ObjectReferences."""
    assert COMMAND_ROWS['getisreference'].emit.startswith('({ref} as ObjectReference) == ')
    assert COMMAND_ROWS['getisref'].emit.startswith('({ref} as ObjectReference) == ')
