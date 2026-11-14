"""FO3/FNV StartCombat player on Fallout 4: the attacker's allies join, as FNV's combat group does.

See: docs/fork/fo4_pipeline.md#allies-join
"""

import re
from pathlib import Path

POLYFILL = Path(__file__).resolve().parents[1] / 'script_convert/static_scripts/fallout4/overrides/TES4Polyfill.psc'


def _function(name: str) -> str:
    """The body of polyfill override function `name`, header to EndFunction."""
    found = re.search(rf'(?ms)^(?:\S+ )?Function {name}\(.*?^EndFunction', POLYFILL.read_text())
    assert found, name
    return found[0]


def test_only_a_fight_on_the_player_rallies_and_never_blocks_the_caller():
    """ForceCombatNow queues RallyAllies after StartCombat, for a player target only, without waiting on it."""
    body = _function('ForceCombatNow')
    rally = body.index('CallGlobalFunctionNoWait("TES4Polyfill", "RallyAllies", args)')
    assert body.index('akAttacker.StartCombat(akTarget)') < rally
    assert body.rindex('If akTarget == player', 0, rally) > body.index('akAttacker.StartCombat(akTarget)')


def test_a_helper_joins_hating_the_player_as_the_attacker_does():
    """Each helper RallyAllies finds is put in _PlayerEnemyFaction before its StartCombat on the player."""
    body = _function('RallyAllies')
    assert '_Assists(a, akAttacker, akPlayer, assistance)' in body
    assert body.index('a.AddToFaction(hatesPlayer)') < body.index('a.StartCombat(akPlayer)')
    assert 'TES4Polyfill.AV("Assistance")' in body and 'akAttacker.FindAllReferencesWithKeyword(' in body


def test_assists_follows_fnv_assistance_tiers():
    """Ally (2) needs Assistance 1, Friend (3) needs 2; a friend of the player, a teammate or a fighter stays out."""
    body = _function('_Assists')
    assert 'reaction < 2 || akHelper.GetValue(akAssistance) < reaction - 1' in body
    assert 'akHelper.GetFactionReaction(akPlayer) >= 2' in body
    assert all(gate in body for gate in ('IsDead()', 'IsInCombat()', 'IsPlayerTeammate()'))
    assert 'akAttacker.IsDetectedBy(akHelper) || akPlayer.IsDetectedBy(akHelper)' in body


def test_the_nearby_searches_share_one_keyword_table():
    """Both searches walk _ActorTypes: Fallout4.esm's four ActorType keywords."""
    assert all('Int[] types = _ActorTypes()' in _function(f) for f in ('EvaluateNearby', 'RallyAllies'))
    ids = [int(v) for v in re.findall(r'types\[\d\] = (\d+)', _function('_ActorTypes'))]
    assert ids == [0x13794, 0x13795, 0x2CB73, 0x6D7B6]
