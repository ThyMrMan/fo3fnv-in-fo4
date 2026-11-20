# FO3 preflight triage on Fallout 4 (2026-11-19)

The first preflight run (`py -3.14 -m tools.validate.preflight --fo4
temp/profile_data_fo3/Fallout3.esm`) on the FO3 whole-map build, triaged into
`tools/validate/preflight/review_ledger.json`. Each decision was checked
against `export/Fallout3.esm` and the build; every number here was measured on
that build.

## Counts

| Audit | Before: errors / reviews | After: errors / reviews / hidden |
|---|---|---|
| quest | 5 / 4 | 7 / 0 / 2 (the 4 MS14 reviews now `bug`) |
| start | 0 / 2,143 | 1 / 10 / 0 (alias audit fix; the 1 is MS14Fin, `bug`) |
| dialogue | 216 / 0 | 216 / 0 / 0 (left open) |
| conditions | 5 / 292 | 5 / 292 / 0 (left open) |
| menus | 1 / 0 | 1 / 0 / 0 (left open) |
| targets | 1 / 13 | 1 / 0 / 13 |
| timing | 123 / 3 | 62 / 3 / 0 (timing audit fix; all 62 are MS14 `bug`) |
| properties | 1,542 / 226 | 1,651 / 52 / 65 |
| packages | 0 / 67 | 0 / 0 / 67 |
| behavior | 3 / 252 | 2 / 252 / 1 |

Errors grew in properties because a `bug` decision lists a review as an error.
1,684 findings are now marked `bug`; 871 are undecided. Measured on the
rebuild with the QF_Doctors fix (one QUST changed against the deployed
plugin, no FormID added or removed).

## Confirmed bugs (ledger `bug`)

| Bug | Findings | What it breaks |
|---|---|---|
| Quest MS14 is renamed `myMS14` (`safe_property_name`, `papyrus_reserved`) and the FO4 fill matches by name, never undoing the rename | 84 properties, 62 timing, 4 quest, MS14Fin start | "You Gotta Shoot 'Em in the Head": every SetStage, objective and variable write hits None |
| Speech challenge globals `TES4SpeechNeed0`-`5`: the script stage adds them to every challenge line, no FO4 step makes them | 1,398 (233 lines x 6) | Every FO3 speech challenge's Reroll gets None |
| `Say <topic> 1 <speaker>` (said as someone else) converts to `SpeakAs` + a `TES4Scene_` property only the Skyrim importer builds | 11, plus the CrMisterGutsy target | Fawkes's intercom, the MS14 power armor voice, Button Gwinnett's 4 intercoms, the planetarium, the Adams Morgan preacher say nothing |
| Script-named explosions (EXPL) have no on-demand maker (fixed: medium fixes) | 47 | Scripted explosions and traps (the Megaton nuke, FakeForce pushes) place nothing |
| WEAP/ARMO with no `replacements.json` entry are never built (fixed: medium fixes) | 22 | MQ04's rolling pin, slasher knife and mask; slave collars; Pip-Boy glove; creature weapons scripts fire |
| Non-reference forms typed `ObjectReference` (imagespaces, music types, encounter zones, a projectile); not a bug, named only in comments: medium fixes | 22 | HD01/HD02 imagespace swaps, MQ05/MQ11 music, zone tests |
| `attach.ITEM_TYPES` lacks `Holotape` | 13 | MS08's notes, MQ03Holo21 |
| Effect family keywords (`TES4FX_`) from MGEFs the build never converts (fixed but concussion: medium fixes) | 10 | Addiction and concussion tests in GenericScript |
| ActorBase properties filled before the people stage (build count: 5) | 5 | The MQ05 Taft Tunnel ghoul ambush and Enclave waves never spawn |
| FO4 dialogue has no `LinkFrom` handling (4,352 FO3 lines, 645 FNV use it) | MQ01 stage 58; 175 lost lines in the dialogue audit | Topics reached only through LinkFrom never play |
| Four FO3 stations get no frequency: 20 Pip-Boy stations, 14 free FO4 slots (`radio.FREQUENCIES`, FormID order) | MS16 stage 10, MS18 stage 5 | Vault 101 Emergency Frequency, the Rangers' signal, Agatha's station (MS17) and FFRadioSignal02 are not built, so hearing them never starts MS16 or MS18 |

Found outside the audits: `FALLOUT3_QF_Doctors` failed to compile (the only
one of 13,644). The Doctors stage 10 item is guarded by `GetInCell
CitadelBRing` run on the Subject, which a quest stage does not have, and the
converter wrote `None.GetParentCell()`, which Papyrus cannot parse. Fixed in
`commands.get_in_cell` (it now reads `False`, FO3's failed call); see
[quest-script-has-no-reference](../commentary/script_convert.md#quest-script-has-no-reference).

## Fixed the same day

Rebuilt and re-audited: unhidden errors 1,946 -> 383 (properties 1,651 ->
153, timing 62 -> 2, quest 7 -> 3; MS14Fin starts). Against the deployed
plugin nothing is removed; added are 6 GLOBs, 5 holotapes with their speaker
NPCs and quests. The fixed classes' `bug` entries were removed from the ledger.

- **MS14**: `constants.source_name` undoes the reserved-word rename, and
  `attach.ObjectScripts.properties` looks a property up under it.
- **Speech thresholds**: `attach.speech_need` writes `TES4SpeechNeed0`-`5` as
  float globals at `speech_chance_falloutnv.first_needs` (shared with the
  Skyrim importer). Challenges still never fail on FO4: no success gate or
  failure lines are built there yet.
- **Holotapes**: `Holotape` joined `attach.ITEM_TYPES`; the 13 properties
  name voice notes, which become holotapes, so the type binds.
- **Silent radio lines with a result script** are kept
  ([silent-script-lines](../fork/fo4_radio.md#silent-script-lines)). They do
  not fire for MS16/MS18 until those stations get a frequency.
- Not fixed: ActorBase properties filled before the people stage. A
  creature's or templated NPC's FormID is chosen as the people stage makes
  it (size, template, leveled list), so it cannot be reserved early as
  packages are (`Packages.named`); it needs the script fill moved after that
  stage or the VMAD patched there.

## Medium fixes (same day)

Rebuilt and re-audited: unhidden errors 383 -> 291 (properties 153 -> 61).
Against the deployed plugin: 25 EXPL and 1 WEAP added; one STAT removed
(`WeapNukaCocktail`, placed twice as a static; its 2 references keep their
FormIDs and now place the weapon).

- **Explosions**: a script property naming an explosion gets the damage
  stages' stand-in copy
  ([script-explosions](../fork/fo4_pipeline.md#script-explosions)).
- **"Mistyped" properties were not a bug**: the 22 imagespace, music, zone
  and projectile properties come from the SCRO table, and the scripts name
  them only in `;NE: TODO` notes of commands with no FO4 equivalent
  (`SetCellImageSpace`, `GetInZone`, `PlayMusic`, `UseWeapon`,
  `FireWeapon`). The timer audit counted those comments as uses;
  `script_props.timer_uses` now reads code only. The commands stay
  unconverted.
- **Items**: `WeapNukaCocktail`, `MS03BaitGrenade` and `MQ04Mine` joined
  `replacements.json`, since no rule covers thrown weapons. The rolling pin,
  slasher knife and mask, and the medic power armor were built, but their
  own scripts name them while they are being made
  ([item-own-script](../fork/fo4_pipeline.md#item-own-script)). The
  Pip-Boy glove has no FO4 counterpart (`ok`). Creature weapons are named
  only in `UseWeapon` notes (`ok`). The slave collar (neck slot, skinned to
  `Bip01 Neck1`) now builds through the outfit path, weighted to FO4's
  `Neck` ([neck-items](../fork/fo4_pipeline.md#neck-items)). On rebuild,
  its 12 script uses are filled, 6 slave lines gated on `GetEquipped
  SlaveCollar` are built, and unhidden errors go 291 -> 282 (properties
  61 -> 52).
- **Effect families**: the addiction families read `AddictionEffect` and
  morphine reads Med-X's keyword
  ([effect-family-stand-ins](../fork/fo4_pipeline.md#effect-family-stand-ins)).
  Found on the way: `PlayerConcussed` had lost its crippled-head test, so
  GenericScript gave every FO3 player Perception -4 for good. Effect
  `GetActorValue` tests are now written
  ([consumable-effects](../fork/fo4_pipeline.md#consumable-effects)); 13
  `IgnoreNegativeEffects` tests are still dropped, since FO4 lacks that
  value.

## OnTimer property triage (same day)

The 35 undecided timer properties (an OnTimer pass that names an empty
property fails every pass). 34 are `bug`, 1 `ok`; nothing fixed. Unhidden
errors 282 -> 281.

| Cause | Properties | What it breaks |
|---|---|---|
| Fixed: a base only `PlaceAtMe` spawns: FO3 places it 0 times, and `cell.placed_bases` indexes placed bases only, so `ObjectScripts._base` finds no name ([base-properties](../fork/fo4_pipeline.md#base-properties)) | 12: the 3 Vertibird encounters, `FFEU08SmokeTrail`, `FXArtilleryStrike01` (6 scripts), `FXFlyingRocks01`, `BarrelToxicWaste02`, `ShotgunTrapShell01` | Vertibird drops, artillery strikes, falling rocks, the barrel and shotgun traps |
| The package is left out (behavior audit: Find target not furniture, or `GetInCellParam` / `HasMagicEffect`) | 7 | CJ Young, Father Clifford, MS08, MS12, MS13, MS14 Crowley, Simone Cameron |
| `Say GREETING`: deliberately not scripted ([fo4_pipeline.md](../fork/fo4_pipeline.md)) | 5 | MQ05 pump, fuse box, mainframe; MS01; MS09 door |
| FO4 has one human race and nothing fills `Race` properties | 4 (`EndingBinksScript`) | No `GetRace` test passes, so no closing epilogue movie (B19-B26) plays |
| `HumanClips.seated` reads a crouched first frame (thighs level, pelvis low) as seated | `Loose3rdPBrahminPush` | The brahmin push idle |
| No `data/effect_shaders.json` entry | `HaroldLiniment`, `HaroldSap` | Harold's heart effects |
| fo4_import has no `TES4Movers_` list (`tes5_import/dialogue/reset_interior.py` is Skyrim only) | `TES4Movers_pfallslockandload` | Paradise Falls' ResetInterior sends nobody home |
| A script names a placeable water reference, which `cell._part_refs` splits into tiles on hashed ids | `TakomaFactoryExplosion03REF` | Takoma's third explosion |
| Radio topic of the Vault 101 Emergency Frequency, one of the 4 stations with no frequency (above) | `CG04EmergencyBroadcast` | CG04's broadcast |
| `ok`: the behemoth is a Fallout4.esm stand-in with no own rig, so an FO3 clip cannot play on it | `BMTStretch` | - |

Spawned bases fixed: the name index reads every base of a placed type
(`converters.base_records`). On rebuild the 12 are filled, along with 3
non-timer reviews. Two scripts on the newly built bases were then
checked for the first time. `FXFlashBangGrenadeSCRIPT.MQ08FlashBangExplosion`
had no explosion stand-in; its art now maps to `fragGrenadeExplosion`,
showing its own model as FNV's flashbang does
([explosion-models](../fork/fo4_thrown_weapons.md#explosion-models)).
`Vault87TrapGasSCRIPT.FlamerMagicEffect` is the SCRO class (`ok`).
Unhidden errors 281 -> 269 (properties 51 -> 39). Against the deployed
plugin nothing new is removed. Added: 10 ACTI, 2 MSTT, the Enclave
Vertibird patrol NPC, a sound and the flash-bang EXPL.

## Decided harmless (ledger `ok`)

- 67 package navmesh reviews: every cell is an `FFER`/`FFEU` encounter staging
  cell with no navmesh in Fallout3.esm either.
- 39 unfilled Cell properties: 58 of FO3's 421 interiors are not built because
  no door or script reaches them; they are empty `GetInCell` prefix cells
  (Megaton, RC, Tenpenny) or cut content (Vault101Reactor 641 refs and
  Vault101Demo 540 refs: no door leads in, CG04Script names the reactor only
  in a comment; the Little Lamplight armory).
- CG04 stages 110/120 and CG03Stanley's package: in those cut cells.
- 12 Topic properties naming topics with no INFO in Fallout3.esm.
- 13 stage targets the source game lacks too.
- 5 FO3 `ref` variables that start empty in FO3 too.
- `TES4DayDone` (only daily chats), radio `NPCReceiver` and `Playlist`,
  `TES4WalkTrigger` with no trigger location, the reputation tab's sounds
  (FO3 has no reputations).

## Audit fixes

- **Timing**: package blocks run in `TES4_<block>_<package>`, called from the
  package fragment; the audit read them as dropped or moved (57 false errors).
  [fo4_timing_audit.md](../fork/fo4_timing_audit.md#writers)
- **Start**: an alias filled from its quest's Story Manager event (ALFE) is
  a known fill; the chat quests gave 2,132 false reviews.
  [tools_preflight.md](../commentary/tools_preflight.md#findings-and-the-review-ledger)

## Still open (not verified)

- Dialogue: 945 lost lines over 216 keys. Causes: INFO missing from the build
  361 (129 radio: the build log leaves out 34 radio lines with no recording
  and 27 with no voice type), LinkFrom 175, GetIsID 51, unconverted conditions
  (GetIsCurrentPackage, GetInCell, crime counts, disposition) the rest.
- Behavior: 252 packages left out, mostly Dialogue packages with no topic
  (118) and Find packages whose target is not furniture (60).
- Conditions: 292 scene-copy reviews and 5 scene steps no line can pass.
- Properties: the 57 non-timer unfilled properties (reviews) are not
  triaged; the timer ones are (above).
- The world and assets audits report 0 on FO3; not checked whether they ran
  over FO3's data.
