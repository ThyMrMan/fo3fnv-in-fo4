"""fo4_graph_check: each check finds its gecko-spike mistake in a small built graph and passes the fixed one."""

import struct

from fo4_import.havok import graph as G
from fo4_import.havok.gun_anim_text import crc, entry_id
from tools.validate import fo4_graph_check as C

ROOT_VARS = [(v, G.BOOL, 0) for v in C.ROOT_VARIABLES]


def built(exit_=('attackStop',), variables=(), events=C.ROOT_EVENTS) -> C.Graph:
    """A root graph: an idle state and an attack state entered by a meleeStart wildcard, exiting with `exit_`."""
    g = G.Graph('Test')
    idle, bite = g.clip('Idle', 'Animations\\Idle.hkt', G.LOOPING), g.clip('Bite', 'Animations\\Bite.hkt', G.SINGLE)
    states = [g.state(0, 'Idle', idle), g.state(1, 'Attack', bite, exit_=exit_)]
    machine = g.machine('Root', states, 0, wildcard=[('meleeStart', 1)], effect=g.blend_effect('Blend', 0.2))
    g.finish(machine, events=events, variables=[*ROOT_VARS, *variables])
    return C.graph_of('Test.hkx', {o['#']: o for o in g.objects})


def test_root_names_and_subgraph_names():
    """A name a third-person subgraph uses and the root lacks is an error (test 12); a first-person subgraph's
    is not; a missing vanilla root name is a warning (the vertibird lacks them)."""
    assert C.missing_names(built(), []) == [] and C.root_names(built()) == []
    sub = built(variables=[('iState_Other', G.INT32, 0)])
    sub.path = 'Core.hkx'
    found = C.missing_names(built(), [sub])
    assert len(found) == 1 and 'iState_Other' in found[0] and 'Core.hkx' in found[0]
    sub.path = 'Actors\\Character\\_1stPerson\\Behaviors\\Core.hkx'
    assert C.missing_names(built(), [sub]) == []
    assert 'Test.hkx lacks event PickNewIdle' in C.root_names(built(events=('Ragdoll',)))


def test_wildcards_need_a_scope_flag():
    """A wildcard transition flagged neither local nor global is reported; a global one (vanilla's 0x400) is not."""
    g = built()
    rows = [t for o in g.objs.values() if o['class'] == 'hkbStateMachineTransitionInfoArray'
            for t in o['fields']['transitions']]
    rows[0]['flags'] = 0x600
    assert C.unflagged_wildcards(g) == []
    rows[0]['flags'] = 0x200
    assert C.unflagged_wildcards(g) == ['Test.hkx: Root wildcards on meleeStart']


def test_shared_clip_names():
    """Two clip generators with one name are reported once."""
    g = built()
    assert C.shared_clip_names(g) == []
    for o in g.objs.values():
        if o['class'] == 'hkbClipGenerator':
            o['fields']['name'] = 'Same'
    assert C.shared_clip_names(g) == ['Test.hkx: Same']


def test_istate_variables():
    """Two iState_ variables at the value iState starts at (the gecko's iState_Molerat) are an error; at another
    value (vanilla's super mutant), or naming no MOVT, a warning; distinct values (vanilla's deathclaw) pass."""
    distinct = built(variables=[('iState', G.INT32, 0), ('iState_Gecko', G.INT32, 0), ('iState_GeckoSwim', G.INT32, 1)])
    assert C.clashing_states(distinct) == [] and C.odd_states(distinct, {'gecko', 'geckoswim'}) == []
    clash = built(variables=[('iState_Gecko', G.INT32, 0), ('iState_Molerat', G.INT32, 0)])
    assert C.clashing_states(clash) == ['Test.hkx: iState_Gecko, iState_Molerat all start at 0']
    later = built(variables=[('iState_A', G.INT32, 0), ('iState_B', G.INT32, 5), ('iState_C', G.INT32, 5)])
    assert C.clashing_states(later) == []
    assert C.odd_states(later, {'a', 'b'}) == ['Test.hkx: iState_B, iState_C all start at 5',
                                               'Test.hkx: iState_C names no MOVT']


def test_attacks_need_attack_stop():
    """An attack state raising no attackStop is reported; one ending in a combo state that raises it, or inside a
    state that raises it on exit (vanilla's deathclaw), passes."""
    assert C.attack_faults([built()], {'meleestart'}) == []
    assert C.attack_faults([built(exit_=())], {'meleestart'}) == [
        'Test.hkx: state Attack (meleeStart) never raises attackStop']
    assert C.attack_faults([combo(inner=True)], {'meleestart'}) == []
    assert C.attack_faults([combo(inner=False)], {'meleestart'}) == []
    assert C.unnamed_attacks([built()], {'meleestart', 'meleestart_power'}) == [
        'no graph names attack event meleestart_power']


def combo(inner: bool) -> C.Graph:
    """An attack machine (Swing, then Tail on comboNext) whose Tail raises attackStop (`inner`), or whose enclosing
    Attack state does on exit."""
    g = G.Graph('Combo')
    swing, tail = g.clip('Swing', 'Animations\\Swing.hkt', G.SINGLE), g.clip('Tail', 'Animations\\Tail.hkt', G.SINGLE)
    fx = g.blend_effect('Blend', 0.2)
    inside = g.machine('Attacks', [g.state(0, 'Swing', swing, to=[('comboNext', 1)], effect=fx),
                                   g.state(1, 'Tail', tail, exit_=('attackStop',) if inner else ())], 0)
    idle = g.clip('Idle', 'Animations\\Idle.hkt', G.LOOPING)
    states = [g.state(0, 'Idle', idle), g.state(1, 'Attack', inside, exit_=() if inner else ('attackStop',))]
    outer = g.machine('Root', states, 0, wildcard=[('meleeStart', 1)], effect=fx)
    for o in g.objects:
        if o['#'] == inside:
            o['fields']['wildcardTransitions'] = g.transitions([('meleeStart', 0)], fx, G.LOCAL_WILDCARD)
    g.finish(outer)
    return C.graph_of('Combo.hkx', {o['#']: o for o in g.objects})


def test_clips_must_be_listed_and_present():
    """A clip missing from the file data, or listed but absent, is reported."""
    files = {'Actors\\Test\\Animations\\Idle.hkx': b'x'}
    listed = {'Idle': 'Animations\\Idle', 'Bite': 'Animations\\Bite'}
    found = C.unlisted_clips(built(), listed, files.get, C.PureWindowsPath('Actors\\Test'))
    assert found == ['Test.hkx: Bite listed as Animations\\Bite.hkx, which is not there']
    assert C.unlisted_clips(built(), {'Idle': 'Animations\\Idle'}, files.get, C.PureWindowsPath('Actors\\Test')) == [
        'Test.hkx: Bite not in its file data']
    files['Actors\\Shared\\Bite.hkx'] = b'x'
    up = {'Idle': 'Animations\\Idle', 'Bite': '..\\Shared\\Bite'}
    assert C.unlisted_clips(built(), up, files.get, C.PureWindowsPath('Actors\\Test')) == []


def test_anim_text_files_per_project_graph_and_entry():
    """The project's file data, the root graph's files and each entry's files are required unless persistent."""
    race = C.Race('TestRace', 'Actors\\Test\\TestProject.hkx', set(),
                  [{'graph': 'Actors\\Test\\Behaviors\\Root.hkx', 'paths': ['Actors\\Test\\Animations']}])
    key, root = entry_id(race.entries[0]['paths'], race.entries[0]['graph']), crc('actors\\test\\behaviors\\root.hkx')
    files = {f'AnimTextData\\{k}.txt': b'' for k in ('AnimationFileData\\testproject', f'AnimEventInfo\\{root}',
                                                     f'ClipGeneratorData\\{root}', f'AnimationFileData\\{key}')}
    assert C.missing_anim_text(race, race.entries[0]['graph'], files.get) == [
        f'DynamicIdleData\\{key}.txt (Actors\\Test\\Behaviors\\Root.hkx)']
    files['AnimTextData\\AnimationOffsets\\PersistantSubgraphInfoAndOffsetData.txt'] = f'{key}.txt\r\n'.encode()
    assert C.missing_anim_text(race, race.entries[0]['graph'], files.get) == []


def test_movement_speed_layout_follows_form_version():
    """A 17-float SPED at form version 131 (the gecko's freeze) is reported."""
    movts = {'Old': (98, 'old', bytes(68)), 'New': (131, 'new', bytes(112)),
             'Bad': (131, 'bad', struct.pack('<17f', *range(17)))}
    assert C.bad_speeds(movts) == ['Bad: form version 131, SPED 68 bytes']
