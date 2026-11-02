"""FNV commands that used to convert to inert `;NE:` markers, now FO4-native calls.

See: docs/fork/script_markers.md#built
"""

import pytest

from script_convert import anim_action_falloutnv as _anim
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph, authored_trigger_blocks
from script_convert.constants import papyrus_script_name
from script_convert.emit import script as _S
from script_convert.tes4 import nodes as N
from script_convert.tes4.parser import Mode, parse


@pytest.fixture
def converter(monkeypatch):
    """A Fallout 4 converter over an empty graph."""
    monkeypatch.setenv('TES4SKYRIM_PAPYRUS_TARGET', 'fallout4')
    return ScriptConverter(CrossRefGraph())


def _lines(conv, source, extends='ObjectReference'):
    """Every Papyrus line one TES4 statement emits, newline-joined."""
    body = [st for st in parse(source, Mode.FRAGMENT).body if not isinstance(st, N.Blank)]
    return '\n'.join(ln.strip() for ln in _S.emit_stmt(conv, body[0], extends, 0))


@pytest.mark.parametrize('source, papyrus', [
    ('BossREF.KillActor', '.Kill()'),
    ('BossREF.ResurrectActor 0', '.Resurrect()'),
    ('ArcadeREF.SetPlayerTeammate 0', '.SetPlayerTeammate(false)'),
    ('ArcadeREF.MoveToMarkerWithFade WaitMarker', 'ArcadeREF.MoveTo(WaitMarker)'),
    ('NeroREF.RemoveFromAllFactions', '.RemoveFromAllFactions()'),
    ('AddFormToFormList GiftList KidREF', 'GiftList.AddForm(KidREF)'),
    ('GateREF.do 50', 'GateREF.DamageObject(50'),
    ('ResetQuest RadioQuest', 'RadioQuest.Reset()'),
])
def test_command_is_a_native_call(converter, source, papyrus):
    """Each command converts to its Papyrus native, with no `;NE:` marker."""
    out = _lines(converter, source)
    assert papyrus in out and ';NE:' not in out


def test_open_teammate_container_opens_the_speakers_inventory(converter):
    """A companion's 'let's trade' line opens that companion's inventory."""
    out = _lines(converter, 'OpenTeammateContainer 1', 'TopicInfo')
    assert '(akSpeakerRef as Actor).OpenInventory(True)' in out


def test_casino_comp_guard_reads_no_winnings(converter):
    """GetCasinoWinningsLevel reads 0, so a comp guard stays false."""
    out = _lines(converter, 'if GetCasinoWinningsLevel GomorrahCasinoData == 1 && SmallFry == 0\nendif')
    assert out.startswith('If 0 == 1 && SmallFry == 0')


def test_permanent_special_reads_the_actor_value(converter):
    """A bobblehead's `< 10` check reads the player's SPECIAL rather than going inert."""
    out = _lines(converter, 'if Player.GetPermanentActorValue Strength < 10\nendif')
    assert 'GetTES4ActorValue(Game.GetPlayer(), "Strength") < 10' in out


def test_weapon_in_list_tests_the_equipped_weapon(converter):
    """IsWeaponInList asks the list for the actor's equipped weapon."""
    out = _lines(converter, 'if VictimREF.IsWeaponInList GasList\nendif')
    assert 'GasList.HasForm(' in out and 'GetEquippedWeapon()' in out


def test_self_cast_to_actor_goes_through_object_reference(converter):
    """FO4 rejects `Self as Actor` in a script extending ObjectReference."""
    assert ScriptConverter._cast('Self', 'Actor') == '((Self as ObjectReference) as Actor)'


@pytest.mark.parametrize('source, papyrus, lists', [
    ('player.RemoveAllTypedItems LockerREF 1 0 40 NVHoldoutWeapons',
     'TES4Polyfill.RemoveAllTypedItems(Game.GetPlayer(), LockerREF, true, false, 40, TES4ItemType40, NVHoldoutWeapons)',
     {'TES4ItemType40', 'NVHoldoutWeapons'}),
    ('LockerREF.RemoveAllTypedItems player 1 1',
     'TES4Polyfill.RemoveAllTypedItems(LockerREF, Game.GetPlayer(), true, true, 0, None, None)', set()),
    ('RemoveAllTypedItems player 0 0 47',
     'TES4Polyfill.RemoveAllTypedItems(Self, Game.GetPlayer(), false, false, 47, TES4ItemType47, None)',
     {'TES4ItemType47'}),
])
def test_remove_all_typed_items_moves_the_type_list(converter, source, papyrus, lists):
    """RemoveAllTypedItems moves its type code's list, keeping the except list."""
    out = _lines(converter, source)
    assert out == papyrus
    assert {p for p, kind in converter.sc.property_refs.items() if kind == 'FormList'} == lists


def test_remove_all_typed_items_unknown_type_stays_a_marker(converter):
    """A type code with no inventory list stays a note."""
    out = _lines(converter, 'player.RemoveAllTypedItems LockerREF 1 0 99')
    assert out.startswith(';NE: player.RemoveAllTypedItems') and 'TES4Polyfill' not in out


@pytest.mark.parametrize('source, papyrus', [
    ('if GetAnimAction == 2 && Cloaked == 1\nendif', 'If TES4_AnimAction(Self) == 2 && Cloaked == 1'),
    ('if Owner.GetAnimAction == 2 && Firing == 0\nendif', 'If TES4_AnimAction(Owner) == 2 && Firing == 0'),
])
def test_anim_action_reads_the_attack_listener(converter, source, papyrus):
    """GetAnimAction reads, and asks for, the attack listener on its actor."""
    assert _lines(converter, source, 'Actor').startswith(papyrus)
    assert converter.sc.uses_anim_action


def test_anim_action_listener_hears_attack_events(converter):
    """The listener registers for the attack events and holds 2 from a start to a stop."""
    converter.sc.uses_anim_action = True
    merged, order = {}, []
    declared = '\n'.join(_anim.listen(converter, merged, order))
    heard = '\n'.join(merged[order[0]])
    assert order[0][0].startswith('Event OnAnimationEvent(')
    assert 'RegisterForAnimationEvent(akRef, "HitFrame")' in declared and 'Int Function TES4_AnimAction(' in declared
    assert 'TES4_AnimAct = 2' in heard and '"attackStop"' in heard and '"readyState"' in heard
    assert '"attackState"' not in heard + declared
    assert f'now - TES4_AnimStartedAt >= {_anim.ATTACK_SECONDS}' in declared


def test_anim_action_stays_inert_off_fallout4(monkeypatch):
    """Skyrim has no attack events to listen for: the read stays the inert 0."""
    monkeypatch.setenv('TES4SKYRIM_PAPYRUS_TARGET', 'skyrim')
    conv = ScriptConverter(CrossRefGraph())
    assert 'TES4_AnimAction' not in _lines(conv, 'if GetAnimAction == 2 && Cloaked == 1\nendif', 'Actor')
    assert not conv.sc.uses_anim_action


@pytest.mark.parametrize('source, extends, papyrus', [
    ('refvar.SetForceSneak 1', 'Actor', 'refvar.StartSneaking()'),
    ('SetForceSneak 1', 'Actor', 'StartSneaking()'),
])
def test_force_sneak_on_starts_sneaking(converter, source, extends, papyrus):
    """SetForceSneak 1 starts the actor's sneak with FO4's native."""
    assert _lines(converter, source, extends).endswith(papyrus)


def test_force_sneak_off_stays_a_marker(converter):
    """FO4 has no native that ends a sneak: SetForceSneak 0 stays a note."""
    assert _lines(converter, 'refvar.SetForceSneak 0', 'Actor').startswith(';NE: ')


def _trigger_graph(sctx: str) -> CrossRefGraph:
    """A graph with `CodeBoxREF` placed from a base carrying script `CodeBoxScript` of source `sctx`."""
    xref = CrossRefGraph()
    xref.trigger_blocks = {'codeboxscript': authored_trigger_blocks(sctx)}
    xref.script_formid_to_edid['00000A01'] = 'CodeBoxScript'
    xref.edid_to_formid['codeboxref'] = '00000B01'
    xref.record_base['00000B01'] = '00000C01'
    xref.record_scri['00000C01'] = '00000A01'
    return xref


def test_enter_trigger_calls_the_scripts_entry_event(monkeypatch):
    """EnterTrigger runs the trigger script's own OnTriggerEnter (escaped SCTX, as exported)."""
    monkeypatch.setenv('TES4SKYRIM_PAPYRUS_TARGET', 'fallout4')
    conv = ScriptConverter(_trigger_graph(r'scn CodeBoxScript\r\nbegin OnTriggerEnter player\r\nend'))
    out = _lines(conv, 'CodeBoxREF.EnterTrigger Player')
    assert f'(CodeBoxREF as {papyrus_script_name("CodeBoxScript")}).OnTriggerEnter(' in out


def test_enter_trigger_leaves_an_ontrigger_script_inert(monkeypatch):
    """An OnTrigger body waits on a leave event a forced entry never sends, so it stays a marker."""
    monkeypatch.setenv('TES4SKYRIM_PAPYRUS_TARGET', 'fallout4')
    conv = ScriptConverter(_trigger_graph(r'scn CodeBoxScript\r\nbegin OnTrigger player\r\nend'))
    out = _lines(conv, 'CodeBoxREF.EnterTrigger Player')
    assert 'OnTriggerEnter(' not in out and ';NE: TODO: CodeBoxREF.EnterTrigger' in out
