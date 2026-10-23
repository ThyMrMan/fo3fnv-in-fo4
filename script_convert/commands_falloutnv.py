"""FO3/FNV command handlers whose behaviour depends on the RECEIVER's record.

A row in `FALLOUT_COMMAND_ROWS` renders one template for every call site. A
handler belongs here only where FO3/FNV spell one command against two different
receiver types, or where its output names a property built from its arguments,
which a single template cannot express.

Exported as a plain table rather than through `commands.command`, so this module
imports nothing from `commands` and the two cannot form a cycle.

See: docs/commentary/script_convert.md#getfactionrelation-has-two-receivers
"""

from fo4_import.base.bink import movie_key
from script_convert.constants import FALLOUT4_POSE_PREFIX, fallout4_swap_property, safe_property_name, typed_already
from script_convert.message_menus import authored_site
from script_convert.target import (CHARACTER_PROPERTY, CHARACTER_SCRIPT, CONTROLS_PROPERTY, CONTROLS_SCRIPT, arm_update,
                                   av_property, fallout4_av_name, is_fallout4)
from tes5_import.record_types.equipment_falloutnv import WEAPON_ANIM_LISTS


def faction_relation(ctx, call):
    """`<x>.GetFactionRelation <actor>` -- reaction toward another actor.

    Declines (returns None) for an ACTOR receiver so the row renders the real
    `Actor.GetFactionReaction`; only the FACTION receiver is handled here,
    because Papyrus has no faction-toward-actor read at all.
    """
    ref = call.ref or ''
    fid = ctx.xref.edid_to_formid.get(ref.lower(), '') if ctx.xref else ''
    if not fid or ctx.xref.record_type.get(fid, '') != 'FACT':
        return None
    return ctx.note(f'NE: {ref}.GetFactionRelation - Papyrus has no '
                    f'faction-toward-actor reaction (read as 0)')


#: Quest natives FO4 ignores on a quest not running, where FO3/FNV kept the objective (StartForObjective first).
_OBJECTIVE_SETTERS = ('SetObjectiveDisplayed', 'SetObjectiveCompleted')
#: FO3/FNV command -> Quest native it becomes, the quest argument as receiver.
_QUEST_NATIVES = {
    'setobjectivedisplayed': 'SetObjectiveDisplayed',
    'setobjectivecompleted': 'SetObjectiveCompleted',
    'setobjectivefailed': 'SetObjectiveFailed',
    'getobjectivedisplayed': 'IsObjectiveDisplayed',
    'getobjectivecompleted': 'IsObjectiveCompleted',
    'getobjectivefailed': 'IsObjectiveFailed',
    'setquestdelay': 'RegisterForSingleUpdate',
}


#: FO3/FNV quest command -> the argument-less Quest native it becomes (ForceActiveQuest: the tracked quest).
_QUEST_CALLS = {'forceactivequest': 'SetActive', 'completeallobjectives': 'CompleteAllObjectives'}
#: Owner record type -> (Cell native setting it as owner, its property type).
_OWNER_SETTERS = {'FACT': ('SetFactionOwner', 'Faction'), 'NPC_': ('SetActorOwner', 'ActorBase')}


#: Quest EditorID (lower) -> frozenset of authored QOBJ indices, per process.
_QUEST_OBJECTIVES: dict = {}


def set_quest_objectives(index: dict) -> None:
    """Install the authored-objective index in this process."""
    _QUEST_OBJECTIVES.clear()
    _QUEST_OBJECTIVES.update(index)


def quest_objective_indices(by_type: dict) -> dict:
    """Quest EditorID (lower) -> frozenset of authored QOBJ indices.

    Only quests that author an Objective[] block appear; a quest absent from
    this map is never second-guessed.
    See: docs/commentary/script_convert.md#fnv-unknown-objective-index
    """
    out = {}
    for rec in by_type.get('QUST', []):
        edid = (rec.get('EditorID') or '').lower()
        count = rec.get('ObjectiveCount')
        if not edid or count is None:
            continue
        idx = set()
        for i in range(int(count or 0)):
            raw = rec.get(f'Objective[{i}].Index')
            if raw is not None:
                try:
                    idx.add(int(raw))
                except (TypeError, ValueError):
                    pass
        if idx:
            out[edid] = frozenset(idx)
    return out


def _unauthored_objective(quest_edid: str, index_src: str) -> bool:
    """True when this quest authors objectives but not THIS index.

    FO3/FNV scripts call objective indices their own quest never defines
    (nVPrimmDeputyConv polls 31 of an authored 10).  Fallout ignored the call;
    Skyrim logs "unknown quest objective N" on every one, and these sit in
    GameMode polls.  Unknown quest or non-literal index -> never suppressed.
    """
    authored = _QUEST_OBJECTIVES.get(quest_edid.lower())
    if not authored:
        return False
    src = (index_src or '').strip()
    return src.isdigit() and int(src) not in authored


def quest_native(ctx, call):
    """`<cmd> <quest> <args...>` -- Papyrus makes the quest the receiver.

    The quest property keeps a type it already has (a TES4_<script> class
    answers these natives and its variable reads need that type).
    See: docs/commentary/script_convert.md#fnv-objective-commands
    """
    parts = ctx.arg_srcs()
    if len(parts) < 2:
        return None
    quest_edid = parts[0].strip()
    native = _QUEST_NATIVES[call.name]
    if (native != 'RegisterForSingleUpdate'
            and _unauthored_objective(quest_edid, parts[1])):
        return ctx.note(f'{call.name} {quest_edid} {parts[1].strip()} - '
                        f'{quest_edid} authors no such objective')
    prop = safe_property_name(quest_edid)
    if not typed_already(ctx.sc.property_refs, prop):
        ctx.sc.property_refs[prop] = 'Quest'
    args = ', '.join(call.arg(i) for i in range(1, len(parts)))
    if native == 'RegisterForSingleUpdate':
        return _quest_delay(ctx, quest_edid, prop, args)
    started = (f'TES4Polyfill.StartForObjective({prop})\n  '
               if is_fallout4() and native in _OBJECTIVE_SETTERS else '')
    return f'{started}{prop}.{native}({args})' + _objective_mirror(ctx, call, quest_edid, parts)


def quest_call(ctx, call):
    """`<cmd> <quest>` -- the Quest native _QUEST_CALLS names, no arguments, on the quest."""
    parts = ctx.arg_srcs()
    if not parts:
        return None
    prop = safe_property_name(parts[0].strip())
    if not typed_already(ctx.sc.property_refs, prop):
        ctx.sc.property_refs[prop] = 'Quest'
    return f'{prop}.{_QUEST_CALLS[call.name]}()'


def cell_ownership(ctx, call):
    """`SetCellOwnership <cell> [owner]` -- Cell.SetFactionOwner for a faction, SetActorOwner for an NPC or, with
    no owner, the player (as FO3/FNV gave the cell to the player); None (a note) for any other owner."""
    parts = [p.strip() for p in ctx.arg_srcs()]
    if not parts:
        return None
    cell = safe_property_name(parts[0])
    ctx.sc.property_refs.setdefault(cell, 'Cell')
    if len(parts) < 2:
        return f'{cell}.SetActorOwner(Game.GetPlayer().GetActorBase())'
    fid = ctx.xref.edid_to_formid.get(parts[1].lower(), '') if ctx.xref else ''
    setter = _OWNER_SETTERS.get(ctx.xref.record_type.get(fid, '') if fid else '')
    if setter is None:
        return None
    owner = safe_property_name(parts[1])
    ctx.sc.property_refs.setdefault(owner, setter[1])
    return f'{cell}.{setter[0]}({owner})'


def _quest_delay(ctx, quest_edid: str, prop: str, secs: str) -> str:
    """SetQuestDelay: Fallout 4's quest script keeps the delay (assemble._quest_delay); else one poll after `secs`.
    See: docs/fork/performance.md#papyrus
    """
    script = ctx.xref.get_quest_script_type(quest_edid) if ctx.xref else 'Quest'
    if is_fallout4() and script != 'Quest':
        return f'{script}.TES4SetDelay({prop} as {script}, {secs})'
    return arm_update(secs, f'{prop}.')


def _mirror_values(name: str, flag: str, value: str) -> dict:
    """{state: Papyrus value} an objective command sets; completing also displays."""
    if name == 'setobjectivedisplayed':
        return {'Shown': value}
    return {'Done': value, **({'Shown': '1'} if flag not in ('0', '') else {})}


def _objective_mirror(ctx, call, quest_edid: str, parts: list) -> str:
    """The SetValue lines keeping this objective's condition globals in step, or ''.

    See: docs/commentary/tes5_import_conditions.md#fallout-objective-conditions
    """
    index = parts[1].strip()
    if call.name not in ('setobjectivecompleted', 'setobjectivedisplayed') or not index.isdigit():
        return ''
    globs = ctx.objective_globals.get((quest_edid.lower(), int(index)), {})
    flag = parts[2].strip() if len(parts) > 2 else '1'
    value = call.arg(2) if len(parts) > 2 else '1'
    out = ''
    for state, setting in _mirror_values(call.name, flag if flag.isdigit() else '', value).items():
        if state in globs:
            ctx.sc.property_refs.setdefault(globs[state], 'GlobalVariable')
            out += f'\n  {globs[state]}.SetValue({setting})'
    return out


def show_message(ctx, call):
    """`ShowMessage <MESG> ...` -- a buttoned MESG is a menu: Show() parks
    this thread and the pick feeds the script's GetButtonPressed poll.

    Declines (None) so the row renders a plain Show() unless the MESG is one
    of this script's planned button sites (message_menus.button_messages).
    See: docs/commentary/script_convert.md#fnv-showmessage-menus
    """
    name = authored_site(ctx.message_menus, ctx.sc.edid,
                         call.source(0).strip() if len(call) else '')
    if not name:
        return None
    mesg = safe_property_name(name)
    ctx.sc.property_refs[mesg] = 'Message'
    ctx.sc.uses_msg_buttons = True
    return f'TES4_MsgButton = TES4_ShowMsg({mesg})'


#: TES4 command name -> handler, merged into `commands.REGISTRY`.
def weapon_anim_type(ctx, call) -> str:
    """`<actor>.GetWeaponAnimType`: the Fallout animation type of the equipped weapon.

    Each type's weapons are a FormList the importer writes, so the value is
    the sum of each type times whether its list holds the weapon; no weapon
    reads 0, Hand to Hand, as in Fallout. Skyrim's own weapon types number
    differently (a converted rifle is a crossbow).
    See: docs/commentary/script_convert.md#fallout-weapon-anim-type
    """
    ref = ctx._convert_ref(call.ref, call.extends, as_receiver=True) if call.ref else 'Self'
    weapon = f'({ref} as Actor).GetEquippedWeapon()'
    for name in WEAPON_ANIM_LISTS.values():
        ctx.sc.property_refs[name] = 'FormList'
    terms = (f'{kind} * ({name}.HasForm({weapon}) as Int)' for kind, name in WEAPON_ANIM_LISTS.items())
    return '(' + ' + '.join(terms) + ')'


def _open_state_target(ctx, call) -> str:
    """The receiver of an open-state command, `Self` when bare."""
    return ctx._convert_ref(call.ref, call.extends, as_receiver=True) if call.ref else 'Self'


def get_open_state(ctx, call):
    """FO3/FNV GetOpenState, two-state activators included; declines elsewhere.

    See: docs/commentary/script_convert.md#two-state-activators
    """
    if not (ctx.xref and ctx.xref.is_fallout()):
        return None
    return f'TES4_TwoStateActivator.OpenState({_open_state_target(ctx, call)})'


def set_open_state(ctx, call):
    """FO3/FNV SetOpenState, two-state activators included; declines elsewhere."""
    if not (ctx.xref and ctx.xref.is_fallout()):
        return None
    arg = call.arg(0)
    state = {'0': 'false', '1': 'true'}.get(arg.strip(), f'({arg} != 0)')
    return f'TES4_TwoStateActivator.SetOpenState({_open_state_target(ctx, call)}, {state})'


def swap_texture(ctx, call):
    """FNV `SwapTexture <ref> "<node>" "<texture>"` on Fallout 4: TES4Polyfill.SwapMaterial (F4SE) with its MatSwap.

    The importer writes each MatSwap from the property's name (fallout4_swap_property); declines elsewhere.
    See: docs/fork/fo4_spikes.md#spike-2-vcg01
    """
    if not is_fallout4() or len(call) < (2 if call.ref else 3):
        return None
    first = 0 if call.ref else 1
    ref = _open_state_target(ctx, call) if call.ref else call.arg(0)
    prop = fallout4_swap_property(call.source(first).strip('"'), call.source(first + 1).strip('"'))
    ctx.sc.property_refs[prop] = 'MatSwap'
    return f'TES4Polyfill.SwapMaterial({ref}, {prop})'


def player_package(ctx, call):
    """FO3/FNV `player.AddScriptPackage <package>` / `RemoveScriptPackage` on Fallout 4: HoldPlayer / ReleasePlayer.

    FO4 runs no package on the player; the importer fills the `TES4Pose_<package>` ObjectReference property with
    the seat that package becomes, or leaves it empty. Declines for other receivers and targets.
    See: docs/fork/fo4_spikes.md#spike-2-vcg01
    """
    if not is_fallout4() or (call.ref or '').lower() not in ('player', 'playerref'):
        return None
    ctx.sc.property_refs[CONTROLS_PROPERTY] = CONTROLS_SCRIPT
    if call.name == 'removescriptpackage' or not len(call):
        return f'{CONTROLS_PROPERTY}.ReleasePlayer()'
    prop = FALLOUT4_POSE_PREFIX + safe_property_name(call.source(0).strip('"'))
    ctx.sc.property_refs[prop] = 'ObjectReference'
    return f'{CONTROLS_PROPERTY}.HoldPlayer({prop})'


def tag_skill(ctx, call):
    """FNV `IsPlayerTagSkill <skill>` and `SetPlayerTagSkill <skill> <slot>` on Fallout 4, on the skill's ActorValue:
    LevelUpMenuEx's IsTagSkillAV, and F3NV_CharacterEvents.SuggestTag (tagged ahead of the tag menu, which the
    player may still change; FNV's slot is the menu's order). The tag menu is LevelUpMenuEx's (F3NV_CharacterRules).
    See: docs/fork/fo4_spikes.md#spike-2-vcg01
    """
    if not is_fallout4() or not len(call):
        return None
    raw = call.source(0).strip('"')
    prop = av_property(fallout4_av_name(raw) or raw)
    ctx.sc.property_refs[prop] = 'ActorValue'
    if call.name == 'setplayertagskill':
        ctx.sc.property_refs[CHARACTER_PROPERTY] = CHARACTER_SCRIPT
        return f'{CHARACTER_PROPERTY}.SuggestTag({prop})'
    return f'PRKF:PRKF.IsTagSkillAV({prop})'


#: FO3/FNV PlayBink's optional flags after the file -- interruptible, mute audio, pause music, letterbox -- defaults.
_BINK_FLAG_DEFAULTS = ('0', '1', '1', '1')


def _flag(call, n: int, default: str) -> str:
    """Argument `n` as a Papyrus Bool under FO3/FNV's nonzero-is-true, `default` when absent."""
    raw = call.source(n).strip() if len(call) > n else default
    if raw.lstrip('-').replace('.', '', 1).isdigit():
        return 'true' if float(raw) else 'false'
    return f'({call.arg(n)} != 0)'


def play_bink(ctx, call):
    """FO3/FNV `PlayBink "<movie>" [flags]` on Fallout 4: Game.PlayBink with the same flags, for a shipped movie only.

    Fallout 4 hangs on a movie it cannot find, so a call naming one the build
    does not ship (ctx.xref.movies) is dropped. Declines elsewhere.
    See: docs/fork/bink_movies.md#plan
    """
    if not is_fallout4() or not len(call):
        return None
    movie = call.source(0).strip().strip('"')
    if movie_key(movie) not in ctx.xref.movies:
        return ctx.note(f'{call.written()} - movie not shipped (a missing movie hangs Fallout 4)')
    flags = ', '.join(_flag(call, n, default) for n, default in enumerate(_BINK_FLAG_DEFAULTS, 1))
    return f'Game.PlayBink("{movie.replace(chr(92), chr(92) * 2)}", {flags})'


FALLOUT_HANDLERS = {'getfactionrelation': faction_relation,
                    'playbink': play_bink,
                    'isplayertagskill': tag_skill,
                    'setplayertagskill': tag_skill,
                    'addscriptpackage': player_package,
                    'removescriptpackage': player_package,
                    'getopenstate': get_open_state,
                    'setopenstate': set_open_state,
                    'getweaponanimtype': weapon_anim_type,
                    'showmessage': show_message,
                    'swaptexture': swap_texture,
                    'setcellownership': cell_ownership,
                    **{name: quest_call for name in _QUEST_CALLS},
                    **{name: quest_native for name in _QUEST_NATIVES}}
