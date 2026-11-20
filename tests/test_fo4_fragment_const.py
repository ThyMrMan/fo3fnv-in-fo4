"""Fragment scripts declare their form properties Auto Const on Fallout 4, as vanilla's do (symbols.form_property).

See: docs/fork/fo4_pipeline.md#const-properties
"""

from script_convert.symbols import form_property, property_declarations
from script_convert.target import FALLOUT4, SKYRIM, TARGET_ENV


def test_fallout4_fragment_forms_are_const_and_values_are_not(monkeypatch):
    """On Fallout 4 a form property is Const (a quest restart resets a plain Auto one to None); a value is not."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    assert property_declarations({'MS03': 'Quest', 'MS03DreamCrusherPerk': 'Perk'}, set()) == [
        'Quest Property MS03 Auto Const', 'Perk Property MS03DreamCrusherPerk Auto Const']
    assert form_property('GlobalVariable', 'TES4Karma') == 'GlobalVariable Property TES4Karma Auto Const'
    assert form_property('Int', 'Count') == 'Int Property Count Auto'


def test_skyrim_keeps_plain_auto(monkeypatch):
    """The Skyrim target is unchanged."""
    monkeypatch.setenv(TARGET_ENV, SKYRIM)
    assert property_declarations({'MS03': 'Quest'}, set()) == ['Quest Property MS03 Auto']
