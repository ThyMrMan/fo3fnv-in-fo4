"""Fallout 4 conversions that left a DLC script uncompilable (2026-11-04): each converts to Papyrus naming only what
it declares.

See: docs/commentary/script_convert.md#last-activator
"""

import pytest

from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV

#: Dead Money's kitchen back door (NVDLC01KitchenBackDoor02Script): a message box whose MenuMode 1001 activates.
KITCHEN_DOOR = ('Scn T\nShort bUsed\nShort nButton\nBEGIN OnActivate\n  If (IsActionRef Player == 1) && (bUsed == 0)\n'
                '    ShowMessage SomeMsg\n  else\n    Activate\n  Endif\nEND\nBEGIN MenuMode 1001\n'
                '  set nButton to GetButtonPressed\n  if (nButton == 1)\n    Set bUsed to 1\n    Activate\n  endif\nEND\n')


@pytest.fixture
def fallout4(monkeypatch):
    """Emit Fallout 4 Papyrus for the test."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)


def test_a_message_box_activating_declares_and_records_the_last_activator(fallout4):
    """TES4_MessageBoxClosed activates for whoever activated last; OnActivate records it first, and it is declared."""
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', KITCHEN_DOOR, 'ObjectReference', 'T')
    lines = [line.rstrip() for line in out.splitlines()]
    assert 'ObjectReference TES4_LastActivator' in lines
    opener = lines.index('Event OnActivate(ObjectReference akActionRef)')
    assert lines[opener + 1] == '  TES4_LastActivator = akActionRef'
    assert any('Activate(TES4_LastActivator' in line for line in lines[opener + 2:])


def _fallout_conv():
    """A converter whose cross-reference graph reads as FO3/FNV."""
    xref = CrossRefGraph()
    xref.is_fallout = lambda: True
    return ScriptConverter(xref)


def test_broadcast_state_and_the_essential_flag_are_commands(fallout4):
    """Dead Money's radios read and set the station's state through the polyfill (a bare read is a call, not a
    property), and its ghosts test IsEssential."""
    src = ('scn T\nshort x\nbegin OnActivate\n  if (RadioRef.GetBroadcastState == 1)\n    RadioRef.SetBroadcastState 0\n'
           '  endif\n  if IsActorRefEssential\n    set x to 1\n  endif\nend\n')
    out = _fallout_conv().convert_standalone('T', src, 'Actor', 'T')
    assert 'TES4Polyfill.GetBroadcastState(RadioRef) == 1' in out
    assert 'TES4Polyfill.SetBroadcastState(RadioRef, (0) != 0)' in out
    assert 'If Self.IsEssential()' in out


def test_a_fragment_hoists_a_declaration_nested_in_an_if():
    """A local declared inside an `if` of a package fragment is declared once."""
    out = '\n'.join(_fallout_conv().convert_fragment(
        'If GetDistance Player >= 600\n  Short bRand\n  Set bRand to GetRandomPercent\nEndif\n', 'Package'))
    assert out.count('Int bRand') == 1 and out.index('Int bRand') < out.index('bRand = ')


def test_set_restrained_goes_through_the_polyfill(fallout4):
    """Deputy Beagle's freeing line (re-evaluating, then unrestraining) frees him through TES4Polyfill.Restrain,
    which re-evaluates his packages once he is free, as vanilla's captives are.
    See: docs/fork/fo4_pipeline.md#restrained
    """
    src = 'scn T\nbegin OnLoad\n  PrimmDeputyRef.evp\n  setrestrained 0\n  setrestrained 1\nend\n'
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'Actor', 'T')
    assert 'TES4Polyfill.Restrain(Self, false)' in out and 'TES4Polyfill.Restrain(Self, true)' in out
    assert '.SetRestrained(' not in out


def test_remove_me_takes_an_item_out_of_its_inventory(fallout4):
    """FNV's .38 Special box (38SpecialAmmoAddScript) pays out and RemoveMe's: Delete left it in the player's
    inventory, paying 50 rounds each pass; RemoveMe takes it out (or into a target container)."""
    src = ('scn T\nint killme\nBEGIN OnAdd Player\n  Set killme to 1\nEND\nbegin GameMode\n  if (killme == 1)\n'
           '    Player.AddItem Ammo38Special 50\n    RemoveMe\n  endif\nend\n')
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'ObjectReference', 'T')
    assert 'TES4Polyfill.RemoveMe(Self, None)' in out and 'Delete()' not in out
    moved = ScriptConverter(CrossRefGraph()).convert_standalone('T', 'scn T\nbegin OnAdd Player\n  RemoveMe BoxRef\nend\n',
                                                                 'ObjectReference', 'T')
    assert 'TES4Polyfill.RemoveMe(Self, BoxRef)' in moved


def test_add_special_points_opens_the_character_rules_box(fallout4):
    """Intense Training's `AddSpecialPoints 1` is the addspecial menu."""
    out = '\n'.join(_fallout_conv().convert_fragment('AddSpecialPoints 1\n', 'Quest'))
    assert '.Menu("addspecial", 1' in out and 'TODO' not in out


def test_a_package_fragments_bare_call_acts_on_its_actor(fallout4):
    """A package fragment's StartConversation speaks as its actor, not Self."""
    out = '\n'.join(_fallout_conv().convert_fragment('StartConversation Player\n', 'TopicInfo'))
    assert 'akSpeakerRef' in out and 'StartConversation(TES4Talk_GREETING, Self)' not in out
