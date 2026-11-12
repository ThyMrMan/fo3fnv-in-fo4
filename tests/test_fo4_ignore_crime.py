"""FO3/FNV IgnoreCrime and SetInCharGen on Fallout 4: the converted calls and the helper quest they keep state in.

See: docs/fork/fo4_plan_script_functions.md#ignore-crime
"""

import re
from pathlib import Path

from script_convert.constants import FALLOUT4_HELPER_PLUGIN, FALLOUT4_HELPER_QUESTS
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV

POLYFILL = Path(__file__).resolve().parents[1] / 'script_convert/static_scripts/fallout4/overrides/TES4Polyfill.psc'


def _fo4(src: str, extends: str = 'Quest') -> str:
    """`src` converted for Fallout 4 as a standalone script extending `extends`."""
    return ScriptConverter(CrossRefGraph()).convert_standalone('T', src, extends, 'T')


def test_the_polyfill_reads_the_state_quest_the_helper_plugin_holds():
    """SourceState() names F3NV_State's helper id and plugin."""
    found = re.search(r'GetFormFromFile\((0x[0-9A-Fa-f]+), "([^"]+)"\) as F3NV_State', POLYFILL.read_text())
    assert int(found[1], 16) == FALLOUT4_HELPER_QUESTS['F3NV_State'] == 0x903 and found[2] == FALLOUT4_HELPER_PLUGIN


def test_butch_ignores_crime_and_a_saved_flag_is_restored(monkeypatch):
    """CG03's `ButchREF.IgnoreCrime 1`, and MS13's saved flag read back and restored, convert with no TODO."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    out = _fo4('scn T\nshort Was\nbegin GameMode\n  ButchREF.IgnoreCrime 1\n  set Was to GetIgnoreCrime\n'
               '  IgnoreCrime Was\nend\n', 'Actor')
    assert 'TES4Polyfill.IgnoreCrime(ButchREF' in out and ', true)' in out
    assert 'Was = TES4Polyfill.GetIgnoreCrime(Self)' in out and 'TES4Polyfill.IgnoreCrime(Self, Was as Bool)' in out
    assert 'TODO' not in out and ';NE:' not in out


def test_set_in_char_gen_is_remembered(monkeypatch):
    """CG04's `SetInCharGen 0` and a GetInCharGen read convert to the polyfill's remembered flag."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    out = _fo4('scn T\nshort x\nbegin GameMode\n  SetInCharGen 0\n  set x to GetInCharGen\nend\n')
    assert 'TES4Polyfill.SetInCharGen(false)' in out and 'x = TES4Polyfill.GetInCharGen()' in out
    assert ';NE:' not in out
