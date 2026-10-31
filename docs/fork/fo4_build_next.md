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

## <a id="order"></a>Order

| # | Item | Size | Why here |
|---|---|---|---|
| 0 | [Play test, then commit](#play-test) | S | Everything from 2026-10-29 is unplayed; the later items build on it |
| 1 | [Creatures with no FO4 base](#no-base) | S | A bug; 47 placed creatures and 3 aliens come back |
| 2 | [`[Speech 50]` tag](#speech-tag) | S | Small, visible in every skill check |
| 3 | [Creatures' Combat skill](#creature-skill) | S | Pairs with the weapon-skill rules already built |
| 4 | [Gun sway](#sway) | S-M | Corrects the combat-feel drift; one play test with 3 |
| 5 | [Audits](#audits) | M | Find what the play test can't; run after each build from here |
| 6 | [Super mutants on FNV's mesh](#super-mutants) | S-M | Optional look upgrade after 1 |
| 7 | [Screens and the elevator](#screens) | M | Victor, Yes Man and Mr. House are on the main quest path |
| 8 | [Papyrus cost 2 to 4](#papyrus) | M | Before the whole map gets long play sessions |
| 9 | [Look pass](#look) | M | Polish; each step is one play test |
| 10 | [Object LOD](#object-lod) | M | The skyline; large build cost, do once the world is stable |
| 11 | [App phase 7](#app) | M | Release work |
| 12 | [Kill cams](#kill-cams) | M | Needs an FO4 census first |
| 13 | [Casino and Caravan](#casino) | L | The largest; nearly all new UI |
| 14 | [Built-in scopes at FNV's zoom](#scope-zoom) | S | Built 2026-10-31: scoped guns zoom as FNV's (2–2.8x), not FO4's 6–10x |

Items 1 to 4 fit one build and one play test. Items 6 to 13 do not depend on
each other.

## <a id="play-test"></a>0. Play test and commit

The order a play test meets the new work, and what to check, is in the
ROADMAP's [What is left](ROADMAP.md#fo4-next). Commit what plays well; fix
what doesn't before anything below. The four cheap checks there (the aim
cone's half-angle, V.A.T.S. audio at 2%, the speed taking, the Creation Kit's
archive wait) each settle a guess in the built code.

## <a id="no-base"></a>1. Creatures with no FO4 base (a converter bug)

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

## <a id="screens"></a>7. Securitron and Mr. House screens, the Lucky 38 elevator

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

**Found:** FNV runs them as engine menus opened by script commands:
`ShowBlackjackMenuParams` and `ShowRouletteMenuParams` (5 casinos each),
`ShowSlotMachineMenuParams` (4), `ShowCaravanMenu <deck> <0|1> <ratio>` (27
line scripts). The data is in CSNO (5: shuffle, payouts, reel stops, decks,
max winnings, chip, winnings quest, soft 17), CCRD (270 cards), CDCK (13
decks), CHIP (5), CMNY (6); the export prints them as unknown types, and the
converter turns the commands into TODO comments. FO4 has no card or casino
engine; no FO4 blackjack or Caravan mod was found.

**Build:**

1. Decode the five record types in `tes4_export` (layouts in xEdit's
   `wbDefinitionsFNV.pas`).
2. Write them as data: a struct per casino and deck, cards and chips as
   misc items, the winnings stage wired as FNV's.
3. FO4 command rows calling one `F3NV_Casino` helper quest, which opens a
   new Scaleform menu through F4SE (as the character menus do).
4. In order: slots and roulette (random and payout, S each), blackjack
   (S-M), Caravan (a rules engine and an opponent, deck building from CMNY
   and CCRD, results feeding the challenges: L).
