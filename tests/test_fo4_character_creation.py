"""Fallout 4's character creation stands in for FO3/FNV's: menu frames, the skipped race menu, the sex box.

See: docs/fork/fo4_pipeline.md#character-creation
"""
from script_convert import target
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.message_menus import build_message_plan, sex_buttons

#: FO3's CG00SCRIPT idiom: a box whose pressed button sets the player's sex.
SEX_BOX = ('scn CG00SCRIPT\nshort button\n\nbegin GameMode\n  ShowMessage CG00SexMessage\n'
           '  set button to GetButtonPressed\n  if button == 0\n    player.SexChange male\n'
           '  elseif button == 1\n    player.SexChange female\n  endif\nend\n')


def fo4(monkeypatch, src: str, name: str = 'T', plan: 'dict | None' = None) -> str:
    """Quest script `src` named `name`, converted for Fallout 4 with message plan `plan`."""
    monkeypatch.setenv(target.TARGET_ENV, target.FALLOUT4)
    conv = ScriptConverter(CrossRefGraph())
    conv.message_menus = plan or {}
    return conv.convert_standalone(name, src, 'Quest', name)


def test_a_polled_menumode_runs_on_menu_frames_and_gamemode_outside_them(monkeypatch):
    """MenuMode runs on menu frames (MenuFrame); GameMode outside menus."""
    out = fo4(monkeypatch, 'scn T\nshort b\nbegin MenuMode\n  set b to 1\nend\nbegin GameMode\n  set b to 2\nend\n')
    assert 'If TES4Polyfill.MenuFrame()' in out
    assert 'If !TES4Polyfill.InMenuMode()' in out


def test_a_race_menu_close_also_takes_the_skipped_race_menu(monkeypatch):
    """A `MenuMode 1036` listener registers for RaceMenuSkipped and takes it as the LooksMenu closing."""
    out = fo4(monkeypatch, 'scn T\nshort b\nbegin MenuMode 1036\n  set b to 1\nend\n')
    assert 'RegisterForCustomEvent(TES4PlayerControls, "RaceMenuSkipped")' in out
    assert 'Event F3NV_PlayerControls.RaceMenuSkipped(F3NV_PlayerControls akSender, Var[] akArgs)' in out
    assert '  OnMenuOpenCloseEvent("LooksMenu", False)' in out
    assert 'F3NV_PlayerControls Property TES4PlayerControls Auto' in out


def test_other_menu_listeners_get_no_skipped_race_menu(monkeypatch):
    """Only the race menu has a stand-in."""
    out = fo4(monkeypatch, 'scn T\nshort b\nbegin MenuMode 1008\n  set b to 1\nend\n')
    assert 'RaceMenuSkipped' not in out


def test_the_sex_buttons_are_the_branches_that_set_the_players_sex():
    """(male, female) buttons; a box whose branches do something else is not a sex box."""
    assert sex_buttons(SEX_BOX) == (0, 1)
    assert sex_buttons(SEX_BOX.replace('\n', '\r\n')) == (0, 1)
    assert sex_buttons(SEX_BOX.replace('player.SexChange female', 'set b to 1')) == ()


def test_a_sex_box_answers_with_the_sex_already_chosen(monkeypatch):
    """The box is not shown: its button is the one matching the player's sex (TES4Polyfill.SexButton)."""
    plan = build_message_plan([{'EditorID': 'CG00SCRIPT', 'SCTX': SEX_BOX}],
                              [{'EditorID': 'CG00SexMessage', 'DNAM': '1',
                                'Button[0].Text': 'Boy', 'Button[1].Text': 'Girl'}])
    out = fo4(monkeypatch, SEX_BOX, 'CG00SCRIPT', plan)
    assert 'TES4_MsgButton = TES4Polyfill.SexButton(0, 1)' in out
    assert 'TES4_ShowMsg(CG00SexMessage)' not in out
