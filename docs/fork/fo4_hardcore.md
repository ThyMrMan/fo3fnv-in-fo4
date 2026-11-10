# FNV's Hardcore mode in place of Fallout 4's Survival

Plan, written 2026-11-07; what was built from it is in [As built](#built).
Status lives in [ROADMAP.md](ROADMAP.md#fo4-next).

**The goal:** a converted FNV game on Fallout 4 runs New Vegas's own Hardcore
mode, not FO4's Survival mode. Survival adds needs too, but it handles them
differently. It is tuned to FO4's faster pace and adds disease, adrenaline,
bed-only saves and no fast travel. Hardcore is a separate switch from
difficulty, with slow numeric needs, healing over time, ammo weight, limbs
that need a doctor, and companions who die.

This reverses the 2026-10-22 decision to keep FO4's Survival mode as it is
([drift](fo4_drift.md), the Hardcore row;
[survival needs](fo4_pipeline.md#survival-needs)).

Contents:
1. [What FNV Hardcore does](#fnv)
2. [What FO4 Survival does, and how](#fo4)
3. [What the converter does today](#today)
4. [The approach](#approach)
5. [Step-by-step plan](#plan)
6. [Per-world and all-worlds profiles](#profiles)
7. [Drift, recorded](#drift)
8. [Risks and open questions](#open)
9. [As built](#built)

Sources:
- `export/FalloutNV.esm` and the DLC exports.
- FalloutNV.exe (GOG) and the matching decompilation in `references/fnv_decomp`.
- The FNV Prima guide and the Fallout wiki dump ("Hardcore mode", "Survival mode").
- `references/Fallout4.esm`.
- The vanilla FO4 scripts in `references/fo4_scripts/Base/Hardcore`. `HC_ManagerScript.psc` (3,365 lines) was read in full.

Claims marked *(inferred)* were not confirmed in an exe.

---

## <a id="fnv"></a>1. What FNV Hardcore does

**Hardcore is engine-driven.** One player flag gates every Hardcore behavior:
- the needs ticking;
- ammo weight;
- companion mortality;
- the HUD and Pip-Boy readouts;
- limb healing on sleep.

The flag is `PlayerCharacter+0x7BC`, read by the `IsHardcore` condition at
0x005A5F90. No quest or script drives the needs. The data side is about
190 `IsHardcore` conditions on consumables and spells, plus the switch in
Doc Mitchell's intro.

### <a id="fnv-needs"></a>Needs: thirst, hunger, sleep

**Actor values.** The needs are three actor values on a 0 to 1000 scale:
- 73 `Dehydration` (H2O)
- 74 `Starvation` (FOD)
- 75 `SleepDeprivation` (SLP)

**How the engine raises them.** The tick is `HardcorePlayer` 0x00969C30. It
runs from the player update (0x0093E860) and once per hour waited or slept
(`sleepwaitmenu.cpp` 0x007C0580). For each need it:
1. computes an interval as the rate setting × `TimeScale` / 60, in game minutes;
2. adds 1 to the actor value for each interval that has passed.

Sleep Deprivation does not rise while the player sleeps.

| Need | Setting | Value | Points per game hour (TimeScale 30) |
|---|---|---|---|
| Thirst | `fHCDehydrationRate` | 10 (exe default; FalloutNV.esm does not set it) | 12 |
| Hunger | `fHCStarvationRate` | 25 (FalloutNV.esm; exe default 0.39) | 4.8 |
| Sleep | `fHCSleepDeprivationRate` | 50 (FalloutNV.esm; exe default 0.26) | 2.4 |

**Sleep recovery.** Each hour slept lowers Sleep Deprivation by
`fHCSleepRestorationMod` (60, exe default), but never below 0. The code is
in `PlayerCharacter` 0x0094DF80.

**Stages.** Stages are three new FNV record types: `DEHY` (`Water1`–`Water5`),
`HUNG` (`hunger1`–`hunger5`) and `SLPD` (`sleep1`–`sleep5`). Each holds a
threshold and a spell. The export reads them as `# Unknown record type`, so
the values below were parsed from the ESM itself.

| Need | 200 | 400 | 600 | 800 | 1000 |
|---|---|---|---|---|---|
| Dehydration (`Dehydration200`…`1000`) | END −1 | END −2, PER −1 | END −3, PER −2, INT −1 | END −3, AGL −2, PER −2 | `DamageHealth` 10000: death |
| Starvation (`Starvation200`…) | STR −1 | STR −2, CHR −1 | STR −3, CHR −2, PER −1 | STR −3, CHR −2, PER −2 | death |
| Sleep Deprivation (`SleepDeprivation200`…) | AGL −1 | AGL −2, INT −1 | AGL −3, INT −2, END −1 | AGL −3, END −2, INT −2 | death |

The ESM values above are what the game uses. The Prima guide's dehydration
table differs slightly at 600 and 800.

**What raises or lowers the needs.**
- **Effects.** `Restore*Level` lowers a need and `Damage*Level` raises it.
  The MGEFs are `RestoreDehydrationLevel`, `DamageDehydrationLevel`,
  `RestoreStarvationLevel`, `DamageStarvationLevel`,
  `RestoreSleepDeprivationLevel` and `DamageSleepDeprivationLevel`.
- **Counts in FalloutNV.esm's ALCH and SPEL records:**
  - hunger lowered 96 times;
  - thirst lowered 38 times and raised 27 times;
  - sleep lowered 9 times.
- **Examples:**
  - `WaterPurified`: H2O −50 (+7 more with `WaterChallengePerk`).
  - `InstaMash`: FOD −25.
  - `Whiskey`: H2O +25.
  - `NukaCola`: H2O +10 and SLP −15.
  - Drinking from water sources: the `WaterHeal*` spells, H2O −200.
  - The intro's `VMQ03RestUp` and the DLC `*RestUp` spells: all needs −10000.

**Switching off.** `SetHardcore 0` (0x005DE920 → 0x00969E90) does two things:
- It removes the modifiers on all three needs, so they reset to 0.
- It clears a second flag at `+0xE38`. This is the "always Hardcore" flag that
  tracks the achievement.

### <a id="fnv-healing"></a>Stimpaks, RadAway, ammo weight

**Healing over time.** This part is data-driven. The healing items carry both
versions of their effect, gated by condition function 0x24A `IsHardcore`:
- **`Stimpak`:** in Hardcore, `RestoreHealth` 5 per second for 6 s (6 with
  Fast Metabolism). Otherwise `RestoreHealthStimpak` 30 at once (36 with the
  perk). Checked in the export: effects 0–3, each conditioned on 0x24A plus
  HasPerk 0x94EBF.
- **`RadAway`:** in Hardcore, `RestoreRadiationLevel` 5 per second for 10 s.
  Otherwise 50 at once.

**Ammo weight.** This part is engine-driven.
`TESWeightForm::GetWeightForForm` (0x0048EBC0) returns an AMMO record's
weight only when its caller passes `IsHardcore`. The callers are the
inventory, container, HUD, recipe, interface and player code. All 92 AMMO
records carry a weight in every mode, for example `Ammo223` 0.026 and
`Ammo12GaMagnum` 0.075. There is no ammo-weight game setting.

### <a id="fnv-limbs"></a>Crippled limbs

- **Doctor's Bag.** `NVDoctorBag` gives `NVRestoreLimbs` 36 in Hardcore (45
  with Fast Metabolism), and `RestoreAllLimbs` otherwise.
- **Sleep.** At the end of sleep the engine heals health and the limb
  condition values (0x008A0960, actor values 0x19–0x1F) only when Hardcore is
  off. In Hardcore, sleep does not mend limbs.
- **Pip-Boy.** The Pip-Boy's limb-heal click uses a different healing item in
  Hardcore (`statsmenu.cpp` 0x007DC1B0). It is probably the Doctor's Bag
  *(inferred)*.
- **Doctors** heal limbs through dialogue scripts that are not
  Hardcore-specific.
- **Tutorial.** The tutorial line `CGTutorialCrippleHardcore` ("use a Doctor's
  Bag or find a doctor") is picked by `player.IsHardcore` in
  `VCGTutorialSCRIPT` and `CGTutorialSCRIPT`.

### <a id="fnv-companions"></a>Companions dying for good

- **Engine.** The essential check (`actor.cpp` 0x0087F3D0) treats a player
  teammate as essential whenever Hardcore is off. In Hardcore, companions are
  mortal, and a dead companion stays dead.
- **Scripts.**
  - `HVBunkerExplosionScript` kills the companions left in the Hidden Valley
    bunker only `if player.IsHardcore`.
  - `VNPCFollowersQuestSCRIPT` re-enables a destroyed ED-E (`EDE3REF`) only
    outside Hardcore.

### <a id="fnv-switch"></a>The switch, HUD and achievement

**The switch at the start.** It happens in Doc Mitchell's intro:
1. An INFO result script activates `VCG01CasualHardcoreMessageREF`.
2. That reference's script, `VCG01CasualHardcoreMessageSCRIPT`, shows MESG
   `VCG01CasualHardcoreMessage` with the buttons "No (Recommended)" and "Yes".
3. The script then calls `SetHardcore 1` or `0`.

The message lists the rules. It says the mode can be changed at any time in
the Gameplay settings, and that keeping it on to the end earns a reward.

**The switch later.** The game's settings menu has a Hardcore Mode option
(`startmenu.cpp`). Turning it off and on again works, but the achievement is
lost once it has been off.

**HUD and Pip-Boy.**
- The HUD shows H2O, FOD and SLP as numbers. Their color steps come from four
  engine-only settings, `fHCHalfAlphaTextThreshold` 200,
  `fHCFullAlphaTextThreshold` 400, `fHCRedTextThreshold` 600 and
  `fHCFlashTextThreshold` 800. These match the guide's "dark, light, red,
  pulsing red".
- Stage changes print messages such as `sDehydrationIncrease` and
  `sSleepDeprevationDecrease`.
- The Pip-Boy's Status page gains three sub-tabs (0–5 against 0–2) for the
  needs *(inferred from `statsmenu.cpp`)*.
- Help: `HelpHardcoreNeeds`. Load screen: `HardcoreLoadScreen01`.

**Achievement.** `AddAchievement 30` runs in the ending quests
`VHDHouseBattle`, `VHDIndependentBattle`, `VHDLegionBattle` and
`vHDBattleController`. Each checks `If (player.behemoth == 1)` first.
`behemoth` is the short name of `IsAlwaysHardcore`, which reads the `+0xE38`
flag. Achievements are numbered in the exe; there is no CHAL record for this
one.

### <a id="fnv-counts"></a>Counts

| Plugin | `IsHardcore` on ALCH (records) | on SPEL (records) | Other |
|---|---|---|---|
| FalloutNV.esm | 179 (124) | 11 (8: `VMQ03RestUp`, `CazadorPoison`, the six `WaterHeal*`) | 5 script uses ([markers](script_markers.md)), `SetHardcore` 2 |
| DeadMoney.esm | 30 (25) | 4 (2) | the autodoc MESGs `NVDLC01SuitesAutoDocMsg`, `NVDLC01ClinicAutoDocMsg`; 2 INFOs |
| HonestHearts.esm | 8 (6) | 3 (1) | — |
| OldWorldBlues.esm | 6 (4) | 7 (2) | — |
| LonesomeRoad.esm | 12 (4) | 13 (4) | — |
| ClassicPack.esm | — | 1 (`PreordVault13CanteenHeal`) | — |
| The other packs, GunRunnersArsenal | 0 | 0 | — |

---

## <a id="fo4"></a>2. What FO4 Survival does, and how

**Survival is mostly Papyrus.** One quest, `HC_Manager` (0x80E, start game
enabled), carries `Hardcore:HC_ManagerScript` and `HC_WaterBottleScript`. A
handful of effect scripts call back into it. The engine supplies only the
difficulty level and a few hard-coded rules.

### On and off

- **Start.** `OnInit` registers the player's `OnDifficultyChanged`. It calls
  `StartupHardcore()` if `Game.GetDifficulty() == 6`.
- **Changes.** `Actor.OnDifficultyChanged` (line 164) calls
  `StartupHardcore()` when the difficulty goes to 6, and
  `ShutdownHardcore()` when it leaves 6. Nothing polls.
- **Rule globals.** Nine globals, all 0 in the ESM:
  - `HC_Rule_NoFastTravel`
  - `HC_Rule_AdrenalineOn`
  - `HC_Rule_SleepEffects`
  - `HC_Rule_NoLimbConditionHeal`
  - `HC_Rule_DamageWhenEncumbered`
  - `HC_Rule_ScaleDamage`
  - `HC_Rule_SustenanceEffects`
  - `HC_Rule_DiseaseEffects`
  - `HC_Rule_CompanionNoHeal`

  They are listed in FLST `HC_Rules`. No script sets them except the debug
  function `SetHardcoreMode`, so the engine must set them on difficulty 6
  *(inferred)*.
- **The one-way lock.** Leaving Survival blocks going back. This is an engine
  check on the misc stat "Survival Denied" (wiki). Difficulty 5 is a dead
  "Survival without Hardcore" slot.

### The needs

**Pools.**
- `OnItemEquipped` adds an item's **price** to the food or drink pool, chosen
  by keyword (`ObjectTypeFood`, `HC_SustenanceType_QuenchesThirst`). Some
  keywords take value away instead: 0.65 × price for hunger, 0.5 × price for
  thirst.
- Each 1-hour tick costs 4 from each pool. A 0.1-hour game-time timer drives
  it. Sleep counts at 0.25.

**Stages.**

| Pool | Stages |
|---|---|
| Food | Peckish −24, Hungry −48, Famished −96, Ravenous −144, Starving −256 |
| Drink | Parched −16, Thirsty −36, Mildly Dehydrated −72, Dehydrated −120, Severely Dehydrated −180 |
| Sleep | Rested … Incapacitated; one tier every 14 hours |

**How a stage takes effect.**
- The stage is stored in the actor values `HC_HungerEffect`, `HC_ThirstEffect`
  and `HC_SleepEffect`.
- Stage potions (`HC_HungerEffect_Peckish` … and the rest) are equipped
  silently. Each potion's effects are conditioned on `GetValue(<AV>) == <stage
  global>`. So the stage logic is records, and Papyrus only moves the number.
- The effects:
  - SPECIAL penalties;
  - a lower action point regeneration rate;
  - no sprinting from Exhausted, no running at Incapacitated;
  - damage over time when Starving or Severely Dehydrated.
- The `Fatigue` actor value, a weighted mix of the three needs, shows as the
  red part of the AP bar.

**Sleep.**
- The bed type caps sleep and limits what it cures: a sleeping bag 3 hours,
  a mattress 5, a bed with no cap.
- 7 hours in a bed gives Well Rested or Lover's Embrace.
- `CacheValuesBeforeSleep` / `DamageValuesBackToCachedValues` undo the
  engine's full heal on sleep. The script then gives back a share that grows
  with the hours slept.
- Caffeine takes one tier off and delays the next.

**Disease, adrenaline, cannibalism.** All are Papyrus on the same quest:
- disease from a risk pool (six diseases, antibiotics and herbal cures, immune
  deficiency from RadAway);
- adrenaline (5 kills per rank, up to +50% damage, lost on sleep);
- cannibal hunger.

### Rules outside the needs

| Rule | How | Engine or data |
|---|---|---|
| No fast travel | `HC_Rule_NoFastTravel`, FLST `HC_FastTravelAllowedList`, the Pip-Boy map's `CheckHardcoreModeFastTravel` | engine reads the global *(inferred)* |
| Saving only in beds, no quicksave, no console | nothing in records or scripts | engine, on difficulty 6 *(inferred)* |
| Damage ×2 taken, ×0.5 dealt at difficulty 6 | `fDiffMultHPToPCSV` 2, `fDiffMultHPByPCSV` 0.5 | GMST |
| Damage ×2 taken, ×1.5 dealt on top, conditioned on `HC_Rule_ScaleDamage` | `HC_DamageMultPerk`, multiplying by the actor values `HC_IncomingDamageMult` 2.0 and `HC_OutgoingDamageMult` 1.5 | perk |
| Slow healing | `fDiffMultEffectDuration_SV` 10 | GMST, engine stretches restore effects *(inferred)* |
| No limb healing over time | `HC_ReduceLimbConditionHealRateSpell`, conditioned on `HC_Rule_NoLimbConditionHeal` | spell |
| Lower carry weight, damage when over-encumbered | `HC_ReduceCarryWeightAbility` (−125), `HC_EncumbranceEffect_*` | spell and Papyrus |
| Ammo weight | the AMMO weight field (`Ammo10mm` 0.025) | engine applies it only at difficulty 6 ([confirmed](#dll)) |
| Companions need a stimpak to get up | `CompanionSetNoBleedoutRecovery`, conditioned on `HC_Rule_CompanionNoHeal` | Papyrus |
| Slower respawn | `HC_HoursToRespawnCellMult` 5, `HC_HoursToRespawnCellClearedMult` 4 | engine reads the globals *(inferred)* |
| No enemy markers, shorter compass | GMSTs swapped at difficulty 6; `Game.InitializeMarkerDistances()` refreshes them | engine *(inferred)* |

**HUD.** There are no meters:
- Stage changes show MESG notifications (`HC_HE_Msg_*`, `HC_TE_Msg_*`,
  `HC_SE_Msg_*`, `HC_DE_Msg_*`).
- The stage potions appear in the Pip-Boy's status effects.
- `HC_Tutorial*` help messages explain the rules.

---

## <a id="today"></a>3. What the converter does today

- **Routing.** `fo4_import/record_routes.py` routes "hardcore needs" as a
  system, with the note "rebuilt from quests, globals and scripts". Nothing
  rebuilds it as a system yet.
- **Consumable needs, built 2026-10-23, not played.**
  `fo4_import/spike/survival_needs.py` feeds FNV's need effects into
  **Survival's** pools ([survival needs](fo4_pipeline.md#survival-needs)):
  - Hunger and thirst go through `F3NV_SurvivalNeed`, a script effect calling
    `HC_Manager`'s `ModFoodPoolAndUpdateHungerEffects` and
    `ModDrinkPoolAndUpdateThirstEffects`. The FNV amount is converted to the
    game hours it covers.
  - Sleep becomes one of Survival's two caffeine steps.
  - Items with needs carry `HC_IgnoreAsFood`.
  - These effects count `IsHardcore` as on.
- **Every other `IsHardcore` is read as off:**
  - on consumable effects (`consumable_effects.UNCONVERTED`): the stimpak and
    RadAway heal-over-time variants and the Doctor's Bag's Hardcore limb
    restore are dropped;
  - on message buttons (`spike/attach.py` `_hardcore_off`): Dead Money's
    autodoc "cure exhaustion" is hidden;
  - in scripts: `ishardcore` emits `0` (`script_convert/constants_falloutnv.py`).
    `sethardcore` (2 uses) and the four `behemoth` checks are `;NE:` markers
    ([script markers](script_markers.md)).
- **Difficulty.** FO4's five non-Survival difficulty multipliers already equal
  FNV's. Survival keeps FO4's own
  ([combat feel](fo4_combat_feel.md)).
- **No starting-world global.** The FO4 build has no character
  starting-world global yet.
- **Stage records.** FNV's `DEHY`, `HUNG` and `SLPD` stage records are not in
  the export at all.

So today an FNV character on Fallout 4 has no needs unless the player picks
Survival. Then FO4's whole Survival ruleset runs, with FNV food feeding it.

---

## <a id="approach"></a>4. The approach

### <a id="switch"></a>Turning FO4 Survival off and FNV Hardcore on

**Keep Hardcore apart from difficulty, as FNV does.** Survival needs no
switching off: `HC_Manager` runs only at difficulty 6, so a player who never
picks Survival never gets it. FNV Hardcore becomes its own switch, a global
`F3NV_Hardcore` that our quest reads. Difficulty stays FO4's very easy to
very hard, which already carry FNV's multipliers.

**The switch at the start: FNV's own.** Doc Mitchell's
`VCG01CasualHardcoreMessage` already converts as a message box.
`SetHardcore 1`/`0` converts to a call on our manager. Our manager:
- sets `F3NV_Hardcore` and `F3NV_HardcoreAlways` (the achievement flag);
- starts or stops the needs;
- on `SetHardcore 0`, clears the needs and `F3NV_HardcoreAlways`, as the
  engine does.

The prompt's text stays FNV's, except "Gameplay menu", which points at the
later switch below.

**The switch later.** FO4's Gameplay settings have no free slot, and adding
one means drawing into the settings menu from F3NV.dll. Two Papyrus options
come first:
- **A Hardcore entry in the Pip-Boy.** A weightless holotape or MISC item,
  the pattern `HC_WaterBottleScript` and the FO4 mods use, shows a two-button
  message ("Hardcore: on / off"). Turning it off warns that the reward is
  lost.
- **MCM, when the player has it.** A soft dependency, read only if
  installed: an MCM page with the same switch.

A settings-menu entry from F3NV.dll is the last resort, and only on the
user's say-so.

**If the player picks Survival anyway.** An FNV-start character can still
set difficulty 6. Recommended: our quest also registers
`OnDifficultyChanged`. When an FNV character moves to 6, it shows a message:
"New Vegas characters use Hardcore mode; Survival's needs are turned off".
It then:
- calls `HC_Manager.ShutdownHardcore()`;
- zeroes the sustenance, sleep, disease and adrenaline rule globals;
- turns `F3NV_Hardcore` on.

These are runtime state changes, not record overrides. FO4's engine-side
difficulty-6 rules stay as the player's own choice: bed saves, no quicksave,
damage, ammo weight and the compass. The other choice, leaving both running,
doubles every need, so it is not offered.
See [open questions](#open) item 1.

### <a id="mechanisms"></a>What reuses FO4's own mechanisms

| Piece | FNV | On Fallout 4 | Kind |
|---|---|---|---|
| Need values | engine actor values 73–75 | three new actor values in `FalloutHelpers.esl`: `F3NV_Dehydration`, `F3NV_Starvation`, `F3NV_SleepDeprivation` (0–1000) | records |
| Stage effects | DEHY/HUNG/SLPD records → `Dehydration200` … spells | **One constant ability on the player**, carrying FNV's stage effects as SPECIAL reductions. Each effect is conditioned on `GetValue F3NV_<need> >= 200 AND < 400` (and so on), as vanilla's stage potions are conditioned on `HC_*Effect`. FO4 re-evaluates ability conditions by itself, so no script runs a stage. The 1000 stage is FNV's `DamageHealth` 10000 under the same condition | records (FO4's `HC_*Effect` pattern) |
| Need ticks | engine tick per rate setting | `F3NV_HardcoreManager`, one quest script: a game-time timer (0.1 h, as `HC_Manager`'s poll), adding rate × elapsed game hours from `Utility.GetCurrentGameTime()`. Sleep, wait and fast travel move game time, so they count as in FNV. Sleep Deprivation is held while sleeping (`OnPlayerSleepStart`/`Stop`), then lowered by 60 per hour slept | Papyrus |
| Food, drink, caffeine | `Restore/Damage*Level` effects with an FNV amount | FNV's own amount, 1:1 on the same 0–1000 scale, with no hours conversion. Either a value-modifier effect on our actor value (no script; to be tested, see [open](#open) item 3) or `F3NV_SurvivalNeed` pointed at our manager, its `Amount` property as now | records, else Papyrus |
| `IsHardcore` on effects, spells, messages, INFOs | condition 0x24A | `GetGlobalValue F3NV_Hardcore == 1`, so every Hardcore variant is kept rather than dropped: the stimpak and RadAway over time, the Doctor's Bag limb restore, the `WaterHeal*` and `RestUp` needs, the autodoc option | records |
| `IsHardcore`, `SetHardcore`, `IsAlwaysHardcore` in scripts | script functions | the global's value; `SetHardcore` calls the manager | Papyrus |
| No limb healing on sleep | engine (0x008A0960 skipped) | FO4's `HC_Manager` pattern: cache the six limb condition values on `OnPlayerSleepStart` and damage them back on `OnPlayerSleepStop` | Papyrus |
| No limb healing over time | FNV has none outside sleep | our spell on FO4's MGEF from `HC_ReduceLimbConditionHealRateSpell` (−100 limb heal rate), conditioned on our global rather than `HC_Rule_NoLimbConditionHeal` | records |
| Companions die | engine: teammates are essential unless Hardcore | FO4's `Followers.Companion` alias is Essential (alias flags 0x142). In Hardcore, our quest catches `OnEnterBleedout` on FNV companions and calls `Actor.KillEssential()`, a FO4 native. `HVBunkerExplosionScript`'s and `VNPCFollowersQuestSCRIPT`'s checks read the global | Papyrus |
| Ammo weight | engine weighs AMMO only in Hardcore | FO4 weighs ammo only at difficulty 6. First planned as a Papyrus carry-weight debit; built as an F3NV.dll hook that lets the engine weigh it while Hardcore is on ([DLL](#dll)) | F3NV.dll |
| HUD meters | H2O/FOD/SLP numbers, colored at 200/400/600/800 | First: notifications on each stage change, in FNV's own words (`sDehydrationIncrease` …); the stage ability shows in the Pip-Boy's status effects; FNV's `HelpHardcoreNeeds` as a help message. Built: the numbers on the HUD from F3NV.dll ([DLL](#dll)) | F3NV.dll |
| Pip-Boy needs page | Status sub-tabs | three lines on our STAT tabs ([Pip-Boy tabs](fo4_pipboy_tabs.md)), which F3NV.dll already draws: a small addition to an existing DLL page, not a new DLL need | F3NV.dll (existing) |
| Achievement | Steam achievement 30 | FO4's achievements are FO4's own. The four ending checks read `F3NV_HardcoreAlways`, and `AddAchievement 30` becomes a Vault Boy notification plus a CHALLENGES-tab entry ([challenges](fo4_pipeline.md#challenges-left-out)) | Papyrus |

### <a id="dll"></a>What uses F3NV.dll

The user approved F3NV.dll for the ammo weight and the UI (2026-11-07).
Everything else stays records and Papyrus. Code:
`tes_runtime/fo4_condition/hardcore.cpp`, fed by the native script
`F3NV_HardcoreNative.Track(global, needs)`, which `F3NV_Hardcore` calls on
start and on each load.

**Ammo weight** (confirmed in Fallout4.exe 1.11.240):
- FO4's form weight is `0x321FD0`. It switches on the form type
  (`formType - 0x1A`, jump table at `0x32210C`).
- The AMMO case (type 0x2C) at `0x3220D9` calls the difficulty getter
  `0xD6D600` at `0x3220E0`. It returns the weight (TESWeightForm at +0x150)
  only when the answer is 6, else 0.
- The getter returns 5 + Survival's flag byte for a stored difficulty of 5
  or more, so 6 means Survival.
- The ALCH case (type 0x30, `0x322057`) has a Survival test of its own,
  which is left alone.
- The hook points that one call at `AmmoDifficulty`, which answers 6 while
  `F3NV_Hardcore` is on and the real difficulty otherwise. The engine then
  weighs ammo everywhere it weighs items: the Pip-Boy, containers, barter
  and carry weight. FNV's ammo carries FNV's weight in its AMMO DATA
  (`consumables.ammo`).
- Drift: FO4's own ammo also weighs its record's weight while Hardcore is
  on, as it does in Survival.

**HUD.** `HUDMenu.swf` pins `LeftMeters_mc`, which holds the health bar,
to the bottom left. On each HUD open, F3NV.dll adds a clip above it with
three text fields: H2O, FOD and SLP. An enterFrame listener updates them
from the player's three need values while the global is on, and hides
them otherwise.
- Font: `$MAIN_Font_Bold`.
- Steps, from the guide's "dark, light, red, pulsing red" at FNV's
  thresholds *(the exact alpha below 200 is inferred)*:
  - dim (half alpha) below 400;
  - full from 400;
  - the HUD's warning color from 600;
  - flashing from 800.
- Colors: the player's `iHUDColor*` and `iHUDColorWarning*`. The HUD's own
  scripts never tint, so the engine colors only its own clips, not a field
  we add.

**Not built: a Hardcore line in the Gameplay settings menu.** The plan
switches through the Hardcore Mode aid item, so nothing needs it.

### <a id="retire"></a>What changes in today's code

- `survival_needs.py`:
  - retargeted from `HC_Manager`'s pools to our actor values and FNV's own
    amounts;
  - the hours conversion, the caffeine potions and `HC_IgnoreAsFood` dropped.
  
  Vanilla FO4 food the player eats is then neither fed by price into
  Survival nor counted by us. FNV's world has FNV food.
- **The `IsHardcore` handling:**
  - `consumable_effects.UNCONVERTED` and `attach._hardcore_off` write the
    global condition instead of settling the test as off;
  - `constants_falloutnv.py` emits a read of the global for `ishardcore` and
    `behemoth`, and a manager call for `sethardcore`.
- **The export** learns `DEHY`, `HUNG`, `SLPD` and `RADS`, so the stage
  thresholds and spells come from the data, not from a table.

---

## <a id="plan"></a>5. Step-by-step plan

Each step is one build and one play check
([single-variable tests](../../CLAUDE.md#verifying-your-work)). Every new
form gets a hashed FormID from authored data: the FNV EditorID, or a fixed
site key for the helper forms. No existing FormID moves. The retargeted
`F3NV_SurvivalNeed` effects keep their keys.

1. **Export the stage records.** Teach the FNV export `DEHY`, `HUNG`,
   `SLPD` and `RADS` (threshold + spell). Check: 5 of each in FalloutNV.esm,
   thresholds 200–1000, spells as listed in [section 1](#fnv-needs).
2. **Helper forms** in `FalloutHelpers.esl`:
   - the three need actor values;
   - the globals `F3NV_Hardcore` and `F3NV_HardcoreAlways`;
   - the quest `F3NV_Hardcore` (not start-enabled; started by the switch);
   - the ammo FormList;
   - the limb heal-rate spell.

   Check: FO4Edit 0 errors.
3. **Stage ability.** One ability built from the stage records and FNV's
   stage spells, its effects conditioned on the need's range. Death at 1000
   by FNV's `DamageHealth` effect. Check: `SetValue F3NV_Starvation 450` in
   the console shows STR −2, CHR −1.
4. **The manager script.** `F3NV_HardcoreManager`:
   - ticks the needs at FNV's rates, read from the GMSTs and `TimeScale` at
     build time, as `survival_needs.fnv_per_hour` does;
   - handles sleep, through Sleep Deprivation held and lowered, and the limb
     values cached and restored;
   - sends the stage messages;
   - provides `SetHardcore` / `IsHardcore` for converted scripts.

   Check: a game hour waited raises H2O 12, FOD 4.8, SLP 2.4 under FNV's
   TimeScale.
5. **Consumables.** Retarget `survival_needs.py` to FNV amounts on our
   actor values. Write `IsHardcore` as the global condition on every effect
   and spell. Check: purified water −50 H2O; a stimpak heals over 6 s in
   Hardcore and at once outside it; the Doctor's Bag mends limbs.
6. **Scripts and messages.**
   - `ishardcore` / `behemoth` read the globals; `sethardcore` calls the
     manager.
   - The Doc Mitchell prompt works.
   - The autodoc button is gated on the global.

   Check: the intro's "Yes" starts the needs, and "No" leaves them off.
7. **Companions.** Bleedout → `KillEssential` in Hardcore; the bunker and
   ED-E checks. Check: a companion downed in Hardcore dies, and outside it
   recovers.
8. **Ammo weight.** The F3NV.dll hook ([DLL](#dll)). Check: 500 rounds of
   .308 weigh FNV's weight in the Pip-Boy while Hardcore is on, nothing when
   it is off.
9. **Later switch and Survival guard.** The Pip-Boy Hardcore item and the
   optional MCM page. The `OnDifficultyChanged` guard that shuts down
   `HC_Manager` for FNV characters at difficulty 6.
10. **Pip-Boy page and ending reward.** Needs on the STAT tabs; the
    achievement notification and the challenge entry.
11. **DLC.** The same steps over the DLC plugins' 56 ALCH and 28 SPEL
    `IsHardcore` conditions, and Dead Money's two autodoc messages. The
    manager is shared.
12. **Docs.** Update the [drift](fo4_drift.md) Hardcore row and the
    consumable-needs row, and the [survival needs](fo4_pipeline.md#survival-needs)
    record. Status goes to ROADMAP.

---

## <a id="profiles"></a>6. Per-world and all-worlds profiles

- **Rules key on the character's starting world.** Hardcore is FNV's rule,
  offered only in FNV's intro. A character who starts in FO3 never sees the
  prompt, so `F3NV_Hardcore` stays 0 and nothing runs. FO3 had no Hardcore.
  - The FO4 build has no starting-world global yet. It is needed for the
    Survival guard (step 9) and is shared with the
    [character plan](character.md#profiles). Until it exists, the guard can
    key on `F3NV_Hardcore` having been offered: VCG01's prompt ran.
- **Per-world profile.** FNV's plugins, `FalloutHelpers.esl` and F3NV.dll.
  Everything above applies as written.
- **All-worlds profile (FO3 + FNV).**
  - The globals and the quest live in the shared helper plugin, so they are
    loaded once.
  - The state is the character's own: a global in the save.
  - An FNV Hardcore character keeps Hardcore when travelling to the Capital
    Wasteland. FO3's food and water carry no need effects, though, so they
    would not feed it. See [open](#open) item 4.
- **No base-game overrides.** No Fallout4.esm record is edited:
  - `HC_Manager` is called, not changed;
  - the rule globals are set at runtime, only for an FNV character who picks
    Survival;
  - the limb spell is our copy.

---

## <a id="drift"></a>7. Drift, recorded

- **Pace.** FO4's default TimeScale is 20 and FNV's is 30. The rates are
  written per game hour, so they follow whatever TimeScale the build sets.
  At 20, needs rise 1.5 times slower in real time.
- **Ammo weight** is the engine's own, through F3NV.dll ([DLL](#dll)).
  While Hardcore is on, FO4's own ammo weighs too.
- **HUD.** The H2O, FOD and SLP numbers sit above FO4's health bar
  ([DLL](#dll)).
- **The settings-menu switch** becomes a Pip-Boy item or MCM.
- **The achievement** becomes a notification and a challenge entry.
- **Doctors.** They work through their converted scripts, as now.
- **Fatigue.** FO4's red AP bar does not show FNV's needs.

---

## <a id="open"></a>8. Risks and open questions

1. **Survival at difficulty 6.** Should an FNV character be able to pick it
   at all? This plan shuts down Survival's needs and keeps its engine rules.
   - Risk: the engine may rewrite the `HC_Rule_*` globals on a difficulty
     change or a load *(inferred)*. The guard then re-applies them on
     `OnPlayerLoadGame`, as Survival-tuning mods do.
   - Alternative: hide or refuse difficulty 6 for FNV characters, which needs
     a DLL.
   - Needs the user's choice.
2. **Engine checks to confirm in Fallout4.exe:**
   - that ammo weighs nothing below difficulty 6 (confirmed, see [DLL](#dll));
   - that nothing outside `HC_Manager` reacts to our actor values;
   - what writes the `HC_Rule_*` globals.
3. **Value-modifier effects on a new actor value.** Can a plain FO4
   value-modifier MGEF lower `F3NV_Starvation` by a magnitude, with no script?
   - FO4's restore effects only undo damage, and our tick raises the value.
   - Test in step 5: tick by `DamageValue` on an actor value whose base is
     1000 and read the need as 1000 − current. Restore then lowers the need
     natively.
   - If that fails, keep the `F3NV_SurvivalNeed` script effect, as built.
4. **FO3 food for FNV Hardcore characters** in the all-worlds profile. The
   options:
   - leave FO3 food without needs (drift);
   - give FO3 consumables FNV amounts by the matching FNV item, where both
     games share one (Purified Water, Nuka-Cola, InstaMash). Items with no
     match stay without needs.
5. **TimeScale.** Which TimeScale the converted FNV game runs at. The pace
   of needs follows it.
6. **Existing saves.** A save from the Survival-needs build has
   `F3NV_SurvivalNeed` effects that pointed at `HC_Manager`. Their FormIDs
   are kept, and only their script properties change. Saves made at
   difficulty 6 keep Survival until the guard runs on load.
7. **Performance.** One game-time timer every 0.1 h. That is within the [Papyrus cost](performance.md#papyrus) rules,
   and lighter than `HC_Manager`'s six timers.

---

## <a id="built"></a>9. As built

Built 2026-11-07. It has not been built into the game or played. Code:
- `fo4_import/spike/hardcore.py`;
- the static scripts `F3NV_Hardcore`, `F3NV_HardcoreNeed`, `F3NV_HardcoreItem`
  and `F3NV_HardcoreNative`;
- `tes_runtime/fo4_condition/hardcore.cpp` in F3NV.dll ([DLL](#dll));
- the script rows in `script_convert/command_rows_fallout4.py`.

**Decisions taken on the open questions** (the recommended option each time;
any can be changed):
- **Survival at difficulty 6** (item 1). A character who has made FNV's
  Hardcore choice and picks Survival gets Hardcore instead:
  - The quest calls `HC_Manager.ShutdownHardcore()`, sets
    `HC_Rule_SustenanceEffects`, `HC_Rule_SleepEffects`,
    `HC_Rule_DiseaseEffects` and `HC_Rule_AdrenalineOn` to 0, shows a
    notification, and turns Hardcore on.
  - It does this again on each load while the difficulty is 6.
  - Survival's engine rules stay: bed saves, damage, no fast travel.
- **FO3 food in the all-worlds profile** (item 4). It stays without needs.
- **TimeScale** (item 5). It stays FO4's 20, which `F3NV_NewGame` sets. The
  rates are per game hour, so needs rise 1.5 times slower in real time than
  in FNV.
- **Need effects** (item 3). They stay script effects (`F3NV_HardcoreNeed`).
  This is the one path known to work; the value-modifier test was not run.
- **The later switch.** The Hardcore Mode aid item, not MCM.

**What the build makes** (FalloutNV.esm; counts from a run on the real export
and Fallout4.esm through a stub writer, no plugin written):

| Piece | How |
|---|---|
| Needs | Three helper plugin actor values: `Dehydration` 0x823, `Hunger` 0x824, `SleepDeprivation` 0x825. FNV's script spellings `SleepDeprevation` and `Starvation` alias them, so FNV conditions and scripts that read the needs convert as they stand. |
| Globals | `F3NV_Hardcore` (record conditions read it for `IsHardcore`) and `F3NV_HardcoreAlways`. |
| Stages | 12 potions, `FNV_Dehydration200` … `FNV_SleepDeprivation800`, named as FNV's stage spells ("Minor Dehydration" …). Each holds its spell's effects with a 0x337E4680-second duration, each effect tested `GetValue need >= threshold AND < next`. Each carries Survival's `HC_EffectType_*` keyword. The manager equips one silently when its stage begins, as Survival does. The 1000 stage kills. The thresholds and spells are read from FalloutNV.esm's DEHY, HUNG and SLPD records (two uint32s each); the export does not read those types. |
| Rates | 12, 4.8 and 2.4 points per game hour (`fHCDehydrationRate` exe default 10, `fHCStarvationRate` 25, `fHCSleepDeprivationRate` 50, TimeScale 30). Sleep takes 60 an hour (`fHCSleepRestorationMod`). |
| Messages | 6 notifications in FNV's words: the ESM's `sDehydration*` and `sSleepDeprevation*`, and FalloutNV.exe's text for `sHungerIncrease` and `sHungerDecrease` ("Your Hunger level has increased"). Also the Survival notification and the two boxes of the Hardcore item. |
| Quest | `FNV_Hardcore`, start-game, running `F3NV_Hardcore`. It ticks the needs every 0.1 game hours from `GetCurrentGameTime`, so wait, sleep and fast travel count. It holds Sleep Deprivation while sleeping, then lowers it per hour slept. It caches the six limb conditions on sleep and damages back what sleep healed. It also runs the Survival guard, and hands F3NV.dll the global and the needs on start and on each load. |
| Switch | `SetHardcore 1/0` in Doc Mitchell's `VCG01CasualHardcoreMessageSCRIPT` calls the quest's `SetHardcore`. The first call gives the **Hardcore Mode** aid item: a weightless hotkey item, as the Ammo Type hotkey. Using it shows the three needs (H2O, FOD, SLP) and a switch. Turning Hardcore off resets the needs and clears `F3NV_HardcoreAlways` for good, as FNV clears its tracking flag. |
| Scripts | `IsHardcore` reads `TES4Hardcore.IsOn()`. `IsAlwaysHardcore` and its short name `behemoth` read `IsAlways()`. `SetHardcore` calls `SetHardcore()`. `TES4Hardcore` is filled by name with the quest. This retires the bunker and ED-E `IsHardcore` markers and the two `SetHardcore` markers. |
| Conditions | `IsHardcore` on consumable and spell effects becomes `GetGlobalValue F3NV_Hardcore`, so both variants are kept: the stimpak's 5/s for 6 s and its 30 at once, RadAway's over 10 s, the Doctor's Bag limb restore, the `WaterHeal*` and `RestUp` needs. In dialogue and message buttons it maps through the form map (`say_topics.HARDCORE_KEY`), so Dead Money's autodoc "cure exhaustion" shows in Hardcore. |
| Need effects | Script effects of FNV's own amount on the 0–1000 scale, with no hours conversion. They are keyed as the Survival feed's were (`FNV survival need`, effect and amount), so no FormID moves. |
| Ammo weight | F3NV.dll lets FO4's form weight weigh AMMO while `F3NV_Hardcore` is on, as it does in Survival ([DLL](#dll)). Each converted AMMO holds FNV's weight. |
| HUD | F3NV.dll shows H2O, FOD and SLP above the health bar while Hardcore is on, dim below 400, full from 400, the warning color from 600, flashing from 800 ([DLL](#dll)). |
| DLC | They master the base game's forms (derive_formid returns the master's). Their consumables' `IsHardcore` and need effects convert the same way. |

**Removed:**
- The Survival feed: `spike/survival_needs.py`, `F3NV_SurvivalNeed`, the two
  hidden caffeine potions, and `HC_IgnoreAsFood` on items with needs.
- FNV consumables no longer feed `HC_Manager`. A non-FNV character who plays
  Survival is fed by price, as vanilla.
- The "Hardcore is off" settling in `attach._gate` and
  `consumable_effects`. A build with no stage records (FO3) still settles
  `IsHardcore` as off.

**Not built, for later:**
- **Companions.** FNV makes every teammate essential outside Hardcore, and
  falls back to the actor's own Essential flag in Hardcore. FO4's
  `SetPlayerTeammate`, as converted, never makes one essential, so in
  Hardcore converted companions already behave as FNV's. Outside Hardcore
  they are mortal unless their record is Essential. Fixing that needs a
  teammate hook that FO3 builds, whose followers die, must not take.
- **The ending's reward.** `AddAchievement 30` is still a marker. The ending
  checks now read `IsAlways()`.
- **A settings-menu line.** The Hardcore Mode aid item is the switch.
- **An existing save past the intro** gets no Hardcore item, since
  `SetHardcore` never runs for it. The console can add `FNV_HardcoreItem`.
- **FNV refuses sleep, wait or fast travel that would kill.** Not done:
  Hardcore death waits for the next tick.

**Build steps** (main session):
- the helper plugin (`FalloutHelpers.esl`, three new actor values);
- `--scripts-only` for FalloutNV.esm (new static scripts, the `SetHardcore`
  rows);
- the base FalloutNV.esm import, then the DLCs;
- F3NV.dll: `tes_runtime/fo4_condition/build.bat` (call the Community
  `vcvars64.bat` first), then deploy `tes_runtime/dist/F3NV.dll` with the
  scripts. Without it, ammo weighs nothing and the HUD shows no needs; the
  rest works.

No existing FormID moves. The `F3NV_HardcoreAmmo` keyword of the first build
was never shipped and is gone.
