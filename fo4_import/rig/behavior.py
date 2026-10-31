"""An own-rig creature's behaviour files: one root graph holding the whole creature, its character and project.

Root state machine: Creature (0: non-combat and combat machines, each standing or moving, combat with one attack
state per melee event), RagdollAndGetUp (1: Fully Ragdoll and GetUpFromRagdoll sharing a pose matcher; GetUpEnd on
leaving) and DeathAnimation (3: the ragdoll keyframed to a short hold, then Ragdoll). The graph carries the template
root's event and variable names after its own, minus other creatures' iState_ links.

See: docs/fork/fo4_spikes.md#own-rig-ragdoll
"""

import re
import struct
from collections import Counter
from pathlib import Path

from asset_convert.havok.kf_decode import split_root_motion
from fo4_import.havok import graph as G
from fo4_import.havok import packfile, packfile_write
from fo4_import.havok.kf_cache import decoded

#: The get-up clip raises ReevaluateGraphState here (the radroach's GetUp_Faceup).
REEVALUATE_AT = 0.43333330750465393
#: The death step's hold before it raises Ragdoll (0.3 s showed as a freeze).
RELEASE_AT = 0.05
#: Vanilla's RangedAttack state ends AttackEnd this far before the clip's end.
RANGED_END = -0.2
#: Seconds the blend into an attack takes; a gun fires no sooner, its arm then raised.
ATTACK_BLEND = 0.1
#: FNV text keys a gun clip fires on: Hit, and Fire (an attack loop's start: the fire ant's flame).
SHOT_KEYS = ('hit', 'fire')
#: The robots' combat idle raises these (its arm attacks blend over it, so they hold while it fires).
READY_ENTER, READY_EXIT = ('ReadyState', 'Enter'), ('ReadyState', 'Exit')
#: The event FO4 fires an actor's gun on (a robot clip's weaponFire.<slot> annotation: the slot its payload).
FIRE = 'weaponFire'
#: The talk clip role (the idle without one); the robots' DialogueBehavior answers these events (ActionTalking).
TALK, TALK_EVENTS = 'Talk', (('dyn_talkGeneric', ()), ('dyn_Talk', ('StartVoice', 'PCapEnter')))
#: The events that end a talk state (DialogueBehavior's DynamicAnim and PCapDynamicAnim).
TALK_END = ('00NextClip', 'idleStop', 'InstantExitClip')
#: The engine's variables, registered first so their initial values stick.
CONTRACT = [('bGraphDriven', G.BOOL, 1), ('bGraphDrivenTranslation', G.BOOL, 1), ('bGraphDrivenRotation', G.BOOL, 0),
            ('bAnimationDriven', G.BOOL, 0), ('bAllowRotation', G.BOOL, 0), ('bEquipOk', G.BOOL, 1),
            ('IsAttackReady', G.BOOL, 1), ('IsSprinting', G.BOOL, 0), ('bSupportedDeathAnim', G.BOOL, 0),
            ('bManualGraphChange', G.BOOL, 0), ('bAimActive', G.BOOL, 0), ('iState', G.INT32, 0)]
CONTRACT_AFTER = [('iSyncTurnState', G.INT32, 1), ('iIsInSneak', G.INT32, 0), ('Speed', G.REAL, 0.0),
                  ('SpeedSmoothed', G.REAL, 0.0), ('TurnDeltaSmoothed', G.REAL, 0.0), ('Direction', G.REAL, 0.0),
                  ('weaponSpeedMult', G.REAL, 1.0), ('camerafromx', G.REAL, 0.0), ('camerafromy', G.REAL, 0.0),
                  ('camerafromz', G.REAL, 0.0), ('iCombatState', G.INT32, 0), ('iSyncIdleLocomotion', G.INT32, 0)]
ROOT_WILDCARDS = [('Ragdoll', 1), ('RagdollInstant', 1), ('g_InitializeGraph', 0), ('g_InitializeGraphInstant', 0),
                  ('DeathAnimation', 3)]
#: The event a gun's fire IDLE sends, per equip slot (the robots' rightArmFireSingle and the like).
FIRE_START = 'rangedAttackStart{}'
LIMP = {'maxForce': 0.0, 'tau': 0.8, 'damping': 1.0, 'proportionalRecoveryVelocity': 2.0,
        'constantRecoveryVelocity': 1.0}


def shot_times(text_keys: list) -> list:
    """A gun clip's shots: its SHOT_KEYS `text_keys`, none before ATTACK_BLEND.
    See: docs/fork/fo4_own_rig.md#ranged
    """
    return [max(t, ATTACK_BLEND) for t, key in text_keys if key.strip().lower() in SHOT_KEYS]


def fire_start(slot: int) -> str:
    """The event starting the attack of the gun in equip slot `slot`."""
    return FIRE_START.format(slot)


class Builder:
    """Builds one creature's root graph from its rig entry, its FNV clips and its skeleton.nif's ragdoll bones."""

    def __init__(self, rig, fnv_dir: Path, ragdoll: dict, sounds, bones: list = ()):
        """`ragdoll`: skeleton.nif's {bone: ragdoll index}; `sounds`: a RigSounds; `bones`: the skeleton's bones
        (assets.skeleton_bones), for the arm layer's weights."""
        self.rig, self.fnv_dir, self.ragdoll, self.sounds = rig, fnv_dir, ragdoll, sounds
        self.bones = list(bones)
        self.g = G.Graph(f'{rig.project}RootBehavior')
        self.uses = Counter()

    def fnv(self, role: str):
        return decoded(str(self.fnv_dir / self.rig.clips[role]))[0]

    def root_speed(self, role: str) -> float:
        """Units per second the FNV clip's root travels; 0 for a clip with no root motion (an immobile creature's
        idle in every movement role)."""
        clip = self.fnv(role)
        motion = split_root_motion(clip)
        if motion is None or motion.get('translations') is None:
            return 0.0
        travel = motion['translations'][-1] - motion['translations'][0]
        return float((travel ** 2).sum() ** 0.5) / clip.duration

    def triggers(self, role: str, cyclic: bool) -> list:
        """FO4 events from the FNV clip's text keys: hits, footfalls (synced on cycles) and sounds."""
        out = []
        for t, key in self.fnv(role).text_keys:
            k = key.strip()
            if k.lower() == 'hit' and role not in {gun[0] for gun in self.rig.guns}:
                out += [(max(0.0, t - 0.2), 'preHitFrame', False), (max(0.0, t - 0.1), 'weaponSwing', False),
                        (t, 'HitFrame', False)]
            elif k in ('Enum: Left', 'Enum: Right', 'Enum: BackLeft', 'Enum: BackRight'):
                side = 'Left' if k.endswith('Left') else 'Right'
                out += [(t, f'Foot{side}', False)] + ([(t, f'Sync{side}', False)] if cyclic else [])
            sound = self.sounds.of(k)
            out += [(t, sound, False)] if sound else []
        return sorted(out)

    def clip(self, role: str, mode: int, extra=()) -> str:
        """A clip generator on `role`'s animation; a second use of the role is named `<role>_2` and so on."""
        self.uses[role] += 1
        node = self.g.clip(role, f'Animations\\{role}.hkt', mode,
                           self.triggers(role, mode == G.LOOPING) + list(extra))
        if self.uses[role] > 1:
            self.g.get(node)['name'] = f'{role}_{self.uses[role]}'
        return node

    def standing(self, prefix: str, idle: str, talks: bool = False) -> str:
        """Idle and in-place turns (TurnRight 0, Idle 1, TurnLeft 2), starting where iSyncTurnState says; with
        `talks`, the talk states (talking())."""
        g = self.g
        fx = g.blend_effect(f'{prefix}TurnBlend', 0.2)
        states = [g.state(0, 'TurnRight', self.clip('TurnRight', G.LOOPING), to=[('turnStop', 1), ('turnLeft', 2)],
                          effect=fx),
                  g.state(1, 'Idle', self.clip(idle, G.LOOPING), to=[('turnLeft', 2), ('turnRight', 0)], effect=fx),
                  g.state(2, 'TurnLeft', self.clip('TurnLeft', G.LOOPING), to=[('turnStop', 1), ('turnRight', 0)],
                          effect=fx)]
        talk, wildcard = self.talking(idle, fx) if talks else ([], ())
        start = g.bindings([('startStateId', ('iSyncTurnState', G.INT32, 1))])
        return g.machine(f'{prefix}StandingSM', states + talk, 1, wildcard=wildcard, effect=fx, binding=start)

    def talking(self, idle: str, fx: str) -> tuple:
        """(states, wildcard transitions) of the talk states, as the robots' DialogueBehavior: dyn_talkGeneric
        (an ActionTalking IDLE) and dyn_Talk (dyn_Talk's raising StartVoice) each enter one playing the talk clip,
        left on TALK_END.
        See: docs/fork/fo4_own_rig.md#talk
        """
        role = TALK if TALK in self.rig.clips else idle
        states = [self.g.state(3 + i, f'Talk{i}', self.clip(role, G.LOOPING), enter=enter,
                               to=[(end, 1) for end in TALK_END], effect=fx)
                  for i, (_, enter) in enumerate(TALK_EVENTS)]
        return states, [(event, 3 + i) for i, (event, _) in enumerate(TALK_EVENTS)]

    def moving(self, prefix: str) -> str:
        """Walk and run forward blended on Speed at their FNV root speeds."""
        kids = [(self.clip('WalkForward', G.LOOPING), self.root_speed('WalkForward')),
                (self.clip('RunForward', G.LOOPING), self.root_speed('RunForward'))]
        return self.g.blend(f'{prefix}MoveBlend', kids, 'Speed', G.FLAG_SYNC | G.FLAG_PARAMETRIC)

    def locomotion(self, prefix: str, idle: str, talks: bool = False) -> str:
        """Standing (0) and moving (1), starting where iSyncIdleLocomotion says; standing() with `talks`."""
        g = self.g
        fx = g.blend_effect(f'{prefix}MoveTransition', 0.2)
        states = [g.state(0, 'Standing', self.standing(prefix, idle, talks), to=[('moveStart', 1)], effect=fx),
                  g.state(1, 'Moving', self.moving(prefix), to=[('moveStop', 0)], effect=fx)]
        start = g.bindings([('startStateId', ('iSyncIdleLocomotion', G.INT32, 0))])
        return g.machine(f'{prefix}LocomotionSM', states, 0, binding=start)

    def attack(self, sid: int, role: str, fx: str) -> str:
        """One attack state: the clip under bAnimationDriven, AttackEnd back to combat locomotion; leaving raises
        attackStop and startAnimationDriven (vanilla's shared core)."""
        g = self.g
        driven = g.is_active(f'{role}_AnimDriven', ['bAnimationDriven'])
        body = g.with_modifiers(role, [driven], self.clip(role, G.SINGLE, [(-0.1, 'AttackEnd', True)]))
        return g.state(sid, role, body, exit_=('attackStop', 'startAnimationDriven'), to=[('AttackEnd', 0)],
                       effect=fx)

    def ranged(self, sid: int, gun: tuple, moving: str, fx: str) -> str:
        """Gun `gun`'s (role, slot, bones, fire node) attack state, as the shared core's RangedAttack: its clip over `moving` on
        its bones (layered()), firing its slot by its triggers (fire_triggers), not animation driven;
        AttackState<slot> Enter and Exit around it.
        See: docs/fork/fo4_own_rig.md#ranged
        """
        role, slot, bones, _ = gun
        body = self.layered(f'{role}Layer', moving,
                            self.clip(role, G.SINGLE, [self.ranged_end(role), *self.fire_triggers(role, slot)]), bones)
        state = f'AttackState{slot}'
        return self.g.state(sid, role, body, enter=((state, 'Enter'),),
                            exit_=((state, 'Exit'), 'startAnimationDriven'), to=[('AttackEnd', 0)], effect=fx)

    def arm_layer(self, moving: str, fx: str) -> str:
        """`moving` with the gun attacks layered over its guns' bones, as the robots' arm attacks over their combat
        locomotion: an arm machine idling on `moving` itself, entering each gun's ranged() on its fire_start(slot)
        from anywhere and leaving on AttackEnd, READY_ENTER on each return (FO4 fires once per ReadyState).
        See: docs/fork/fo4_own_rig.md#ranged
        """
        g = self.g
        guns = list(enumerate(self.rig.guns, 1))
        states = [self.ranged(sid, gun, moving, fx) for sid, gun in guns]
        arm = g.machine('ArmAttack', [g.state(0, 'ArmIdle', moving, enter=(READY_ENTER,)), *states], 0,
                        wildcard=[(fire_start(gun[1]), sid) for sid, gun in guns], effect=fx)
        return self.layered('CombatLayers', moving, arm, [b for gun in self.rig.guns for b in gun[2]])

    def layered(self, name: str, under: str, over: str, bones) -> str:
        """`over` on `bones`' subtrees (layer_weights), `under` elsewhere."""
        weights = self.layer_weights(bones)
        return self.g.layered(name, [(under, [1.0 - w for w in weights], 1.0), (over, weights, 0.0)])

    def layer_weights(self, names) -> list:
        """Per skeleton bone, 1 inside the subtrees of bones `names` (every bone without any), else 0."""
        inside = []
        for bone in self.bones:
            parent = inside[bone.parent] if bone.parent >= 0 else False
            inside.append(parent or not names or bone.name in names)
        return [1.0 if b else 0.0 for b in inside]

    def shots(self, role: str) -> list:
        """The times gun clip `role` fires (shot_times)."""
        return shot_times(self.fnv(role).text_keys)

    def fire_triggers(self, role: str, slot: int) -> list:
        """FIRE at each of gun clip `role`'s shots(), payload equip slot `slot`."""
        return [(t, (FIRE, str(slot)), False) for t in self.shots(role)]

    def ranged_end(self, role: str) -> tuple:
        """AttackEnd RANGED_END before gun clip `role`'s end, but after its last shot.
        See: docs/fork/fo4_own_rig.md#ranged
        """
        clip = self.fnv(role)
        last = max(self.shots(role), default=0.0)
        return max(clip.duration + RANGED_END, (last + clip.duration) / 2), 'AttackEnd', False

    def combat(self) -> str:
        """Combat locomotion (under the arm layer when the rig has guns) going to each attack state on its melee
        event, under IsAttackReady; READY_ENTER on each return to it."""
        g = self.g
        fx = g.blend_effect('AttackBlend', ATTACK_BLEND)
        to_attacks = [(attack[0], sid) for sid, attack in enumerate(self.rig.attacks.values(), 1)]
        moving = self.locomotion('Combat', 'CombatIdle')
        moving = self.arm_layer(moving, fx) if self.rig.guns else moving
        states = [g.state(0, 'CombatLocomotion', moving, enter=(READY_ENTER,), to=to_attacks, effect=fx)]
        states += [self.attack(sid, role, fx) for sid, role in enumerate(self.rig.attacks, 1)]
        machine = g.machine('CombatSM', states, 0)
        return g.with_modifiers('Combat', [g.is_active('AttackReady', ['IsAttackReady'])], machine)

    def creature(self) -> str:
        """DefaultSM: non-combat (0) and combat (1), synced to iCombatState, bEquipOk while active."""
        g = self.g
        fx = g.blend_effect('EquipBlend', 0.3)
        states = [g.state(0, 'NonCombat', self.locomotion('NonCombat', 'Idle', True), enter=('weaponSheathe',),
                          to=[('weapEquip', 1)], effect=fx),
                  g.state(1, 'Combat', self.combat(), enter=('weaponDraw', READY_ENTER), exit_=(READY_EXIT,),
                          to=[('weapUnequip', 0)], effect=fx)]
        default = g.machine('DefaultSM', states, 0, binding=g.bindings([('isActive', ('bEquipOk', G.BOOL, 1))]))
        g.get(default).update(startStateMode=1, syncVariableIndex=g.var('iCombatState', G.INT32, 0))
        return default

    def ragdoll_and_getup(self) -> str:
        """RagdollAndGetUp (1): Fully Ragdoll (2) and GetUpFromRagdoll (6) on one pose matcher; GetUpEnd on leaving.
        See: docs/fork/fo4_spikes.md#own-rig-ragdoll
        """
        g = self.g
        pelvis, chest, arm = (self.ragdoll[b] for b in self.rig.pose_bones)
        limp = g.add('hkbPoweredRagdollControlsModifier', name='Powered Ragdoll No Matching', enable=1, userData=1,
                     controlData=dict(LIMP), bones=g.add('hkbBoneIndexArray', boneIndices=[]),
                     boneWeights=g.add('hkbBoneWeightArray', boneWeights=[]),
                     worldFromModelModeData={'poseMatchingBone0': pelvis, 'poseMatchingBone1': chest,
                                             'poseMatchingBone2': arm, 'mode': 4})
        timer = g.add('hkbTimerModifier', name='GetUpTimerModifier', enable=1, alarmTimeSeconds=0.5,
                      alarmEvent=g.payload('GetUpStart'))
        armed = g.add('hkbEventDrivenModifier', name='EnableGetUp_EDM', enable=1, userData=1, modifier=timer,
                      activateEventId=g.ev('GetUpBegin'), deactivateEventId=g.ev('EnterFullyRagdoll'),
                      activeByDefault=0)
        matcher = self.pose_matcher(pelvis, chest, arm)
        pose = g.with_modifiers('FullyRagdoll', [limp, armed], matcher)
        fx = g.blend_effect('GetUpBlend', 0.2)
        enter = ('RemoveCharacterControllerFromWorld', 'AddRagdollToWorld', 'EnterFullyRagdoll')
        inner = [g.state(2, 'Fully Ragdoll', pose, enter=enter, to=[('GetUpStart', 6)], effect=fx),
                 g.state(6, 'GetUpFromRagdoll', matcher)]
        machine = g.machine('RagdollAndGetUpSM', inner, 2, wildcard=[('Ragdoll', 2)],
                            effect=g.blend_effect('InstantBlend', 0.0))
        return g.state(1, 'RagdollAndGetUp', machine, exit_=('GetUpEnd',))

    def pose_matcher(self, pelvis: int, chest: int, arm: int) -> str:
        """A pose matcher on the Idle clip: matches on EnterFullyRagdoll, plays it on GetUpStart."""
        g = self.g
        clip = g.clip('GetUp_Faceup', 'Animations\\Idle.hkt', G.SINGLE, [(REEVALUATE_AT, 'ReevaluateGraphState', False)])
        child = g.add('hkbBlenderGeneratorChild', generator=clip, boneWeights=g.add('hkbBoneWeightArray', boneWeights=[]),
                      weight=1.0, worldFromModelWeight=1.0)
        return g.add('hkbPoseMatchingGenerator', name='Reanimate Pose Matcher', maxCyclicBlendParameter=1.0,
                     indexOfSyncMasterChild=-1, children=[child], worldFromModelRotation=(0.0, 0.0, 0.0, 1.0),
                     blendSpeed=1.0, minSpeedToSwitch=0.2, minSwitchTimeNoError=0.2,
                     startPlayingEventId=g.ev('GetUpStart'), startMatchingEventId=g.ev('EnterFullyRagdoll'),
                     rootBoneIndex=pelvis, otherBoneIndex=chest, anotherBoneIndex=arm, pelvisIndex=pelvis, mode=0)

    def death(self) -> str:
        """DeathAnimation (3): the ragdoll added and keyframed to a CombatIdle hold, bAnimationDriven and
        bSupportedDeathAnim held, Ragdoll raised after RELEASE_AT (the template race's death contract).
        See: docs/fork/fo4_spikes.md#own-rig-ragdoll
        """
        g = self.g
        keyframe = g.add('hkbKeyframeBonesModifier', name='KeyframeFullRagdoll', enable=1, userData=1,
                         keyframeInfo=[], keyframedBonesList=g.add('hkbBoneIndexArray',
                                                                   boneIndices=list(range(len(self.ragdoll)))))
        active = g.is_active('DeathAnimation_IsActiveModifier', ['bAnimationDriven', 'bSupportedDeathAnim'])
        cry = [(0.0, self.sounds.death, False)] if self.sounds.death else []
        hold = g.clip('DeathHold', 'Animations\\CombatIdle.hkt', G.SINGLE, [(RELEASE_AT, 'Ragdoll', False)] + cry)
        mods = g.add('hkbModifierList', name='DeathModifierList', enable=1, userData=1, modifiers=[keyframe, active])
        body = g.add('hkbModifierGenerator', name='Death_MG', userData=1, generator=hold, modifier=mods)
        return g.state(3, 'DeathAnimation', body, enter=('AddRagdollToWorld',))

    def build(self, template_names: tuple) -> G.Graph:
        """The finished root graph; `template_names` is (events, variables) to carry after its own."""
        g = self.g
        for v in CONTRACT + [(f'iState_{self.rig.project}', G.INT32, 0)] + CONTRACT_AFTER:
            g.var(*v)
        states = [g.state(0, 'Creature', self.creature()), self.ragdoll_and_getup(), self.death()]
        machine = g.machine('Root', states, 0, ROOT_WILDCARDS, g.blend_effect('InstantBlend', 0.0))
        events, variables = template_names
        mine = {v[0] for v in g.variables}
        return g.finish(machine, events=[e for e in events if e not in g.events],
                        variables=[v for v in variables if v[0] not in mine])


def template_names(behavior: bytes, project: str) -> tuple:
    """(events, (name, type, initial value) variables) of a template root graph, without another creature's
    iState_<name> link (two links sharing value 0 make the game pick a movement type at random)."""
    pf = packfile.read(behavior)
    found = {o['class']: o['fields'] for o in pf.objects}
    s, d, v = (found[c] for c in ('hkbBehaviorGraphStringData', 'hkbBehaviorGraphData', 'hkbVariableValueSet'))
    variables = []
    for name, info, w in zip(s['variableNames'], d['variableInfos'], v['wordVariableValues']):
        if name.lower().startswith('istate_') and name != f'iState_{project}':
            continue
        raw = w['value']
        variables.append((name, info['type'], struct.unpack('<f', struct.pack('<i', raw))[0] if info['type'] == G.REAL
                          else raw))
    return s['eventNames'], variables


def bone_pairs(names: list) -> list:
    """Mirror map: each bone to its L/R counterpart by name, else itself."""
    index = {n: i for i, n in enumerate(names)}
    swap = lambda n: re.sub(r'\b([LR])\b', lambda m: 'R' if m.group(1) == 'L' else 'L', n)
    return [index.get(swap(n), i) for i, n in enumerate(names)]


def character(template: bytes, rig, bone_names: list) -> bytes:
    """The template character re-pointed at the creature: rig, root behaviour, clip list, mirror map."""
    pf = packfile.read(template)
    by = {o['#']: o['fields'] for o in pf.objects}
    data = next(o['fields'] for o in pf.objects if o['class'] == 'hkbCharacterData')
    data['characterPropertyInfos'] = []
    values = by[data['characterPropertyValues']]
    values['wordVariableValues'], values['variantVariableValues'] = [], []
    by[data['stringData']].update(
        skinNames=[{'fileName': 'CharacterAssets\\Skeleton.hkt', 'meshName': rig.project}],
        animationBundleNameData=[{'bundleName': None, 'assetNames': [f'Animations\\{c}.hkt' for c in rig.clips]}],
        characterPropertyNames=[], name=f'{rig.project}Character',
        behaviorFilename=f'Behaviors\\{rig.project}RootBehavior.hkx')
    by[data['mirroredSkeletonInfo']]['bonePairMap'] = bone_pairs(bone_names)
    objects = [o for o in pf.objects if o['class'] != 'hkbBoneWeightArray']
    return packfile_write.write(objects, objects[0]['#'])


def project(template: bytes, rig) -> bytes:
    """The template project naming the creature's character."""
    pf = packfile.read(template)
    next(o['fields'] for o in pf.objects if o['class'] == 'hkbProjectStringData')['characterFilenames'] = [
        f'Characters\\{rig.project}Character.hkx']
    return packfile_write.write(pf.objects, pf.objects[0]['#'])
