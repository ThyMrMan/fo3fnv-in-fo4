# Plan: what to build next on Fallout 4 (2026-10-30)

The plan for the items in the ROADMAP's [What is left](ROADMAP.md#fo4-next)
table. Status stays in the ROADMAP; this file holds the design. Items that
already have their own plan point to it and say only where to pick up.

Research for this plan was done on 2026-10-29/30 from FalloutNV.exe (GOG
1.4.0.525), Fallout4.exe 1.11.240, the FalloutNV.esm export, Fallout4.esm and
xEdit's definitions. Addresses are FalloutNV.exe's unless they start `0x14`.

## Contents

- [Order](#order)
- [0. Play test and commit](#play-test)
- [1. Creatures with no FO4 base (a converter bug)](#no-base)
- [2. The `[Speech 50]` tag](#speech-tag)
- [3. Creatures' Combat skill](#creature-skill)
- [4. Gun sway from FNV's skill](#sway)
- [5. Audits: preflight, menus, timing](#audits)
- [6. Super mutants on FNV's own mesh](#super-mutants)
- [7. Securitron and Mr. House screens, the Lucky 38 elevator](#screens)
- [8. Papyrus cost 2 to 4](#papyrus)
- [9. The rest of the look pass](#look)
- [10. Object LOD](#object-lod)
- [11. Conversion app phase 7](#app)
- [12. Kill cams on Fallout 4](#kill-cams)
- [13. Casino games and Caravan](#casino)
- [14. Built-in scopes at FNV's zoom](#scope-zoom)
- [15. Human clothing on FO4's body](#human-clothing)

## <a id="order"></a>Order

| # | Item | Size | Why here |
|---|---|---|---|
| 0 | [Play test, then commit](#play-test) | S | Everything from 2026-10-29 is unplayed; the later items build on it |
| 1 | [Creatures with no FO4 base](#no-base) | S | A bug; 47 placed creatures and 3 aliens come back |
| 2 | [`[Speech 50]` tag](#speech-tag) | S | Small, visible in every skill check |
| 3 | [Creatures' Combat skill](#creature-skill) | S | Pairs with the weapon-skill rules already built |
| 4 | [Gun sway](#sway) | S-M | Corrects the combat-feel drift; one play test with 3 |
| 5 | [Audits](#audits) | M | Find what the play test can't; run after each build from here |
| 6 | [Super mutants on FNV's mesh](#super-mutants) | S-M | Played 2026-11-02: FO4's body, head and hands, tinted, under FNV's armor |
| 7 | [Screens and the elevator](#screens) | M | Victor, Yes Man and Mr. House are on the main quest path |
| 8 | [Papyrus cost 2 to 4](#papyrus) | M | Before the whole map gets long play sessions |
| 9 | [Look pass](#look) | M | Polish; each step is one play test |
| 10 | [Object LOD](#object-lod) | M | The skyline; large build cost, do once the world is stable |
| 11 | [App phase 7](#app) | M | Release work |
| 12 | [Kill cams](#kill-cams) | M | Needs an FO4 census first |
| 13 | [Casino and Caravan](#casino) | L | The largest; nearly all new UI |
| 14 | [Built-in scopes at FNV's zoom](#scope-zoom) | S | Built 2026-10-31: scoped guns zoom as FNV's (2–2.8x), not FO4's 6–10x |
| 15 | [Human clothing on FO4's body](#human-clothing) | S-M | FNV's own weights for clothes (the super mutants' fix), wrists, dismemberment; CBBE as an opt-in |

Items 1 to 4 fit one build and one play test. Items 6 to 13 do not depend on
each other.

## <a id="play-test"></a>0. Play test and commit

The order a play test meets the new work, and what to check, is in the
ROADMAP's [What is left](ROADMAP.md#fo4-next). Commit what plays well; fix
what doesn't before anything below. The four cheap checks there (the aim
cone's half-angle, V.A.T.S. audio at 2%, the speed taking, the Creation Kit's
archive wait) each settle a guess in the built code.

## <a id="no-base"></a>1. Creatures with no FO4 base (a converter bug)

**Built 2026-10-30, not played.**

**Found:** the 47 placed creatures of 14 kinds counted `ACRE skipped (no FO4
base)` are not missing a rig or a counterpart. The rules already map
`creatures\smspinebreaker` to `EncSuperMutantTemplate` and `creatures\ghoul`
to `encFeralGhoul01Template`, and 144 placed super mutants and ghouls with
their own model convert. The 47 have **no model of their own**: their
template flags take Model/Animation (0x40) from the template but not Traits
(0x01). Example: `BMRoadblock1Mutant` (CREA 000E84A1, flags 0x3C0) →
LVLC `EncSuperMutantMelee` → `VarSupermutant1Melee` → `CrSuperMutant1MeleeA`
on `Creatures\SMSpineBreaker\Skeleton.nif`.

`Npcs._creature` (`fo4_import/spike/npcs.py`) treats a record as templated
only when it takes Traits (`_traits_templated`), so these fall to
`Creatures.converts`, whose `_entry` keys the rule on the record's own
`Model.MODL` folder: empty, no rule, skipped. `marker_creature.nif` (6) is
the editor placeholder on the same kind of record (`BMSupermutantGunMob`,
`LvlTurretCeiling2048Robot`). `dlc05\creatures` (3) is different: the Wild
Wasteland aliens `CrAlien` ×2 and `CrAlienCaptain` (`VERT5Alien01/02REF`,
`VERT5AlienCaptainREF`, initially disabled), for which no rule exists.

**Build:**

1. A creature whose template flags take Model/Animation resolves its rule
   from the template chain's model (follow TPLT through LVLC entries as the
   Traits path does), and its FO4 template actor takes Traits too (FO4's
   race and skin sit under Traits; Model/Animation alone would show FO4's
   human body). The creature's own traits carry little (no FULL).
2. A rule `dlc05\creatures` → Fallout4.esm `encAlien` (00184C51, AlienRace).
   `skeleton_folder` keys DLC paths on two parts; check it reaches this one.
3. Nightkin keep FNV's `CrNightkinSCRIPT`, whose `StealthBoyInvisibilitySpell`
   already maps to `AssaultronStealthEFFECT` (played on nightstalkers); check
   the script reaches the base.

**Verify:** the count `ACRE skipped (no FO4 base)` falls from 47 to 0; the
Black Mountain roadblocks and REPCON's ghouls stand in game.

## <a id="speech-tag"></a>2. The `[Speech 50]` tag

**Built 2026-10-30, played 2026-10-31.**

**Found:** FNV's engine writes the tag from the line's condition; the
authored text has none (28 topic texts and 1 prompt carry a bracket). The
dialogue menu's strings sit after "TopicsList(): has a topic without
topictext OR info prompt" (0xC71200): `[%s`, `%s %d/%d`, `%s]  %s`, read as
`[Speech 50]` when passed and `[Speech 30/50]` when failed (from the
strings, not disassembled). `[SUCCEEDED]` and `[FAILED]` are authored in the
answers (472 and 436). 1,055 lines test a player skill or SPECIAL; each
check is two lines with one prompt, gated `>= N` and `< N` (Speech 243/218,
Barter 86/81).

The build groups lines by prompt and quest into one option
(`fo4_import/spike/conversation.py`), so the option shows the bare prompt;
XDI hides options that fail and adds nothing. FO4's own Challenge field is a
Charisma roll, not a threshold, and doesn't fit.

**Build:** when an option's lines test a player actor value against a
number, prefix the option text `[<skill> N]` (FNV's skill names; skip
prompts that already start with `[`). For FNV's failing look, split the
option in two by the test: the passing half as `[Speech 50]`, the failing
half as `[Speech 50]` too, its answers already saying `[FAILED]`. FO4 can't
put the player's current value in the text (unverified), so `30/50` is
drift.

**Verify:** the menu audit's structure check ([5](#audits)) still finds one
option per topic; Doc Mitchell's and Sunny Smiles' checks in game.

## <a id="creature-skill"></a>3. Creatures' Combat skill

**Built 2026-10-30, not played.**

**Found:** FNV reads CREA Combat Skill at +0x12D (0x5F8F70), plus level ×
`fCreatureCalcCombat` (2) when a base-data flag is set (0x461560, probably
the level-mult flag). TESCreature's actor-value getter (0x5FA180) returns it
for every actor value flagged 0x400: Energy Weapons, Explosives, Melee
Weapons, Guns, Unarmed. So a creature's weapon skill **is** its Combat skill,
and it scales damage (0x644E66 → 0x644E97, the same formula as NPCs, skipped
with no weapon) and NPC-style gun spread (0x646910 via mode 2). 381 of
1,578 creatures carry a weapon; Combat skill clusters at 50 to 59.

The build reads none of it (exported at `tes4_export/record_types/actors.py`),
so creature weapon skills are 0, the weapon-skill entries' owner tests fail,
and creatures keep full damage and spread.

**Build:** write Combat Skill (with its level term when the flag is set) into
each converted creature's PRPS for the five flagged skills' helper actor
values. The existing `FNV_CombatRules` entries then apply unchanged. A
creature without a weapon is unaffected, as in FNV.

**Verify:** a robot's and a super mutant's PRPS; a turret's hit rate against
FNV's feel in play.

## <a id="sway"></a>4. Gun sway from FNV's skill

**Built 2026-10-30, not played.**

**Found, correcting [combat feel](fo4_combat_feel.md#base-accuracy):**
`Actor::GetSpread` mode 3 (0x7F14CA, ×`fNPCMaxGunWobbleAngle`) is the
V.A.T.S. hit chance (0x646F70), not sway. FNV's player sway is
PlayerCharacter's per-frame update (0x962DE0): the mode-2 sum (stance,
skill, requirements) × `fNonAttackGunWobbleMult` 0.25 outside attacks, eased
at `fGunWobbleChaseDriftTime`, scales an authored wobble animation per
weapon type on a first-person node (hip and iron sights); scoped, the mode-0
sum × `fGunWobbleMultScope` 0.2 rotates the scope view. Melee gets none.

FO4's sway is scoped only (0x140D61DD0): `AimWobble = clamp(1 − base
stability × AimStability, 0, 1)`, AimStability 0.5 on the player, then entry
point **102 Mod Actor Scope Stability** (vanilla: `mod_armor_StabilizedPerk`;
Sniper's `+0.05`). Hip and iron-sight sway has no data hook.

**Build:**

1. Per weapon skill on `FNV_CombatRules`: entry 102, Multiply Value m, then
   Multiply 1 + Actor Value Mult (skill × k), on the weapon's skill keyword,
   so scoped sway halves from skill 0 to 100 as FNV's does (m 0.5, k 0.015:
   0.75 → 0.375; vanilla's is 0.5). Requirement shortfalls add to it the
   same way, from the requirement keywords.
2. The cone entries (134, skill and requirement) become NPC-only (an owner
   condition, not the player): FNV's skill never touches the player's cone,
   and for NPCs it scales their added spread. Hip-fire sway from skill is
   then drift, recorded in [fo4_drift.md](fo4_drift.md).
3. Fix the base-accuracy note in [combat feel](fo4_combat_feel.md) to this.

**Verify:** a scoped varmint rifle at Guns 10 and 100.

## <a id="audits"></a>5. Audits: preflight, menus, timing

Each has its plan; pick up here:

- **Preflight** ([fo4_preflight.md](fo4_preflight.md#results)): rerun on
  the 2026-10-29 build (`py -3.14 -m tools.validate.preflight --fo4
  <plugin>`), then triage by audit: quest (speakers left out by GetIsID,
  unattached scripts), start (132 quests the build doesn't hold), dialogue
  (Mr. House, Arcade, Caesar by GetIsID; HELLO/GOODBYE as custom topics),
  assets (8). The two converter leaks it found (a left-out line's responses
  still written; readiness gaps) first.
- **Menu audit** ([fo4_menu_audit.md](fo4_menu_audit.md#phases)): phases 1
  to 3 run in parallel; phase 2 gives the first whole-map report.
- **Timing audit** ([fo4_timing_audit.md](fo4_timing_audit.md#phases)):
  phases 1 and 2 built; phase 3 (the whole stage graph) next. Euclid's
  C-Finder still needs PlaceAtReticle.

## <a id="super-mutants"></a>6. Super mutants on FNV's own mesh

After [1](#no-base) every super mutant and nightkin stands as FO4's super
mutant. FNV's look is a step further and cheap: FNV's super mutant mesh is
skinned to a humanoid Bip01 skeleton (59 nodes, 53 skin bones on
`nv_sm_v2_1_base.nif`, pelvis at z 88), and FO4's
`Actors\Supermutant\CharacterAssets\skeleton.nif` (111 nodes, pelvis 89.5)
uses the human bone names, every one `outfit.py`'s `HUMAN` map targets. So
it is one body pair (`Pair(HUMAN, supermutantbody.nif, skeleton.nif)` in
`fo4_import/nif/creature.py`) and `"as": "fnv"` on the rule, on
`EncSuperMutantTemplate`'s skin `SkinSuperMutant` → `SuperMutantBody`.

Risks: `SuperMutantRace` has head parts and FaceGen, so FO4's head may show
over FNV's unless the skin covers the head slot; FNV's armor is merged into
the body; FO4's animations, not FNV's. An own rig (as the geckos) keeps
FNV's motion but is L and FO4's graph already fits.

As first built, two more than the pair: FO4's super mutant body skins 140 units
below its skeleton, which the fit now corrects as the human body fit does,
and the skin added the head slot (since dropped: the race's head shows). Play-tested in the 2026-10-31 build (Black
Mountain): bodies stretched when dead and armor came apart, fixed by keeping
FNV's own weights; some nightkin uncloaked, a script conversion bug
(`GetAnimAction`), not this change. Played again in the 2026-11-01 build:
nightkin fought unarmed, because `SuperMutantRace` has no subgraph for
FNV's gun and melee keywords. Fixed by a super mutant additive race
(`spike.mutant_subgraphs`). FNV's hands can't hold FO4's weapons (their joints are FNV's), so super mutants now wear FO4's own body, tinted, under FNV's armor, with FO4's head (played 2026-11-02: [creatures](fo4_spikes.md#spike-4-creatures)). Not this change, and since addressed in
[creatures](fo4_spikes.md#spike-4-creatures): `CrNightkinGunScript`'s cloak
shader now plays (a Fallout4.esm shader; the converted `GetAnimAction` still
latches, so gun nightkin don't re-cloak), and REPCON's corpses (Starts Dead
placements; the ghouls are also killed on load) get FNV's ragdoll poses
(converted 2026-11-01, not rebuilt). Findings: [creatures](fo4_spikes.md#spike-4-creatures).

**Pistols and the Multiplas (built 2026-11-08, not played):** `NEAREST` now maps `AnimsGripPistol` to the pipe gun's `AnimsRecieverHandmadePipe` (FO4's own pipe pistols carry both, so super mutants already fire them with the PipeRifle set) and `AnimsPlasmaRifle` (the Multiplas's grip keyword, which its own replaces) to `AnimsHuntingRifle`, the rifle set every super mutant rifle class falls back on. Against the 2026-11-08 build, guns a super mutant can fire go from 66 to 103 of 119; still none: shotguns, the gatling laser, grenade launchers, the Fat Man.

## <a id="screens"></a>7. Securitron and Mr. House screens, the Lucky 38 elevator

**Steps 1 to 4 built 2026-11-02, not played:** [rigid parts](fo4_own_rig.md#rigid-parts),
[clip shader channels](fo4_own_rig.md#screen-clips),
[free controllers](fo4_pipeline.md#free-controllers),
[expressions](fo4_own_rig.md#expressions).

**Found:** a securitron's screen is a rigid body part
(`NVSecuritronVictorScreen01.NIF` on `Bip01 Screen10`, `Victor_Neutral.dds`)
plus a static overlay (`whitenoise01.dds`). The motion is in the creature's
clips: `mtidle.kf` and the special idles key five texture transforms (UV
glitch) and an emissive color on `Screen01:0`; `talking.kf` pulses the
emissive. Expressions come from `SetSecuritronExpression <ref> <face>
<expr>` (`<face>_neutral/_alert.dds`; 3 scripts, 2 lines), dropped today.
Mr. House's `nvdefaultscreen.nif` layers his face, Yes Man, Connection Lost
and scanlines with their own controllers, switched by alpha from
`dynamicidle_*.kf`. FO4's shader controllers cover UV offset and scale,
alpha and emissive (`fo4_import/nif/shader_anim.py` maps them); Havok clips
can't drive shaders.

**Build:**

1. Rigid parts on rig bodies ([own rig](fo4_own_rig.md)), so the screen
   shows at all.
2. Bake `mtidle.kf`'s screen channels into the screen NIF as free-running
   loop controllers.
3. Keep controllers that have no manager in static conversion: the
   penthouse screen's alpha is keyed to 0 today, so it shows nothing
   ([talking machines](fo4_creature_audit.md#talking-machines)).
4. Expressions as screen armors swapped by equip (vanilla's way), from a
   converted `SetSecuritronExpression`.

**The Lucky 38 elevator** (MESG `Lucky38ElevatorMessageVictor`, shown by
`Lucky38VictorElevatorScript` on 4 references after Victor's goodbye): its
`MenuMode 1009` block moved into the poll's dialogue gate on 2026-10-28 and
`MenuMode` became a real read; never confirmed in game. Play it; fix only if
it fails.

## <a id="papyrus"></a>8. Papyrus cost 2 to 4

[performance.md](performance.md#papyrus): item 2 (GameMode loops, safest,
converter only), then 3 (dialogue state in actor values), then 4 (patrol
arrival checks). Item 1 is built for Fallout 4. Each needs the FO4 scripts
regenerated and one play session timed against today's.

## <a id="look"></a>9. The rest of the look pass

[fo4_look.md](fo4_look.md#order): the grass shards, FNV's horizon glow at
night, and the neon on the Strip (parked until the Strip is played). Each
step ends with FO4 shots beside FNV's.

## <a id="object-lod"></a>10. Object LOD

**Found:** FNV ships pre-merged object LOD at level 4 only (289
`wastelandnv.level4.x.y.nif` plus 6 `.high`, one atlas
`wastelandnv.buildings.dds`), 692 per-object `*_lod.nif` beside their
models, and the Visible When Distant flag (0x8000) on 469 of 6,785 statics.
FO4 needs BTO files per 4/8/16-cell block and an objects atlas, and its STAT
keeps four LOD models (MNAM) and the flag. The build writes neither: STATs go
out with flags 0 and no MNAM (`fo4_import/spike/records.py` `pack_stat`).

The Skyrim side already drives `LODGenx64.exe` (`asset_convert/lod/lod_gen.py`:
the input file, `_lod`/`_far` resolution, levels 4/8/16, missing atlas
normals; `lod_far_gen.py` decimates `_far` meshes), and LODGenx64 knows FO4
(`FO4`, `TerrainFO4`, `.bto` in the exe).

**Build:**

1. Keep the 0x8000 flag on converted statics; write MNAM with the converted
   `_lod.nif` (else a `_far` from `lod_far_gen`).
2. Convert the 692 `_lod.nif` through the static mesh path.
3. Run `lod_gen` with `GameMode=FO4` (its plugin scan must read form
   version 131 and FO4's MNAM); build the atlas map.

The cheap fallback, FNV's 289 level-4 blocks straight to BTO as terrain LOD
reuses FNV's tiles, gives level 4 only: the skyline ends there.

**As built (2026-10-31, not yet in a build or played):** steps 1 to 3, plus
the atlas, as [fo4_pipeline.md](fo4_pipeline.md#object-lod) describes. The
build writes LODGen's input list itself from the references it places (no
plugin rescan), and `pipeline/object_lod.py` runs `LODGenx64.exe` headless
in FO4 mode inside the build, after Elric and before the texture archive,
cached and bounded ([unattended](fo4_pipeline.md#lodgen-unattended)). Trees
are not in it: FO4 has no tree LOD and FNV's are SpeedTrees; crossed cards
from FNV's billboards come after.

## <a id="app"></a>11. Conversion app phase 7

[fo4_gui.md](fo4_gui.md#phases): opt-in MO2 mod and profile setup, a Play
button, and modlist status (each required mod installed, at the right
version, or missing: F4SE, Address Library, LevelUpMenuEx, XDI). The deploy
should copy no staging (the build now keeps it in `output/fo4_cache/ba2`).

## <a id="kill-cams"></a>12. Kill cams on Fallout 4

[kill_cams.md](kill_cams.md) was written for Skyrim (its census reads
`Skyrim.esm`). For Fallout 4 the first step is the same census on
Fallout4.esm: V.A.T.S. kill cam settings and the melee killmove idles with
their `WeaponType*` and animation keyword conditions, against what the build
stamps on converted weapons (`FNV_WeaponAnim*`, the template's keywords).
Then the plan's options apply: keep FO4's kill cams where the keywords
match, turn off the misfiring killmoves.

## <a id="scope-zoom"></a>14. Built-in scopes at FNV's zoom (built 2026-10-31, not played)

**As built:** `weapon_mods.scope_properties`, `scope_preset` and
`zoom_presets` are shared by weapon-mod scopes and `Guns._fnv_scope`. The
template's scope part in a scoped gun's combination
(`GunChoices.magnified_scope`) is always copied, its DATA taking those
properties (`with_properties`: each replaces the part's own of the same
property or keyword). The camera lift subtracts that preset's camera z
(`_clip_lift`).

**Found (2026-10-31):** a gun with a scope of its own (`built_in_scope`:
Has Scope without Scope from Mod) takes the template's scope part as it
is, so it zooms as FO4 shipped that part, not as FNV did:

| Gun | FNV (70 / SightFOV) | Now |
|---|---|---|
| Bozar | 2x | 10x (Assault Rifle) |
| Gobi, Sniper Rifle | 2.8x | 10x (Assault Rifle) |
| AMR (both) | 2.5x | 6x (Hunting Rifle) |
| Gauss, La Longue Carabine, Boone's | 2.2–2.8x | 6x (Pipe Bolt-Action, Pipe Gun) |

No FO4 gun's combinations offer a scope under 4x, so no choice of template
fixes it. FNV's weapon-mod scopes already zoom right: `WeaponMods._scope`
writes ZoomData as the vanilla preset nearest FNV's magnification
(`ZOOMS`, night-vision presets under Scope has NightVision), a FOV
multiplier of exactly 70 / FNV's FOV, HasScope and the scope keywords.

**Build:**

1. Move `_scope` out of `WeaponMods` to a function both callers share
   (it needs only the ZOOM records and the keyword map).
2. In `Guns._part_sub`, for the copy of the part that `GunChoices.scoped`
   swapped in, replace its ZoomData property with `_scope`'s preset and
   add the FOV multiplier and keywords, using FNV's `DNAM.SightFOV` and
   `DNAM.Flags2` Scope has NightVision (0x1000).
3. Camera lift: `Guns._clip_lift` subtracts the template's zoom camera
   offset (WZMD's ZOOM GNAM z). Take the swapped preset's offset instead,
   so FNV's eye point stays on the camera through the scope.
4. A test: a 2x FNV gun's scope copy carries ZM_Standard_Scope_x2, FOV
   multiplier 2.0, and the lift uses that ZOOM's offset.
5. Rebuild the game, then GRA. Check with the scratch part dump that the
   eight guns above carry FNV's multiplier. Report it as unplayed.

**Not in this step.** Letting a gun with no scope part become scoped
(its sights part given the scope's properties) would let the scoped-first
template match go. It's unproven that a sights part shows the overlay, so
the match stays until a play test shows it does.

## <a id="casino"></a>13. Casino games and Caravan

**Found (researched 2026-10-31):** FNV runs all four as engine menus with
hard-coded rules. FO4 has no card or casino engine, and no FO4 blackjack,
roulette or Caravan mod exists.

- **Openers:**
  - 14 object scripts call `ShowBlackjackMenuParams`,
    `ShowRouletteMenuParams` (5 casinos each) and `ShowSlotMachineMenuParams`
    (4: no slots at the Ultra-Luxe) as `<cmd> <CSNO> 1 <max> 0`. Blackjack
    and roulette max out at 200; slots at 25, 40, 60 or 75.
  - 17 INFO records (23 calls) run `ShowCaravanMenu <CDCK> <0|1> <max bet
    share>`, for 11 players. The KlamathBob and Melissa decks are unused.
  - Each game is gated on the casino quest's `bFloorManagerIncoming`, or
    `Banned` at the Atomic Wrangler.
- **Records:** layouts are in `wbDefinitionsFNV.pas` 8196-8360. The export
  prints all five types as unknown, so they need decoding.
  - CSNO (5, plus 1 in Dead Money): reshuffle share, blackjack payout,
    7 reel stops, decks, max winnings, chip, winnings quest, and a soft-17
    flag. It also names table NIFs, chip models, slot symbols and card backs.
  - CCRD (270, five 54-card sets): suit and value (Joker 5/15), face and
    back textures, and `CardAddToPlayerScript`.
  - CDCK (13): the list of cards; its DATA count is wrong in 6 decks.
  - CHIP (5) and CMNY (6, the Caravan bills and coins).
- **Results never pass through script.** The engine moves chips, caps and
  pots itself, and counts misc stats 37/38 (Caravan won/lost) and 40-42
  (roulette, blackjack, slots). Those stats feed the challenges: Caravan
  3/27 wins and 5 losses; 10 games of each casino game.
  - Comps poll `GetCasinoWinningsLevel <CSNO>` at levels 1-4 (SmallFry,
    BigWinner, Whale, Banned). The levels fit net winnings of 25, 50, 75
    and 100% of the CSNO max (guide figures; inferred). The engine enforces
    the ban (`sGamblingBannedText`).
  - Achievement 29 fires when the Tops, Ultra-Luxe and Gomorrah have all
    banned the player.
- **FNV's UI:**
  - The panels are XML in `Fallout - Misc.bsa\menus\`: `black_jack_menu`,
    `roulette_menu`, `slot_machine_menu`, and `caravan_menu` with its bet,
    deck-building, game and results sub-menus.
  - The playing surfaces are custom 3D scenes the menu renders live
    (`meshes\terminals\nv_*`, 102 NIFs), not screenshots:
    - each table NIF carries its own `NiCamera` (the fixed slanted view),
      an `NiPointLight` and `NiControllerSequence` animations;
    - named spots (`Players_Discard`, `Dealers_Discard`, `Hand1_Arrow`)
      place the separate card, chip, dealer, hand, reel and money NIFs;
    - the materials have normal and environment maps, lit in real time.
  - **Textures:**
    - The blackjack felt (`NV_Blackjack-Table03`, 2048×512) is a flat
      top-down painting, stored upside down for its UV. It reads "INSURANCE
      PAYS 2 TO 1", which FNV doesn't offer, so it was likely copied from a
      real layout (inferred).
    - The Caravan top (`NV_Caravan-Table01`, 2048²) is a photo-sourced
      railroad-tie wood.
    - Roulette and slots are UV atlases for their models.
  - The minigame NIFs are their own files. Whether the casino furniture
    shares them is not checked.
  - Art: 336 card faces (128×256 DXT1, in sets B, G, L, T and U), 8 slot
    symbols, table textures, and 41 `GAME*` sounds (114 WAVs).
- **Rules:**
  - Caravan: three caravans sold at 21-26; suit and direction rules; Jack,
    Queen, King and Joker effects; a 30-card minimum deck; bidding.
  - Blackjack: hit, stay, double on the first two cards, split, surrender
    for half; no insurance; Luck biases the deal.
  - Roulette: American wheel, FNV's payouts, 0 never pays (an FNV bug).
  - Slots: FNV's payout table; Luck biases the reels.

  Sources: `references\FalloutWiki` and the Prima guide.

**FO4 has the pieces for a new menu, but this project has never made one.**
Every FO4 menu change so far edits vanilla menus while they run (F3NV.dll's
open/close sink, `enterFrame` and key hooks, `SendExternalEvent`), or comes
from a dependency (LevelUpMenuEx, XDI). The earlier note that the character
menus are custom Scaleform menus was wrong.

- **Opening a menu:** F4SE's `UI.RegisterCustomMenu(name, path, root,
  MenuData)` loads `Interface\<path>.swf` as a real IMenu. Its flags cover
  pausing the game, the cursor, modality, gamepad handling and HUD color.
  Flash calls back with `root.f4se.SendExternalEvent`, and Papyrus calls in
  with `UI.Invoke`, `Set` and `Get`. CommonLibF4's `UI::RegisterMenu` is
  the DLL-side alternative.
- **Card art at run time:** `f4se.MountImage(menu, texturePath, name)`
  loads any texture (loose or BA2), and AS3 then loads `img://<name>`. So
  the conversion can copy the user's FNV card, symbol and table DDS files to
  `Textures\F3NV\Casino\`, and the SWF needs no art of its own.
- **Missing:** an AS3 compile step. FFDec (Java 8) can compile AS3, but the
  project has only used it to decompile. Apache Flex `mxmlc` is not
  installed. The inherited Python SWF writer handles only AS2 or movies with
  no script.

**Design (proposed, not built):**

1. **One movie, `F3NV_Casino.swf`, holding the game screens:**
   - one screen each for blackjack, roulette and slots;
   - Caravan's bet, deck, game and results screens.

   It's a flat 2D table, not FNV's 3D scenes. The backgrounds are the
   felt and wood, which are already top-down (the felt flipped); the cards,
   chips, slot symbols and wheel go on top as flat images. FO4 can render
   3D inside a menu (the lockpicking menu does), but redrawing FNV's scenes
   would need F3NV.dll to load the converted NIF and its camera, light and
   animations: a possible later upgrade, not a first step. It is written from our own
   AS3 source, with no Bethesda art or decompiled `Shared.*` classes, and
   built by a tool in `tools/` from the source in the repo. It takes FO4's
   own fonts by name and the HUD color.
2. **Game rules in F3NV.dll**, as native functions added to the movie on open
   (the `pipboy.cpp` pattern). The rules cover the deal, the RNG with
   FNV's Luck bias, payouts, the Caravan engine and the opponent.
   - Write a greedy Caravan opponent from the rules. Open-source players
     exist, but the clearest (r3w0p/caravan) is GPL-3.0; MIT ones exist
     (jackklassen, kairaSahin) if code is wanted.
3. **Papyrus (`F3NV_Casino` quest):**
   - the converted openers (the casino or deck, max bet);
   - chip and cap transfers;
   - net winnings per casino behind `GetCasinoWinningsLevel`, and the ban;
   - the misc stats and challenge counters.
4. **Records:**
   - decode the five types;
   - cards, chips and Caravan money become MISC items; the player's
     Caravan cards stay inventory items, which the deck builder reads;
   - the `GAME*` sounds become SNDR.
5. **Order:**
   - the AS3 tool and the menu shell (S-M);
   - slots (S), then roulette (M: the betting board), then blackjack (M);
   - Caravan (L: rules, opponent, deck building, bidding).

## <a id="human-clothing"></a>15. Human clothing on FO4's body (planned 2026-11-02)

**Where it stands.**
- **Clothes:** every FNV item covering the upper body shows FNV's mesh (the
  replacement table's `_rules.armor`, `"as": "fnv"`). Each mesh is
  retargeted from FNV's skeleton to FO4's and moved onto FO4's body by the
  offsets between the two bodies (`fo4_import/nif/outfit.py`,
  [outfits](fo4_spikes.md#spike-4-outfits)).
- **Weights:** every vertex takes FO4's body weights at its nearest
  surface point (`BodyFit.skin`).
- **Body, head and hands:** FO4's own. Bare skin inside an FNV outfit
  keeps FNV's shape on FO4's body texture and skin shader.
- **Animations:** humans use FO4's skeleton, graphs and movement; FNV's
  idles and gun clips are retargeted onto it.
- **Known flaws:**
  - FO4's hand is larger than FNV's forearm, so the wrist seam shows.
  - FO4's female body texture has painted underwear, and it shows where
    FNV clothes leave skin bare.
  - Loose cloth sits off the body (the dress hem up to 13 units).
  - Dismemberment does not cut the outfits.

**What the super mutants showed** ([super mutants](#super-mutants),
[mesh](fo4_spikes.md#spike-4-creatures)). FNV's super mutant body on FO4's
super mutant skeleton was built and played twice, 2026-10-31 to 11-02:
- **Weights.** Nearest-surface weights fail on anything shaped unlike FO4's
  body: armor lying nearest FO4's arms took arm weights and stretched up to
  34.5x with an arm raised. FNV's own weights, each FNV bone on its mapped
  FO4 bone (`creature.Pair.own_weights`), brought that to 3.4x, against 4.0x
  for FO4's own super mutant.
- **Hands.** FNV's hands can't hold FO4's weapons: their finger joints are
  FNV's.
- **Head.** FNV's head on FO4's body left a gap and a second head showing,
  because FO4's head part is built for its own neck.
- **The result.** Super mutants now wear FO4's body, head and hands,
  tinted, with FNV's armor pushed outside FO4's body (`fo4_body`) — the
  layout humans already have.

**Options weighed.**
- **A. Keep FO4's body, head and hands; fix how FNV clothes sit on them.**
  Chosen.
- **B. FNV's body and hands on FO4's skeleton.** Dropped: the hands fail
  (point 2), and a human must keep FO4's head for FaceGen, hair and
  LooksMenu, so the neck seam that failed (point 3) would come back.
- **C. BodySlide projects for CBBE.** Kept as an opt-in user option (below).

**Build (A):**
1. **FNV's own weights for clothes.** Each outfit vertex keeps its FNV
   weights, each FNV bone on its `HUMAN` rig bone in FO4's body or that
   bone's `_skin` helper, an unmapped bone (fingers, twists) on its nearest
   mapped ancestor: the super mutant `_targets` rule, shared rather than
   copied. Check first whether vertices that touch skin (cuffs, collars,
   waistbands, the skin shapes) stay closer to FO4's body under its own
   weights. If so, blend from FO4's surface weights at the body to FNV's
   farther out. Measure as the super mutants were: edge stretch with an arm
   raised 90 degrees and a leg forward, on the dress, a duster
   (`BountyHunterDuster`), leather armor and a vault suit. Old against new;
   the skirts and coat tails should stop splitting between the legs.
2. **Wrists.** The seam step already joins a sleeve's or bare forearm's edge
   to FO4's wrist edge. Also taper the last few units of forearm toward
   FO4's wrist, so the step to FO4's larger hand shrinks.
3. **Dismemberment segments.** Give each outfit the cut data FO4's body
   carries, so a severed limb takes its sleeve or leg with it.
4. **Painted underwear** stays: a body texture replacer the player
   installs covers it, as does option C.

Step 1 is played on its own first, since it changes every outfit; 2 and 3
can share a play test.

**C, as a user option.** A "Body" choice in the app and the replacement
profiles: FO4's body (A, the default) or CBBE with BodySlide.
- **With C:** the converter fits each outfit onto CBBE's body, read from
  the player's install and never shipped, instead of FO4's. It writes a
  BodySlide project per outfit, with slider data made as Outfit Studio's
  conform makes it, and the player batch-builds with their own preset.
- **What carries over:** A's weights and seams apply to C unchanged.
- **The app:** finds CBBE and BodySlide in the mod folders it reads, and
  greys the option out without them.
- **Open:** CBBE's permissions for generated conversions
  ([CBBE and BodySlide](fo4_replacements.md#bodyslide)).
