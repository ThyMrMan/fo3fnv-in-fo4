"""Fallout 4's rows for the commands whose Skyrim row emits a call Fallout 4 lacks.

Keyed by the Skyrim `Cmd` itself, so every spelling that shares a row takes
the Fallout 4 row too; `emit_row` picks it when Fallout 4 is the target.
Actor values are ActorValue form properties (`target.av_property`) declared
through `self_type`; behavior-graph events go through PlayAnimation. Where
Fallout 4 has FO3/FNV's own feature the row uses it (RewardXP is the native
RewardPlayerXP); the character menus, which Skyrim sends as SKSE mod events,
become one custom event from the TES4_CharacterEvents helper. IsAnimPlaying
is 0: FO4 cannot ask a NIF sequence, and the graph read errored (fo4_pipeline.md#log-noise).

See: docs/fork/fo4_spikes.md#spike-3-target
"""

from script_convert.command_rows import ACTOR, AV, COMMAND_ROWS, MAP, OBJREF, RAW, Cmd
from script_convert.target import CHARACTER_PROPERTY, CHARACTER_SCRIPT, CONTROLS_PROPERTY, CONTROLS_SCRIPT, av_property


def _av(name: str) -> tuple:
    """`self_type` declaring the ActorValue property for actor value `name`."""
    return av_property(name), 'ActorValue'


#: The FO4 helper quest sending FO3/FNV's character menus as a custom event.
_CHARACTER = (CHARACTER_PROPERTY, CHARACTER_SCRIPT)
#: The FO4 helper quest holding the shared InputEnableLayer (controls, fast travel).
_CONTROLS = (CONTROLS_PROPERTY, CONTROLS_SCRIPT)


def _menu(kind: str, value: str = '{f0}', **row) -> Cmd:
    """A character-menu command as TES4_CharacterEvents.Menu(kind, value)."""
    return Cmd(f'{_CHARACTER[0]}.Menu("{kind}", {value})', self_type=_CHARACTER, **row)


#: TES4 command -> its Fallout 4 row, then keyed by the Skyrim row it replaces.
FALLOUT4_ROWS = {COMMAND_ROWS[name]: row for name, row in {
    'getarmorrating': Cmd(f'{{ref}}.GetValue({av_property("DamageResist")})', ACTOR,
                          self_type=_av('DamageResist'), flags='actor_only'),
    'setcurrenthealth': Cmd(f'{{ref}}.SetValue({av_property("Health")}, {{a0}})', RAW,
                            self_type=_av('Health'), defaults={0: '0'}),
    'resethealth': Cmd(f'{{ref}}.RestoreValue({av_property("Health")}, 9999)', AV,
                       self_type=_av('Health'), flags='actor_only branch_only'),
    'advancepclevel': Cmd(f'Game.GetPlayer().ModValue({av_property("Level")}, 1)', self_type=_av('Level')),
    'setforcerun': Cmd(f'{{ref}}.SetValue({av_property("SpeedMult")}, {{?01}})', ACTOR, self_type=_av('SpeedMult'),
                       defaults={0: '0'}, arms=('150.0', '100.0'), flags='actor_only branch_only'),
    'gethealthpercentage': Cmd(f'{{ref}}.GetValuePercentage({av_property("Health")})', ACTOR,
                               self_type=_av('Health'), flags='actor_only zero_arg'),
    'player.gethealthpercentage': Cmd(f'Game.GetPlayer().GetValuePercentage({av_property("Health")})',
                                      self_type=_av('Health'), flags='zero_arg'),
    'pickidle': Cmd('{ref}.PlayAnimation("{s0}")', ACTOR, defaults={0: 'IdleForceDefaultState'}, flags='zero_arg'),
    'playidle': Cmd('{ref}.PlayIdle({p0})', ACTOR, types={0: 'Idle'}),
    'rewardxp': Cmd('Game.RewardPlayerXP({i0})'),
    'isanimplaying': Cmd('0'),
    'setrestrained': Cmd('{ref}.SetRestrained({b0})', ACTOR, defaults={0: '0'}),
    'getlos': Cmd('HasDetectionLOS', MAP, flags='actor_only'),
    'removeallitems': Cmd('RemoveAllItems', MAP, flags='actor_only objref_shared', max_args=2),
    'enablefasttravel': Cmd(f'{CONTROLS_PROPERTY}.FastTravel({{b0}})', self_type=_CONTROLS, defaults={0: '1'}),
    'setcanfasttravelfromworld': Cmd(f'{CONTROLS_PROPERTY}.FastTravel({{b1}})', self_type=_CONTROLS,
                                     defaults={1: '1'}),
    'setspecialpoints': _menu('special'),
    'showlovetestermenuparams': _menu('special'),
    'showspecialbookmenu': _menu('special', defaults={0: '40'}),
    'ssbmp': _menu('special', defaults={0: '40'}),
    'settagskills': _menu('tags'),
    'showtraitmenu': _menu('traits', '0.0', flags='zero_arg'),
    'showracemenu': Cmd(f'{CONTROLS_PROPERTY}.ShowRaceMenu()', self_type=_CONTROLS, flags='zero_arg'),
    'sexchange': Cmd('TES4Polyfill.SetSex({ref}, "{s0}")', ACTOR, defaults={0: '-1'}, flags='actor_only zero_arg'),
    'showtraitselectmenu': _menu('traits', '0.0', flags='zero_arg'),
    'rewardkarma': Cmd('TES4Polyfill.ModKarma(TES4Karma, {f0})', self_type=('TES4Karma', 'GlobalVariable')),
    'addnote': Cmd('Game.GetPlayer().AddItem({p0}, 1, False)', types={0: 'Form'}),
    'removenote': Cmd('Game.GetPlayer().RemoveItem({p0}, 1, True)', types={0: 'Form'}),
    'gethasnote': Cmd('Game.GetPlayer().GetItemCount({p0})', types={0: 'Form'}),
    'showbartermenu': Cmd('TES4Polyfill.ShowBarterMenu({ref})', ACTOR, flags='actor_only', max_args=0),
    'addscriptpackage': Cmd('TES4ScriptPackages.Add({ref}, {p0})', ACTOR, types={0: 'Package'},
                            self_type=('TES4ScriptPackages', 'TES4_ScriptPackages'), flags='actor_only'),
    'removescriptpackage': Cmd('TES4ScriptPackages.Remove({ref})', ACTOR, max_args=0,
                               self_type=('TES4ScriptPackages', 'TES4_ScriptPackages'), flags='actor_only'),
    'getweaponhealthperc': Cmd('TES4_ConditionCalls.WeaponPercent({ref})', ACTOR, flags='actor_only zero_arg'),
    'setweaponhealthperc': Cmd('TES4_ConditionCalls.SetWeaponPercent({ref}, {f0})', ACTOR, flags='actor_only'),
    'modweaponhealthperc': Cmd('TES4_ConditionCalls.ModWeaponPercent({ref}, {f0})', ACTOR, flags='actor_only'),
    'additemhealthpercent': Cmd('TES4_ConditionCalls.AddWithHealth({ref}, {p0}, {i1}, {f2}, {b3})', OBJREF,
                                types={0: 'Form'}, defaults={1: '1', 2: '1.0', 3: '0'}),
}.items()}
