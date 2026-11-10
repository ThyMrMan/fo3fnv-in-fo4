# NVSE features for FO4: what FNV mods need and where it would come from

Research only, 2026-10-23. Nothing here is built or decided. The question:
which parts of NVSE (and the NVSE plugins FNV mods require) would have to
exist in FO4 for converted FNV mods to work, and which layer should supply
each one.

Sources read:
- xNVSE source: `references/xNVSE`
- JIP LN NVSE source: `references/JIP-LN-NVSE`
- F4SE 0.7.9 source (`src/f4se-0.7.9.tar.gz` in the FO4 install) and its
  scripts in `references/fo4_scripts/F4SE`
- Vanilla FO4 scripts in `references/fo4_scripts/Base`
- The two Papyrus extenders already in the MO2 instance: Garden of Eden
  23.6 (`references/GardenOfEden`) and Hydra 1.0.2 (`mods/Hydra/Scripts/Source`)
- A web survey of the FNV plugin ecosystem. Nexus and both GECK wikis
  refused the fetches, so the mod-usage counts below are **not verified**.

## <a id="summary"></a>Summary

- **Most of NVSE is a converter problem, not a DLL problem.** NVSE's biggest
  pieces are its script language (`Let`, `eval`, `foreach`, user-defined
  functions, lambdas, a second C-like syntax) and its containers (arrays,
  maps, string variables). Papyrus already has functions, structs, `Var`,
  custom events and timers, so most of this becomes converter lowering.
- **Hydra and Garden of Eden already cover most of the rest.** Between them:
  unbounded arrays, maps saved in the co-save, strings and regex, INI, JSON
  and file I/O, console execution, key state, about 60 global events with
  filters, cell reference scans, inventory by index, and roughly 1,400 form
  field getters and setters. Hydra overlaps NVSE most closely.
- **What only our own F3NV.dll can supply is short.** See
  [the F3NV.dll list](#f3nv-gaps): a per-frame tick, JIP-style per-ref
  storage that cleans itself up, the few hook events neither extender
  has, synchronous veto events, FNV-only item data, and translation tables.
- **Some of it can't be ported at all.** FNV's XML tile UI, kNVSE animation
  folders, FNV engine fixes, and compiling script text at runtime. Mods
  built on those need hand work or are out of scope.
- **The next step is a usage survey, not code.** xNVSE has 634 commands and
  JIP about 1,086. A real mod uses a few dozen. Grepping the script source
  of a set of candidate mods would turn this inventory into a priority list
  ([next steps](#next-steps)).

## <a id="layers"></a>Where each feature would come from

Four layers, cheapest first:

1. **Converter lowering to vanilla Papyrus.** Syntax, control flow, UDFs,
   most string handling, math, form lists, quest and actor commands that
   FO4 has natively.
2. **F4SE 0.7.9 natives.** About 232 functions and 8 events. Useful parts:
   key and control events, `UI.Get/Set/Invoke` on Scaleform paths,
   `InstanceData` weapon and armor stats, game setting setters,
   `GetInstalledPlugins`, bit math. F4SE has **no** string functions, no
   INI or file I/O, no key-state query, no cell reference walk, no maps and
   no global gameplay events.
3. **A Papyrus extender (Hydra or Garden of Eden).** Called only through
   our own wrapper script, with a fallback when it is missing, per the
   [dependency policy](fo4_target.md#dependency-policy).
4. **F3NV.dll natives and hooks.** Only for what layers 1 to 3 can't do.
   The plugin already registers Papyrus natives (`tes_runtime/fo4_condition/plugin.cpp`),
   so the pattern exists.

## <a id="ecosystem"></a>The NVSE ecosystem, and which part matters

FNV's script-extender plugins fall into three groups. Only the first
matters for FO4.

| Group | Plugins | For FO4 |
|---|---|---|
| Script functions | xNVSE, JIP LN NVSE, JohnnyGuitar, ShowOff, SUP, TTW's plugin | Port what mods actually call |
| FNV engine fixes | NVTF, lStewieAl's Tweaks, NVAC, Mod Limit Fix, JIP's patch half | Not applicable: they patch the FNV exe |
| UI and animation frameworks | UIO, MCM, yUI, kNVSE | Not portable as such. MCM menus are rebuilt on FO4's MCM; kNVSE animation sets would be redone for FO4's behavior graphs |

Mods by kind (dependency counts unverified):

| Kind | Examples | Worth porting? |
|---|---|---|
| Quest and content | New California, Frontier, TTW's content | Yes. Mostly vanilla script plus strings, arrays and events |
| Companions | Willow, follower frameworks | Yes, the companion scripts. JIP's companion helper commands are mod-specific |
| Gameplay overhauls | JSawyer Ultimate, JAM, Delay DLC | Yes. They lean on events, ref scans, inventory walks and INI settings |
| MCM menus | Hundreds | Partly: keep the settings, rebuild the menu |
| UI/HUD | UIO, yUI, Darnified, HUD add-ons | No |
| Animation | kNVSE sets, B42 Inspect | No, redo |

Prior art: F4NV (Fallout 4: New Vegas) didn't emulate NVSE. It rebuilt FNV's
systems natively on F4SE, XDI and Garden of Eden. OpenMW doesn't run MWSE
mods at all. Skyblivion and upstream's PR 54 (OBSE calls to SKSE-aware
Papyrus) translate scripts ahead of time, which is our model too.

## <a id="xnvse"></a>xNVSE core

634 script commands, plus 20 console commands made script-callable
(`CommandTable.cpp`, `AddCommandsV1` to `V6`).

| Area | Count | What it is | FO4 route |
|---|---|---|---|
| Inventory, items, weapon/armor/ammo fields | 153 + 8 | Field get/set on WEAP, ARMO, AMMO; equipped object; inventory walk; inventory references | F4SE `InstanceData` and `Form`; Hydra `Forms/*`; GOE Nth-item functions. FNV-only fields: see [below](#fnv-only-fields) |
| References and base forms | 68 | `GetFirstRef`/`GetNextRef`, `GetRefs`, base object, parent cell, linked door, owner, flags | Vanilla for most; ref walks via Hydra `Cell.FindAllRefs` or GOE `GetCellReferences`, lowered to an array loop |
| Strings | 60 | `sv_*`, `ToUpper`, `GetName`, format specifiers (`%n %i %k %v %z %r`) | Hydra `Strings`/`Regex`; GOE's ~10 string functions. Format specifiers expand in the converter |
| Script control | 57 + 34 | Get/SetVariable, `GetCallingScript`, `CallAfterSeconds`/`CallWhile`/`CallWhen`, event handlers, `Ternary`, `TypeOf` | Converter + timers; events: [below](#events) |
| Arrays | 44 | `ar_*`; three kinds (list, numeric map, string map); nested; ref-counted; co-saved | Hydra arrays (no 128 cap) and SaveMap/TempMap; converter lowering of `foreach` |
| Math and vectors | 30 + 19 | Trig in degrees, bit ops, vectors, quaternions | Vanilla `Math` + F4SE bit ops; the rest in a Papyrus library |
| Input | 27 | `IsKeyPressed`, `TapKey`, `DisableKey`, `GetControl` | F4SE key events; Hydra `IsKeyPressed`/`TapKey`; raw-key disable needs F3NV.dll |
| Game | 26 | Game settings, INI settings, `GetGameLoaded`/`GetGameRestarted`, `IsModLoaded`, `BuildRef`, `MessageBoxEx` | Vanilla `GetFormFromFile`/`IsPluginInstalled`; F4SE settings; Hydra `IniSettings`; load flags from an `OnPlayerLoadGame` alias |
| Packages, factions, quests, lists | 39 | Package lists, objectives, form lists | Mostly vanilla; runtime package editing has no Papyrus route |
| UI | 13 | `GetUIFloat`/`SetUIFloat` on tile paths | [Not portable as is](#not-portable) |
| Console | 8 + 20 | Print, echo, imported console verbs | Hydra/GOE console execution |

### <a id="language"></a>The script language

A translator has to parse two front ends. Both compile to the same
bytecode (SCDA); the SCTX source text is in either syntax.

**Legacy syntax with NVSE expressions** (`ScriptUtils.cpp`):
- `Let`, `eval`, `if eval`, `While`/`Loop`, `ForEach x <- arr`, `Break`,
  `Continue`, `Call`, `SetFunctionValue`, `Return`, `Label`/`Goto`.
- Operators: `:=`, compound assignments, `[ ]` indexing and slices,
  `->` (string-map member), `::` (pair), `$` (to string), `#` (to number),
  `<-` (foreach), `^` (power), unary `*` and `&` (unbox, box).
- Types `array_var`, `string_var`, `int`; comma-separated declarations.
- Compile-time rewrites: `x = expr` becomes `let x := expr`; `int i = 5`
  becomes a declaration and a `let`.
- Compiler override: `begin _GameMode` or `_Command`, which lets every
  command in the block take full expressions.
- **UDFs:** a script whose one block is `Begin Function {a, b}`, at most 15
  parameters, called with `Call`. Lambdas inline `(begin function {…} … end)`
  or `{a} => expr`; they capture the parent's variables by reference.
- `#Version("nvse", …)` directives in comments.

**New C-like syntax** (`nvse/nvse/Compiler/`, used when SCTX starts with
`name`): typed declarations, `fn (args) { … }`, `for (x in arr)`,
`for ([k, v] in arr)`, `match`, ternary, `++`, map and array literals,
lambdas. Examples to use as converter test fixtures:
`nvse/nvse/unit_tests/new_compiler/*.txt` and `unit_tests/old_compiler/*.txt`.

Our converter inherits the OBSE handling from the Skyrim path:
`SetEventHandler`, `foreach` and array element writes currently emit
`NE:` notes (`script_convert/command_rows.py`, `converter.py`).

How each piece lowers:

| NVSE construct | Papyrus |
|---|---|
| UDF | A global function on a generated script |
| Lambda | A named function, captured variables lifted onto the owning script or passed in a `Var[]` |
| `ForEach` over an array | Index loop; over a map, loop over its keys |
| `Label`/`Goto` | Restructured into `While` loops (Papyrus has no goto) |
| `GameMode` polling | Timers or events, as the converter already does for vanilla blocks ([performance](../performance.md#papyrus)) |
| `GetGameLoaded` / `GetGameRestarted` | A flag set from an `OnPlayerLoadGame` alias |
| `string_var` | Papyrus `string`. Watch for case: Papyrus strings are interned and case-insensitive |
| `array_var` held in a float | Doesn't translate directly; needs the Hydra handle or a typed rewrite |

### <a id="events"></a>Events

NVSE handlers are **global and filtered**: one UDF gets every `OnHit` in the
game, optionally filtered by target or weapon (a form list filter matches
any member). They have priorities, and they are **not saved**: mods register
them again on every load. Papyrus events are per object (an attached script
or `RegisterForRemoteEvent` on a known reference). Hydra's events are the
closest match: global, filtered, persistence chosen per registration. Garden
of Eden's events are not saved, which matches NVSE's behavior.

| NVSE / JIP event | FO4 route |
|---|---|
| OnHit, OnHitWith | Hydra `OnObjectHit` (check its weapon filter); vanilla `RegisterForHitEvent` is single-shot and must be re-armed |
| OnActorEquip, OnActorUnequip | Hydra `OnItemEquipUnequip`, GOE `OnEquipUnequip` |
| OnAdd, OnDrop | Hydra `OnItemAddRemove`; vanilla `OnItemAdded` with inventory filters |
| OnDeath, OnMurder | Hydra `OnActorDeath`; vanilla `OnDeath`/`OnKill` per actor |
| OnActivate | Hydra `OnObjectActivate`, GOE `OnActivateGlobal` |
| OnStartCombat, OnCombatEnd | Hydra/GOE combat state |
| OnPackageStart/Change/Done | Hydra `OnAIPackageChange`; vanilla per actor |
| OnLoad, OnCellAttach/Detach | Hydra `OnObjectLoadUnload`, `OnCellAttachDetach` |
| OnSell, OnGrab, OnOpen/OnClose, OnTrigger* | Hydra |
| OnMagicEffectHit | Hydra `OnActiveEffectApplyRemove` |
| OnLockpickSuccess/Broken, OnTerminalHacked | Hydra `OnLockPick`, `OnTerminalHack` |
| OnFire (any actor) | Vanilla only has the player's. **F3NV.dll hook** unless Hydra covers it |
| LoadGame, PostLoadGame, SaveGame, NewGame | Hydra lifecycle events; F4SE messaging |
| ExitGame, ExitToMainMenu, RuntimeScriptError | No route; rarely needed |
| OnMenuOpen/Close (JIP) | Vanilla `RegisterForMenuOpenCloseEvent`, with an FNV menu code → FO4 menu name table |
| OnKeyDown/Up, OnControlDown/Up | F4SE `RegisterForKey`/`RegisterForControl` |
| OnCellEnter/Exit, OnCrosshairOn/Off (JIP) | Hydra `OnCellEnterExit`, `OnCrosshairRefChange` |
| OnQuestStage (JIP) | Vanilla `OnStageSet`; Hydra `OnQuestStageChange` |
| OnCrippledLimb (JIP) | Vanilla `OnCripple`; Hydra `OnLimbCripple` |
| OnHealthDamage, OnProjectileImpact, OnReloadWeapon, OnUseAidItem, OnCrafting, OnRagdoll (JIP) | **F3NV.dll hooks**, after checking Hydra's list |
| OnMenuClick, OnMouseoverChange, OnPlayGroup (JIP) | No equivalent (tile UI, FNV animation groups) |
| User-defined (`DispatchEvent`) | Hydra `SendUserEvent`, or a Papyrus `CustomEvent` |

**Timing differs.** NVSE handlers run inside the engine's call, before the
game acts, and some can cancel what follows. Papyrus events are queued and
arrive later. A mod that relies on cancelling an action in the same frame
needs a native hook, or accepts the drift
([accept drift](../fo4_drift.md)).

## <a id="jip"></a>JIP LN NVSE

About 1,086 live commands (1,118 registered, 32 retired). The categories
that matter:

| Area | ≈Cmds | FO4 route |
|---|---|---|
| Actor runtime: last-hit data, combat targets, detection, velocity, limbs, perks on NPCs | ~212 | Many vanilla; GOE `GetLastHitData`, `GetCombatTargeters`, `GetDetectionLevel`; forced detection needs a hook |
| References, NIF nodes, physics, raycasts, linked refs, map markers | ~147 | Vanilla positions and linked refs; GOE/Hydra raycasts, node and velocity calls. Attaching models and lights at runtime is large native work |
| Item and record fields, leveled lists, recipes | ~157 | F4SE `ConstructibleObject` and `InstanceData`; Hydra `Forms/*`. FNV weapon mod slots become OMODs in the converter |
| Environment: weather, climate, cell, water, texture sets | ~100 | Hydra/GOE field setters; vanilla `ForceActive` for weather |
| Script utilities, INI, files, regex, load order | ~89 | Hydra `Ini`/`Json`/`File`/`Regex`; GOE `ReadIni`/`WriteIni`. `RunScriptSnippet` and `AddScriptVariable` can't port |
| UI: `InjectUIXML`, tiles, minimap, text input | ~66 | [Not portable](#not-portable) |
| Input, gamepad | ~40 | F4SE events, Hydra key state; faking gamepad input is low value |
| Quests, challenges | ~40 | Objectives vanilla; challenges are our own system ([challenges](../fo4_pipeline.md#challenges)) |
| Projectiles, explosions | ~32 | Hydra `Forms/Projectile`; live projectile refs need natives |
| **AuxVars, RefMaps** | 31 | [Below](#aux-storage) |
| Magic effects, sound | 43 | Mostly vanilla and Hydra |
| Hardcore needs, casino, karma, Big Guns, a companion framework | ~45 | No FO4 system; only where our own emulation supplies the target |

JIP's engine fixes and optional gameplay patches (FO3 repair, Big Guns,
DT/DR variants) patch the FNV exe and don't apply.

### <a id="aux-storage"></a>AuxVars and RefMaps

JIP's per-reference storage is common in gameplay mods and has no FO4
equivalent. How it works (`internal/jip_core.h`, `internal/serialization.h`):

- **AuxVar:** mod → owner form → name → array of float, ref or string values.
  Called on a reference, the owner is that reference.
- **RefMap:** mod → map name → reference → value, iterable.
- **Name prefixes:** `*` makes it temporary (never saved). `_` makes it public
  (shared by all mods). Otherwise it is private to the calling mod.
- Saved in JIP's co-save chunks `JPAV` and `JPRM`; form IDs remapped on load.

Hydra's SaveMap can hold this (Var keys, saved in its co-save), but each
namespace must be declared in a JSON file under `Data/Hydra/ScriptSaveMaps/`
(the converter could generate it), and entries for deleted references
aren't removed by themselves. A small F3NV.dll store with the same layout,
the prefix rules and cleanup on form delete is a better fit.

## <a id="f3nv-gaps"></a>What F3NV.dll would add

After Hydra and Garden of Eden, in rough priority:

1. **AuxVar/RefMap store** with an F4SE co-save chunk and cleanup when a
   form is deleted ([above](#aux-storage)).
2. **Hook events missing from both extenders**, each checked against Hydra
   first: any actor firing, reloading, health damage with attacker and
   amount, projectile impact, aid item use, crafting.
3. **A per-frame tick** that wakes registered scripts, for the few
   `GameMode` loops that must run every frame. Most should stay on timers.
4. **Synchronous veto events**, only where a mod has to cancel an action
   (activation, equip) in the same frame.
5. **FNV-only item and record data** ([below](#fnv-only-fields)), saved in
   the co-save. Item condition already works this way (`F3NV_Condition`).
6. **Raw key disable** (`DisableKey`/`EnableKey`). FO4 only has control
   layers (`InputEnableLayer`).
7. **Translation tables** in Papyrus or the converter: FNV actor value codes
   → FO4 `ActorValue` forms, form type codes (`GetFirstRef 42`) → FO4 types,
   FNV menu codes → FO4 menu names, FNV game setting names.
8. Maybe **FNV-named console commands**, added by patching the console
   command table the way F4SE takes over `ForceRSXCrash`
   (`Hooks_ObScript.cpp`). Low priority.

If the [dependency decision](fo4_target.md#dependency-policy) goes against
Hydra, items from layer 3 move here: maps saved in the co-save, strings,
INI/JSON I/O, key state and the global event bus. That is several times
more work; Hydra's surface is about 2,800 natives.

### <a id="fnv-only-fields"></a>FNV-only fields

These NVSE/JIP getters and setters have no FO4 field behind them, so they
read our own data or become no-ops (documented as drift):

- Weapon: condition and health, skill and Strength requirements, VATS hit
  chance, the three mod slots and their effects, `GetWeaponFlags1/2` bits,
  hand grip, sight usage.
- Ammo effects; item health on armor; karma, reputation and hardcore
  needs, where our emulation holds the value.
- Creature-only fields (FO4 has no CREA record).

Record setters in NVSE and JIP aren't saved: mods reapply them every load.
A port can keep that behavior.

## <a id="not-portable"></a>Not portable

- **UI on tile paths:** `GetUIFloat`/`SetUIFloat`, JIP's `InjectUIXML` and
  tile templates, the minimap. FNV's UI is an XML tile tree; FO4's is
  Scaleform. F4SE `UI.Get/Set/Invoke` reach AS3 members with different
  paths. Each mod's UI needs its own SWF or a PrismaUI page.
- **Runtime script compilation:** `CompileScript`, `RunScriptLine`,
  `RunScriptSnippet`, `Call "file.txt"`, JIP's script-runner text files.
  Convert those files ahead of time instead.
- **Runtime form creation and surgery:** `TempCloneForm`, `GenericAddForm`,
  `SetNthDefaultForm`, runtime package editing, `SetScript`/`RemoveScript`.
  Papyrus can't create forms; each case gets a converter-side workaround.
- **kNVSE animation overrides** and FNV animation groups.
- **FNV engine fixes** of any kind.

## <a id="dependencies"></a>Hydra and Garden of Eden as dependencies

| | Hydra 1.0.2 | Garden of Eden 23.6 |
|---|---|---|
| Natives | ~2,800 | ~1,290 |
| Maps saved in co-save | Yes (namespaces declared in JSON) | No |
| Strings, regex | Full | ~10 functions, no regex |
| Global events | ~60, filtered, persistence per registration | 16, filtered, not saved |
| INI, JSON, files | Yes | INI and lines, no JSON |
| Form field get/set | ~1,400 over 40 types | Hundreds |
| Maturity | One author, young, already changed behavior once | Long-running, multi-runtime, required by F4NV add-ons |

Both are in the MO2 instance now. The open question from
[fo4_target](fo4_target.md#dependency-policy) still stands. This research
adds one point: for converted **mods**, as against FNV itself, Hydra is close
to an NVSE stand-in, so depending on it behind our wrapper would save the
most work.

## <a id="usage-survey"></a>Usage survey (2026-11-09)

**Sample:** the Viva New Vegas Extended profile (`C:\Modlists\VNV`,
42 plugins). Scripts in 16 non-vanilla plugins call NVSE or JIP. The
survey reads every SCTX (script source text). Any identifier that also
appears in the vanilla FNV and DLC scripts is dropped. What remains is
counted against command names taken from the xNVSE source (695 names and
aliases) and the JIP source (1,244). Scripts:
`temp/nvse_survey/commands.py` and `survey.py`; full results in
`survey.json`.

**Result:** 436 distinct commands, 10,970 calls. 153 are xNVSE, 283 JIP.
265 are used by a single mod, 171 by two or more, and 92 by three or
more. Calls are lopsided: JustAssortedMods makes 4,623 of them, Enhanced
Movement 1,292, Agua Fria 952. YUP's 3,775 scripts call none. Not
counted: JohnnyGuitar and ShowOff, which VNV installs but whose source we
don't have. Their names show up among the leftover identifiers, e.g.
`SetJohnnyOnCompleteQuestEventHandler` (3 mods), `SendStealingAlarm`
(4), `TapControl` (3), and MCM's `SetMCMFloat`/`SetMCMString`.

The main commands among the 92 used by three or more mods, by route:

| Group | Commands (mods using it) | Route |
|---|---|---|
| Script language | `eval` (14), `Function` (12), `Call` (9), `while`/`loop` (9), `Let` (6), `ForEach`, `continue`, `break`, `SetFunctionValue`, `ar_*` (`ar_Null` 9, `ar_Find` 7, `ar_Size` 6, `ar_List`), `sv_Construct`/`sv_Destruct` | Converter lowering |
| Load and mod checks | `IsModLoaded` (11), `GetGameRestarted` (7), `GetGameLoaded`, `IsFormValid`, `GetFormFromMod`, `GetModIndex`, `GetSourceModIndex`, `GetPluginVersion`, `GetOptionalPatch`, `IsReference` | Vanilla `Game.IsPluginInstalled`/`GetFormFromFile` plus an `OnPlayerLoadGame` alias |
| Events and delays | `SetEventHandler` (11), `SetEventHandlerAlt`, `RemoveEventHandler`, `CallAfterSeconds` (6), `CallWhen` (6), `CallAfterFrames`, `SetGameMainLoopCallback`, `SetOnMenuOpen/CloseEventHandler`, `SetOnUseAidItemEventHandler` | Timers; global events from the extender, F3NV.dll hooks for the rest ([events](#events)) |
| Settings files | `GetINIFloat` (7 mods, 453 calls), `FileExists`, `GetNumericIniSetting` | Extender INI functions, or F3NV.dll |
| Form lists and items | `ListAddForm`, `ListGetCount`, `ListGetNthForm`, `GetListForms`, `IsRefInList`, `AddItemAlt`, `EquipItemAlt`, `BaseRemoveItem`, `GetEquippedObject`, `GetBaseObject`, `GetArmorClass`, `GetItemRefCurrentHealth`, `GetWeaponItemMod*` | Mostly vanilla FormList/ObjectReference and F4SE; condition from `F3NV_Condition` |
| Record fields | `SetNthPerkEntryValue1` (4 mods, 110 calls), `GetPerkModifier`, `Get/SetNumericGameSetting`, `Get/SetFormDescription`, `SetName`, `SetNthEffectTraitNumeric`, `GetNumEffects`, `GetNthEffectBase`, `HasKeyword`, `SetSpeedMult` | F4SE and the extender's form setters; perk entry edits have no Papyrus route |
| Input | `IsKeyPressed`, `EnableControl`/`DisableControl` | F4SE key events, `InputEnableLayer` |
| Interface | `GetUIFloat` (4), `SetUIFloat` (3 mods, 980 calls), `GetActiveMenuMode`, `GetMenuTargetRef`, `RefreshItemsList`, `MessageExAlt` | [Not portable](#not-portable), except `MessageExAlt` → a message |
| Game state | `ToggleHardcoreTracking`, `SetGameHour`, `IsPlayerSwimming`, `GetWaterImmersionPerc`, `GetCrosshairRef`, `GetDistance3D`, `GetMaxOf`/`GetMinOf`, `SetBit`, `IsSpellTargetAlt`, `SetWeaponOut`, `GetAutoMove` | Vanilla, math, or our hardcore emulation |

JIP's per-reference storage is heavily used where it appears:
`AuxiliaryVariable*` calls come from 4 mods (Enhanced Movement,
JustAssortedMods, Unofficial Patch NVSE Plus, Bad Touch), 1,044 calls in
all, 643 of them `AuxiliaryVariableGetFloat`. So
[the F3NV.dll store](#aux-storage) stays first on the DLL list.

**What it means:**
- The script language comes first. `eval`, user functions, loops and
  arrays are in nearly every scripted mod, and no command works without
  them.
- After the language, load checks and timers are vanilla Papyrus, so most
  of the top group needs no extender.
- The extender decision rests on events, INI files and form setters. INI
  alone is 7 of 16 mods.
- `SetUIFloat`-style interface scripting is concentrated in a few mods
  (Vanilla UI Plus, JustAssortedMods, MCM). They stay out of scope.

## <a id="next-steps"></a>Next steps

1. **Usage survey.** Done on VNV ([above](#usage-survey)). Rerun the
   scripts on any other mod list. Add JohnnyGuitar's and ShowOff's command
   names once we have their source.
2. **A converter test corpus** from xNVSE's `unit_tests/*_compiler/*.txt`.
3. **Decide the extender dependency**, then write the wrapper script the
   converter calls.
