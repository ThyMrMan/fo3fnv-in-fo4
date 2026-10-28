"""Build Havok 2014 behaviour graphs as packfile objects: nodes start from their class defaults, and events and
variables are named, their indices assigned as they are first used.

See: docs/fork/fo4_spikes.md#own-rig-code
"""

import struct

from fo4_import.havok.packfile import ARRAYS, FLOATS, PRIM, Classes, classes

BOOL, INT32, REAL = 0, 3, 4
FLAG_SYNC, FLAG_PARAMETRIC = 0x1, 0x10
LOOPING, SINGLE = 1, 0
#: FLAG_IS_LOCAL_WILDCARD: on all of vanilla's wildcard transitions; Havok ignores a wildcard without it.
LOCAL_WILDCARD = 0x800
NO_EVENT = {'id': -1, 'payload': None}
INTERVAL = {'enterEventId': -1, 'exitEventId': -1, 'enterTime': 0.0, 'exitTime': 0.0}


def word(kind: int, value) -> int:
    """A variable's initial value as hkbVariableValueSet stores it (floats as bits)."""
    return struct.unpack('<i', struct.pack('<f', value))[0] if kind == REAL else int(value)


class Graph:
    """One behaviour file's objects, event names and variables."""

    def __init__(self, name: str, cl: Classes = None):
        """An empty graph `name` (its root-level container made)."""
        self.cl, self.name = cl or classes(), name
        self.objects, self.events, self.variables = [], [], []
        self.top = self.add('hkRootLevelContainer', namedVariants=[])

    def defaults(self, cls: str) -> dict:
        return {m.name: self.default(m) for m in self.cl.members(cls) if not m.ignored}

    def default(self, m):
        """A member's zero value: 0, zero floats, empty array, a struct's defaults or None."""
        if m.arrsize:
            return [self.default(m.single()) for _ in range(m.arrsize)]
        vtype = m.sub if m.vtype in ('TYPE_ENUM', 'TYPE_FLAGS') else m.vtype
        if vtype in PRIM:
            return 0
        if vtype in FLOATS:
            return (0.0,) * FLOATS[vtype]
        if vtype in ARRAYS:
            return []
        if vtype == 'TYPE_STRUCT':
            return self.defaults(m.ctype)
        return (0, 0) if vtype == 'TYPE_RELARRAY' else None

    def add(self, cls: str, **fields) -> str:
        """A new `cls` object from its defaults and `fields`; its name."""
        values = self.defaults(cls)
        unknown = set(fields) - set(values)
        if unknown:
            raise KeyError(f'{cls}: {sorted(unknown)}')
        values.update(fields)
        name = f'#{len(self.objects):04d}'
        self.objects.append({'#': name, 'class': cls, 'fields': values})
        return name

    def get(self, name: str) -> dict:
        return self.objects[int(name[1:])]['fields']

    def ev(self, event: str) -> int:
        """The index of event `event`, added on first use."""
        if event not in self.events:
            self.events.append(event)
        return self.events.index(event)

    def var(self, name: str, kind: int = BOOL, value=0) -> int:
        """The index of variable `name`; added with `kind` and initial `value` on first use."""
        names = [v[0] for v in self.variables]
        if name in names:
            return names.index(name)
        self.variables.append((name, kind, value))
        return len(names)

    def payload(self, event) -> dict:
        """An event reference: a name, or (name, text) with a string payload."""
        if isinstance(event, tuple):
            return {'id': self.ev(event[0]), 'payload': self.add('hkbStringEventPayload', data=event[1])}
        return {'id': self.ev(event), 'payload': None}

    def events_array(self, events) -> str:
        return self.add('hkbStateMachineEventPropertyArray', events=[self.payload(e) for e in events]) if events else None

    def bindings(self, pairs) -> str:
        """A binding set tying each member path to a variable (name, kind, value)."""
        binds = [{'memberPath': path, 'variableIndex': self.var(*v), 'bitIndex': -1, 'bindingType': 0}
                 for path, v in pairs]
        return self.add('hkbVariableBindingSet', bindings=binds, indexOfBindingToEnable=-1)

    def blend_effect(self, name: str, duration: float) -> str:
        return self.add('hkbBlendingTransitionEffect', name=name, selfTransitionMode=3, duration=duration,
                        alignmentBone=-1)

    def transitions(self, pairs, effect: str, flags: int = 0) -> str:
        """A transition array: (event, to state id) pairs, all with `effect` and `flags` (LOCAL_WILDCARD for a state
        machine's wildcard transitions; 0 for a state's own)."""
        if not pairs:
            return None
        rows = [{'triggerInterval': dict(INTERVAL), 'initiateInterval': dict(INTERVAL), 'transition': effect,
                 'condition': None, 'eventId': self.ev(e), 'toStateId': to, 'fromNestedStateId': 0,
                 'toNestedStateId': 0, 'priority': 0, 'flags': flags} for e, to in pairs]
        return self.add('hkbStateMachineTransitionInfoArray', transitions=rows)

    def state(self, sid: int, name: str, generator: str, enter=(), exit_=(), to=(), effect=None) -> str:
        """A state info: its generator, enter and exit events, and its transitions."""
        return self.add('hkbStateMachineStateInfo', name=name, stateId=sid, generator=generator, probability=1.0,
                        enable=1, enterNotifyEvents=self.events_array(enter),
                        exitNotifyEvents=self.events_array(exit_), transitions=self.transitions(to, effect))

    def machine(self, name: str, states: list, start: int, wildcard=(), effect=None, sync=None, binding=None) -> str:
        """A state machine over `states` (state infos); `sync` names an int variable to sync the state id to."""
        return self.add('hkbStateMachine', name=name, states=states, startStateId=start,
                        eventToSendWhenStateOrTransitionChanges=dict(NO_EVENT), returnToPreviousStateEventId=-1,
                        randomTransitionEventId=-1, transitionToNextHigherStateEventId=-1,
                        transitionToNextLowerStateEventId=-1,
                        syncVariableIndex=self.var(sync, INT32, 1) if sync else -1,
                        maxSimultaneousTransitions=32, selfTransitionMode=2, variableBindingSet=binding,
                        wildcardTransitions=self.transitions(wildcard, effect, LOCAL_WILDCARD))

    def clip(self, name: str, animation: str, mode: int, triggers=(), mirror: bool = False) -> str:
        """A clip on `animation`; triggers are (local time, event, relative to end)."""
        rows = [{'localTime': t, 'event': self.payload(e), 'relativeToEndOfClip': int(end), 'acyclic': 0,
                 'isAnnotation': 0} for t, e, end in triggers]
        trig = self.add('hkbClipTriggerArray', triggers=rows) if rows else None
        return self.add('hkbClipGenerator', name=name, animationName=animation, mode=mode, triggers=trig,
                        playbackSpeed=1.0, animationBindingIndex=-1, flags=4 if mirror else 0)

    def blend(self, name: str, children, parameter: str, flags: int) -> str:
        """A blender over (generator, weight) children, its blend parameter bound to float `parameter`."""
        kids = [self.add('hkbBlenderGeneratorChild', generator=g, weight=w, worldFromModelWeight=1.0)
                for g, w in children]
        return self.add('hkbBlenderGenerator', name=name, children=kids, flags=flags, indexOfSyncMasterChild=-1,
                        maxCyclicBlendParameter=1.0, variableBindingSet=self.bindings(
                            [('blendParameter', (parameter, REAL, 0.0))]))

    def layered(self, name: str, children) -> str:
        """A blender over (generator, bone weights, world-from-model weight) children, each at weight 1: per bone,
        the children whose weights cover it (the robots' arm attack layers over combat locomotion)."""
        kids = [self.add('hkbBlenderGeneratorChild', generator=g, weight=1.0, worldFromModelWeight=wfm,
                         boneWeights=self.add('hkbBoneWeightArray', boneWeights=list(weights)))
                for g, weights, wfm in children]
        return self.add('hkbBlenderGenerator', name=name, children=kids, flags=0, indexOfSyncMasterChild=-1,
                        blendParameter=1.0, maxCyclicBlendParameter=1.0)

    def is_active(self, name: str, variables) -> str:
        """A BSIsActiveModifier that holds each bool variable true while active."""
        binding = self.bindings([(f'bIsActive{i}', (v, BOOL, 0)) for i, v in enumerate(variables)])
        return self.add('BSIsActiveModifier', name=name, enable=1, variableBindingSet=binding, userData=2)

    def with_modifiers(self, name: str, modifiers: list, generator: str) -> str:
        mods = self.add('hkbModifierList', name=f'{name}_ML', enable=1, modifiers=modifiers, userData=1)
        return self.add('hkbModifierGenerator', name=f'{name}_MG', modifier=mods, generator=generator, userData=1)

    def finish(self, root_generator: str, events=(), variables=()) -> 'Graph':
        """Close the graph: string data, variable infos and values, the graph node; extra names are kept too."""
        for e in events:
            self.ev(e)
        for v in variables:
            self.var(*v)
        values = self.add('hkbVariableValueSet', wordVariableValues=[{'value': word(k, v)} for _, k, v in self.variables],
                          quadVariableValues=[], variantVariableValues=[])
        strings = self.add('hkbBehaviorGraphStringData', eventNames=list(self.events), attributeNames=[],
                           variableNames=[n for n, _, _ in self.variables], characterPropertyNames=[])
        infos = [{'role': {'role': 0, 'flags': 0}, 'type': k} for _, k, _ in self.variables]
        data = self.add('hkbBehaviorGraphData', attributeDefaults=[], variableInfos=infos, characterPropertyInfos=[],
                        eventInfos=[{'flags': 0} for _ in self.events], variableBounds=[],
                        variableInitialValues=values, stringData=strings)
        graph = self.add('hkbBehaviorGraph', name=f'{self.name}.hkb', variableMode=0, rootGenerator=root_generator,
                         data=data)
        self.get(self.top)['namedVariants'] = [{'name': 'hkbBehaviorGraph', 'className': 'hkbBehaviorGraph',
                                                'variant': graph}]
        return self
