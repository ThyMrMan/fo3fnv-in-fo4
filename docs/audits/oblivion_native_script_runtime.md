# Oblivion scripts on a native runtime: commands needed beyond MorrowindRuntime

**Date:** 2026-09-30 · **Corpus:** `export/Oblivion.esm`, `export/Nehrim.esm` ·
**Question:** if TES4 scripts ran in an SKSE runtime like MorrowindRuntime
instead of being converted to Papyrus, how many commands would be new, and how
much Oblivion.exe code sits behind them?

## Method

- **Command list:** Oblivion.exe's own script command table, read in place
  (1.2.0416 from the Nehrim install). Script commands: RVA `0x70c8c0`, 370 rows
  of 0x28 bytes. Console commands: RVA `0x70b420`, 131 rows. The row layout is
  xOBSE's `CommandInfo` (`CommandTable.h`): +0 long name, **+4 short alias**,
  +8 opcode, **+0x18 execute handler**. `tools/disasm/oblivion_engine_extract.py`
  reads the same table but labels the +4 field "description". It is really the
  short alias (`evp`, `PMS`, `SetAV`).
- **Call sites:** every identifier in `SCPT.SCTX`, `INFO.ResultScript` and
  `QUST Stage[].Log[].ResultScript` that matches a long name or alias. Comments
  and string literals are stripped first. A local variable that shares a
  command's name is counted, so the counts are an upper bound.
- **MorrowindRuntime coverage:** joined by name against
  `tools/script/mwscript_opcode_audit.py --tsv` (508 registrations; ported, no-op
  or stub). **Name match is an upper bound on reuse.** For example, MWScript
  `Say` plays a sound file, while TES4 `Say` speaks a topic.
- **Handler size:** the bytes reachable by recursive descent inside each
  execute handler, without following calls (capstone, x86-32).

## Results

| | Commands | Call sites | Share |
|---|---:|---:|---:|
| Used by Oblivion.esm or Nehrim.esm | 270 | 59,601 | 100% |
| Same name already ported in MorrowindRuntime | 52 | 26,121 | 43.8% |
| Same name, MorrowindRuntime no-op | 1 | 185 | 0.3% |
| Same name, MorrowindRuntime stub | 7 | 1,708 | 2.9% |
| No MorrowindRuntime counterpart | 210 | 31,587 | 53.0% |
| **New work (not ported)** | **218** | **33,480** | 56.2% |

Oblivion.esm uses 252 distinct commands and Nehrim.esm uses 176.

How concentrated the new work is:

| First N new commands | Call sites covered | Share of new |
|---:|---:|---:|
| 20 | 24,051 | 72% |
| 50 | 29,960 | 89% |
| 100 | 32,467 | 97% |
| 150 | 33,265 | 99.4% |

**Handler code:** the 270 used handlers total 41,972 bytes (median 91 bytes,
largest `PlaceAtMe` at 2,016). All 501 table handlers total 83,415 bytes.
Handlers are thin. They unpack arguments and call into Oblivion's `Actor`,
`TESQuest` and process classes, and none of those exist in Skyrim. So reading a
handler tells you what the command meant in Oblivion, not how to do it in
Skyrim. That Skyrim-side mapping is the real cost, and it is the same work
`script_convert` already does for Papyrus.

### Block types (event hooks)

Each block type a script uses needs an engine event delivered to the runtime.
MWScript has only a few engine-written locals (`OnActivate`, `OnDeath`,
`OnPCEquip`…), so MorrowindRuntime's event wiring covers very little of this.

- **Oblivion.esm, 27 block types:** `GameMode` 1332, `OnActivate` 891,
  `OnDeath` 441, `OnReset` 215, `OnLoad` 208, `OnPackageDone` 174, `OnTrigger`
  151, `OnPackageEnd` 133, `OnAdd` 102, `OnPackageChange` 89,
  `ScriptEffectStart` 84, `OnHit` 82, `OnPackageStart` 61, `ScriptEffectFinish`
  57, `OnMagicEffectHit` 44, `MenuMode` 42, `OnEquip` 41, `ScriptEffectUpdate`
  35, `OnAlarm` 32, `OnTriggerActor` 31, `OnHitWith` 31, `OnStartCombat` 29,
  `OnUnequip` 23, `OnDrop` 8, `OnTriggerMob` 5, `OnSell` 2, `OnActorEquip` 1.
- **Nehrim.esm:** 22 vanilla block types, plus 7 OBSE `Function` blocks.

### OBSE

These names come from the `DEFINE_COMMAND`/`kCommandInfo_` entries in
`references/xOBSE-master/obse/obse/Commands_*.cpp`, 1,550 names in all.

- **Oblivion.esm:** 3 matches, 19 hits. All three are local-variable name
  collisions, not real OBSE calls.
- **Nehrim.esm:** 37 distinct, 953 hits. Most are OBSE's expression language,
  not commands: `call` 474, `eval` 174, `let` 156, `loop` 21, user `Function`
  blocks 7. A runtime that runs Nehrim must implement OBSE's expression
  evaluator. Its source is in `references/xOBSE-master`, so this needs no
  disassembly.

### Bytecode

`export/*/SCPT.txt` holds only the source text (`SCTX`). The CS-compiled
bytecode (`SCDA`) is not exported. A runtime has two options:

- compile the source itself, as MorrowindRuntime does with OpenMW's MWScript
  compiler. No Oblivion compiler exists to vendor.
- interpret `SCDA`. xOBSE documents the format. This needs `tes4_export` to
  dump `SCDA`.

## Top 50 new commands

| # | Command | Alias | Oblivion | Nehrim | Handler bytes | MW runtime |
|---:|---|---|---:|---:|---:|---|
| 1 | `SetStage` | | 3479 | 1310 | 117 | — |
| 2 | `GetStage` | | 2078 | 1049 | 89 | — |
| 3 | `MoveToMarker` | `MoveTo` | 850 | 1468 | 159 | — |
| 4 | `EvaluatePackage` | `evp` | 1163 | 699 | 62 | — |
| 5 | `PlayGroup` | | 841 | 815 | 742 | stub |
| 6 | `SetActorValue` | `SetAV` | 416 | 868 | 138 | — |
| 7 | `Message` | | 313 | 926 | 527 | — |
| 8 | `IsActionRef` | | 757 | 279 | 136 | — |
| 9 | `GetSelf` | `this` | 619 | 186 | 119 | — |
| 10 | `MessageBox` | | 482 | 255 | 893 | — |
| 11 | `SayTo` | | 318 | 366 | 352 | — |
| 12 | `SetFactionRank` | | 542 | 90 | 182 | — |
| 13 | `GetParentRef` | | 426 | 145 | 97 | — |
| 14 | `Look` | | 182 | 375 | 145 | — |
| 15 | `StopQuest` | | 441 | 55 | 80 | — |
| 16 | `GetDead` | | 405 | 86 | 23 | — |
| 17 | `PlayMagicShaderVisuals` | `PMS` | 149 | 333 | 450 | — |
| 18 | `GetInCell` | | 394 | 57 | 89 | — |
| 19 | `SetAlert` | | 263 | 179 | 117 | — |
| 20 | `GetStageDone` | | 319 | 73 | 105 | — |
| 21 | `AddScriptPackage` | | 275 | 101 | 407 | — |
| 22 | `SetEssential` | | 279 | 84 | 134 | — |
| 23 | `StartQuest` | | 324 | 11 | 80 | — |
| 24 | `StartConversation` | | 165 | 124 | 374 | — |
| 25 | `PickIdle` | | 189 | 96 | 248 | — |
| 26 | `KillActor` | `kill` | 167 | 113 | 115 | — |
| 27 | `IsAnimPlaying` | | 211 | 62 | 254 | — |
| 28 | `SetGhost` | | 89 | 168 | 140 | — |
| 29 | `GetActorValue` | `GetAV` | 94 | 128 | 89 | — |
| 30 | `SetQuestObject` | | 191 | 30 | 113 | — |
| 31 | `DisableLinkedPathPoints` | | 141 | 79 | 22 | — |
| 32 | `Reset3DState` | | 125 | 81 | 28 | — |
| 33 | `EquipItem` | `EquipObject` | 157 | 46 | 514 | — |
| 34 | `RemoveMe` | | 7 | 192 | 283 | — |
| 35 | `ShowMap` | | 171 | 14 | 259 | no-op |
| 36 | `SetDestroyed` | | 157 | 26 | 102 | — |
| 37 | `EnableLinkedPathPoints` | | 110 | 67 | 22 | — |
| 38 | `StopMagicShaderVisuals` | `SMS` | 92 | 79 | 169 | — |
| 39 | `GetRandomPercent` | | 91 | 64 | 23 | — |
| 40 | `SetOpenState` | | 73 | 65 | 178 | — |
| 41 | `ModPCFame` | | 138 | 0 | 136 | — |
| 42 | `TriggerHitShader` | `ths` | 36 | 102 | 78 | — |
| 43 | `GetIsCurrentPackage` | | 123 | 8 | 102 | — |
| 44 | `ModPCMiscStat` | `ModPCMS` | 40 | 76 | 98 | — |
| 45 | `SetOwnership` | | 112 | 0 | 125 | — |
| 46 | `IsInCombat` | | 31 | 80 | 25 | — |
| 47 | `PlayMagicEffectVisuals` | `PME` | 109 | 1 | 762 | — |
| 48 | `ModActorValue` | `ModAV` | 91 | 18 | 176 | — |
| 49 | `GetIsID` | | 90 | 15 | 89 | — |
| 50 | `SetCellPublicFlag` | `setpublic` | 101 | 0 | 107 | — |

The other 168 each have fewer than 100 call sites across both plugins.

**Same-name commands MorrowindRuntime already ports (52):** Disable, Enable,
GetSecondsPassed, AddItem, PlaySound, Activate, GetDistance, RemoveItem,
GetItemCount, Say (different meaning), AddSpell, Cast, RemoveSpell, GetDisabled,
StartCombat, ModDisposition, GetLevel, Unlock, SetPos, GetPos, GetDeadCount,
Lock, AddTopic, PlaySound3D, EnablePlayerControls, DisablePlayerControls,
ResurrectActor, StopCombat, PlaceAtMe, GetButtonPressed, SetFactionReaction,
GetAngle, Rotate, SetAngle, GetLineOfSight, GetDisposition, GetDetected,
GetLocked, GetCurrentTime, PayFine, GetCurrentAIPackage, SetScale,
ModFactionReaction, MenuMode, GetStartingPos, GoToJail,
GetPlayerControlsDisabled, PositionCell, GetStartingAngle, Drop, PayFineThief,
GetForceSneak.

## AI packages

Oblivion.exe's RTTI has 9 `*Package` classes: `TESPackage`, `AlarmPackage`,
`DialoguePackage`, `FleePackage`, `SpectatorPackage`, `TrespassPackage` and 3
`Extra*`. None of them is a per-procedure class for Find, Follow, Wander, Eat
and the rest. So the procedures are built into the actor process code, beside
its pathing, detection and combat, and cannot be lifted out on their own. This
audit did not measure that code's size.

## Where recent quest fixes landed

I read the subjects of the 59 fix commits from the last 60 days that mention
quest/stage/script/package/dialog. After dropping merges and unrelated hits
(LOD, textures, release, GUI, weather, BSA), about 41 remain. **This sort is my
reading of commit subjects, not of the diffs.**

- **About 20 come from translating to Papyrus.** A native runtime would remove
  this class of bug: property and VMAD binding, name and EditorID resolution,
  Papyrus typing and `ObjectReference`→`Actor` promotion, `GameMode` poll
  start, Say/stage timing races, master-script rekeying.
  Examples: `d00d304f`, `229eded2`, `ef5ff4b8`, `62d813d3`, `c42d7ece`,
  `150bafdc`, `a5ef621d`, `c0f65b30`, `31238afe`, `6687ab20`.
- **About 9 come from what a command means in Skyrim.** These stay with a
  native runtime, because C++ must make the same choice: `1fb0300e`
  StartCombat, `052f4639` SetFactionRank -1, `69c9b452` SetDestroyed,
  `da8d6dd9` havok release, `67a9f8b3` Speed/StopCombat, `75762ac6` GetInCell.
- **About 12 are not scripts at all** and stay: dialogue, packages, aliases,
  conditions, records. Examples: `21356b0b`, `e07ca011`, `804f8a97`,
  `7787a11a`, `3ae6bf34`, `6934e4e1`, `7df23ba2`.
