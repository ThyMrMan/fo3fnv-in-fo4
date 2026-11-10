# NPC behavior and navigation (plan)

A plan for the medium and large NPC behavior rows of the
[issue plan](fo4_issue_plan.md): daily routines, holding a routine through
combat, navmesh cover and islands, the deathclaw's charge, stairs and idle
markers. It is design only. Status lives in [ROADMAP](ROADMAP.md) only.

## Contents

- [1. Goal and rows](#goal)
- [2. What exists](#exists)
- [3. The framework: a behavior parity audit](#framework)
- [4. Phases](#phases)
- [5. What the play test should tell us first](#play-test)
- [6. Open questions](#questions)

## <a id="goal"></a>1. Goal and rows

Every FNV package, combat style, navmesh and idle marker should either reach
Fallout 4 with the same behavior or be listed as drift with its reason. One
audit pairs each FNV record with what the build wrote, so each fix below is
measured by a count that drops, not by a guess.

| Row | Size | Doc |
|---|---|---|
| Daily routines (85 left out) | M | [packages](fo4_pipeline.md#packages) |
| Routines dropped in combat | part of the above | [combat override](fo4_pipeline.md#combat-override) |
| Navmesh cover and island data | M | [navmesh](fo4_pipeline.md#exterior-navmesh) |
| Deathclaw charge attacks | Play | [styles](fo4_pipeline.md#combat-styles) |
| Stair pitch | Play | [stairs](fo4_pipeline.md#stair-helper-pitch) |
| Idle markers missing (108 of 1,424) | not sized | [markers](fo4_pipeline.md#audit-fixes) |

## <a id="exists"></a>2. What exists

**Packages.** `fo4_import/spike/packages.py`:
- `Packages._plan` maps an FNV type to a copied vanilla instance (`PLANS`,
  `INSTANCES`). Find (0) and Escort (2) are not in `PLANS`, so they return
  `type Find` / `type Escort`.
- `Packages.package` leaves a package out when `_plan` returns a reason or
  `say_topics.conditions_of` returns None, and counts it by reason.
  `say_topics.blocker` names the first function that failed.
- `Packages._write` gives only an FNV Guard (type 14) with Continue During
  Combat a combat override copy; `Packages.combat_list` puts those copies
  in the NPC's ECOR list (`npcs.py`, line 579). Creatures get none.
- The package conditions see a smaller form map than dialogue lines.
  `cell.py` builds `Npcs` with `_form_map` plus `_cells` (line 901). Dialogue
  lines also get `items.shared`, `actor_values(HELPER_INDEX)`,
  `condition_forms` (items made on demand, map regions' locations) and
  `region_watch.form_map()` (line 710). That gap fits the
  GetActorValue, GetEquipped, GetItemCount, GetHasNote and PlayerInRegion
  rows below. This is read from the code, not yet measured.

**The 85 left out** (`temp/build_1107i.log`, lines 1120 to 1135):

| Reason | Count |
|---|---|
| type Find | 30 |
| condition GetInWorldspace / GetInCell / GetIsID / GetQuestVariable, "never true in this build" | 8 / 3 / 2 / 1 |
| condition GetEquipped / GetActorValue / PlayerInRegion / GetItemCount / GetHasNote / GetActorFactionPlayerEnemy | 7 / 6 / 4 / 3 / 2 / 2 |
| target not built | 8 |
| type Escort | 4 |
| flee by way of a location; no weapon target; target not a seat | 2 / 2 / 1 |

Not every Find loots: `NellisFindJanet`, `V03BryceDiePackage` and
`SSHQJacklynAttacksTomasPackage` are Find packages too (log lines 1146 to
1152). Looting itself is recorded drift ([drift](fo4_drift.md#recorded)).

**Combat styles.** `fo4_import/spike/combat_styles.py`: `pack_style` starts
every converted style from Fallout4.esm's default style body and sets the
converted values. Its DATA flags therefore come from the default style, so
no converted style has Charging (0x08). A creature takes its traits' style
in place of its stand-in's, so FNV deathclaws lose `csDeathclaw`'s Charging
tree. `CSDeathclaw` exports `CSTD.RushingAttackChance=50`.
`creature_attacks.py` keeps a charge attack (flag 0x8) only when the
style's rushing chance is above 0, so deathclaw charge attacks stay in the
list, but FO4 feeds charge attacks to the charge behavior, which Charging
picks ([creature attacks](fo4_pipeline.md#creature-attacks)).

**Navmesh.** `fo4_import/spike/navmesh.py`:
- `pack_nvnm` writes three zero counts after the door links: the cover
  array, the cover-triangle mappings and the waypoints (xEdit
  `wbDefinitionsFO4.pas`, NVNM, lines 4420 to 4455). Triangle cover flags
  carry over from FNV's NVTR.
- `_info` writes NVMI flags 0 and "no island".
- FNV's NAVI holds the island data: 1,687 of its 4,772 NVMI entries have
  Is Island (0x20) set (`export/FalloutNV.esm/NAVI.txt`).
- FNV's cover triangles (NVCA) are **not exported**:
  `tes4_export/record_types/falloutnv.py:_emit_navm_deltas` dumps NVVX,
  NVTR, NVDP and NVEX only, though 1,659 of 4,771 FNV navmeshes have a
  nonzero `DATA.CoverTriangleCount`.

**Idle markers.** `fo4_import/spike/idle_markers.py:stand_in` picks the
Fallout4.esm marker that plays most of a marker's idles (`PLAYS`). It
returns None, and the marker is left out, when FO4 plays none of them.
The doc counts 108 left out (protectron 55, watering plants 18, Mr Gutsy
15, picking up 7, Mesmetron 5). The 1107i log shows only six
`idle marker left out` lines and `idle marker placed: 91`. The counts need
re-taking from one build before phase work starts.

**Stairs.** `fo4_import/nif/stairs.py:_ramp` lays the helper slab at the
flight's median pitch. `tools/nif/stairs_audit.py` ranks meshes by open
foot, tall risers and over-max steps. The Novac motel's 16-unit riser in
front of a 38° ramp leads the tall-riser list. The stuck spot there is not
pinned down.

**Audits to build on.** `tools/validate/preflight/package_ai.py` already
reads the built PACK records and their users (bad targets, schedules, a
destination cell with no navmesh). `condition_diff.py` evaluates an FNV line
against its copy under sampled states and pairs forms by EditorID and the
ledger ([condition differential](fo4_preflight.md#condition-diff)).

## <a id="framework"></a>3. The framework: a behavior parity audit

One preflight audit, `--audit behavior`, added beside `package_ai`. It
reads the FNV export and the built plugin, pairs records, and prints one row
per FNV record with the field that differs.

| FNV record | Paired with | Compared |
|---|---|---|
| PACK | the PACK of the same EditorID (`pack_package` keeps it); `<EditorID>Combat` | built or left out and why; template; location and target kind; schedule; Continue During Combat against an ECOR entry |
| PACK conditions | the copy's CTDAs | through `condition_diff.evaluate`, sampled states |
| CSTY | `FNV_<EditorID>` | the converted values; DATA flags against the stand-in race's vanilla style |
| NPC_ / CREA | the built actor | how many packages it keeps; whether any package still runs |
| NAVM | the NAVM of the hashed id | cover triangles in FNV against the cover array; Is Island against NVMI flags |
| IDLM (placed) | the placed stand-in | placed or left out, by what it plays |

Why one audit covers these rows: each one is "FNV authored a behavior and
the build silently wrote less". The build log counts reasons, but not who
is hurt. The audit adds the actor (Chet with no routine is worse than a
spare Find), and it gives each phase a number to drive to zero or to
the drift list. It follows the preflight rules: forms pair by authored
names, never through the converter's own tables.

Stairs are not a record pairing. They keep `stairs_audit.py`, and the
behavior report links its counts.

### <a id="dll"></a>DLL decisions

None of the phases needs a DLL. Two places where one could come up:

| Candidate | DLL would do | Alternative (planned) |
|---|---|---|
| Continue During Combat on Travel, Follow, Patrol, UseWeapon (FNV-wide 153, 57, 32, 43) | keep the package running while combat AI fights | ECOR copies per type where the CK wiki says the procedure still fights (HoldPosition, maybe UseWeapon); the rest stays drift |
| Looting Find packages | a loot procedure | a Sandbox with fragments that take items from N nearby containers in Papyrus, or keep the drift |

## <a id="phases"></a>4. Phases

<a id="phase-1"></a>**Phase 1. The audit, packages first (S).** `--audit behavior` with the PACK
and actor rows only. It delivers the 85 broken down by NPC, with the actors
left with no package at all on top.
- *Check:* its left-out total equals the build log's 85, reason by reason.
- *Depends on:* the play-test build and its stamp.
- *Built (2026-11-08):* `tools/validate/preflight/behavior.py`, run by
  `py -3.14 -m tools.validate.preflight --fo4 <plugin> --audit behavior`.
  An FNV PACK pairs with the built PACK of its EditorID. One not built is
  listed (review, `behavior|<game>|package|<EditorID>`) when a built actor
  lists it, the readiness report (`temp/fo4_readiness/<stem>.json`) names an
  actor it was left out for, or a converted script declares a property of
  its name; any other was never reached. Its cause is the readiness
  report's reason, the same text as the build log's
  `package left out (<why>)`. A built actor whose FNV list is not empty but
  whose FO4 record (or AI packages template) holds no package is an error
  (`no-package`). The run prints the left-out count by cause.
- *Gap:* the readiness report covers only packages left out for an NPC
  (`Packages.for_npc`). The 1107i readiness report has 76 such packages
  (Find 30, target not built 8, GetInWorldspace 8, GetActorValue 5, Escort 4,
  PlayerInRegion 4, GetItemCount 3, GetInCell 3, two each of
  GetActorFactionPlayerEnemy, GetHasNote, GetIsID and no weapon target, one
  each of GetQuestVariable, target not a seat and flee by way of a location).
  The other 9 of the log's 85 (GetEquipped 7, GetActorValue 1, flee 1) are
  left out only through a script property (`write_pending`), so the audit
  lists them as "no cause recorded". Closing it needs `Packages.package`
  to add a readiness entry for every package it leaves out.
- *Gap closed (2026-11-09, not built):* `Packages.package` adds one
  entry per left-out package (owner the FNV package, detail
  `<EditorID> (<why>)`); the audit reads both detail forms.
- *Not yet run on a full build:* the 2026-11-08 build was still writing
  the plugin.

**Phase 2. Package conditions see the dialogue forms (S).** `Packages`
takes the same form map additions as dialogue lines: items made on demand,
actor values, region locations and worldspaces. One shared function, not a
second copy.
- *Check:* the audit's condition rows drop from 38. GetEquipped,
  GetActorValue, PlayerInRegion, GetItemCount and GetHasNote (22) should go
  to 0. The 14 "never true" stay only where the form is truly absent: the
  audit names the form.
- *Depends on:* phase 1.
- *Built (2026-11-09, not played):* `condition_forms.condition_map` makes
  both maps; a package's tested items are made when it converts
  (`condition_items`). GetActorFactionPlayerEnemy (2) is
  `IsHostileToActor` of the player (drift). Measured by a probe over the
  1108d plugin and export (scratch, not a tool): of the 38 condition
  cases and the 9 script-only ones, all but 7 convert. Left: GetInCell 3
  (`vHD*PowerPlant*`, the cell is not built), GetIsID 2 (Fisto's, the NPC
  is not placed), GetQuestVariable 1 (`VRRCMessengerDialogue`, quest 0),
  and `vPowderGangerFactionRewardDialogue`, whose next test
  (GetReputationThreshold) the probe could not map; the build's
  reputation slots should. Boone's 7 `VNovacBooneRevenge*` UseWeapon
  packages (GetEquipped of the beret) now convert.
  [package conditions](fo4_pipeline.md#package-conditions)

**Phase 3. Find, Escort and unbuilt targets (M).**
- A Find whose target is one reference becomes a Travel to it (Nellis, the
  V03 Bryce package).
- Find by object type with Allow Stealing or Killing stays drift, unless the
  Papyrus loot option is approved.
- Escort copies a Fallout4.esm Escort instance, if one exists (not
  checked), else a FollowNPC. *Built 2026-11-09, not played:* FO4 has an
  `EscortPlayer` template (38 instances); the copy is
  `RRM01LowRoadEscortPackage01`'s. Orris's 4 convert
  ([escort](fo4_pipeline.md#escort)).
- "Target not built" (8) goes through `named_refs` as locations did.
- *Check:* the audit's Find, Escort and target rows; Bryce Anders and
  Linda Schuler keep their packages in the whole-map log.
- *Depends on:* phase 1.

**Phase 4. Routines through combat (M).**
- The audit adds the combat column: FNV Continue During Combat against an
  ECOR entry.
- ECOR copies widen to the types the play test shows still fight.
- Creatures get ECOR lists the same way.
- *Check:* the audit lists every FNV package with the flag as kept or as
  drift; the Goodsprings gunfight settlers hold their posts and fire.
- *Depends on:* the play test's gunfight check.

**Phase 5. Combat style flags (S).** The CSTY rows compare DATA flags with
the stand-in race's vanilla style. A creature replacing a style that sets
Charging (`csDeathclaw`, `csRadStagCharge`) keeps that bit, when its FNV
style rushes.
- *Check:* the audit lists 0 creatures that lost a vanilla Charging bit; a
  deathclaw charges in game.
- *Depends on:* the play test's deathclaw check (skip if charges fire).

**Phase 6. Navmesh cover and islands (L).**
- Export NVCA (one exporter change, a `--types NAVM` re-export).
- Census Fallout4.esm's cover array: what the 4-byte Data holds and how
  cover edges relate to triangle cover flags.
- Write the cover array and mappings in `pack_nvnm`, and FNV's island
  data and Is Island flag in `_info`.
- *Check:* the audit's NAVM rows: every FNV navmesh with cover triangles
  has a cover array, and every FNV island has its NVMI island data. FO4Edit
  loads the plugin clean. In game, raiders at a camp take cover.
- *Depends on:* phase 1. The census decides the layout.

**Phase 7. Idle markers (S).**
- The IDLM rows re-count what is left out, from one build.
- Robots' markers (protectron, Mr Gutsy) become `EmptyIdleMarker`, as
  patrol points already do (`CellBuilder.idle`), so the robot still stands
  there.
- Watering and picking up get a vanilla marker if a census finds one.
- *Check:* the left-out count drops by the robot share (70 by the doc).
- *Depends on:* phase 1.

**Phase 8. Stairs (S, only if the play test fails).**
- Mark a plain riser directly in front of a collision ramp with the stairs
  material, the case `stairs_audit` ranks first.
- *Check:* the tall-riser count for `architecture/novac` drops; the Novac
  motel stairs climb.
- *Depends on:* the play test's stairs check.

## <a id="play-test"></a>5. What the play test should tell us first

- **Deathclaw charge.** If FNV deathclaws charge, phase 5 is dropped. If
  they never close in at a run, phase 5 moves up.
- **Goodsprings gunfight.** Trudy and the settlers on their ECOR lists:
  if they hold and fire, the ECOR mechanism works and phase 4 widens it. If
  they stand still or leave, phase 4 first finds out why.
- **Stairs.** The Novac motel and Vikki and Vance's steps. A pass drops
  phase 8.
- **Cover.** Whether any NPC takes cover in a firefight now. FO4 may use
  triangle cover flags alone; then phase 6 is only islands and is smaller.
- **Mr. Janitor's route** ([patrol points](fo4_pipeline.md#patrol-points)).
  If FO4 ignores the patrol topic, patrol actions join phase 4's scope.
- **Prospectors and Chet.** Who stands idle where FNV has a routine. Each
  name is a row the phase 1 audit must explain.

## <a id="questions"></a>6. Open questions

- What does the 4-byte Data of an FO4 cover entry hold? Is FNV's cover
  triangle list enough to fill it? (Not checked; needs the census.)
- Does Fallout4.esm have an Escort package template and instances? Yes:
  `EscortPlayer` (0x1D281, 38 instances), `EscortPlayerWhenNear` (19).
- Are the 8 GetInWorldspace "never true" packages real, or only missing
  worldspaces in the package form map? Missing from the map: WastelandNV
  and TheStripWorldNew are built; phase 2 adds them.
- Does FO4 rebuild island data at load, which would make writing FNV's
  moot? (Not checked.)
- Which idle marker counts are current: the doc's 108 left out, or the
  1107i log's six lines?
- Should looting become Papyrus, or stay drift? The user's call.
