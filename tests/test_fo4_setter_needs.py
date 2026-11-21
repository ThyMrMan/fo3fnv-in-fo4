"""What a source stage setter needs that the stage sweep cannot give (tools.live.fo4_setter_needs)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.live import fo4_setter_needs as N
from tools.validate.preflight.quest_source import Setter

XEDIT = Path(__file__).resolve().parents[1] / 'references' / 'xEdit' / 'Core' / 'wbDefinitionsFO3.pas'
SCRIPT = ('scn TestQuestScript\\r\\nshort intro\\r\\nbegin gamemode\\r\\n'
          'if ( getStage TestQuest == 90 ) && ( Player.GetSitting == 0 )\\r\\n  setstage TestQuest 100\\r\\nendif\\r\\n'
          'if intro == 5\\r\\n  setstage TestQuest 6\\r\\nendif\\r\\n'
          'if Player.GetInCell SomeCell\\r\\n  setstage TestQuest 20\\r\\nelse\\r\\n  setstage TestQuest 21\\r\\nendif\\r\\n'
          'end\\r\\nbegin menumode 1056\\r\\n  setstage TestQuest 72\\r\\nend')


def test_branch_reads_the_taken_branch_of_each_frame():
    """An `else` adds no condition; an enclosing `if` does."""
    assert N.branch(SCRIPT, 'setstage TestQuest 20') == ['Player.GetInCell SomeCell']
    assert N.branch(SCRIPT, 'setstage TestQuest 21') == []


def test_unwrap_keeps_two_parenthesised_halves():
    """`( a ) && ( b )` is not one parenthesised whole."""
    assert N.unwrap('( a ) && ( b )') == '( a ) && ( b )'
    assert N.unwrap('(( a && b ))') == 'a && b'


@pytest.fixture(name='needs')
def needs_fixture():
    """Needs over a stand-in source: one quest script, a line setting `intro` to 5, a stage log on GetDead."""
    if not XEDIT.is_file():
        pytest.skip('needs references/xEdit')
    info = SimpleNamespace(result='set TestQuest.intro to 5', quest=1)
    dead = (0x00, 1.0, 46, 0x1234, 0)
    source = SimpleNamespace(stage_logs={('TestQuest|40', '2'): ('setStage TestQuest 50', [dead])},
                             infos={1: info}, quest_fids={1: 'TestQuest'},
                             quest_script_of={'testquestscript': 'testquest'})
    return N.Needs(source, {'testquestscript': SCRIPT}, 'Fallout3.esm')


def test_a_stage_or_a_function_at_zero_holds(needs):
    """GetStage and `GetSitting == 0` hold; so does a variable a line sets."""
    assert needs.of(Setter('script', 'TestQuestScript', 'gamemode', 'TestQuest', 100, 'setstage TestQuest 100')) == []
    assert needs.of(Setter('script', 'TestQuestScript', 'gamemode', 'TestQuest', 6, 'setstage TestQuest 6')) == []


def test_a_place_a_menu_and_a_death_are_needs(needs):
    """GetInCell, a MenuMode block naming its menu and a log entry on GetDead == 1 are needs."""
    assert needs.of(Setter('script', 'TestQuestScript', 'gamemode', 'TestQuest', 20, 'setstage TestQuest 20')) == [
        'Player.GetInCell SomeCell']
    assert needs.of(Setter('script', 'TestQuestScript', 'menumode 1056', 'TestQuest', 72, 'setstage TestQuest 72')) == [
        'the menu of menumode 1056 open']
    assert needs.of(Setter('stage', 'TestQuest|40', '2', 'TestQuest', 50, 'setStage TestQuest 50')) == [
        "the log entry's GetDead == 1"]
