"""The game a run emits Papyrus for: Skyrim (the default) or Fallout 4.

Set once per run and inherited by every process spawned after it, through
the environment, as the asset namespace is. The converter keeps Skyrim's
spelling internally (event headers are also merge keys); each construct that
differs asks here for the target's spelling where it is written out.

See: docs/fork/fo4_spikes.md#spike-3-target
"""

import os

from script_convert.constants import FALLOUT4_AV_NATIVES, FALLOUT4_EVENTS

SKYRIM, FALLOUT4 = 'skyrim', 'fallout4'
TARGET_ENV = 'TES4SKYRIM_PAPYRUS_TARGET'

#: Fallout 4 delivers OnHit once per RegisterForHitEvent, so it is armed at start and again on each hit.
HIT_REGISTRATION = 'RegisterForHitEvent(Self)'
#: Prefix of the ActorValue property a Fallout 4 script declares per actor value it names.
AV_PROPERTY_PREFIX = 'TES4AV_'
#: Property and script of the helper quest holding the one InputEnableLayer all scripts share.
CONTROLS_PROPERTY, CONTROLS_SCRIPT = 'TES4PlayerControls', 'TES4_PlayerControls'


def set_target(name: str) -> None:
    """Make `name` the target here and in every process spawned from here on."""
    if name not in (SKYRIM, FALLOUT4):
        raise ValueError(f'unknown Papyrus target {name!r}')
    os.environ[TARGET_ENV] = name


def is_fallout4() -> bool:
    """True when this run emits Fallout 4 Papyrus."""
    return os.environ.get(TARGET_ENV) == FALLOUT4


def event_opener(skyrim_opener: str) -> str:
    """The target's spelling of an event opener given in Skyrim's."""
    return FALLOUT4_EVENTS.get(skyrim_opener, skyrim_opener) if is_fallout4() else skyrim_opener


def is_hit_event(skyrim_opener: str) -> bool:
    """True for Skyrim's OnHit opener."""
    return skyrim_opener.startswith('Event OnHit(')


def arm_update(secs: str, receiver: str = '') -> str:
    """Schedule the next poll pass: RegisterForSingleUpdate, or Fallout 4's StartTimer."""
    native = 'StartTimer' if is_fallout4() else 'RegisterForSingleUpdate'
    return f'{receiver}{native}({secs})'


def av_property(av: str) -> str:
    """The ActorValue property a Fallout 4 script reads actor value `av` through."""
    return AV_PROPERTY_PREFIX + av


def av_call(native: str, av: str, args: tuple = ()) -> tuple:
    """(call, {property: type}) for a Skyrim actor-value native on actor value `av`.

    Skyrim `GetActorValue("Health")`; Fallout 4 `GetValue(TES4AV_Health)`,
    the actor value as a form property.
    """
    if not is_fallout4():
        quoted = f'"{av}"'
        return f'{native}({", ".join((quoted,) + tuple(args))})', {}
    prop = av_property(av)
    return f'{FALLOUT4_AV_NATIVES[native]}({", ".join((prop,) + tuple(args))})', {prop: 'ActorValue'}


def anim_event_call(ref: str, event: str) -> str:
    """Send animation event `event` to `ref` (Fallout 4: PlayAnimation)."""
    if is_fallout4():
        return f'{ref}.PlayAnimation("{event}")'
    return f'Debug.SendAnimationEvent({ref}, "{event}")'


def controls_call(verb: str, args: str) -> tuple:
    """(call, {property: type}) toggling controls; FO4 via the shared layer."""
    if not is_fallout4():
        return f'Game.{verb}PlayerControls({args})', {}
    return f'{CONTROLS_PROPERTY}.{verb}({args})', {CONTROLS_PROPERTY: CONTROLS_SCRIPT}


def run_update_now() -> str:
    """Run one poll pass right away: the poll event called as a function."""
    return 'OnTimer(0)' if is_fallout4() else 'OnUpdate()'
