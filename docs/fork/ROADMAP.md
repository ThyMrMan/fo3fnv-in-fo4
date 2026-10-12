# Fork roadmap

The one place status lives. Plan files in this folder hold design only; when a
piece is built, played or dropped, the change is made here and nowhere else.

**Focus:** standalone play of each converted world, stability, performance.
Staying equivalent to upstream is not a goal; staying mergeable with it is, so
the fork's docs live in `docs/fork/` and upstream's plans stay in
`docs/plans/`, unedited.

| File | Holds |
|---|---|
| [character.md](character.md) | Attributes, skills, leveling, perks, standings and the stats menu, for all four games |
| [standalone_play.md](standalone_play.md) | Setup, MO2 integration, per-world profiles, launcher, world picker |
| [performance.md](performance.md) | Rules for new systems, Papyrus runtime cost, FO3/FNV occlusion |
| [kill_cams.md](kill_cams.md) | Kill cams and killmoves on converted weapons, per game |
| [bink_movies.md](bink_movies.md) | Source-game Bink 1 movies (parked) |
| [research/](research/) | Findings and notes that are not plans: [character findings](research/character_findings.md), [graphics options](research/graphics_options.md), [Fallout 4 as the target](research/fo4_target.md), [dynamic collision for FO4 (parked mod idea)](research/fo4_dynamic_collision.md) |
| [done/](done/) | Plans that are built, kept as their design record: [preflight audits](done/preflight_audits.md) |
| [fo4_spikes.md](fo4_spikes.md) | **This repo's current work:** the spikes that decide whether FO3/FNV on Fallout 4 is buildable |
| [fo4_pipeline.md](fo4_pipeline.md) | The plan from the spike to the whole of FNV: the base it grows on, what to build and research first, speed, stability, order |
| [fo4_replacements.md](fo4_replacements.md) | The user-editable replacement table (items, then creatures: FO4 records, FNV stats, FNV meshes on FO4 rigs, other mods' records), its profiles and GUI, and the Wabbajack modlist as a soft requirement for the full experience |

## <a id="fo4"></a>Fallout 4 spikes

**Direction (2026-10-10): the modlist is a soft requirement.** The
converter alone makes FNV playable: everything converts, and what it
cannot rebuild stands in as Fallout 4's nearest record. A Wabbajack
modlist is the full experience: hand-made ports (guns, creatures with no
FO4 rig, bodies and clothing, better assets) wired in by a replacement
profile, never required to run and never shipped by us. Work that does
not automate (gun animations, new creature rigs and behaviour graphs) is
parked as future work rather than ground on
([direction](fo4_replacements.md#direction)).

| Piece | Status |
|---|---|
| [Step 0: groundwork](fo4_spikes.md#step-0) | **Built 2026-10-05:** FO4 writer + tests, `Fallout4.esm` dump, script sources, compiler checked. Not yet loaded in FO4Edit or the CK |
| [Spike 1: dialogue](fo4_spikes.md#spike-1) | **1a text-only played 2026-10-05:** greeting opens the menu with all of Doc's options; added topics, Say Once variants, skill checks, sub-menu returns and Goodbye confirmed ([design](fo4_spikes.md#spike-1-design)). **1b played 2026-10-05, passed** ([1b](fo4_spikes.md#spike-1b)): three speakers share one forced-alias scene, each seeing only their own options; `[Leave]` replaces Tab, walking away ends the talk, Random piles vary. The gate is passed: 1b needs no hand work. **Voice played 2026-10-05** ([voice](fo4_spikes.md#spike-1-voice)): Doc's FNV lines as `.fuz` with CK-generated lips. Only the player opens a talk (`GetPlayerActivated`, played). Open: the player's "Hi" |
| [Spike 3: one script](fo4_spikes.md#spike-3) | **Measured 2026-10-05** ([results](fo4_spikes.md#spike-3-measured)): of 199 sampled converted FNV scripts, 81 compile unchanged with FO4's compiler, 54 fail only through our helper scripts, 64 on their own code (update loop, actor values, `SendModEvent` lead). 20 of 554 command rows change; VMAD changes are small. **Target switch built** ([target](fo4_spikes.md#spike-3-target)): Doc Mitchell's script emits as FO4 Papyrus and compiles with FO4's compiler; Skyrim output unchanged. **Corpus gate built** ([gate](fo4_spikes.md#spike-3-gate)): all FNV scripts converted for FO4; **98.5% compile** (17,425 of 17,698) after `RewardXP` → native `RewardPlayerXP` and the character menus → a custom event. **All 16 FO4 helpers compile** ([helpers](fo4_spikes.md#spike-3-helpers)): 3 left out as unneeded, the converter's FO4 rules applied to the shared source, 8 function overrides with a drift guard. **99.9% compile** (17,672 of 17,695) after `OnTrigger`, `SetRestrained`, fast travel, sleep and menu events and the singles ([singles](fo4_spikes.md#spike-3-singles)); a duplicate-name guard and per-game prefixes ([names](fo4_spikes.md#spike-3-names)). The doctors' stage scripts compile since a quest stage's bare call acts on the player ([VDoctors](fo4_spikes.md#spike-3-vdoctors)); **17,676 after the singles** ([singles](fo4_spikes.md#spike-3-else-text)): text after `else` is dropped as FO3/FNV's compiler drops it (18 lines in 13 scripts), a no-value call's `set` stores the empty value. Left: 19, all in scripts nothing attaches. **FO4 VMAD built** ([vmad](fo4_spikes.md#spike-3-vmad)): matches vanilla byte for byte (520 of 521 INFOs, all sampled quests). **End to end played 2026-10-05** ([end to end](fo4_spikes.md#spike-3-end-to-end)): Doc's converted script on his stand-in binds; `setav FNV_Variable01 1` turns the player's controls off and back on. FO4 has no `Variable01`–`10`, so the plugin carries its own. The 8-second wait measured at 8.06 s ([timing](fo4_spikes.md#spike-3-timing)). **Dialogue fragments played 2026-10-05** ([fragments](fo4_spikes.md#spike-3-fragments)): 29 lines carry their converted FNV scripts; paid treatment, stimpaks, water and barter work. The stand-ins' own FO4 greetings and scenes still compete with ours (stand-in only). **Shared helper plugin played 2026-10-05** ([helper plugin](fo4_spikes.md#spike-3-helper-plugin)): `TES4Helpers.esl` holds Variable01-10, the FO3/FNV skills, the helper quests and `TES4ControlsDisabled`; `AV()` reads it and FO3/FNV skills keep their names on FO4; corpus still 17,672 of 17,695. **VDoctors played 2026-10-05** ([VDoctors](fo4_spikes.md#spike-3-vdoctors)): the doctors quest with its converted stage script, treatment heals and the radiation line clears rads (stages 10 and 30 done). The compile gate now compiles only changed scripts, and their users only when a declaration they compile against changed |
| [Spike 4: Goodsprings and its items](fo4_spikes.md#spike-4-exterior) | **Built 2026-10-07/08, played 2026-10-08:** the 3×3 Goodsprings block ([trees](fo4_spikes.md#spike-4-trees), [sounds](fo4_spikes.md#spike-4-sounds) and [door and container animations](fo4_spikes.md#spike-4-animations) built 2026-10-09, played 2026-10-10); [creature census](fo4_spikes.md#creature-census) 2026-10-10; [Cheyenne on Dogmeat](fo4_spikes.md#spike-4-creatures), FNV's dog mesh on FO4's dog, played 2026-10-10; geckos as FO4 mole rat stand-ins (FNV's gecko on the deathclaw tried and dropped), played 2026-10-10, grass, climbable steps, consumables and ammo ([exterior](fo4_spikes.md#spike-4-exterior)); player collision box at 115, played ([player collision](research/fo4_target.md#player-collision)); weapons and armor on FO4 records ([equipment](fo4_spikes.md#spike-4-equipment)), melee weapons ([melee](fo4_spikes.md#spike-4-melee)) and headgear ([headgear](fo4_spikes.md#spike-4-headgear)) on FNV's meshes, played; the pre-war outfits on FNV's meshes moved onto FO4's body (played; variants as material swaps; CBBE and BodySlide later) ([outfits](fo4_spikes.md#spike-4-outfits)). FNV's guns on FO4 receivers tried twice and parked as experimental: FO4's animations fit only FO4's layouts ([guns](fo4_spikes.md#spike-4-guns)). **Step 1 of the replacement table built** ([replacements](fo4_replacements.md)): guns back on FO4's guns by default |
| [Spike 2: one interior cell](fo4_spikes.md#spike-2) | **Step 1, one static, played 2026-10-06** ([static](fo4_spikes.md#spike-2-static)): an FO4 NIF reader/writer ([nif](fo4_spikes.md#spike-2-nif)), BGSM ([bgsm](fo4_spikes.md#spike-2-bgsm)) and BGEM ([bgem](fo4_spikes.md#spike-2-bgem)), each rebuilding vanilla byte for byte (32,397 meshes, 6,616 BGSMs, 283 BGEMs). Three FNV statics from Doc's house render in QASmoke: a shelf, a Craftsman wall corner (specular maps from FNV's normal-map alpha), a test-tube rack (glass as vanilla's beaker effect material). **Step 2, Doc's house cell, played 2026-10-06** ([cell](fo4_spikes.md#spike-2-cell)): 427 of 434 references (meshes as statics, FNV lighting, lights, a door to QASmoke and back), unlit FNV shapes as inline effect shaders. Looks right; fog and colour judged once it has a standard interior's imagespace. **Step 3, collision, played 2026-10-06** ([collision](fo4_spikes.md#spike-2-collision)): FNV's Havok blocks in FO4's pre-Elric form, the CK's Elric builds the FO4 physics, grafted into our meshes; mesh winding through the shared repair. **Step 4, FaceGen, played 2026-10-06** ([facegen](fo4_spikes.md#spike-2-facegen)): the CK exports FaceGen through MO2; FNV's face shape baked into the exported head (C1 kept; FO4's sliders capture 2.3% of it). **Step 5, the face in FO4's own systems, played 2026-10-06**: FNV's face texture can't hide the hairline ([face texture](fo4_spikes.md#spike-2-face-texture)), so the face is rebuilt from FO4 sculpt regions fitted through the CK (70% of the shape, [sculpt](fo4_spikes.md#spike-2-sculpt)) and face detail layers plus skin tone ([tints](fo4_spikes.md#spike-2-tints)); ST kept. **Step 6, hair, played 2026-10-06** ([hair](fo4_spikes.md#spike-2-hair)): FO4 hair, facial hair and eyes matched by drawn coverage and iris colour, hair colour through both games' shaders, brows in the tint fit (tattoos kept out). **Step 7, imagespace, played 2026-10-06** ([imagespace](fo4_spikes.md#spike-2-imagespace)): FNV's cinematic grading and tone curve baked into an FO4 LUT. **Step 8, blended surfaces, played 2026-10-06** ([transparency](fo4_spikes.md#spike-2-transparency)): FO4 draws no blended lit surface but a decal, so FNV blends become decals, insect-wing or glass effect materials, or cut-outs with their see-through triangles split off. **Step 9, the cell's objects, played 2026-10-06**: misc items, leveled lists and containers ([items](fo4_spikes.md#spike-2-items)); furniture with seats and beds from FNV's markers ([furniture](fo4_spikes.md#spike-2-furniture)), after Elric was found to read FNV's motion types and node rotations in Havok 2014's terms; activators with their converted scripts, messages, triggers and drinkable water ([activators](fo4_spikes.md#spike-2-activators)). **Step 10, navmesh, played 2026-10-06** ([navmesh](fo4_spikes.md#spike-2-navmesh)): FNV's authored navmesh as FO4 NVNM 15 in the NAVI singleton; Doc follows the player through the house. **Step 11, Doc's intro quest (VCG01), in progress** ([vcg01](fo4_spikes.md#spike-2-vcg01)): the quest and its scripts, Doc's scripted lines, the Reflectron, the psych test as scenes with XDI menus, and Doc's AI packages, played to the door 2026-10-06. Next: Doc after the intro ([his quests](fo4_spikes.md#spike-2-doc-quests), built 2026-10-09: VFreeformGoodsprings and VDoctors, one greeting and topic list for every cell quest), sounds, open/close animation |
| [Pipeline](fo4_pipeline.md) | **Planned 2026-10-10.** Grows on the Skyrim converter's stack (which already converts all of FalloutNV.esm), not on the spike's `cell.py`. **Step 1 built 2026-10-10:** no FormID is counted any more ([FormIDs](fo4_spikes.md#formids)); FNV's own ids for one-to-one records, hashed ids for generated ones, FalloutNV.esm's ids reserved first. **Step 2, the record census, built 2026-10-10** ([census](fo4_pipeline.md#census)): every FO3/FNV type routed to its FO4 type (`fo4_import/record_routes.py`); 27 types (86% of FNV's records) have a spike converter, 23 are partly converted, 57 (8,472 records, mostly the rules data AI and quests need) are not started. **Step 3, the pipeline skeleton, built 2026-10-10** ([skeleton](fo4_pipeline.md#skeleton)): `fo4_import.pipeline.run` builds the spike block with the export read once, meshes converted on every core into a cache, Elric's output cached, scripts compiled only when changed; byte-identical to the spike's plugin, 362 s → 168 s cold, 108 s rebuilt. **Placed-type converters and `--region` built 2026-10-10** ([converters](fo4_pipeline.md#converters)). **Exterior navmesh built 2026-10-10** ([exterior navmesh](fo4_pipeline.md#exterior-navmesh)): every navmesh in the build, linked across cells with FO4's facing-edge byte; played. **Interiors reached by doors built 2026-10-10** ([interiors](fo4_pipeline.md#interiors)): a build includes every interior its doors lead into (9 for the spike block, 27 for Goodsprings to Primm); played. Script properties now take FO4's engine globals (`GameHour`). **Goodsprings to Primm built 2026-10-10** ([region](fo4_pipeline.md#region)): 252 cells, 27 interiors, 20,725 references, 400 navmeshes, 177 s with meshes cached; played once: interior rooms and portals, ragdoll poses, fog max and height-fog colors fixed after it ([rooms](fo4_pipeline.md#rooms)); interior fog still renders brighter than FNV's. **Region play-tests 2026-10-10/11, played:** collision, joints, locks, lights, lighting templates, emittance, glow, effect animation, particles, add-ons, land texture blending, FNV climate and weathers. In test: enable parents, region emittance. **Order reworked 2026-10-11** ([order](fo4_pipeline.md#order)): close the region's world (frame rate, build time), then the rules records, real NPCs and the opening quests in the region, then the whole Mojave, then LOD; visual parity work is [parked](fo4_pipeline.md#parked). **Next: step 1, measure the region** |

## <a id="phases"></a>Phases

1. **Stable ground.** Play everything written but not yet played (below), run
   the preflight audits after every build, and land the two safest Papyrus
   cost fixes.
2. **The stats sheet.** Character pieces T and G1 (data, then a sheet that
   writes nothing), then checks S1 to S3, then F.
3. **Setup without hand work.** Standalone play pieces B, C and D, then H.
4. **Systems with gameplay weight.** Item condition (H), level-up and chargen
   in the sheet (G2), and skill effects built with their systems (J).

## <a id="character"></a>Character systems

Carried over from the character plan's own status notes of 2026-09-28.

| Piece | State |
|---|---|
| A: character data | Built for Oblivion and Fallout; Morrowind not started |
| I: runtime leveling gate | Built; played with Oblivion |
| D: skill-use leveling | Built; played with Oblivion 2026-09-27 |
| E: Fallout XP leveling | Built; played in New Vegas 2026-09-27 |
| E: perks and traits, level-up perk and trait menus | Written, **not played** |
| E: reputation and karma for scripts and conditions | Written, **not played** |
| E: karma and infamy from kills and thefts | Written, **not played** |
| E: Fallout 3 rules plugin | Builds (2026-09-28), **not played** |
| E: Fallout 3 speech challenges | Written, **not played** |
| G: Fallout chargen as message boxes (S.P.E.C.I.A.L., tag skills) | Written |
| B, C: shared stat store and NPC stat natives | Not started |
| T: skill table columns | Not started |
| G1: read-only stats sheet | Not started |
| F: own-store skills, active skill | Not started; waits on S1 to S3 |
| G2, H, J | Not started |

## <a id="stability"></a>Stability

- **Play-test backlog:** every "not played" row above.
- **Preflight audits:** built (`python -m tools.validate.preflight`, `--audit
  logs` after a play-test). Open gaps:
  - audit 1 doesn't check stage-item conditions or Say Once lines;
  - audit 2 doesn't evaluate condition-filled aliases, and marks required
    ones for review;
  - audit 4 uses the quest audit's dialogue models rather than the two
    emulators;
  - audit 6 doesn't check that quest actors have a package bringing them to
    their scenes.
- **[Kill cams and killmoves](kill_cams.md):** not started. Killmoves misfire
  on converted weapons (FO3/FNV's baton plays a sword killmove). Options
  recorded; first step is the census of the vanilla killmove conditions.

## <a id="performance"></a>Performance

| Item | State |
|---|---|
| [Papyrus cost](performance.md#papyrus) 2: GameMode loops | Not started; first, safest |
| Papyrus cost 1: quest poll interval | Not started; after the Creation Kit check |
| Papyrus cost 3: dialogue state in actor values | Not started |
| Papyrus cost 4: patrol arrival checks | Not started; lowest |
| [FO3/FNV occlusion](performance.md#occlusion) | Not started; cost in play unmeasured |

## <a id="standalone-play"></a>Standalone play

| Item | State |
|---|---|
| Pieces A to H | Not started. MO2 profiles `FNV`, `FO3` and `Oblivion` exist, made by hand |
| World picker on the main menu | Candidate; needs DLL work |
| Upstream PR #65 | Open, with the plan's earlier copy; the fork's copy has moved on |

## <a id="parked"></a>Parked

| Item | Why |
|---|---|
| [Bink movies](bink_movies.md) | Nothing plays; low value against the rest |
| OBSE command coverage | Until the standalone Oblivion work is done; probe in `probes\obse_coverage` |
| Nehrim | Deprioritized for the four main games |
| [Graphics and OpenMW research](research/graphics_options.md) | Notes to revisit when the project is more mature |

## <a id="upstream"></a>Upstream plans, not followed

These stay in `docs/plans/` as upstream wrote them.

| Plan | Why not |
|---|---|
| [character_sheet.md](../plans/character_sheet.md) | Conflicts with [character.md](character.md#sources) on leveling, layout and governing stats; its menu plumbing, stat store and Statistics tab are reused |
| [horse_rideability.md](../plans/horse_rideability.md) | Outside the focus |
| [in_app_update.md](../plans/in_app_update.md) | Outside the focus |
| [morrowind_object_scripts.md](../plans/morrowind_object_scripts.md) | Built and confirmed upstream; nothing left to follow |
| [navmesh_lattice.md](../plans/navmesh_lattice.md) | Upstream's experiment, opt-in |
| [vanilla_creature_swap.md](../plans/vanilla_creature_swap.md), [vanilla_item_swap.md](../plans/vanilla_item_swap.md) | Optional add-ons, outside the focus |

## <a id="elsewhere"></a>Notes kept elsewhere

- The Claude Doc "Oblivion Profile Research" predates this folder. Anything in
  it that is still true belongs here; after that, treat it as frozen.
- Agent memory is per machine and is never the only copy of a finding.
