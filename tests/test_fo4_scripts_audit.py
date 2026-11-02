"""The Fallout 4 script fixes from the converter audit: atomic adds (own reads after a direct write, the adder's local,
placed-reference owners), the quest poll delay, the incremental compile's state and orphans, and compile staging.

See: docs/fork/fo4_tool_audit.md#scripts
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from core import memory_budget
from fo4_import.spike import script as spike_script
from script_convert import atomic_adds
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV
from tools.script import compile_papyrus as CP

#: A quest poll counting GetSecondsPassed, as VOVLighting's flicker does.
FLICKER = 'ScriptName FlickerScript\n\nfloat timer\n\nBegin GameMode\n  set timer to timer + GetSecondsPassed\nEnd\n'


@pytest.fixture
def fallout4(monkeypatch):
    """Emit Fallout 4 Papyrus for the test."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)


def test_a_direct_write_after_an_add_is_what_its_mirror_and_later_reads_see(monkeypatch):
    """S1: `Q.v = 4` after an add sets the kept value first, so the mirror reads 4, not the add's stale result."""
    monkeypatch.setattr(atomic_adds, 'CALLS', {('q', 'v'): 'Int'})
    lines = ['Event OnDeath(Actor akKiller)', '  If Q.v < 3', '    Q.TES4Add_v((1))', '  Else',
             '    Q.v = 4\n      TES4Polyfill.SetMirror(TES4QVar_Q_v, Q.v)', '  EndIf', '  Foo(Q.v == 4)', 'EndEvent']
    assert atomic_adds.own_reads(lines) == [
        'Event OnDeath(Actor akKiller)', '  TES4Added_Q_v = Q.v', '  If Q.v < 3',
        '    TES4Added_Q_v = Q.TES4Add_v((1))', '  Else', '    TES4Added_Q_v = 4', '    Q.v = TES4Added_Q_v',
        '      TES4Polyfill.SetMirror(TES4QVar_Q_v, TES4Added_Q_v)', '  EndIf', '  Foo(TES4Added_Q_v == 4)',
        'EndEvent', 'Int TES4Added_Q_v']


def test_an_adder_mirrors_and_returns_its_own_sum(monkeypatch, fallout4):
    """S7: the new value lives in a local; the trace reads the counter before any call out."""
    monkeypatch.setattr(atomic_adds, 'OWNED', {'qscript': ['v']})
    conv = SimpleNamespace(sc=SimpleNamespace(edid='QScript', var_types={'v': 'Int'}, property_refs={}))
    assert atomic_adds.adders(conv, {('qscript', 'v'): 'TES4QVar_Q_v'}) == [
        'Int Function TES4Add_v(Float afBy)', '  Int TES4_Sum = (v + afBy) as Int', '  v = TES4_Sum',
        '  TES4Polyfill.TraceValue(Self, "v", v)', '  TES4Polyfill.SetMirror(TES4QVar_Q_v, TES4_Sum)',
        '  Return TES4_Sum', 'EndFunction', '']
    assert conv.sc.property_refs == {'TES4QVar_Q_v': 'GlobalVariable'}


def test_a_counter_on_a_placed_actor_is_found_through_the_graph():
    """S8: an increment of `DealerREF.n`, an ACHR whose base NPC carries the script, needs the graph's references."""
    by_type = {'SCPT': [{'FormID': '00000A01', 'EditorID': 'DealerScript', 'VariableCount': '1',
                         'Variable[0].Name': 'nPlayers', 'SCTX': 'short nPlayers'},
                        {'FormID': '00000A02', 'EditorID': 'StoolScript',
                         'SCTX': 'begin OnActivate\\r\\nset DealerREF.nPlayers to DealerREF.nPlayers + 1\\r\\nend'}],
               'NPC_': [{'FormID': '00000B01', 'EditorID': 'Dealer', 'SCRI': '00000A01'}]}
    xref = CrossRefGraph()
    xref.formid_to_edid['00000C01'] = 'DealerREF'
    xref.record_base['00000C01'] = '00000B01'
    xref.record_scri['00000B01'] = '00000A01'
    xref.script_formid_to_edid['00000A01'] = 'DealerScript'
    assert atomic_adds.find_adds(by_type) == ({}, {})
    assert atomic_adds.find_adds(by_type, xref) == ({('dealerref', 'nplayers'): 'Int'}, {'dealerscript': ['nplayers']})


def test_a_fallout4_quest_poll_counts_its_live_delay_after_a_pause(fallout4):
    """S3: a gap over 2 s counts the quest's TES4_Delay (SetQuestDelay may have shortened it); S2: 0 is the default."""
    out = ScriptConverter(CrossRefGraph()).convert_standalone('FlickerScript', FLICKER, 'Quest', 'FlickerScript')
    assert '  If TES4_SecondsPassed < 0.0 || TES4_SecondsPassed > 2.0\n    TES4_SecondsPassed = TES4_Delay\n' in out
    assert ('  If afSecs <= 0.0\n    afSecs = 5.0\n  EndIf\n  akQuest.TES4_Delay = Math.Max(afSecs, 0.1)\n'
            in out)


def test_a_poll_pass_skips_while_the_last_runs_and_every_return_ends_it(fallout4):
    """A pass that starts while the last still runs returns after the insurance arm; the body's return and the
    menu hold and the end of the pass all clear the mark. See docs/fork/performance.md#poll-overlap."""
    src = 'scn T\nshort b\nbegin GameMode\n  if b\n    return\n  endif\n  set b to 1\nend\n'
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'Quest', 'T')
    event = out.split('Event OnTimer(')[1].split('EndEvent')[0]
    assert event.index('StartTimer(5.0)') < event.index('If TES4_PassStarted > 0.0') < event.index('b = 1')
    assert event.count('TES4_PassStarted = 0.0') == 3
    assert 'Float TES4_PassStarted = 0.0' in out


def test_a_trigger_traces_who_enters_and_what_it_holds_when_its_cell_attaches(fallout4):
    """A reference script with OnTriggerEnter opens it with TraceTrigger and gains an OnCellAttach trace."""
    src = 'scn T\nshort b\nbegin OnTriggerEnter player\n  set b to 1\nend\n'
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'ObjectReference', 'T')
    assert ('Event OnTriggerEnter(ObjectReference akActionRef)\n  TES4Polyfill.TraceTrigger(Self, akActionRef)\n'
            in out)
    assert 'Event OnCellAttach()\n  TES4Polyfill.TraceTriggerAttach(Self)\nEndEvent' in out
    plain = ScriptConverter(CrossRefGraph()).convert_standalone('T', 'scn T\nbegin OnLoad\nend\n', 'ObjectReference', 'T')
    assert 'TraceTrigger' not in plain


@pytest.mark.parametrize('extends,game', [('Quest', 'skyrim'), ('ObjectReference', FALLOUT4)])
def test_other_polls_keep_the_interval_literal(extends, game, monkeypatch):
    """S3: a Skyrim quest and a Fallout 4 object script keep the interval literal."""
    monkeypatch.setenv(TARGET_ENV, game)
    out = ScriptConverter(CrossRefGraph()).convert_standalone('FlickerScript', FLICKER, extends, 'FlickerScript')
    assert '    TES4_SecondsPassed = 0.1\n' in out and 'TES4_Delay' not in out


def _fake_compiler(compiled: list):
    """A compile_folder stand-in writing a .pex per .psc and naming each in `compiled`."""
    def compile_folder(folder, out_dir, _imports):
        """One batch: every .psc in `folder` compiles."""
        for psc in Path(folder).glob('*.psc'):
            (Path(out_dir) / f'{psc.stem}.pex').write_text('pex', encoding='utf-8')
            compiled.append(psc.stem)
        return ''
    return compile_folder


def test_incremental_compile_follows_header_contents_and_removes_orphans(tmp_path, monkeypatch):
    """S4: a header's changed contents (same path) recompile everything; S5: a .pex the last run listed goes when
    its source is gone, and one it did not list (another plugin's, whatever its name) stays."""
    compiled = []
    monkeypatch.setattr(CP, 'compile_folder', _fake_compiler(compiled))
    head, src, out = tmp_path / 'head', tmp_path / 'src', tmp_path / 'out'
    for folder in (head, src, out):
        folder.mkdir()
    (head / 'Base.psc').write_text('ScriptName Base', encoding='utf-8')
    for name in ('FALLOUTNV_A', 'FALLOUTNV_B', 'TES4Helper'):
        (src / f'{name}.psc').write_text(f'ScriptName {name}', encoding='utf-8')
    args = SimpleNamespace(src=str(src), out=str(out), headers=str(head), full=False, workers=1)

    def run() -> list:
        """The names one compile_fallout4 run compiled."""
        compiled.clear()
        CP.compile_fallout4(args)
        return sorted(compiled)
    assert run() == ['FALLOUTNV_A', 'FALLOUTNV_B', 'TES4Helper']
    assert run() == []
    (head / 'Base.psc').write_text('ScriptName Base\nFunction F()\nEndFunction', encoding='utf-8')
    assert run() == ['FALLOUTNV_A', 'FALLOUTNV_B', 'TES4Helper']
    (src / 'FALLOUTNV_B.psc').unlink()
    (src / 'TES4Helper.psc').unlink()
    for name in ('FALLOUTNV_Gone', 'FALLOUT3_Gone', 'OtherMod'):
        (out / f'{name}.pex').write_text('pex', encoding='utf-8')
    assert run() == []
    assert sorted(p.stem for p in out.glob('*.pex')) == ['FALLOUT3_Gone', 'FALLOUTNV_A', 'FALLOUTNV_Gone', 'OtherMod']


def test_a_compiler_that_dies_is_run_again_in_the_same_build(tmp_path, monkeypatch):
    """A batch whose compiler writes nothing and names no error (out of memory) is compiled again, alone, before
    the run's results are kept; the next run compiles nothing."""
    compiled, batches = [], []
    working = _fake_compiler(compiled)

    def compile_folder(folder, out_dir, imports):
        """The first batch holding FALLOUTNV_A dies without output; every other batch works."""
        names = sorted(p.stem for p in Path(folder).glob('*.psc'))
        batches.append(names)
        dies = 'FALLOUTNV_A' in names and sum('FALLOUTNV_A' in b for b in batches) == 1
        return '' if dies else working(folder, out_dir, imports)
    monkeypatch.setattr(CP, 'compile_folder', compile_folder)
    head, src, out = tmp_path / 'head', tmp_path / 'src', tmp_path / 'out'
    for folder in (head, src, out):
        folder.mkdir()
    for name in ('FALLOUTNV_A', 'FALLOUTNV_B'):
        (src / f'{name}.psc').write_text(f'ScriptName {name}', encoding='utf-8')
    args = SimpleNamespace(src=str(src), out=str(out), headers=str(head), full=False, workers=2)
    assert CP.compile_fallout4(args)[0] == {'falloutnv_a', 'falloutnv_b'}
    assert sorted(batches) == [['FALLOUTNV_A'], ['FALLOUTNV_A'], ['FALLOUTNV_B']]
    compiled.clear()
    CP.compile_fallout4(args)
    assert compiled == []


def test_compilers_run_as_many_at_once_as_free_memory_holds(tmp_path, monkeypatch, capsys):
    """With free memory for two compilers beside the spare, three batches run two at a time and all compile;
    memory_workers gives at least one, and the count asked for when free memory cannot be read."""
    each = CP.COMPILER_BYTES + CP.COMPILER_SCRIPT_BYTES
    monkeypatch.setattr(memory_budget, 'free_ram_bytes', lambda: CP.COMPILE_SPARE_BYTES + 2 * each + 1)
    compiled = []
    monkeypatch.setattr(CP, 'compile_folder', _fake_compiler(compiled))
    head, src, out = tmp_path / 'head', tmp_path / 'src', tmp_path / 'out'
    for folder in (head, src, out):
        folder.mkdir()
    for name in ('FALLOUTNV_A', 'FALLOUTNV_B', 'FALLOUTNV_C'):
        (src / f'{name}.psc').write_text(f'ScriptName {name}', encoding='utf-8')
    CP.compile_fallout4(SimpleNamespace(src=str(src), out=str(out), headers=str(head), full=False, workers=3))
    assert 'in 3 batches, 2 at a time (free memory)' in capsys.readouterr().out
    assert sorted(compiled) == ['FALLOUTNV_A', 'FALLOUTNV_B', 'FALLOUTNV_C']
    assert memory_budget.memory_workers(15, each, 1 << 40) == 1
    monkeypatch.setattr(memory_budget, 'free_ram_bytes', lambda: None)
    assert memory_budget.memory_workers(15, each, 0) == 15


def test_compile_into_stages_a_fallout3_folder_by_its_own_prefix(tmp_path, monkeypatch):
    """S6: no Doc Mitchell script needed; FALLOUT3_ scripts are converted ones, staged only when named."""
    scripts = tmp_path / 'Fallout3.esm'
    scripts.mkdir()
    sources = {'FALLOUT3_A': 'FALLOUT3_B Property P Auto', 'FALLOUT3_B': '', 'FALLOUT3_C': '', 'TES4Polyfill': ''}
    for name, body in sources.items():
        (scripts / f'{name}.psc').write_text(f'ScriptName {name}\n{body}', encoding='utf-8')
    staged = {}

    def compile_fallout4(args):
        """Record what was staged and the headers asked for; nothing compiles."""
        staged.update(names=sorted(p.stem for p in Path(args.src).glob('*.psc')), headers=args.headers)
        return set(), {}, []
    monkeypatch.setattr(spike_script, 'STAGE', tmp_path / 'stage')
    monkeypatch.setattr(spike_script, 'compile_fallout4', compile_fallout4)
    assert spike_script.converted_prefix(scripts) == 'FALLOUT3_'
    spike_script.compile_into(scripts, tmp_path / 'Data', ['FALLOUT3_A'])
    assert staged == {'names': ['FALLOUT3_A', 'FALLOUT3_B', 'TES4Polyfill'], 'headers': None}
