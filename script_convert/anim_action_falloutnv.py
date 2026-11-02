"""FO3/FNV GetAnimAction on Fallout 4: an actor's attack, heard from its attack graph events.

Fallout 4 has no anim-action read, so a script that asks for one gets
TES4_AnimAction(<actor>): it registers the script for the actor's attack
events (again whenever the actor's 3D loads) and reads ANIM_ACTION_ATTACK
from an attack's start until its end event, or ATTACK_SECONDS after its last
start when none comes, else none. An attack that ended before
any read is still read for one pass (PASS_SECONDS from its first read), so a
polling script cannot miss a short one and a condition reading it twice agrees.
See: docs/fork/script_markers.md#getanimaction
"""

from script_convert.blocks import FALLOUT4_BLOCK_MAP
from script_convert.target import is_fallout4

#: FO4 graph events starting an attack: a gun's shot, a melee hit frame, a melee swing (vanilla's assaultron cloak).
ATTACK_STARTS = ('weaponFire', 'HitFrame', 'weaponSwing')
#: FO4 graph events ending one: melee's attack stop, a gun's return to ready.
ATTACK_ENDS = ('attackStop', 'AttackEnd', 'readyState')
#: Real seconds after its last start an attack ends with no end event (longest seen: 1.8, shot to ready).
ATTACK_SECONDS = '2.0'
#: GetAnimAction's ANIM_ACTION_ATTACK and its "none" (GECK).
ATTACK, NONE = 2, -1
#: The read the call converts to.
READ = 'TES4_AnimAction'
#: Real seconds an ended attack stays readable after its first read: the rest of that pass, never the next poll.
PASS_SECONDS = '0.1'


def anim_action(ctx, call):
    """`[actor.]GetAnimAction` on Fallout 4: TES4_AnimAction(<actor>); declines elsewhere (the row's inert 0)."""
    if not is_fallout4():
        return None
    ctx.sc.uses_anim_action = True
    return f'{READ}({ctx._resolve_objref_ref(call.ref, call.extends)})'


def _any_of(names: tuple) -> str:
    """A test that the event is one of `names`."""
    return ' || '.join(f'asEventName == "{name}"' for name in names)


def listen(conv, merged: dict, order: list) -> list:
    """Declarations and TES4_AnimAction for a script that reads GetAnimAction; its OnAnimationEvent lines go into
    `merged` (beside an OnFire body's). [] for any other script."""
    if not conv.sc.uses_anim_action:
        return []
    header = FALLOUT4_BLOCK_MAP['onfire']
    if header not in merged:
        merged[header] = []
        order.append(header)
    merged[header] += ['  If akSource == TES4_AnimSource',
                       f'    If {_any_of(ATTACK_ENDS)}',
                       '      TES4_AnimEnded = True',
                       f'    ElseIf {_any_of(ATTACK_STARTS)}',
                       f'      TES4_AnimAct = {ATTACK}',
                       '      TES4_AnimStartedAt = Utility.GetCurrentRealTime()',
                       '      TES4_AnimEnded = False',
                       '      TES4_AnimSeenAt = 0.0',
                       '    EndIf',
                       '  EndIf']
    registers = [f'      RegisterForAnimationEvent(akRef, "{name}")' for name in ATTACK_STARTS + ATTACK_ENDS]
    return ['ObjectReference TES4_AnimSource', 'Bool TES4_AnimLoaded', f'Int TES4_AnimAct = {NONE}',
            'Bool TES4_AnimEnded', 'Float TES4_AnimSeenAt', 'Float TES4_AnimStartedAt', '',
            f'Int Function {READ}(ObjectReference akRef)',
            '  {FNV GetAnimAction on akRef: 2 (attack) from its attack events, held until read; else -1.}',
            '  Bool loaded = akRef && akRef.Is3DLoaded()',
            '  If akRef != TES4_AnimSource || loaded != TES4_AnimLoaded',
            '    TES4_AnimSource = akRef',
            '    TES4_AnimLoaded = loaded',
            f'    TES4_AnimAct = {NONE}',
            '    If loaded',
            *registers,
            '    EndIf',
            '  EndIf',
            '  Float now = Utility.GetCurrentRealTime()',
            f'  If TES4_AnimAct == {ATTACK} && !TES4_AnimEnded && (now - TES4_AnimStartedAt >= {ATTACK_SECONDS} '
            '|| now < TES4_AnimStartedAt)',
            '    TES4_AnimEnded = True',
            '  EndIf',
            f'  If TES4_AnimEnded && TES4_AnimSeenAt > 0.0 && (now - TES4_AnimSeenAt >= {PASS_SECONDS} || now < TES4_AnimSeenAt)',
            f'    TES4_AnimAct = {NONE}',
            '    TES4_AnimEnded = False',
            '    TES4_AnimSeenAt = 0.0',
            '  ElseIf TES4_AnimEnded && TES4_AnimSeenAt == 0.0',
            '    TES4_AnimSeenAt = now',
            '  EndIf',
            '  Return TES4_AnimAct',
            'EndFunction', '']
