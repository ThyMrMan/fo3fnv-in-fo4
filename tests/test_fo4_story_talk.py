"""The story cases' `choose`: which listed prompt a case's words pick; `talk`: activating again until the menu."""
from types import SimpleNamespace

from tools.live import fo4_story_talk as talk
from tools.live.game_bridge import BridgeError


def test_talk_activates_again_until_the_dialogue_menu_opens(monkeypatch):
    """No menu open first; a first activation the NPC ignores (busy with a bark) is followed by another, which opens
    the menu."""
    sent, states = [], iter([[], [], ['DialogueMenu']])

    def waited(bridge, ready, seconds):
        """The fake status wait: the next status, or a timeout when it is not the one waited for."""
        state = {'menus': next(states)}
        if not ready(state):
            raise BridgeError('timed out waiting', 'E_TIMEOUT')
        return state

    monkeypatch.setattr(talk, 'activate', lambda bridge, ref, front: sent.append(ref))
    monkeypatch.setattr(talk, 'aim', lambda bridge, ref: sent.append('look ' + ref))
    monkeypatch.setattr(talk, 'wait_status', waited)
    monkeypatch.setattr(talk, 'accept_boxes', lambda bridge, front: None)
    monkeypatch.setattr(talk, 'in_dialogue', lambda bridge, ref: True)
    monkeypatch.setattr(talk, 'walk', lambda bridge, rest, front: sent.append('walk ' + rest))
    talk.talk(SimpleNamespace(status=lambda: {'menus': []}), '60 0002BF4F0', lambda rest: (60.0, rest.split()[1]),
              lambda: None)
    assert sent == ['0002BF4F0', 'walk 0002BF4F0 64', '0002BF4F0', 'look 0002BF4F0']


def test_in_dialogue_reads_the_consoles_text_answer(monkeypatch):
    """FO4's console answers IsInDialogueWithPlayer in words, not `>> 1`."""
    said = iter(['Actor  is in dialogue state with player.', 'Actor  is not in dialogue state with player.'])
    monkeypatch.setattr(talk, 'send', lambda bridge, text: next(said))
    assert talk.in_dialogue(None, '082BF4F0') and not talk.in_dialogue(None, '0870292D')


def test_someone_in_the_way_who_answers_is_left_and_the_player_steps_nearer(monkeypatch):
    """E opens the Overseer's talk (he stands between the player and Mrs. Palmer): the player leaves it, walks
    within TALK_NEAR of her, and presses E again, which opens hers."""
    sent, speakers = [], iter([False] * talk.SPEAKER_CHECKS + [True])
    monkeypatch.setattr(talk, 'activate', lambda bridge, ref, front: sent.append(ref))
    monkeypatch.setattr(talk, 'aim', lambda bridge, ref: sent.append('look ' + ref))
    monkeypatch.setattr(talk, 'wait_status', lambda bridge, ready, seconds: None)
    monkeypatch.setattr(talk, 'accept_boxes', lambda bridge, front: None)
    monkeypatch.setattr(talk, 'in_dialogue', lambda bridge, ref: next(speakers))
    monkeypatch.setattr(talk, 'bye', lambda bridge, rest, front: sent.append('bye'))
    monkeypatch.setattr(talk, 'walk', lambda bridge, rest, front: sent.append('walk ' + rest))
    monkeypatch.setattr(talk.time, 'sleep', lambda seconds: None)
    talk.talk(SimpleNamespace(status=lambda: {'menus': []}), '60 082BF4F0', lambda rest: (60.0, rest.split()[1]),
              lambda: None)
    assert sent == ['082BF4F0', 'bye', 'walk 082BF4F0 64', '082BF4F0', 'look 082BF4F0']


def test_a_dialogue_the_speaker_opened_is_the_talk(monkeypatch):
    """Sunny's own greeting (after the third bottle) is open with her: talk takes it, activating nothing, and the
    player looks at her."""
    sent = []
    monkeypatch.setattr(talk, 'activate', lambda bridge, ref: sent.append(ref))
    monkeypatch.setattr(talk, 'aim', lambda bridge, ref: sent.append('look ' + ref))
    monkeypatch.setattr(talk, 'send', lambda bridge, text: 'IsInDialogueWithPlayer >> 1.00')
    talk.talk(SimpleNamespace(status=lambda: {'menus': ['DialogueMenu']}), '30 08AF2320',
              lambda rest: (30.0, rest.split()[1]), lambda: None)
    assert sent == ['look 08AF2320']


def test_an_open_notice_box_is_accepted_before_talking(monkeypatch):
    """A reputation notice left open (VMS16 stage 100) takes Enter, as a player accepts it."""
    states, keys = iter([['MessageBoxMenu'], []]), []
    bridge = SimpleNamespace(status=lambda: {'menus': next(states)})
    monkeypatch.setattr(talk.hidden_launch, 'tap_key', keys.append)
    monkeypatch.setattr(talk.time, 'sleep', lambda seconds: None)
    talk.accept_boxes(bridge, lambda: None)
    assert keys == [talk.hidden_launch.SCAN_ENTER]


def test_choose_presses_again_when_the_list_stays(monkeypatch):
    """A lost key press leaves the same list shown; choose presses again, and stops once the list hides."""
    listed = ["Yes, ma'am.", 'Oh, you did not have to.']
    shown, keys = iter([listed] * 14 + [[]]), []
    monkeypatch.setattr(talk, 'options', lambda bridge: next(shown))
    monkeypatch.setattr(talk.hidden_launch, 'tap_key', keys.append)
    monkeypatch.setattr(talk, 'PRESS_WAIT', 1.0)
    monkeypatch.setattr(talk.time, 'sleep', lambda seconds: None)
    clock = iter(range(1000))
    monkeypatch.setattr(talk.time, 'time', lambda: next(clock) * 0.1)
    talk.choose(None, "60 Yes, ma'am.", lambda: None, lambda rest: (60.0, rest.split(' ', 1)[1]))
    assert keys == [talk.hidden_launch.SCANCODES['1']] * 2


def test_choose_passes_on_nothing_to_pick_when_a_way_already_ended(monkeypatch):
    """`A || -` with the list hidden after the last pick: no press, no failure; `-` never matches a prompt."""
    keys = []
    monkeypatch.setattr(talk, 'options', lambda bridge: [])
    monkeypatch.setattr(talk.hidden_launch, 'tap_key', keys.append)
    monkeypatch.setattr(talk.time, 'sleep', lambda seconds: None)
    clock = iter(range(1000))
    monkeypatch.setattr(talk.time, 'time', lambda: next(clock) * 0.5)
    talk.choose(None, '20 Okay. || -', lambda: None, lambda rest: (20.0, rest.split(' ', 1)[1]))
    assert keys == [] and talk.row_of(['Well - maybe.'], '-') == -1


def test_words_match_a_prompt_plainly():
    """Case, spacing, entities and a skill tag don't stop a match."""
    listed = ['[Speech 25] Sure, Butch. &lt;Spit on the sweetroll and give it to him.&gt;', 'Yes,  MA\'AM.']
    assert talk.row_of(listed, "yes, ma'am.") == 1
    assert talk.row_of(listed, 'sure, butch. <spit on the sweetroll') == 0


def test_a_row_number_picks_that_row_once_listed():
    """`#2` is the second row, and nothing until two rows are listed."""
    assert talk.row_of(['Agree.', 'Disagree.'], '#2') == 1
    assert talk.row_of(['Agree.'], '#2') == -1


def test_leave_alone_is_its_own_row_not_every_row():
    """`[Leave]` matches the `[LEAVE]` row, not the first; a skill tag still drops."""
    listed = ['ANYTHING I NEED TO KNOW ABOUT THE G.O.A.T.?', '[LEAVE]']
    assert talk.row_of(listed, '[Leave]') == 1
    assert talk.row_of(['[Speech 30] Trust me.'], 'Trust me.') == 0


def test_alternatives_pick_the_first_one_listed():
    """`A || B`: B's row when only B is listed; A's when both are."""
    assert talk.row_of(['Sure.', 'Enough.'], 'Gone. || Enough.') == 1
    assert talk.row_of(['Sure.', 'Enough.'], 'Sure. || Enough.') == 0


def test_no_prompt_holds_the_words():
    """Words no prompt holds give -1."""
    assert talk.row_of(['Thanks, Stanley.'], 'I really have no idea') == -1
