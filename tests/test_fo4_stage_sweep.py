"""The layer 1 stage sweep without a game: the quest plan, the generated cases, and the sweep's steps."""
import struct
from types import SimpleNamespace

import pytest

from tools.live import fo4_quest_plan as P
from tools.live import fo4_stage_sweep as W
from tools.live import fo4_story_cases as C
from tools.live import fo4_sweep_steps as S
from tools.live.game_bridge import BridgeError
from tools.validate.preflight.quest_source import SourceGame

QUESTS = """---RECORD_BEGIN---
Signature=QUST
FormID=00001000
EditorID=MQ01
SCRI=00002000
DATA.Flags=1
StageCount=3
Stage[0].Index=10
Stage[0].LogCount=1
Stage[0].Log[0].ResultScript=SetStage MQ01 20
Stage[1].Index=20
Stage[1].LogCount=0
Stage[2].Index=30
Stage[2].LogCount=1
Stage[2].Log[0].Flags=1
Stage[2].Log[0].ResultScript=CompleteQuest MQ02\\r\\nTrudyRef.Enable ; the saloon
---RECORD_END---

---RECORD_BEGIN---
Signature=QUST
FormID=00001001
EditorID=MQ02
StageCount=1
Stage[0].Index=5
Stage[0].LogCount=0
---RECORD_END---
"""

SCRIPTS = """---RECORD_BEGIN---
Signature=SCPT
FormID=00002000
EditorID=MQ01Script
SCTX=ScriptName MQ01Script\\r\\nfloat timer\\r\\nBegin GameMode\\r\\n\\tset timer to timer + GetSecondsPassed\\r\\n\\tif timer > 5\\r\\n\\t\\tSetStage MQ01 30\\r\\n\\tendif\\r\\nEnd
---RECORD_END---
"""


def subrecord(tag: bytes, data: bytes) -> bytes:
    """One subrecord: tag, u16 size, data."""
    return tag + struct.pack('<H', len(data)) + data


def plugin_bytes(quests: dict) -> bytes:
    """A Fallout 4 plugin holding a QUST group: {EditorID: [stages]}."""
    body = b''
    for fid, (edid, stages) in enumerate(quests.items(), 0x01000800):
        subs = subrecord(b'EDID', edid.encode() + b'\0') + b''.join(
            subrecord(b'INDX', struct.pack('<HBB', s, 0, 0)) for s in stages)
        body += struct.pack('<4s4IHH', b'QUST', len(subs), 0, fid, 0, 131, 0) + subs
    header = struct.pack('<4s4IHH', b'TES4', 0, 0, 0, 0, 131, 0)
    return header + struct.pack('<4sI4sI8x', b'GRUP', 24 + len(body), b'QUST', 0) + body


@pytest.fixture
def plan(tmp_path):
    """The plan of a two-quest export against a build holding MQ01's stages 10 and 20 only."""
    export = tmp_path / 'Game.esm'
    export.mkdir()
    (export / 'QUST.txt').write_text(QUESTS, encoding='utf-8')
    (export / 'SCPT.txt').write_text(SCRIPTS, encoding='utf-8')
    plugin = tmp_path / 'Game.esm.built'
    plugin.write_bytes(plugin_bytes({'FNV_MQ01': [10, 20]}))
    return P.build_plan(export, P.built_stages(plugin))


def test_the_source_knows_who_enables_a_disabled_ref(tmp_path):
    """MQ01 stage 30 enables TrudyRef (Initially Disabled): that stage's site is her enabler."""
    (tmp_path / 'QUST.txt').write_text(QUESTS, encoding='utf-8')
    (tmp_path / 'ACHR.txt').write_text('---RECORD_BEGIN---\nSignature=ACHR\nFormID=00104C6D\nEditorID=TrudyRef\n'
                                       'RecordFlags=3072\nNAME=00104C6C\n---RECORD_END---\n', encoding='utf-8')
    source = SourceGame(str(tmp_path))
    assert source.disabled == {0x104C6D}
    assert [(s.kind, s.owner) for s in source.enablers({0x104C6D})] == [('stage', 'MQ01|30')]


def test_the_plan_names_each_stage_setter_and_what_was_built(plan):
    """Stages come in order with their setters (another stage's result script, the quest script's timer); the
    built quest, its stages and the missing quest are marked."""
    mq01, mq02 = plan['quests']
    assert (mq01['fo4'], mq01['built'], mq01['start_enabled'], mq02['built']) == ('FNV_MQ01', True, True, False)
    stages = {s['stage']: s for s in mq01['stages']}
    assert list(stages) == [10, 20, 30] and [s['built'] for s in stages.values()] == [True, True, False]
    assert stages[20]['setters'][0] | {'line': ''} == {'kind': 'stage', 'quest': 'MQ01', 'stage': 10, 'line': '',
                                                     'live': True}
    timer = stages[30]['setters'][0]
    assert (timer['kind'], timer['script'], timer['block'], timer['quest']) == ('timer', 'MQ01Script', 'GameMode',
                                                                               'MQ01')
    assert stages[30]['reached'] and not stages[20]['reached']
    assert [s['ends'] for s in stages.values()] == ['', '', 'complete']
    assert [(s['kind'], s['stage']) for s in mq02['completes']] == [('stage', 30)] and not mq01['completes']


def test_a_quest_case_waits_for_stages_that_follow_on_their_own(plan):
    """A stage an earlier stage's result script sets is waited for before it is set; every check is soft."""
    quest = plan['quests'][0]
    text = '\n'.join(W.case_lines(quest, quest['stages'][:2], 'f3nvtest_start'))
    steps = [s[1:] for s in C.parse(text, {})[0].steps]
    assert steps[:2] == [('load', 'f3nvtest_start'), ('run', 'startquest FNV_MQ01')]
    assert ('check', "until 10 GetStageDone FNV_MQ01 20 == 1 | FNV_MQ01 stage 20: not set by MQ01 stage 10's "
                     'result script') in steps
    assert [v for v, _ in steps].count('run') == 3 and {v for v, _ in steps} == {'load', 'run', 'check'}


def test_the_sweep_writes_built_quests_and_the_report_last(plan, tmp_path):
    """Unbuilt quests and stages are left out; the report case sorts after every quest's file."""
    out = tmp_path / 'sweep'
    out.mkdir()
    (out / 'q_Stale.f4test').write_text('case stale\nend\n', encoding='utf-8')
    assert W.write_sweep(plan, out, '', [], True) == (1, 2, 1, {})
    assert sorted(p.name for p in out.glob('*.f4test')) == ['q_MQ01.f4test', 'zz_report.f4test']
    names = [c.name for c in C.parse(C.case_text([out]), {})]
    assert names == ['MQ01', 'zz_report']


LOG = """[11/17/2026 - 10:00:00PM] error: Cannot call SetValue() on a None object, aborting function call
stack:
\t[FNV_VCG01 (0100104C)].FALLOUTNV_QF_VCG01.Fragment_Stage_0010_Item_00() - "FALLOUTNV_QF_VCG01.psc" Line 12
[11/17/2026 - 10:00:01PM] error: Actor value not found
stack:
\t[None].Actor.GetValue() - "<native>" Line ?
\t[FNV_VCG01 (0100104C)].FALLOUTNV_QF_VCG01.Fragment_Stage_0020_Item_00() - "FALLOUTNV_QF_VCG01.psc" Line 3
[11/17/2026 - 10:00:02PM] error: Cannot call Enable() on a None object, aborting function call
stack:
\t[Quest (00012345)].DefaultQuestScript.OnInit() - "DefaultQuestScript.psc" Line 9
"""


def game_with_log(tmp_path):
    """A game whose trace stands at the end of an empty log; the log path."""
    log = tmp_path / 'Papyrus.0.log'
    log.write_text('', encoding='utf-8')
    return SimpleNamespace(trace=C.Trace(log), bridge=None), log


def test_errors_charge_our_frames_and_ignore_vanilla(tmp_path, monkeypatch):
    """Errors in a converted script, or in a native one of ours called, fail the step grouped by cause and
    function; a vanilla script's error and the lines before the window are not counted."""
    monkeypatch.setattr(S.time, 'sleep', lambda s: None)
    game, log = game_with_log(tmp_path)
    with open(log, 'a', encoding='utf-8') as f:
        f.write(LOG)
    with pytest.raises(C.CaseFailed) as failed:
        S.errors(game, '')
    assert '2 Papyrus error(s)' in str(failed.value)
    assert 'FALLOUTNV_QF_VCG01.Fragment_Stage_0020_Item_00' in str(failed.value)
    assert 'DefaultQuestScript' not in str(failed.value)
    S.errors(game, '0')


def test_check_keeps_a_failure_and_report_lists_it(tmp_path, monkeypatch):
    """A failed check is kept and the case goes on; `report` fails naming its note, step and why."""
    game, _log = game_with_log(tmp_path)

    def step(_game, verb, rest):
        """Fails `until`, passes anything else."""
        if verb == 'until':
            raise C.CaseFailed('GetStageDone FNV_MQ01 20 still 0.0 after 10 s')

    S.check(game, 'until 10 GetStageDone FNV_MQ01 20 == 1 | FNV_MQ01 stage 20', step)
    S.check(game, 'errors | FNV_MQ01 stage 20', step)
    with pytest.raises(C.CaseFailed, match=r'1 of 2 checks failed:\n.*FNV_MQ01 stage 20: `until 10 GetStageDone'):
        S.report(game)


class Loader:
    """A bridge that loads a save of the same cell: no loading menu, only the load count rising after a busy poll."""

    def __init__(self):
        """Not loading yet, no load done."""
        self.states, self.loads = [], 0

    def request(self, cmd, text=''):
        """`load`: starts the load."""
        self.states = [BridgeError('loading', 'E_LOADING'), {'menus': [], 'cell': 'Old', 'loads': 0}]
        self.loads = 1
        return {'queued': text}

    def status(self):
        """Each queued state in turn, then the same cell with the load count."""
        state = self.states.pop(0) if self.states else {'menus': [], 'cell': 'Old', 'loads': self.loads}
        if isinstance(state, BridgeError):
            raise state
        return state


def test_load_waits_for_the_load_and_starts_the_window_after_it(tmp_path, monkeypatch):
    """`load` waits for the load count to rise before `ready`, and errors before it are not charged afterwards."""
    monkeypatch.setattr(S.time, 'sleep', lambda s: None)
    monkeypatch.setattr(S, 'LOAD_SETTLE_SECONDS', 0)
    game, log = game_with_log(tmp_path)
    game.bridge = Loader()
    seen = []
    with open(log, 'a', encoding='utf-8') as f:
        f.write(LOG)
    S.load(game, 'f3nvtest_start', lambda bridge, rest: seen.append(bridge.status()))
    assert seen == [{'menus': [], 'cell': 'Old', 'loads': 1}]
    S.errors(game, '0')


def test_errors_the_save_raises_on_its_own_after_a_load_are_background(tmp_path, monkeypatch):
    """A cause seen in the settle after `load` (another quest's timer) is left out of later windows; a new one is not."""
    monkeypatch.setattr(S.time, 'sleep', lambda s: None)
    monkeypatch.setattr(S, 'LOAD_SETTLE_SECONDS', 0)
    game, log = game_with_log(tmp_path)
    game.bridge = Loader()
    with open(log, 'a', encoding='utf-8') as f:
        f.write(LOG)
    S.load(game, 'f3nvtest_start', lambda bridge, rest: None)
    with open(log, 'a', encoding='utf-8') as f:
        f.write(LOG)
    S.errors(game, '0')
    with open(log, 'a', encoding='utf-8') as f:
        f.write(LOG.replace('Fragment_Stage_0020_Item_00', 'Fragment_Stage_0030_Item_00'))
    with pytest.raises(C.CaseFailed, match='Fragment_Stage_0030_Item_00'):
        S.errors(game, '0')


class Dropper(Loader):
    """A bridge whose game drops the first queued load, as a script's autosave did."""

    def __init__(self):
        """No load asked for yet."""
        super().__init__()
        self.asked = 0

    def request(self, cmd, text=''):
        """`load`: dropped the first time, taken after."""
        self.asked += 1
        return super().request(cmd, text) if self.asked > 1 else {'queued': text}


def test_load_queues_again_when_the_game_drops_it(monkeypatch):
    """A load the game has not taken after LOAD_REQUEUE_SECONDS is queued again."""
    monkeypatch.setattr(S.time, 'sleep', lambda s: None)
    monkeypatch.setattr(S, 'LOAD_REQUEUE_SECONDS', 0.05)
    bridge = Dropper()
    S.queue_load(bridge, 'f3nvtest_start')
    assert bridge.asked == 2
