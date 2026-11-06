"""The game a run emits Papyrus for: Skyrim (the default) or Fallout 4.

Set once per run and inherited by every process spawned after it, through
the environment, as the asset namespace is. The converter keeps Skyrim's
spelling internally (event headers are also merge keys); each construct that
differs asks here for the target's spelling where it is written out.

See: docs/fork/fo4_spikes.md#spike-3-target
"""

import os

from script_convert.constants import (FALLOUT4_ACTOR_VALUE_IDS, FALLOUT4_AV_NATIVES, FALLOUT4_EVENTS,
                                      FALLOUT4_FALLOUT_AV_RENAMES, FALLOUT4_HELPER_AV_ALIASES,
                                      FALLOUT4_HELPER_AVS, FALLOUT4_HELPER_PLUGIN, FALLOUT4_MENU_NAMES,
                                      TALKING_ACTIVATOR)

SKYRIM, FALLOUT4 = 'skyrim', 'fallout4'
TARGET_ENV = 'TES4SKYRIM_PAPYRUS_TARGET'

#: Fallout 4 delivers OnHit once per RegisterForHitEvent, so it is armed at start and again on each hit.
HIT_REGISTRATION = 'RegisterForHitEvent(Self)'
#: Prefix of the ActorValue property a Fallout 4 script declares per actor value it names.
AV_PROPERTY_PREFIX = 'TES4AV_'
#: Property and script of the helper quest holding the one InputEnableLayer all scripts share.
CONTROLS_PROPERTY, CONTROLS_SCRIPT = 'TES4PlayerControls', 'F3NV_PlayerControls'
#: Property and script of the helper quest sending the character menus and holding suggested tag skills.
CHARACTER_PROPERTY, CHARACTER_SCRIPT = 'TES4CharacterEvents', 'F3NV_CharacterEvents'


def set_target(name: str) -> None:
    """Make `name` the target here and in every process spawned from here on."""
    if name not in (SKYRIM, FALLOUT4):
        raise ValueError(f'unknown Papyrus target {name!r}')
    os.environ[TARGET_ENV] = name


def is_fallout4() -> bool:
    """True when this run emits Fallout 4 Papyrus."""
    return os.environ.get(TARGET_ENV) == FALLOUT4


def on_talking_activator(conv) -> bool:
    """Whether `conv`'s script is attached to an FO3/FNV talking activator, on Fallout 4, where the game's own
    activation of one opens no greeting (TES4Polyfill.TalkerActivate does).
    See: docs/fork/fo4_pipeline.md#talking-activators
    """
    xref, edid = conv.xref, conv.sc.edid
    return is_fallout4() and bool(xref and edid) and any(
        xref.record_type.get(fid) == TALKING_ACTIVATOR for fid in xref.script_owner_actors(edid))


def event_opener(skyrim_opener: str) -> str:
    """The target's spelling of an event opener given in Skyrim's; Fallout 4's OnDeath and OnHit also trace the
    event (trace_points), OnHit also starting the hit reference's graph event trace (TraceAnimEvents)."""
    if not is_fallout4():
        return skyrim_opener
    trace = {'Event OnDeath(': '\n  TES4Polyfill.TraceDeath(Self, akKiller)',
             'Event OnHit(': '\n  TES4Polyfill.TraceHit(akTarget, akAggressor, akSource)'
                             '\n  TES4Polyfill.TraceAnimEvents(Self, akTarget)'}
    return FALLOUT4_EVENTS.get(skyrim_opener, skyrim_opener) + next(
        (line for opener, line in trace.items() if skyrim_opener.startswith(opener)), '')


def is_hit_event(skyrim_opener: str) -> bool:
    """True for Skyrim's OnHit opener."""
    return skyrim_opener.startswith('Event OnHit(')


def arm_update(secs: str, receiver: str = '') -> str:
    """Schedule the next poll pass: RegisterForSingleUpdate, or Fallout 4's StartTimer."""
    native = 'StartTimer' if is_fallout4() else 'RegisterForSingleUpdate'
    return f'{receiver}{native}({secs})'


def fallout4_actor_values() -> dict:
    """{lower-case name: (canonical name, plugin, object id)} of every actor value a Fallout 4 script can name.

    Fallout4.esm's, then the helper plugin's (FO3/FNV skills and Variable01-10)
    under their own names and the Skyrim skill names the shared helpers use.
    """
    out = {n.lower(): (n, 'Fallout4.esm', fid) for n, fid in FALLOUT4_ACTOR_VALUE_IDS.items()}
    out.update({n.lower(): (n, FALLOUT4_HELPER_PLUGIN, fid) for n, fid in FALLOUT4_HELPER_AVS.items()})
    aliases = {**FALLOUT4_HELPER_AV_ALIASES, **FALLOUT4_FALLOUT_AV_RENAMES}
    out.update({a.lower(): out[n.lower()] for a, n in aliases.items()})
    return out


def fallout4_av_name(name: str) -> 'str | None':
    """On Fallout 4, the name of FO3/FNV actor value `name` (any case) where Skyrim's table would lose it."""
    if not is_fallout4():
        return None
    entry = fallout4_actor_values().get(name.lower())
    if entry is None or (entry[1] != FALLOUT4_HELPER_PLUGIN and name.lower() == entry[0].lower()):
        return None
    return entry[0]


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


def menu_registration(menu: str) -> str:
    """Listen for menu `menu` (Skyrim's name); FO4: its open/close event."""
    if is_fallout4():
        return f'RegisterForMenuOpenCloseEvent("{FALLOUT4_MENU_NAMES.get(menu, menu)}")'
    return f'RegisterForMenu("{menu}")'


def target_menu_name(menu: str) -> str:
    """The target's name for menu `menu` (Skyrim's name)."""
    return FALLOUT4_MENU_NAMES.get(menu, menu) if is_fallout4() else menu


def menu_close_guard() -> list:
    """Lines opening a menu-close body: Fallout 4's one event also fires on opening."""
    return ['  If abOpening', '    Return', '  EndIf'] if is_fallout4() else []


def sleep_registration(register: bool) -> str:
    """Start or stop the sleep events (FO4: RegisterForPlayerSleep)."""
    verb = 'Register' if register else 'Unregister'
    return f'{verb}ForPlayerSleep()' if is_fallout4() else f'{verb}ForSleep()'


def self_as_actor() -> str:
    """The script's own reference as an Actor (FO4 casts through ObjectReference)."""
    return '((Self as ObjectReference) as Actor)' if is_fallout4() else '(Self as Actor)'


def script_as_actor(name: str) -> str:
    """`name`, a property typed as a converted script, cast to Actor.
    See: docs/fork/fo4_pipeline.md#script-casts
    """
    return f'(({name} as ObjectReference) as Actor)' if is_fallout4() else f'({name} as Actor)'


def run_update_now() -> str:
    """Run one poll pass right away: the poll event called as a function."""
    return 'OnTimer(0)' if is_fallout4() else 'OnUpdate()'
