"""FNV GetCurrentAIProcedure on Fallout 4: the polyfill's reading, the helper quest it reads, the converted guard.

See: docs/fork/fo4_pipeline.md#ai-procedure
"""

import re
from pathlib import Path

from script_convert.constants import FALLOUT4_HELPER_PLUGIN, FALLOUT4_HELPER_QUESTS
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV

POLYFILL = Path(__file__).resolve().parents[1] / 'script_convert/static_scripts/fallout4/overrides/TES4Polyfill.psc'


def test_the_polyfill_reads_the_helper_quest_the_helper_plugin_holds():
    """PackageState() names the helper quest's id and plugin."""
    found = re.search(r'GetFormFromFile\((0x[0-9A-Fa-f]+), "([^"]+)"\) as F3NV_PackageState', POLYFILL.read_text())
    assert int(found[1], 16) == FALLOUT4_HELPER_QUESTS['F3NV_PackageState'] and found[2] == FALLOUT4_HELPER_PLUGIN


def test_the_mantis_reads_its_legs(monkeypatch):
    """`IsLimbGone 3` stays in the guard as the polyfill's dismemberment read, no TODO marker."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    src = 'scn T\nshort Gone\nbegin GameMode\n  if Gone == 0 && IsLimbGone 3\n    set Gone to 1\n  endif\nend\n'
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'Actor', 'T')
    assert 'TES4Polyfill.LimbGone(Self, 3)' in out and 'TODO' not in out


def test_camp_golfs_guard_reads_each_misfits_procedure(monkeypatch):
    """`Ref.GetCurrentAIProcedure == 17` stays in the guard as the polyfill's reading, not a dropped term."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    src = ('scn T\nshort x\nbegin GameMode\n  if (PoindexterREF.GetCurrentAIProcedure == 17) && '
           '(RazzREF.GetCurrentAIProcedure == 17)\n    set x to 2\n  endif\nend\n')
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'Quest', 'T')
    assert out.count('TES4Polyfill.AIProcedure(') == 2 and ';NE:' not in out
