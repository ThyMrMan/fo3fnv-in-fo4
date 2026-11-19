"""FO3/FNV GetLocked on Fallout 4: the polyfill's 0/1/2 lock state, compared as a number.

See: docs/fork/fo4_pipeline.md#getlocked-states
"""

from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV


def _fo4(body: str) -> str:
    """`body` in a GameMode block, converted for Fallout 4."""
    src = f'scn T\nshort x\nbegin GameMode\n{body}end\n'
    return ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'ObjectReference', 'T')


def test_locked_out_and_locked_stay_distinct_values(monkeypatch):
    """CG04's `getLocked == 2` and FNV's `GetLocked == 1` keep their numbers rather than folding into IsLocked()."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    out = _fo4('  if CG04OverseersTerminalREF.getLocked == 2\n    set x to 1\n  endif\n'
               '  if DoorREF.GetLocked == 1\n    set x to 2\n  endif\n  if GetLocked != 2\n    set x to 3\n  endif\n')
    assert 'TES4Polyfill.LockState(CG04OverseersTerminalREF) == 2' in out
    assert 'TES4Polyfill.LockState(DoorREF) == 1' in out and 'TES4Polyfill.LockState(Self) != 2' in out
    assert 'IsLocked()' not in out
