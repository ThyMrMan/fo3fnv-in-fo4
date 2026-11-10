# Plan: working through the open issues by size

Every open issue on the [status page](ROADMAP.md), sized from its doc and
the code it would change (2026-11-08). Work goes from the top down: the
play-test batch first, since it costs no code and often closes several rows
at once, then small fixes, then medium, then large. Within each size, rows
are ordered by how much a player feels them.

After the play test, the medium-and-up rows are worked in groups, each with
one shared framework and its own plan:

| Group | Plan | Covers |
|---|---|---|
| Dialogue reachability | [fo4_plan_dialogue_reach.md](fo4_plan_dialogue_reach.md) | Follower options, choices with no line, lines left out, companion barks, the menu and timing audits |
| Animation and clips | [fo4_plan_animation.md](fo4_plan_animation.md) | Third-person guns, melee and unarmed, own-rig reactions and sounds, idles, the rest of the super mutant guns |
| Script functions | [fo4_plan_script_functions.md](fo4_plan_script_functions.md) | Unconverted functions, `IsAnimPlaying`, state-based barks, crime infamy, Papyrus cost |
| Perks, challenges and effects | [fo4_plan_effects.md](fo4_plan_effects.md) | Perk effects with no match, challenges, addiction, Hardcore leftovers, weapon mods, NPC ammo; the DLL decision list |
| Stand-in leftovers | [fo4_plan_standin_leftovers.md](fo4_plan_standin_leftovers.md) | Clothing bonuses, aid item and armor models, projectile looks, outfit fit, CBBE |
| NPC behavior | [fo4_plan_npc_behavior.md](fo4_plan_npc_behavior.md) | Daily routines, routines in combat, navmesh cover and islands, deathclaw charge, idle markers, stairs |
| World look and speed | [fo4_plan_world_look.md](fo4_plan_world_look.md) | Frame rate, distant land and water, tree LOD, seams, room culling, precombines, the look pass |
| Release | [fo4_plan_release.md](fo4_plan_release.md) | Clean install, app phase 7, updates, replacement profiles, mod builds, the Wabbajack modlist |

**Sizes:**

| Size | Means |
|---|---|
| Play | Built; needs only a play test, and a fix if the test fails |
| S | A day or less: cause known, one contained fix |
| M | A few days: several pieces, or one investigation and then a fix |
| L | A week or more: a new subsystem, or a cause not yet found |
| XL | Weeks of research or new tooling |

**Impact:** high blocks or breaks play; medium is visible; low is polish.
**DLL** marks the items that may need F4SE plugin work, which is the last
resort and needs the user's approval first.

## <a id="play"></a>1. The play-test batch

One play session can cover most of these. Each row names where to look.

| Item | Impact | Where and what to check | Doc |
|---|---|---|---|
| Crafting station entry | High | Played 1109a: Primm and Goodsprings put the player at the back marker, exiting into the wall. Fixed 2026-11-09, not built: each open side is its own record with one marker (Gun Runners' bench uses the back copy). Retest Primm, Goodsprings and Gun Runners | [stations](fo4_pipeline.md#station-entry) |
| Securitron and Mr. House screens, the Lucky 38 elevator | High | Victor in Goodsprings, then the Lucky 38: faces animate, the elevator prompt shows | [screens](fo4_build_next.md#screens) |
| Door arrivals into triggers | High | Ringo at the gas station (he stalled behind the script poll pile-up, since fixed). The 156 other door arrivals into a trigger are a risk, not a confirmed bug | [trace](fo4_pipeline.md#trace), [poll overlap](performance.md#poll-overlap) |
| Companions | High | Hire Cass or Boone: follow, trade, gear return, firing, and whether "Let's go" and "Keep close" show | [drift](fo4_drift.md#candidates) |
| Intense Training | Medium | Played 1108c: no box. Fixed 2026-11-08, not built: the box opens after the level-up menu closes, and a held perk's missed stage is run then. Works on old saves; a point already lost doesn't come back | [intense training](fo4_pipeline.md#intense-training) |
| NCR emergency radio and trap computer buttons | Medium | Support buttons near Primm, not on the Strip | [regions](fo4_regions.md#checks) |
| Hair matching, long hair | Medium | Doc Mitchell, Sunny Smiles, any long-haired NPC | [hair](fo4_spikes.md#hair-styles) |
| REPCON's dead super mutants | Medium | They lie posed, not in a T-pose | [poses](fo4_spikes.md#creature-poses) |
| Stair pitch | Medium | The Novac motel stairs, Vikki and Vance's steps | [stairs](fo4_pipeline.md#stair-helper-pitch) |
| Reputation title box | Medium | The Ghost Town Gunfight message shows | [reputation](fo4_pipeline.md#reputation-messages) |
| Distant land holes | Medium | The 2026-11-06 rail-line spot, with the texture half-turn fix | [terrain LOD](fo4_pipeline.md#terrain-lod) |
| Dead Money chips | Low | The Sierra Madre vending machines take chips (needs Dead Money rebuilt) | [items](fo4_casino_plan.md#items-built) |
| Companion dismissal terminal | Medium | Fixed 2026-11-08, not built: a glare pane had been picked as the screen and hid the menu (also the Lucky 38 mainframe). Use the Lucky 38 terminal | [terminals](fo4_pipeline.md#terminals) |
| Gun Runners' Vendortron store | Medium | Fixed 2026-11-08, not built: the only creature vendor now gets a vendor faction and FNV's merchant chest (read from the source plugin). Buy and sell | [vendors](fo4_pipeline.md#vendors) |
| Ambient idles too often | Medium | Played 1108c: Parker and Bert at Aerotech idled back to back. FO4 retries idles 10x as often as FNV (`fAIIdleWaitTime` 0.1 vs 1.0); the ambient root now carries `GetRandomPercent < 10`. Fixed, not built | [trees](fo4_idles.md#trees) |
| Deathclaw charge attacks | Medium | FNV deathclaws drop `csDeathclaw`'s Charging tree; check that their charge attacks still fire | [styles](fo4_pipeline.md#combat-styles) |
| Placed guns | Low | The .22 on the store shelf lies flat | [placed guns](fo4_spikes.md#placed-guns) |
| Casino slots | Medium | Played 1108c: the menu opens; every event fired 5 times (four DLC carried their own casino), Accept had a type mismatch, the image didn't load. Fixed 2026-11-08, not built (29 duplicate DLC records removed, approved). Then the casino session's checks | [slots](fo4_casino_plan.md#slots-built) |
| Load time to the main menu (Release) | High | Built 2026-11-09, not played: meshes and materials (46,886 files) pack into `FalloutNV - Main.ba2` with the sounds; the deploy deletes the mod folder's loose copies. Time the click to the main menu twice against the last 3.5 minutes; then any red error marker or missing mesh at Goodsprings | [load time](fo4_plan_release.md#load-time) |
| Crucified victims hang on their crosses | Medium | Played 1109a: nobody hung; the victims stood at the cross's origin. Fixed 2026-11-09, not built: the marker is FNV's own (in front of the cross), the clips in FNV's frame. The crucifix is its own furniture pose of FNV's clips (an additive subgraph race, FNV's hold, moan and drop). In Nipton: each victim hangs on the cross, not under it; the moan plays; activating one shows FNV's message. Then kill one and watch the fall | [crucifix](fo4_pipeline.md#crucifix) |
| Frame rate | Gates two L items | An Afterburner run through Freeside, the Strip and Novac; `tools/validate/frame_log.py` summarizes it (routes and logging steps in [world look](fo4_plan_world_look.md)) | [measured](fo4_pipeline.md#region-measured) |

## <a id="small"></a>2. Small (S)

| Item | Impact | First step | Doc |
|---|---|---|---|
| Lucky 38 penthouse door | High | Done 2026-11-08, not a bug: `Lucky38Penthouse` is FNV's unused test cell; the real penthouse is in the Lucky38World worldspace, reached by the elevator script | [whole map](fo4_pipeline.md#whole-map) |
| Black triangles on bare land | Medium | Done 2026-11-08: Black Landscape Fix is a required mod in the README and the app's install notes | [exterior](fo4_spikes.md#spike-4-exterior) |
| Pip-Boy map markers in their places | Medium | Played 1109a: the markers sat below their places (Primm under the hooked road). Fixed 2026-11-09, not built: the image is resampled from FNV's marker mapping to FO4's. Check Primm on its crossroads, and Novac and Nipton on their roads | [world map](fo4_pipeline.md#world-map) |
| Pip-Boy maps for Freeside, the Strip and the rest | Medium | Built 2026-11-08, not played: child worlds write their parent, FNV's use-parent flags and map offsets (10 worlds) | [world map](fo4_pipeline.md#world-map) |
| Super mutants unarmed with pistols and the Multiplas | Medium | Built 2026-11-08, not played: pistols, plasma rifles and the Multiplas map to FO4 super mutant sets (guns covered 66 → 104 of 119, the Fat Man was covered). Fixed 2026-11-09, not built: shotguns and the grenade launcher hold like the hunting rifle, the gatling laser like the minigun (104 → 111; the 8 left are creature weapons). A super mutant with a shotgun at Black Mountain fires it | [super mutants](fo4_build_next.md#super-mutants) |
| Explosives-kill challenges | Medium | Open: the `IsKillerObject` kill check crashed the game on a dynamite kill (an engine null read) and was removed; moves to the hit framework in [effects](fo4_plan_effects.md) | [challenges](fo4_pipeline.md#challenges-left-out) |
| Comprehension's extra book point | Low | Built 2026-11-08, not played: skill books add each book-points perk's own bonus (Comprehension +1) | [books](fo4_pipeline.md#skill-books) |
| Unbuilt quest starts | Low | Done 2026-11-08: all three are leftovers (FO3's CG02, a rumble helper, the GECK tutorial's Vault 74), marked ok | [preflight](fo4_preflight.md#results-2026-11-07) |
| Poindexter's scene | Medium | Done 2026-11-08: the audit no longer lists it | [preflight](fo4_preflight.md#results-2026-11-07) |
| Weapon poison confirmation | Low | Built 2026-11-08, not played: a yes/no box before coating; it reads "the weapon", since a message can't name it | [poisons](fo4_pipeline.md#weapon-poisons) |
| Combat-style rushing and fleeing | Low | Done 2026-11-08, left dropped: FO4's Charging flag swaps in a whole behavior tree, not a chance, and FO4 has no flee field (actors flee by Confidence, already converted) | [styles](fo4_pipeline.md#combat-styles) |
| Black Mountain event lines, Lily's recording | Low | Built 2026-11-08, not played: script-only radio topics get their own steps (Black Mountain 15 → 20); a station a script plays on an NPC gets a receiver at that NPC (Lily) | [radio](fo4_radio.md#start-radio-conversation) |
| Starts-dead actors with no pose (22) | Medium | Fixed 2026-11-08, not built: each takes the flattest upright Fallout4.esm corpse's XRGD on its skeleton; 18 of 22 (16 human, 2 brahmin), the protectron and three ED-Es stay out. Vanilla's 98 pose-less corpses are robots, turrets and leveled bases, none persistent on a ragdolled skeleton. Verify in play | [fallback](fo4_spikes.md#fallback-pose) |
| Damage Threshold per pellet, 9 DR armors | Medium | Built 2026-11-08: FO4 resists the whole shot, so `damage.cpp` takes DT once per pellet; DR armors as an armor enchantment | [DT](fo4_pipeline.md#damage-threshold) |

## <a id="medium"></a>3. Medium (M)

| Item | Impact | First step | Doc |
|---|---|---|---|
| Answers repeated, borrowed prompts | Medium | Fixed 2026-11-09, not built: a topic sharing its own line takes no second copy (all 146 `answer repeated` menus are that case; 109 copies gone from the Hub). The borrowed prompts were the audit's: it left a talking-as list free for a named NPC; settled, `duplicate prompt` 104 → 34 menus, the rest FNV's own same-text pairs (Old Ben, Caesar, Benny) | [menu audit](fo4_menu_audit.md#built) |
| Follower talk options missing | High | Checked 2026-11-09 on the 11-08 build: every companion's "Let's go", "Wait here", trade, tactics and "Stay close to me" is in the menus. The 15 follower entries are FNV-dead ("Stick close to me." has no line; firing in RL3Follower's menu). "Let's go" shows only while the companion waits (FNV's `Waiting == 1`), so say "Wait here" first | [conditions](fo4_pipeline.md#dialogue-conditions) |
| Choices with no line (185 on 11-08) | Medium | Fixed 2026-11-09, not built: about 135 to 145 are choices FNV never answers either (72 no line; the rest none the menu's speakers can say), now counted, not entries; the ~40 left say `condition` or `not built`, mostly lines left out (GetIsClass, casino, V22Bohr) | [shared infos](fo4_pipeline.md#shared-infos) |
| Scripts waiting on object animations | Medium | Census the 69 `IsAnimPlaying` checks (now always 0); a Papyrus flag set by `PlayGamebryoAnimation` and timed from the clip length | [census](fo4_idles.md#census) |
| Daily routines | Medium | Fixed 2026-11-09, not built: package conditions see the dialogue forms (items made on demand, actor values, region globals, built worldspaces), GetActorFactionPlayerEnemy is `IsHostileToActor` of the player, Escort copies FO4's `EscortPlayer`; every left-out package has a readiness cause. Predicted 85 left out to about 49: 36 convert, Find (30) stays drift, target not built (8) and 7 truly-absent forms stay. Verify with `--audit behavior`; watch Boone and Manny's 9:00/21:00 nest swap in Novac | [packages](fo4_pipeline.md#package-conditions) |
| Outfits on FO4's body | Medium | FNV's own weights for clothes (shared with `creature.Pair.own_weights`), then the wrist taper and dismemberment. Jacklyn's neck seam (1108d) fixed 2026-11-09, not built: skin rims near a body edge snap whole ([whole skin loops](fo4_spikes.md#spike-4-outfits)) | [clothing](fo4_build_next.md#human-clothing) |
| Child NPCs on adult bodies (37) | Medium | Fixed 2026-11-08, not built: child race → `child_male`/`child_female` bodies (`DiamondCitySchoolChildM03`/`F01` on `HumanChildRace`; Billy is a child ghoul), no face fit, FNV/FO3 `KID*` outfits copied from FO4's child clothes, pieces not drawn on the child race carried (the body's own outfit stays when nothing clothes it) | [children](fo4_pipeline.md#child-bodies) |
| Land strips in the sky | Medium | Played 1108c in Freeside, North Vegas Square, Aerotech (WastelandNVmini, whose mountains reach 13,000–31,000). Not the parent-world flags (PNAM is map-only). In game: `tll` under the strips splits terrain LOD from object LOD | [terrain LOD](fo4_pipeline.md#terrain-lod) |
| Stutter in the North Sewers and WastelandNVmini | Medium | Played 1108c. The sewers are an interior (water, ~1,465 refs, no precombines); try `tws` and `tcl` there, and a `frame_log` run with `tll`/`tg` in the mini world | [measured](fo4_pipeline.md#region-measured) |
| Distant water | Medium | Fixed 2026-11-09, not built: each FNV tile's LOD water is now the tile's `WATER` node, laid out like vanilla's (at level 4 split into 16 cell segments so loaded cells hide it). 163 of WastelandNV's 1,360 tiles carry water. Look west from The Fort at noon: Lake Mead and the Colorado should read as water out to the horizon. Watch for flicker where the lake-coloured stand-in land sits at the water's height | [distant water](fo4_pipeline.md#distant-water) |
| Soft land seams | Low | List the 67 shared vertices with no common texture (`land_layers.kept_textures`) | [exterior](fo4_spikes.md#spike-4-exterior) |
| Navmesh cover and island data | Medium | Write cover and island data in `pack_nvnm` and `_info` | [navmesh](fo4_pipeline.md#exterior-navmesh) |
| Dialogue lines left out (~350) | Low | Drop the 163 lines for actors FNV never places from the count; then GetIsClass and GetDisposition; ~86 wait on the casino | [conditions](fo4_pipeline.md#dialogue-conditions) |
| Seated and weapon-out idles | Low | Retry seated speaker idles on one line (the crash cause is fixed); weapon types to `WeaponAltIdleRoot` | [furniture](fo4_idles.md#furniture) |
| Hardcore leftovers | Low | The settings switch through MCM; teammates essential outside Hardcore | [Hardcore](fo4_hardcore.md#built) |
| Chem addiction | Low | Fixed 2026-11-09, not built: Hydra, Turbo, Steady, tobacco, ant nectar and Quantum each get an own actor value, odds effect, keyword and Addiction-type withdrawal spell (FNV's stat losses plus FO4's addiction markers). Drink Turbo until addicted: the Pip-Boy shows Turbo Withdrawal and Agility -2; a doctor's cure or Addictol removes it | [addiction](fo4_pipeline.md#chem-addiction) |
| Aid item and armor models | Medium | Aid items from `item` to `stats` copies, as the weapons moved | [drift](fo4_drift.md#recorded) |
| Stand-in clothing bonuses | Medium | Fixed 2026-11-09, not built: no armor keeps its FO4 template's enchantment (308 of 408 did); 160 carry FNV's own effects instead (Lucky Shades, the Vault 11 suit's DR). Wear a plain outfit (no CHR/END bonus), then Lucky Shades (Luck +1) | [armor effects](fo4_pipeline.md#armor-enchantments) |
| NPCs firing a gun's first ammo | Low | Census how vanilla NPCs get modded ammo; `NPCAmmoList` isn't written | [ammo](fo4_pipeline.md#ammo-switch) |
| Weapon mods that do nothing (9) | Low | Recheck now that item condition works; ammo regen in Papyrus | [mods](fo4_pipeline.md#weapon-mods) |
| Crime infamy | Medium | Check whether converted crime factions raise the crime-gold event | [standings](fo4_pipeline.md#standings) |
| Companion status barks (91) | Low | UsedDoctorBag, Poisoned and OnFire in `F3NV_CompanionBarks`; WeaponBroke from the stored condition | [barks](fo4_pipeline.md#companion-barks) |
| Papyrus cost 2 to 4 | Medium | GameMode loops: an attach/detach flag in place of `SafeGameModeGate` | [performance](performance.md#papyrus) |
| Room culling in 29 interiors | Low | Measure frame rate in the worst cell first | [rooms](fo4_pipeline.md#rooms) |
| Clean-machine install | High for testers | Follow the README on a clean Windows machine (needs the user); `tools.validate.fo4_install_check` checks each step (28 OK on the dev machine) | [install](../../README.md#install) |
| Replacement profiles | Low | Named profile tables | [replacements](fo4_replacements.md#direction) |
| Build checks | Low | Menu audit phase 2 checks 1 and 2 built 2026-11-08 (`--audit menus`); the rest of check 1, then the timing audit's phases 3 to 6 | [menu](fo4_menu_audit.md), [timing](fo4_timing_audit.md) |
| Mod builds | Dev only | `build_plan --verify` on each plugin, then mod-build step 2 | [mod builds](fo4_mod_builds.md) |

## <a id="large"></a>4. Large (L)

| Item | Impact | First step | Doc |
|---|---|---|---|
| Casino: blackjack, roulette, Caravan | Medium | In progress in its own session: roulette and blackjack on the slots menu, then Caravan (about three weeks) | [plan](fo4_casino_plan.md) |
| Gun animation | Medium | Step 0: list which clips each converted gun falls through to | [plan](fo4_gun_animation.md#order) |
| Own-rig creature reactions and sounds | Medium | List the clips FNV ships per rig; add a stagger and hit-reaction state to the gecko graph | [idles](fo4_own_rig.md#idles) |
| Body choice: CBBE and BodySlide | Medium | Step 1: a body resolver and a CBBE mismatch warning (after the outfit weights) | [plan](fo4_bodies_cbbe.md#plan) |
| Conversion app phase 7 | Medium | Mod Organizer setup in `core/mod_sources.py`; then Play, and the DLL, movie, face and DLC steps | [phases](fo4_gui.md#phases) |
| The look pass | Low | Grass flecks: read the 17 grass meshes' vertex color and alpha; then glow, neon, grass color, tone | [look](fo4_look.md#order) |
| Precombines and previs | Unknown | Wait for the frame-rate run; then a Creation Kit precombine run on one Strip cell | [before](fo4_pipeline.md#before) |
| Tree LOD | Low | Fixed 2026-11-09, not built: Joshua tree A (1,304 placed) uses FNV's own `_lod.nif`; dead trees 02–04, evergreens and the hardwood get cards from Fallout 3's tree LOD atlas; the 3 SpeedTree TREEs get billboard cards. That adds about 19,500 LODGen rows to WastelandNV's 15,664, 18,000 of them shrubs. Not covered: TreeDead01/05 and FNV's own sassafras, aspen and juniper (about 600 placed), which have no billboard to use. Look from Black Mountain toward the Strip | [tree LOD](fo4_pipeline.md#tree-lod) |
| Challenges left out (44) | Medium | Damage and body-part challenges through a combat-hit perk entry; "3/10" needs a goal in the Pip-Boy tab (DLL) | [challenges](fo4_pipeline.md#challenges-left-out) |
| Unconverted script functions | Medium | Rerun the marker census (several were converted since the count); then one function at a time | [markers](script_markers.md#not-built) |
| Projectile looks and sounds | Low | FNV's projectile models, lights and sounds on the copies | [projectiles](fo4_pipeline.md#projectile-copies) |

## <a id="xlarge"></a>5. Extra large (XL)

| Item | Impact | First step | Doc |
|---|---|---|---|
| Perk effects with no FO4 match | Medium | Split up: Papyrus first (Long Haul, Miss Fortune, Run 'n Gun); attack and equip speed need a DLL | [census](fo4_perks.md#census) |
| Melee and unarmed animations, unarmed specials | Medium | Reuse the gun clip retarget for FNV's melee clips (after gun animation) | [melee](fo4_spikes.md#spike-4-melee) |
| Wabbajack modlist | Low | After the clean-machine install | [replacements](fo4_replacements.md#direction) |
| Fallout 3 | — | Export Fallout3.esm and run the pipeline on one region, as the FNV spikes did | [FO4 target](research/fo4_target.md) |

## Accepted differences, not on this plan

V.A.T.S. slowing time instead of pausing (the user's choice), Fallout 4's
sprint, and FO4's follower system in place of FNV's companion wheel. These
are recorded in [fo4_drift.md](fo4_drift.md).

Checked against FNV after the 2026-11-08 play test, and not bugs: Jacklyn
runs to the player from anywhere loaded and attacks when turned away from;
only one forced greet runs at a time; Orris and the Gambler's gate talk
needs a reference FNV never enables; Doc Mitchell's first spot is the
bedside chair; Dixon says "man" to every player.
