"""The Fallout 4 helper set: the source rules, block overrides, and the stale-override guard.

See: docs/fork/fo4_spikes.md#spike-3-helpers
"""

import pytest

from script_convert import helpers_fallout4 as H

SHARED = '\n'.join([
    'ScriptName T extends Quest',
    'Function Keep()',
    '  Float v = GetActorValue("Variable09")',
    'EndFunction',
    'Event OnUpdate()',
    '  RegisterForSingleUpdate(0.5)',
    'EndEvent',
    'Function Long()',
    '  Return',
    'EndFunction',
    'Function Tail()',
    'EndFunction',
])


def _override(tmp_path, monkeypatch, text: str) -> None:
    """Point the module at a temporary overrides folder holding T.psc."""
    (tmp_path / 'T.psc').write_text(text, encoding='utf-8')
    monkeypatch.setattr(H, 'OVERRIDES_DIR', str(tmp_path))


def test_rules_rewrite_actor_values_and_the_update_loop_line_for_line():
    """Actor values go through TES4Polyfill.AV, the poll is a timer, and line counts hold."""
    out = H.apply_rules(SHARED)
    assert 'GetValue(TES4Polyfill.AV("Variable09"))' in out
    assert 'Event OnTimer(int aiTimerID)' in out and 'StartTimer(0.5)' in out
    assert len(out.splitlines()) == len(SHARED.splitlines())


def test_override_replaces_a_longer_block_without_shifting_later_ones(tmp_path, monkeypatch):
    """A block that grows must not move the blocks after it; a new block is appended."""
    lines = SHARED.splitlines()
    sha = H.block_hash(lines, H.blocks(lines)['long'])
    _override(tmp_path, monkeypatch, '\n'.join([
        f'; fallout4: replaces Long {sha}', 'Function Long()', '  A()', '  B()', 'EndFunction', '',
        '; fallout4: new', 'Function Added()', 'EndFunction']))
    out = H.fallout4_helper('T', SHARED).splitlines()
    assert out[7:12] == ['Function Long()', '  A()', '  B()', 'EndFunction', 'Function Tail()']
    assert out[-2:] == ['Function Added()', 'EndFunction']


def test_an_edited_shared_block_stops_the_run(tmp_path, monkeypatch):
    """The override was made for another version of the block: StaleOverride names it."""
    _override(tmp_path, monkeypatch, '\n'.join([
        '; fallout4: replaces Long ' + '0' * 40, 'Function Long()', 'EndFunction']))
    with pytest.raises(H.StaleOverride, match=r'T\.Long'):
        H.fallout4_helper('T', SHARED)


def test_an_unused_function_is_dropped_with_its_comment(tmp_path, monkeypatch):
    """A `Script.Function` in FALLOUT4_UNUSED_HELPERS leaves the script with the comment above it."""
    _override(tmp_path, monkeypatch, '')
    monkeypatch.setattr(H, 'FALLOUT4_UNUSED_HELPERS', frozenset({'T.Long', 'Other.Tail'}))
    shared = SHARED.replace('Function Long()', '; about Long\nFunction Long()')
    out = H.fallout4_helper('T', shared).splitlines()
    assert 'Function Long()' not in out and '; about Long' not in out
    assert out[7:9] == ['Function Tail()', 'EndFunction']


def test_an_unused_entry_naming_no_block_stops_the_run(tmp_path, monkeypatch):
    """A listed function the shared script no longer has: StaleOverride names it."""
    _override(tmp_path, monkeypatch, '')
    monkeypatch.setattr(H, 'FALLOUT4_UNUSED_HELPERS', frozenset({'T.Gone'}))
    with pytest.raises(H.StaleOverride, match=r'T\.Gone'):
        H.fallout4_helper('T', SHARED)


def test_every_shipped_override_matches_its_shared_block():
    """The real overrides apply to the real shared scripts (none is stale)."""
    for script in ('TES4Polyfill', 'TES4_StagePackageAlias'):
        with open(f'script_convert/static_scripts/{script}.psc', encoding='utf-8') as src:
            assert H.fallout4_helper(script, src.read())
