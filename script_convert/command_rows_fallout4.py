"""Fallout 4's rows for the commands whose Skyrim row emits a call Fallout 4 lacks.

Keyed by the Skyrim `Cmd` itself, so every spelling that shares a row takes
the Fallout 4 row too; `emit_row` picks it when Fallout 4 is the target.
Actor values are ActorValue form properties (`target.av_property`) declared
through `self_type`; behavior-graph events go through PlayAnimation. Where
Fallout 4 has FO3/FNV's own feature the row uses it (RewardXP is the native
RewardPlayerXP); the character menus, which Skyrim sends as SKSE mod events,
become one custom event from the F3NV_CharacterEvents helper. IsAnimPlaying is the
anim_playing_falloutnv handler's, not a row. IsPlayerInRegion reads
the region's watch global (fo4_regions.md#built); GetTalkedToPC the TalkedToPC helper value (fo4_pipeline.md#talked-to-pc);
IsHardcore, IsAlwaysHardcore and SetHardcore the game's Hardcore quest (fo4_hardcore.md#built); the casino
openers, GetCasinoWinningsLevel and AddCardToPlayer the casino bank (fo4_casino_plan.md#records-built).

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
#: FNV's Hardcore mode: the game plugin's quest (fo4_import/spike/hardcore.py), filled by name.
_HARDCORE = ('TES4Hardcore', 'F3NV_Hardcore')
#: FNV's casino bank (fo4_import/casino/records.py), filled by name; a casino (CSNO) is its F3NV_CasinoData quest.
_CASINO, _CASINO_DATA = ('TES4Casino', 'F3NV_Casino'), {0: 'F3NV_CasinoData'}


def _casino_game(game: int) -> Cmd:
    """An FNV casino opener as the bank's Open(`game`, casino, min, max, min won)."""
    return Cmd(f'{_CASINO[0]}.Open({game}, {{p0}}, {{i1}}, {{i2}}, {{i3}})', types=_CASINO_DATA, self_type=_CASINO,
               defaults={1: '1', 2: '200', 3: '0'})


def _menu(kind: str, value: str = '{f0}', **row) -> Cmd:
    """A character-menu command as F3NV_CharacterEvents.Menu(kind, value)."""
    return Cmd(f'{_CHARACTER[0]}.Menu("{kind}", {value})', self_type=_CHARACTER, **row)


#: TES4 command -> its Fallout 4 row, then keyed by the Skyrim row it replaces.
FALLOUT4_ROWS = {COMMAND_ROWS[name]: row for name, row in {
    'menumode': Cmd('TES4Polyfill.MenuMode({i0})', defaults={0: '0'}),
    'getarmorrating': Cmd(f'{{ref}}.GetValue({av_property("DamageThreshold")})', ACTOR,
                          self_type=_av('DamageThreshold'), flags='actor_only'),
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
    'setrestrained': Cmd('TES4Polyfill.Restrain({ref}, {b0})', ACTOR, defaults={0: '0'}),
    'getlos': Cmd('HasDetectionLOS', MAP, flags='actor_only'),
    'removeallitems': Cmd('RemoveAllItems', MAP, flags='actor_only objref_shared', max_args=2),
    'enablefasttravel': Cmd(f'{CONTROLS_PROPERTY}.FastTravel({{b0}})', self_type=_CONTROLS, defaults={0: '1'}),
    'setcanfasttravelfromworld': Cmd(f'{CONTROLS_PROPERTY}.FastTravel({{b1}})', self_type=_CONTROLS,
                                     defaults={1: '1'}),
    'setspecialpoints': _menu('special'),
    'addspecialpoints': _menu('addspecial'),
    'showlovetestermenuparams': _menu('special'),
    'showspecialbookmenu': _menu('special', defaults={0: '40'}),
    'ssbmp': _menu('special', defaults={0: '40'}),
    'settagskills': _menu('tags'),
    'showtraitmenu': _menu('traits', '0.0', flags='zero_arg'),
    'showracemenu': Cmd(f'{CONTROLS_PROPERTY}.ShowRaceMenu()', self_type=_CONTROLS, flags='zero_arg'),
    'sexchange': Cmd('TES4Polyfill.SetSex({ref}, "{s0}")', ACTOR, defaults={0: '-1'}, flags='actor_only zero_arg'),
    'showtraitselectmenu': _menu('traits', '0.0', flags='zero_arg'),
    'rewardkarma': Cmd('TES4Polyfill.ModKarma(TES4Karma, {f0})', self_type=('TES4Karma', 'GlobalVariable')),
    'unlockchallenge': Cmd('F3NV_Challenges.Unlock({p0})', types={0: 'GlobalVariable'}),
    'removerecurringfromchallenge': Cmd('F3NV_Challenges.StopRecurring({p0})', types={0: 'GlobalVariable'}),
    'getchallengecompleted': Cmd('F3NV_Challenges.Completed({p0})', types={0: 'GlobalVariable'}),
    'addnote': Cmd('Game.GetPlayer().AddItem({p0}, 1, False)', types={0: 'Form'}),
    'removenote': Cmd('Game.GetPlayer().RemoveItem({p0}, 1, True)', types={0: 'Form'}),
    'gethasnote': Cmd('Game.GetPlayer().GetItemCount({p0})', types={0: 'Form'}),
    'showbartermenu': Cmd('TES4Polyfill.ShowBarterMenu({ref})', ACTOR, flags='actor_only', max_args=0),
    'showrepairmenu': Cmd('F3NV_ConditionCalls.ShowRepairMenu({ref})', ACTOR, flags='actor_only', max_args=0),
    'addscriptpackage': Cmd('TES4ScriptPackages.Add({ref}, {p0})', ACTOR, types={0: 'Package'},
                            self_type=('TES4ScriptPackages', 'F3NV_ScriptPackages'), flags='actor_only'),
    'removescriptpackage': Cmd('TES4ScriptPackages.Remove({ref})', ACTOR, max_args=0,
                               self_type=('TES4ScriptPackages', 'F3NV_ScriptPackages'), flags='actor_only'),
    'getweaponhealthperc': Cmd('F3NV_ConditionCalls.WeaponPercent({ref})', ACTOR, flags='actor_only zero_arg'),
    'setweaponhealthperc': Cmd('F3NV_ConditionCalls.SetWeaponPercent({ref}, {f0})', ACTOR, flags='actor_only'),
    'modweaponhealthperc': Cmd('F3NV_ConditionCalls.ModWeaponPercent({ref}, {f0})', ACTOR, flags='actor_only'),
    'additemhealthpercent': Cmd('F3NV_ConditionCalls.AddWithHealth({ref}, {p0}, {i1}, {f2}, {b3})', OBJREF,
                                types={0: 'Form'}, defaults={1: '1', 2: '1.0', 3: '0'}),
    'removeme': Cmd('TES4Polyfill.RemoveMe({ref}, {a0})', OBJREF, types={0: 'ObjectReference'},
                    defaults={0: 'None'}),
    'isplayerinregion': Cmd('TES4Polyfill.InRegion({p0})', types={0: 'GlobalVariable'}, flags='cmp_bool'),
    'getcurrentaiprocedure': Cmd('TES4Polyfill.AIProcedure({ref})', ACTOR, flags='actor_only zero_arg'),
    'islimbgone': Cmd('TES4Polyfill.LimbGone({ref}, {i0})', ACTOR, flags='actor_only cmp_bool'),
    'ignorecrime': Cmd('TES4Polyfill.IgnoreCrime({ref}, {b0})', ACTOR, flags='actor_only'),
    'getignorecrime': Cmd('TES4Polyfill.GetIgnoreCrime({ref})', ACTOR, flags='actor_only zero_arg'),
    'setinchargen': Cmd('TES4Polyfill.SetInCharGen({b0})'),
    'getinchargen': Cmd('TES4Polyfill.GetInCharGen()', flags='zero_arg'),
    'ishardcore': Cmd(f'{_HARDCORE[0]}.IsOn()', self_type=_HARDCORE, flags='zero_arg cmp_bool'),
    'isalwayshardcore': Cmd(f'{_HARDCORE[0]}.IsAlways()', self_type=_HARDCORE, flags='zero_arg cmp_bool'),
    'behemoth': Cmd(f'{_HARDCORE[0]}.IsAlways()', self_type=_HARDCORE, flags='zero_arg cmp_bool'),
    'sethardcore': Cmd(f'{_HARDCORE[0]}.SetHardcore({{b0}})', self_type=_HARDCORE, defaults={0: '1'}),
    'showblackjackmenuparams': _casino_game(1),
    'showroulettemenuparams': _casino_game(2),
    'showslotmachinemenuparams': _casino_game(3),
    'getcasinowinningslevel': Cmd('{p0}.GetLevel()', types=_CASINO_DATA),
    'showcaravanmenu': Cmd(f'{_CASINO[0]}.OpenCaravan({{ref}}, {{p0}}, {{i1}}, {{f2}})', ACTOR, types={0: 'FormList'},
                           self_type=_CASINO, defaults={1: '0', 2: '0.0'}, flags='actor_only'),
    'addcardtoplayer': Cmd(f'{_CASINO[0]}.AddCard({{ref}})', OBJREF, self_type=_CASINO, flags='zero_arg'),
    'gettalkedtopc': Cmd(f'({{ref}}.GetValue({av_property("TalkedToPC")}) != 0.0)', ACTOR,
                         self_type=_av('TalkedToPC'), flags='actor_only zero_arg cmp_bool'),
    'gettalkedtopcp': Cmd(f'({{ref}}.GetValue({av_property("TalkedToPC")}) != 0.0)', ACTOR,
                          self_type=_av('TalkedToPC'), flags='actor_only zero_arg cmp_bool'),
}.items()}
