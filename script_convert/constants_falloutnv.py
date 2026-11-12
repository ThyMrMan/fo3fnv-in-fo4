"""FO3/FNV script blocks, commands and actor values Oblivion never emits.

`BLOCK_MAP.get(...)` returning None makes `assemble` drop the block body
entirely, so a block type absent from the table is silent data loss. FO3/FNV
author eight Oblivion does not; five have a real Papyrus event, verified
against `references/SkyrimCKWiki_210522/skyrim/<Event>_-_ObjectReference.html`.

See: docs/commentary/script_convert.md#fo3fnv-script-blocks
See: docs/commentary/script_convert.md#fallout-actor-value-names
"""

_END = 'EndEvent'

#: FO3/FNV block type -> (Papyrus event header, terminator).
FALLOUT_BLOCK_MAP = {
    'onopen':   ('Event OnOpen(ObjectReference akActionRef)', _END),
    'onclose':  ('Event OnClose(ObjectReference akActionRef)', _END),
    'ongrab':   ('Event OnGrab()', _END),
    'onrelease': ('Event OnRelease()', _END),
    'ondestructionstagechange': (
        'Event OnDestructionStageChanged(int aiOldStage, int aiCurrentStage)',
        _END),
    'oncombatend': (
        'Event OnCombatStateChanged(Actor akTarget, int aeCombatState)', _END),
}

#: FO3/FNV blocks merged into OnCombatStateChanged, with their state guard.
FALLOUT_COMBAT_STATE_GUARDS = {'oncombatend': 'aeCombatState == 0'}

#: FO3/FNV block filters: block type -> (event parameter, Papyrus type).
FALLOUT_BLOCK_FILTER_PARAM = {
    'onopen':  ('akActionRef', 'ObjectReference'),
    'onclose': ('akActionRef', 'ObjectReference'),
}


#: FO3/FNV names only commands_falloutnv handles, so the parser reads them AS commands.
FALLOUT_HANDLED_COMMANDS = frozenset({
    'setobjectivedisplayed', 'setobjectivecompleted', 'setobjectivefailed',
    'setquestdelay',
})

#: S.P.E.C.I.A.L. stats TES4_ATTRIBUTES lacks; read and written as TES4's attributes are.
FALLOUT_ATTRIBUTES = frozenset({'perception', 'charisma'})

#: FO3/FNV actor-value name -> Skyrim's, where the value exists under another name.
FALLOUT_ACTOR_VALUE_MAP = {
    'barter': 'Speechcraft',
    'lockpick': 'Lockpicking',
    'repair': 'Smithing',
    'speech': 'Speechcraft',
}

#: FO3/FNV actor-value names Skyrim's table lacks: a read is inert, a write dropped.
FALLOUT_UNMAPPED_ACTOR_VALUES = frozenset({
    'actionpoints', 'bigguns', 'bloodymess', 'damagethreshold',
    'dehydration', 'empresist', 'energyresist', 'energyweapons', 'explosives',
    'guns', 'hunger', 'medicine', 'meleeweapons', 'radiationrads',
    'radresist', 'science', 'sleepdeprevation', 'smallguns', 'survival',
    'turbo', 'unarmed', 'xp',
})

#: FO3/FNV spellings of shared handlers: alias -> the handler's TES4 name.
FALLOUT_COMMAND_ALIASES = {'cios': 'cast', 'castimmediateonself': 'cast',
                           #: The fade is the player's screen; the move is MoveTo. See: docs/fork/script_markers.md#moves
                           'movetomarkerwithfade': 'moveto', 'movetofade': 'moveto'}

#: FO3/FNV form type code (xNVSE kFormType) of each inventory record type -> its export type, for RemoveAllTypedItems.
ITEM_TYPE_CODES = {24: 'ARMO', 25: 'BOOK', 26: 'CLOT', 29: 'INGR', 30: 'LIGH', 31: 'MISC', 40: 'WEAP', 41: 'AMMO',
                   46: 'KEYM', 47: 'ALCH', 49: 'NOTE', 103: 'IMOD', 108: 'CHIP', 115: 'CCRD'}
#: Type code -> the FormList property of its items, which the Fallout 4 build writes (spike.items.type_list).
ITEM_TYPE_LISTS = {code: f'TES4ItemType{code}' for code in ITEM_TYPE_CODES}

#: The FormList of factions whose player-enemy flag converted scripts set (TES4_FalloutCrime keeps it).
_ENEMIES = ('TES4PlayerEnemyFactions', 'FormList')

#: FNV's IsAlwaysHardcore (short name behemoth): the ending's Hardcore reward test.
_ALWAYS_HARDCORE = dict(emit='0', note='{f} - Skyrim has no hardcore mode, nor its reward (read as 0)', flags='zero_arg')

#: FO3/FNV commands as COMMAND_ROWS specs (Cmd keyword arguments); 'MAP'/'ACTOR' name constants.MAP/ACTOR.
FALLOUT_COMMAND_ROWS = {
    #: The build stands in for xNVSE 6.4.9 (nvse_version.h). See: docs/fork/fo4_script_compile.md#nvse-version
    'getnvseversion': dict(emit='6', max_args=0),
    'getnvserevision': dict(emit='4', max_args=0),
    'getnvsebeta': dict(emit='9', max_args=0),
    'setenemy': dict(emit='{p0}.SetEnemy({p1}, {b2}, {b3})',
                     types={0: 'Faction', 1: 'Faction'}, defaults={2: '0', 3: '0'}),
    'setally': dict(emit='{p0}.SetAlly({p1}, {b2}, {b3})',
                    types={0: 'Faction', 1: 'Faction'}, defaults={2: '0', 3: '0'}),
    'getfactionrelation': dict(emit='{ref}.GetFactionReaction({a0})',
                               subj='ACTOR', flags='actor_only actor_arg'),
    'applyimagespacemodifier': dict(emit='{p0}.Apply({f1})',
                                    types={0: 'ImageSpaceModifier'}, defaults={1: '1.0'}),
    'removeimagespacemodifier': dict(emit='{p0}.Remove()', types={0: 'ImageSpaceModifier'}),
    'imod': dict(emit='{p0}.Apply({f1})', types={0: 'ImageSpaceModifier'}, defaults={1: '1.0'}),
    'rimod': dict(emit='{p0}.Remove()', types={0: 'ImageSpaceModifier'}),
    #: Skyrim items carry no condition, so the health percent drops (Fallout 4: command_rows_fallout4).
    'additemhealthpercent': dict(emit='{ref}.AddItem({p0}, {a1})', subj='OBJREF', defaults={1: '1'}),
    'iskiller': dict(emit='({ref}.GetKiller() == {a0})', subj='ACTOR', defaults={0: 'None'},
                     flags='actor_only cmp_bool'),
    'showwarning': dict(emit='Debug.MessageBox({fmt})'),
    'showmessage': dict(emit='{p0}.Show({a1}, {a2})', types={0: 'Message'},
                        defaults={1: '0.0', 2: '0.0'}),
    'addtofaction': dict(emit='{ref}.SetFactionRank({p0}, {a1})', subj='ACTOR',
                         types={0: 'Faction'}, defaults={1: '0'},
                         flags='actor_only'),
    'removefromfaction': dict(emit='{ref}.RemoveFromFaction({p0})',
                              subj='ACTOR', types={0: 'Faction'},
                              flags='actor_only'),
    'gethealthpercentage': dict(
        emit='{ref}.GetActorValuePercentage("Health")', subj='ACTOR',
        flags='actor_only zero_arg'),
    'getdestructionstage': dict(emit='{ref}.GetCurrentDestructionStage()',
                                subj='OBJREF', flags='zero_arg'),
    'getcontainerinventorycount': dict(
        emit='0', note='{f} - GetNumItems is SKSE-only, not vanilla (read as 0)',
        flags='zero_arg'),
    'hasbeeneaten': dict(
        emit='0', note='{f} - Skyrim has no cannibalism flag (read as 0)',
        flags='bare_bool cmp_bool zero_arg'),
    #: FNV's abbreviation for GetIgnoreFriendlyHits.
    'gifh': dict(emit='{ref}.IsIgnoringFriendlyHits()', subj='OBJREF',
                 flags='bare_bool cmp_bool zero_arg'),
    'getfurnituremarkerid': dict(
        emit='0', note='{f} - Skyrim has no furniture marker id (read as 0)',
        flags='zero_arg'),
    'gethitlocation': dict(
        emit='0', note='{f} - Skyrim has no hit location (read as 0)',
        flags='zero_arg'),
    'getmapmarkervisible': dict(emit='{ref}.IsMapMarkerVisible()',
                                subj='OBJREF',
                                flags='bare_bool cmp_bool zero_arg'),
    'player.gethealthpercentage': dict(
        emit='Game.GetPlayer().GetActorValuePercentage("Health")',
        flags='zero_arg'),
    'ishardcore': dict(
        emit='0', note='{f} - Skyrim has no hardcore mode (read as 0)',
        flags='zero_arg'),
    #: Hardcore mode exists on Fallout 4 only (command_rows_fallout4, F3NV_Hardcore).
    'isalwayshardcore': _ALWAYS_HARDCORE,
    'behemoth': _ALWAYS_HARDCORE,
    'sethardcore': dict(note='{f} {a} - Skyrim has no hardcore mode'),
    'getinchargen': dict(
        emit='0', note='{f} - SetInCharGen converts to nothing, so never in CharGen (read as 0)',
        flags='zero_arg'),
    'getweaponhealthperc': dict(
        emit='0', note='{f} - Skyrim has no weapon condition (read as 0)',
        flags='zero_arg'),
    'setweaponhealthperc': dict(emit='', note='{f} - Skyrim has no weapon condition'),
    'modweaponhealthperc': dict(emit='', note='{f} - Skyrim has no weapon condition'),
    'showrepairmenu': dict(emit='', note='{f} - Skyrim has no item condition'),
    #: Fallout's per-faction "player is an enemy" crime flag: Skyrim's, kept readable by TES4_FalloutCrime.
    'getactorfactionplayerenemy': dict(
        emit='TES4_FalloutCrime.TES4AnyEnemy({ref}, TES4PlayerEnemyFactions)', subj='ACTOR',
        flags='actor_only zero_arg cmp_bool', self_type=_ENEMIES),
    'clearactorsfactionsplayerenemyflag': dict(
        emit='TES4_FalloutCrime.TES4ClearActor({ref}, TES4PlayerEnemyFactions)', subj='ACTOR',
        flags='actor_only zero_arg', self_type=_ENEMIES),
    'setpcenemyoffaction': dict(emit='TES4_FalloutCrime.TES4SetEnemy({p0}, {i1} != 0, TES4PlayerEnemyFactions)',
                                types={0: 'Faction'}, self_type=_ENEMIES),
    'clearfactionplayerenemyflag': dict(emit='TES4_FalloutCrime.TES4SetEnemy({p0}, False, TES4PlayerEnemyFactions)',
                                        types={0: 'Faction'}, self_type=_ENEMIES),
    'getpcenemyoffaction': dict(emit='TES4_FalloutCrime.TES4IsEnemy({p0}, TES4PlayerEnemyFactions)',
                                types={0: 'Faction'}, flags='cmp_bool', self_type=_ENEMIES),
    'getanimaction': dict(
        emit='0', note='{f} - Skyrim has no anim-action read (read as 0)',
        flags='zero_arg'),
    'getignorecrime': dict(
        emit='0', note='{f} - Skyrim has no ignore-crime read (read as 0)',
        flags='zero_arg'),
    'isgoredisabled': dict(
        emit='0', note='{f} - Skyrim has no gore toggle (read as 0)',
        flags='zero_arg'),
    'iswin32': dict(
        emit='1', note='{f} - always the Windows build (read as 1)',
        flags='zero_arg'),
    'getxpfornextlevel': dict(
        emit='0', note='{f} - Skyrim has no XP curve read (read as 0)',
        flags='zero_arg'),
    'enablefasttravel': dict(emit='Game.EnableFastTravel({b0})', defaults={0: '1'}),
    'ispc1stperson': dict(emit='0', note='{f} - camera state is not a vanilla native (read as 0)',
                          flags='zero_arg'),
    'isps3': dict(emit='0', note='{f} - platform check (read as 0)', flags='zero_arg'),
    #: Radio broadcast state and the essential flag: Fallout 4's handlers (commands_falloutnv); else inert.
    'getbroadcaststate': dict(emit='0', note='{f} - a station broadcast state (read as 0)', flags='zero_arg'),
    'setbroadcaststate': dict(emit='0', note='{f} - a station broadcast state'),
    'isactorrefessential': dict(emit='0', note='{f} - the essential flag (read as 0)', flags='zero_arg'),
    'resetai': dict(emit='{ref}.EvaluatePackage()', subj='ACTOR',
                    flags='actor_only zero_arg'),
    'hasloaded3d': dict(emit='{ref}.Is3DLoaded()', subj='OBJREF', flags='zero_arg cmp_bool'),
    'getownerlasttarget': dict(emit='None', note='{f} - magic-effect owner target is not exposed (read as None)',
                               flags='zero_arg'),
    'gethasnote': dict(emit='Game.GetPlayer().GetItemCount({p0})', types={0: 'Book'}),
    'restoreav': dict(emit='RestoreActorValue', subj='MAP', flags='actor_only av'),
    'restoreactorvalue': dict(emit='RestoreActorValue', subj='MAP', flags='actor_only av'),
    'damageav': dict(emit='DamageActorValue', subj='MAP', flags='actor_only av'),
    'damageactorvalue': dict(emit='DamageActorValue', subj='MAP', flags='actor_only av'),
    'sendassaultalarm': dict(emit='{ref}.SendAssaultAlarm()', subj='ACTOR',
                             flags='actor_only zero_arg'),
    'getplayerteammate': dict(emit='{ref}.IsPlayerTeammate()', subj='ACTOR',
                              flags='actor_only zero_arg cmp_bool'),
    'rewardxp': dict(emit='Game.GetPlayer().SendModEvent("TESCharacterXP", "", {f0})'),
    'setspecialpoints': dict(emit='Game.GetPlayer().SendModEvent("TESCharacterMenu", "special", {f0})'),
    #: Intense Training's `AddSpecialPoints 1`: points to add to the SPECIAL stats the player picks.
    'addspecialpoints': dict(emit='Game.GetPlayer().SendModEvent("TESCharacterMenu", "addspecial", {f0})'),
    'showlovetestermenuparams': dict(emit='Game.GetPlayer().SendModEvent("TESCharacterMenu", "special", {f0})'),
    #: FO3's baby book. Takes no parameter; CG01's `ssbmp 40` writes the 40-point total, the default.
    'showspecialbookmenu': dict(emit='Game.GetPlayer().SendModEvent("TESCharacterMenu", "special", {f0})',
                                defaults={0: '40'}),
    'ssbmp': dict(emit='Game.GetPlayer().SendModEvent("TESCharacterMenu", "special", {f0})',
                  defaults={0: '40'}),
    'settagskills': dict(emit='Game.GetPlayer().SendModEvent("TESCharacterMenu", "tags", {f0})'),
    'showtraitmenu': dict(emit='Game.GetPlayer().SendModEvent("TESCharacterMenu", "traits", 0.0)',
                          flags='zero_arg'),
    'showtraitselectmenu': dict(emit='Game.GetPlayer().SendModEvent("TESCharacterMenu", "traits", 0.0)',
                                flags='zero_arg'),
    'getplayername': dict(note="{f} - Skyrim's race menu names the character"),
    'sexchange': dict(note='{f} {a} - Skyrim Papyrus cannot change sex', subj='ACTOR'),
    'swaptexture': dict(note='{f} {a} - Skyrim Papyrus cannot swap a texture'),
    'addnote': dict(emit='Game.GetPlayer().AddItem({p0}, 1, False)', types={0: 'Book'}),
    'removenote': dict(emit='Game.GetPlayer().RemoveItem({p0}, 1, True)', types={0: 'Book'}),
    #: A REPU is a FormList of its globals; see TES4_Reputation.psc.
    'setreputation': dict(emit='TES4_Reputation.Set({p0}, {i1}, {f2})', types={0: 'FormList'}),
    'addreputation': dict(emit='TES4_Reputation.Add({p0}, {i1}, {f2})', types={0: 'FormList'}),
    'removereputation': dict(emit='TES4_Reputation.Remove({p0}, {i1}, {f2})', types={0: 'FormList'}),
    'addreputationexact': dict(emit='TES4_Reputation.AddExact({p0}, {i1}, {f2})', types={0: 'FormList'}),
    'removereputationexact': dict(emit='TES4_Reputation.RemoveExact({p0}, {i1}, {f2})',
                                  types={0: 'FormList'}),
    'getreputation': dict(emit='TES4_Reputation.Points({p0}, {i1})', types={0: 'FormList'}),
    'getreputationpct': dict(emit='TES4_Reputation.Pct({p0}, {i1})', types={0: 'FormList'}),
    'getreputationthreshold': dict(emit='TES4_Reputation.Threshold({p0}, {i1})', types={0: 'FormList'}),
    'rewardkarma': dict(emit='TES4Karma.Mod({f0})', self_type=('TES4Karma', 'GlobalVariable')),
    'isplayerinregion': dict(emit='0', note='{f} {a} - Skyrim has no region query (read as 0)'),
    'islimbgone': dict(emit='0', note='{f} {a} - Skyrim has no dismemberment query (read as 0)'),
    #: Challenges exist on Fallout 4 only (command_rows_fallout4, F3NV_Challenges).
    'unlockchallenge': dict(note='{f} {a} - Skyrim has no challenges'),
    'removerecurringfromchallenge': dict(note='{f} {a} - Skyrim has no challenges'),
    'getchallengecompleted': dict(emit='0', note='{f} {a} - Skyrim has no challenges (read as 0)'),
    'showbartermenu': dict(emit='ShowBarterMenu', subj='MAP', flags='actor_only', max_args=0),
    'addperk': dict(emit='AddPerk', subj='MAP', flags='actor_only', max_args=1),
    'removeperk': dict(emit='RemovePerk', subj='MAP', flags='actor_only', max_args=1),
    'hasperk': dict(emit='HasPerk', subj='MAP', flags='actor_only cmp_bool', max_args=1),
    #: Rendered by commands_falloutnv.quest_native; the rows carry the Bool flags.
    'getobjectivedisplayed': dict(emit='IsObjectiveDisplayed', subj='MAP', bare=True,
                                  flags='bare_bool cmp_bool'),
    'getobjectivecompleted': dict(emit='IsObjectiveCompleted', subj='MAP', bare=True,
                                  flags='bare_bool cmp_bool'),
    'getobjectivefailed': dict(emit='IsObjectiveFailed', subj='MAP', bare=True,
                               flags='bare_bool cmp_bool'),
    #: Formerly ;NE: markers. See: docs/fork/script_markers.md#built
    'setplayerteammate': dict(emit='{ref}.SetPlayerTeammate({b0})', subj='ACTOR', defaults={0: '1'},
                              flags='actor_only'),
    'openteammatecontainer': dict(emit='{ref}.OpenInventory(True)', subj='ACTOR', flags='actor_only'),
    'removefromallfactions': dict(emit='{ref}.RemoveFromAllFactions()', subj='ACTOR',
                                  flags='actor_only zero_arg'),
    'sendtrespassalarm': dict(emit='{ref}.SendTrespassAlarm({a0})', subj='ACTOR', types={0: 'Actor'},
                              defaults={0: 'Game.GetPlayer()'}, flags='actor_only'),
    'addformtoformlist': dict(emit='{p0}.AddForm({p1})', types={0: 'FormList', 1: 'Form'}),
    'damageobject': dict(emit='{ref}.DamageObject({f0})', subj='OBJREF', defaults={0: '0.0'}),
    'do': dict(emit='{ref}.DamageObject({f0})', subj='OBJREF', defaults={0: '0.0'}),
    'resetquest': dict(emit='{p0}.Reset()', types={0: 'Quest'}),
    #: The weapon the actor holds is in the list. GetEquippedWeapon is None bare-handed; HasForm(None) is False.
    'isweaponinlist': dict(emit='({p0}.HasForm({ref}.GetEquippedWeapon()) as Int)', subj='ACTOR',
                           types={0: 'FormList'}, flags='actor_only'),
    #: Base plus permanent modifiers: the AV handler reads it as the base value. See: docs/fork/script_markers.md#permanent-av
    'getpermanentactorvalue': dict(emit='GetBaseActorValue', subj='MAP', flags='actor_only av av_read'),
    'getpermav': dict(emit='GetBaseActorValue', subj='MAP', flags='actor_only av av_read'),
    #: Skyrim has no casino: no game opens, no comp is owed (FO4 rows exist). See: docs/fork/script_markers.md#casino
    'getcasinowinningslevel': dict(emit='0'),
    'showblackjackmenuparams': dict(note='{f} {a} - Skyrim has no casino games'),
    'showroulettemenuparams': dict(note='{f} {a} - Skyrim has no casino games'),
    'showslotmachinemenuparams': dict(note='{f} {a} - Skyrim has no casino games'),
    'showcaravanmenu': dict(note='{f} {a} - Skyrim has no Caravan', subj='ACTOR'),
    'addcardtoplayer': dict(note='{f} - Skyrim has no Caravan'),
    #: MoveToMarkerWithFade converts to MoveTo, so the fade it waited on never plays. See: docs/fork/script_markers.md#moves
    'isimagespaceactive': dict(emit='0'),
}
