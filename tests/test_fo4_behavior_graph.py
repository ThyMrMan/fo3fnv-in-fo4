"""The behaviour graph builder: a graph using every helper writes, reads back and rebuilds identically, with every
event and variable reference resolving to a name."""

from fo4_import.havok import graph as G
from fo4_import.havok import packfile, packfile_write


def sample() -> G.Graph:
    """A two-state machine: a looping clip with a trigger, and a blend under an is-active modifier."""
    g = G.Graph('SampleBehavior')
    idle = g.clip('Idle', 'Animations\\Idle.hkt', G.LOOPING, [(0.5, 'FootLeft', False), (-0.1, 'Done', True)])
    walk = g.clip('Walk', 'Animations\\Walk.hkt', G.LOOPING)
    run = g.clip('Run', 'Animations\\Run.hkt', G.LOOPING)
    move = g.with_modifiers('Move', [g.is_active('Ready', ['bEquipOk'])],
                            g.blend('MoveBlend', [(walk, 60.0), (run, 500.0)], 'Speed',
                                    G.FLAG_SYNC | G.FLAG_PARAMETRIC))
    fx = g.blend_effect('Blend', 0.2)
    states = [g.state(0, 'Idle', idle, enter=('idleEnter',), to=[('moveStart', 1)], effect=fx),
              g.state(1, 'Move', move, exit_=('moveExit',), to=[('moveStop', 0)], effect=fx)]
    return g.finish(g.machine('Root', states, 0, [('g_reset', 0)], fx, sync='iState'),
                    variables=[('IsAttackReady', G.BOOL, 1)])


#: Per class: (is it a variable reference, the indices one object of it uses).
REFERENCES = {'hkbClipTriggerArray': (False, lambda f: {row['event']['id'] for row in f['triggers']}),
              'hkbStateMachineEventPropertyArray': (False, lambda f: {row['id'] for row in f['events']}),
              'hkbStateMachineTransitionInfoArray': (False, lambda f: {row['eventId'] for row in f['transitions']}),
              'hkbVariableBindingSet': (True, lambda f: {row['variableIndex'] for row in f['bindings']}),
              'hkbStateMachine': (True, lambda f: {f['syncVariableIndex']} - {-1})}


def references(objects: list) -> tuple:
    """(event ids, variable indices) the objects use."""
    found = {False: set(), True: set()}
    for o in objects:
        if o['class'] in REFERENCES:
            is_variable, indices = REFERENCES[o['class']]
            found[is_variable] |= indices(o['fields'])
    return found[False], found[True]


def test_sample_graph_round_trips():
    """The written graph reads back and writes again to the same bytes."""
    g = sample()
    data = packfile_write.write(g.objects, g.top)
    back = packfile.read(data)
    assert packfile_write.write(back.objects, back.objects[0]['#']) == data


def test_every_reference_names_an_event_or_variable():
    """Each event id and variable index used is in the graph's string data, and initial values match kinds."""
    g = sample()
    back = packfile.read(packfile_write.write(g.objects, g.top))
    strings = next(o['fields'] for o in back.objects if o['class'] == 'hkbBehaviorGraphStringData')
    events, variables = references(back.objects)
    assert events <= set(range(len(strings['eventNames'])))
    assert variables <= set(range(len(strings['variableNames'])))
    assert {'FootLeft', 'Done', 'idleEnter', 'moveExit', 'moveStart', 'moveStop', 'g_reset'} <= set(strings['eventNames'])
    values = next(o['fields'] for o in back.objects if o['class'] == 'hkbVariableValueSet')['wordVariableValues']
    index = strings['variableNames'].index('IsAttackReady')
    assert values[index]['value'] == 1


def test_an_event_with_a_string_payload_carries_it():
    """A (name, text) event is that event with an hkbStringEventPayload (vanilla RangedAttack's attackState)."""
    g = G.Graph('Test')
    entry = g.payload(('attackState', 'Enter'))
    assert g.events[entry['id']] == 'attackState' and g.get(entry['payload']) == {'data': 'Enter'}
    assert g.payload('attackStop')['payload'] is None


def test_a_layered_blend_keeps_each_childs_bone_weights():
    """layered() writes one hkbBoneWeightArray per child (the robots' arm layer) and they read back unchanged."""
    g = G.Graph('Layered')
    legs = g.clip('Walk', 'Animations\\Walk.hkt', G.LOOPING)
    arms = g.clip('Fire', 'Animations\\Fire.hkt', G.SINGLE)
    g.finish(g.layered('Layers', [(legs, [1.0, 0.0, 0.0], 1.0), (arms, [0.0, 1.0, 1.0], 0.0)]))
    pf = packfile.read(packfile_write.write(g.objects, g.top))
    weights = [o['fields']['boneWeights'] for o in pf.objects if o['class'] == 'hkbBoneWeightArray']
    assert weights == [[1.0, 0.0, 0.0], [0.0, 1.0, 1.0]]
