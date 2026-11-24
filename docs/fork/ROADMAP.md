# Roadmap and status

What works in **fo3fnv-in-fo4** today, what is built but not yet played, and
what is next. Dates, counts and history are in the
[development log](dev_log.md#roadmap-2026-11-23) and the doc each row links.

## <a id="fo4-state"></a><a id="alpha"></a>Where it stands

**Release:** [f3nv-0.6](https://github.com/ThyMrMan/fo3fnv-in-fo4/releases/tag/f3nv-0.6),
an alpha (prerelease, 2026-11-24). A fresh download converts, NPC faces
included (measured on the user's PC since 0.3, without the Creation Kit).
Since 0.4 the export and caches live in a work folder beside the app, so a
new release unzips beside the old one and upgrades cleanly
([work folder](fo4_gui.md#work-folder)). 0.5 ships the helper scripts every
earlier zip left out ([slim zip](fo4_plan_release.md#slim-zip)), so scripts
compile in Caprica again instead of FO4's slow compiler. Shared
conversation menus keep their topics ([fix](fo4_dialogue_gaps.md#shared-menu-topics)),
so a build's reference check passes. It also lowers the
build's memory peak, and gives a quieter log with a steadier time estimate
([build resources](fo4_build_resources.md)). 0.6 encodes voice with our own
xWMA encoder instead of a Microsoft tool ([encoder](fo4_ck_replacements.md#xwma-spike)),
keeps converted voice files across output folders and releases
([voice cache](fo4_build_speed.md#voice-cache)), and drops the Black
Landscape Fix requirement ([played without it](fo4_spikes.md#empty-land-layers)).
It fixes Fallout 3's `washmontop` distant terrain
([world frame](fo4_pipeline.md#terrain-lod-world-frame)), and the app shows
when a quiet build is still working ([activity line](fo4_gui.md#activity)).

- **New Vegas** is playable from Doc Mitchell's house onward, with its four
  story DLC, five add-on packs and about 20 mods. Nearly every system is
  built; much of it has never been played.
- **Fallout 3** is experimental. Its opening in Vault 101 is built and played
  by our automated story runs. The whole Capital Wasteland and its five DLC
  build, but are unplayed past the vault door.
- **The app** converts either game, its DLC and mods. Its first real-world
  run, a fresh 0.2 download to a New Vegas build in about 80 minutes, built
  everything but the faces; 0.3 fixes those.

Most of what is left is play-testing and fixing what testers find.

| State | Means |
|---|---|
| Works | Played and working |
| Built, not played | In the build; nobody has tried it in game yet |
| Partial | Some of it works, some is missing |
| Not built | Not converted yet |

## <a id="fo4"></a>Status by area

### The world

| Feature | State | What's left | Doc |
|---|---|---|---|
| Landscape | Works | A few soft land seams; no longer needs the Black Landscape Fix mod ([played without it](fo4_spikes.md#empty-land-layers)) | [exterior](fo4_spikes.md#spike-4-exterior) |
| Distant terrain | Partial | Seams between tiles (fix built, not played) | [terrain LOD](fo4_pipeline.md#terrain-lod) |
| Distant objects | Partial | Distant trees and the DLC and mod worlds' objects not played | [object LOD](fo4_pipeline.md#object-lod-masters) |
| Pip-Boy world map | Partial | Marker positions fixed, not played | [world map](fo4_pipeline.md#world-map) |
| Worldspaces and exteriors | Partial | Traps, smoke and burning-car damage not played | [whole map](fo4_pipeline.md#whole-map) |
| Interiors | Works | | [interiors](fo4_pipeline.md#interiors) |
| Room culling | Partial | 29 interiors draw everything at once | [rooms](fo4_pipeline.md#rooms) |
| Water | Partial | Two radiation grades instead of five | [water](fo4_pipeline.md#placeable-water) |
| Navmesh | Partial | No cover data; NPCs sometimes catch on steps | [navmesh](fo4_pipeline.md#exterior-navmesh) |
| Weathers | Partial | Clouds are Fallout 4's, recolored; the amber tint not played | [weathers](fo4_pipeline.md#weathers) |
| Grass | Built, not played | | [grass](fo4_look.md#grass) |
| Lights, neon and glow | Built, not played | The saloon window is too yellow | [neon](fo4_look.md#route-neon) |
| Projector slides and shading overlays | Built, not played | | [slides](fo4_pipeline.md#slide-strips) |
| Color tone | Built, not played | | [FO4 route](fo4_look.md#fo4-route) |
| Modern lighting and Classic Look | Built, not played | | [lights](fo4_look.md#route-lights) |
| Precombines and previs | Not built | Precombines researched; previs needs the Creation Kit | [research](research/fo4_precombines_previs.md#own-precombines) |
| Frame rate | Partial | Freeside, the Strip and Novac not measured | [measured](fo4_pipeline.md#region-measured) |
| Intro movie | Works | | [play test](bink_movies.md#play-test) |

### NPCs

| Feature | State | What's left | Doc |
|---|---|---|---|
| Faces | Works | | [sculpt](fo4_spikes.md#spike-2-sculpt) |
| Hair and eyes | Works | Long-hair stretch fix not checked | [hair](fo4_spikes.md#hair-styles) |
| Our own FaceGen | Built, not played | Mods' own hairstyles; the Creation Kit stays as a fallback | [own stage](fo4_facegen_plan.md#own-stage) |
| DLC and mod faces | Built, not played | | [DLC and mods](fo4_facegen_plan.md#addon-faces) |
| Outfits | Partial | 15 of 323 armors keep Fallout 4's worn models, 24 more its ground model; wrist seam; loose cloth | [clothing](fo4_build_next.md#human-clothing) |
| Headgear | Works | | [headgear](fo4_spikes.md#spike-4-headgear) |
| Race looks (raider grime, tribal paint, burns) | Partial | FNV's raiders work; the other look races not played | [plan](fo4_look_races_plan.md#body) |
| Body choice (CBBE, BodySlide) | Partial | Researched; only the vanilla body is built | [body plan](fo4_bodies_cbbe.md) |
| Super mutants and nightkin | Partial | Fallout 4's mutant body under New Vegas's armor | [super mutants](fo4_build_next.md#super-mutants) |
| Ghouls and glowing ones | Works | | [ghouls](fo4_creature_audit.md#ghouls) |
| Ghost People and holograms | Built, not played | | [Dead Money](fo4_spikes.md#dead-money-humans) |
| Daily routines | Partial | 85 routines missing; most NPCs drop theirs in combat | [packages](fo4_pipeline.md#packages) |
| Scripted routines | Partial | Patrol-point actions not played | [patrol points](fo4_pipeline.md#patrol-points) |
| Standing idles | Works | | [standing](fo4_idles.md#standing) |
| Ambient idles | Built, not played | Weapon-out idles not built | [trees](fo4_idles.md#trees) |
| Seated idles | Partial | Not watched in game | [furniture](fo4_idles.md#furniture) |
| Idle props and markers | Built, not played | 6 markers have no Fallout 4 gesture | [markers](fo4_pipeline.md#audit-fixes) |
| Animated objects | Built, not played | Animations a script didn't start read as stopped | [plan](fo4_plan_script_functions.md#phases) |

### Creatures

| Feature | State | What's left | Doc |
|---|---|---|---|
| Own-rig creatures (geckos, nightstalkers, mantises, cazadors) | Works | | [own rig](fo4_own_rig.md#mantis) |
| Own-rig creatures, the rest | Built, not played | | [remaining](fo4_own_rig.md#remaining) |
| Own-rig reactions | Partial | Crippled reactions and backward walks not played; no staggers or sounds | [hit reactions](fo4_own_rig.md#hit-reactions) |
| Stand-in creatures (deathclaws, dogs, robots...) | Partial | Fallout 4-only moves switched off, not played | [race abilities](fo4_creature_audit.md#race-abilities) |
| Spawns | Built, not played | | [void](fo4_creature_audit.md#void) |
| Corpse poses | Partial | Robots and about 31 others ragdoll | [poses](fo4_spikes.md#creature-poses) |
| Talking machines (Mr. House, Yes Man, Festus) | Partial | Idles, Yes Man and Festus not played | [machines](fo4_creature_audit.md#talking-machines) |
| Securitrons | Partial | Face screen not played | [screens](fo4_build_next.md#screens) |
| Think Tanks | Built, not played | | [think tank](fo4_own_rig.md#think-tank) |

### Dialogue

| Feature | State | What's left | Doc |
|---|---|---|---|
| Conversation menu | Works | Cleanroom UI's dialogue menu; Extended Dialogue Interface must be off | [menu](dialogue_menu_mod.md) |
| Dialogue lines | Partial | 92 lines left out by a condition (61 a GetIsID of an actor never placed) | [census](fo4_dialogue_gaps.md#census-2026-11-23) |
| Shared-answer choices | Partial | 13 choices without a line, 9 for actors never placed | [census](fo4_dialogue_gaps.md#census-2026-11-23) |
| Say Once, skill checks, voices | Works | | [voice types](fo4_pipeline.md#voice-types) |
| Silent player, lip sync, greetings | Built, not played | | [lips](research/lip_format.md#built) |
| Force greets | Partial | Only Ringo and the Primm trooper tested | [greet trigger](fo4_pipeline.md#greet-trigger) |
| The world pauses while you choose | Built, not played | | [built](fo4_talk_in_combat_plan.md#built) |
| Barks and companion barks | Partial | Not heard; 91 companion lines need what Fallout 4 doesn't track | [barks](fo4_pipeline.md#barks) |
| Ambient chats, talking activators | Built, not played | | [chats](fo4_pipeline.md#actor-dialogue) |
| Scenes | Partial | Looping and branching scenes untested | [scenes](fo4_pipeline.md#scene-loops) |

### Quests and scripts

| Feature | State | What's left | Doc |
|---|---|---|---|
| New game | Works | Two timing fixes at Doc Mitchell's not played | [seated](fo4_pipeline.md#furniture-seated) |
| Quests | Partial | Played from Goodsprings to Primm only | [preflight](fo4_preflight.md#results-2026-11-07) |
| Script converter | Partial | 659 calls do nothing; 177 of them have a Fallout 4 native ([audit](../audits/fo4_redo_audit_2026-11-23.md#natives)) | [scripts](fo4_spikes.md#spike-3-gate) |
| Unconverted functions | Partial | Combat styles, package timers, renaming, music cues | [not built](script_markers.md#not-built) |
| Condition reads, triggers, region tests | Built, not played | | [reads](script_markers.md#native-read-follow-ups) |
| Companions | Partial | No companion wheel; hiring and gear return untested | [drift](fo4_drift.md#candidates) |
| Terminals, message boxes | Works | | [terminals](fo4_pipeline.md#terminals) |
| Locks and hacking | Built, not played | | [locks](fo4_pipeline.md#lock-script) |

### Radio

| Feature | State | What's left | Doc |
|---|---|---|---|
| Radio New Vegas, Mojave Music Radio, placed radios | Works | | [radio](fo4_radio.md#steps-model) |
| Black Mountain, lounges, scripted broadcasts | Built, not played | Black Mountain's event lines | [start radio](fo4_radio.md#start-radio-conversation) |

### The character

| Feature | State | What's left | Doc |
|---|---|---|---|
| S.P.E.C.I.A.L., skills, sex change | Works | | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Tag skills | Built, not played | | [special](fo4_opening_progression_plan.md#special-built) |
| Level-ups (our own menu, options in MCM) | Built, not played | | [our menu](fo4_level_up_plan.md#menu) |
| Perks | Partial | 29 effects have no Fallout 4 equivalent | [census](fo4_perks.md#census) |
| Traits | Partial | Effects not played | [drift](fo4_drift.md#recorded) |
| Companion perks, skill books, Intense Training | Built, not played | Comprehension's extra point | [books](fo4_pipeline.md#skill-books) |
| Skill magazines | Works | | [consumables](fo4_pipeline.md#consumable-effects) |
| Karma | Partial | Theft karma untested | [standings](fo4_pipeline.md#standings) |
| Reputation | Built, not played | The title-change box has no text | [reputation](fo4_pipeline.md#reputation-messages) |
| Challenges | Partial | 67 of 105 counted | [left out](fo4_pipeline.md#challenges-left-out) |
| Hardcore mode | Built, not played | No settings-menu switch (an aid item turns it on) | [Hardcore](fo4_hardcore.md#built) |
| Chem addiction | Partial | Withdrawal effects are Fallout 4's | [addiction](fo4_pipeline.md#chem-addiction) |
| Fatigue, disguises | Built, not played | | [disguises](fo4_pipeline.md#disguises) |
| Pip-Boy SKILLS, REPUTATION, KARMA, CHALLENGES | Works | | [tabs](fo4_pipboy_tabs.md#how) |

### Combat

| Feature | State | What's left | Doc |
|---|---|---|---|
| Guns | Partial | New Vegas's third-person clips built, not played; 14 guns have no third-person entry | [guns](fo4_gun_animation.md#order) |
| Ammo types, scopes, jams, criticals, sneak attacks | Works | | [ammo](fo4_pipeline.md#ammo-switch) |
| Weapon mods | Partial | Not played; 9 do nothing | [mods](fo4_pipeline.md#weapon-mods) |
| Condition and repair | Works | Vendor repair not played | [condition](fo4_condition.md#built) |
| Damage Threshold | Built, not played | Defender DT perks, ammo DR | [DT](fo4_pipeline.md#damage-threshold) |
| Weapon poisons | Built, not played | | [poisons](fo4_pipeline.md#weapon-poisons) |
| V.A.T.S. and combat feel | Works | V.A.T.S. slows time instead of pausing | [feel](fo4_combat_feel.md#built) |
| Thrown weapons and explosives | Works | | [thrown](fo4_thrown_weapons.md#built) |
| Melee and unarmed | Partial | Fallout 4's animations; no unarmed special moves | [melee](fo4_spikes.md#spike-4-melee) |
| Projectiles, combat styles | Built, not played | Fallout 4 stand-in looks and sounds | [projectiles](fo4_pipeline.md#projectile-copies) |
| No combat sprinting | Works | | [sprint](fo4_pipeline.md#combat-sprint) |
| Allies join a scripted fight | Built, not played | | [allies](fo4_pipeline.md#allies-join) |

### Items

| Feature | State | What's left | Doc |
|---|---|---|---|
| Consumables | Partial | Script-driven effects not played | [consumables](fo4_pipeline.md#consumable-effects) |
| Crafting | Partial | Our own recipe menu planned | [plan](fo4_crafting_plan.md#recommendation) |
| Caps | Works | | [items](fo4_casino_plan.md#items-built) |
| Other money and cards | Built, not played | | [items](fo4_casino_plan.md#items-built) |
| Item models | Partial | Many aid items show Fallout 4's | [drift](fo4_drift.md#recorded) |

### Casino games

| Feature | State | What's left | Doc |
|---|---|---|---|
| Slots, roulette, blackjack | Works | No animations or sounds; no gamepad cursor | [blackjack](fo4_casino_plan.md#blackjack-built) |
| Caravan | Built, not played | | [caravan](fo4_casino_plan.md#caravan-built) |
| Lucky Horseshoes | Built, not played | | [Lucky Horseshoes](fo4_casino_plan.md#lucky-horseshoes) |

### DLC, mods and Fallout 3

| Feature | State | What's left | Doc |
|---|---|---|---|
| Story DLC | Built, not played | | [DLC](fo4_plugin_layout.md#dlc-build) |
| Gun Runners' Arsenal and courier packs | Built, not played | | [packs](fo4_plugin_layout.md#courier-packs) |
| New Vegas mods (about 20) | Partial | Played only in Doc Mitchell's house | [mod builds](fo4_mod_builds.md) |
| Fallout 3 opening | Partial | The walk to the vault door sticks in the story runs | [FO3](fo4_fo3_plan.md) |
| Fallout 3 world and DLC | Built, not played | | [FO3](fo4_fo3_plan.md#next) |
| Fallout 3's child player | Partial | Scale converted; the child race is planned | [child player](fo4_fo3_child_player.md) |

### <a id="fo4-app"></a>The app and installing

| Feature | State | What's left | Doc |
|---|---|---|---|
| Conversion app | Built, not played | First end-to-end run from a fresh download | [app](fo4_gui.md#convert-screen) |
| Installing | Built, not played | README steps not yet followed on a clean setup | [install](../../README.md#install) |
| Replacements | Partial | Named profiles and a Wabbajack list | [replacements](fo4_replacements.md#direction) |
| Building without the Creation Kit | Partial | Fallbacks remain for faces, meshes and scripts; the face and mesh ones almost never fire ([audit](../audits/fo4_redo_audit_2026-11-23.md#elric)) | [CK replacements](fo4_ck_replacements.md) |
| Linux and macOS | Partial | Never tried; the pinned zlib and the script compile are Windows-only ([blockers](../audits/fo4_redo_audit_2026-11-23.md#off-windows)) | [Windows tools](fo4_gui.md#windows-tools) |

## <a id="known-bugs"></a>Known bugs a player will see

- Holes and dark blocks in distant land, closing as you approach.
  ([terrain LOD](fo4_pipeline.md#terrain-lod))
- Scripts that wait for an animated window or the Lucky 38 lights do nothing.
  ([census](fo4_idles.md#census))
- NPCs and the player catch on some stairs (the Novac motel, Vikki and
  Vance's steps). ([stairs](fo4_pipeline.md#stair-helper-pitch))
- Your left hand briefly leaves the rifle when you aim.
  ([guns](fo4_gun_animation.md#order))
- Explosives-kill challenges count only while an explosive is equipped.
  ([challenges](fo4_pipeline.md#challenges-left-out))
- With CBBE installed, bare skin in converted outfits looks scrambled.
  ([body plan](fo4_bodies_cbbe.md))
- With both `Fallout3.esm` and `FalloutNV.esm` on, both openings start and
  you get stuck in Vault 101. Keep each game in its own MO2 profile.
  ([FO3](fo4_fo3_plan.md))

Please report what you find in
[the issues](https://github.com/ThyMrMan/fo3fnv-in-fo4/issues).

## <a id="fo4-next"></a>Planned work

In rough order. The [issue plan](fo4_issue_plan.md) sizes and orders the fixes.

1. **The app's real-world runs:** New Vegas built from a fresh 0.2 download
   (faces fixed in 0.3); a fresh 0.3 download on a second PC, then Fallout 3,
   are next ([app](fo4_gui.md#convert-screen)).
2. **Play-testing** everything marked "Built, not played", and fixing what
   turns up.
3. **Automated play-tests:** stage sweeps, story runs and unattended runs on
   the test machine ([story runs](fo4_story_tests.md#order), [layers](fo4_test_layers_plan.md)).
4. **Regression checks** against the last build that played well
   ([plan](fo4_regression.md#order)).
5. **Fallout 3:** finish the opening's story runs, then the Capital
   Wasteland and the child player ([next](fo4_fo3_plan.md#next)).
6. **Known bugs** above ([issue plan](fo4_issue_plan.md)).
7. **Gun animation:** play the third-person clips; a third-person entry for the 14 guns without one ([plan](fo4_gun_animation.md#order)).
8. **Creatures:** staggers and sounds for own rigs ([own rig](fo4_own_rig.md#hit-reactions)).
9. **The look:** grass, neon, glow, tone, distant trees and water ([plan](fo4_look.md)).
10. **Distant terrain of our own** ([plan](fo4_terrain_lod_plan.md)).
11. **Crafting on our own menu** ([plan](fo4_crafting_plan.md#recommendation)).
12. **Body choice:** CBBE and BodySlide ([plan](fo4_bodies_cbbe.md)).
13. **Load order:** mods in your New Vegas order, a conflict report and LOOT
    rules ([plan](fo4_load_order.md)).
14. **Build speed:** move the hot spots to native code ([plan](fo4_build_speed.md)).
15. **Precombines** for Freeside and the Strip ([research](research/fo4_precombines_previs.md#own-precombines)).
16. **Script speed** ([performance](performance.md#papyrus)).

## <a id="parked"></a>Parked

| Item | Why |
|---|---|
| A choice between New Vegas and Fallout 4 combat | An idea, not planned |
| Other languages' movie tracks | Only English is checked ([Bink](bink_movies.md)) |
| [Graphics research](research/graphics_options.md) | Notes to revisit |
| [Spin-off mods](spin_offs.md) (Cleanroom UI, f3ui, our level-up menu, the casino games) | Cleanroom UI is split out and shipped; the others aren't released |
| [Dynamic collision](dynamic_collision_mod.md) | Planned as its own mod |
| [Ideas the build without the CK makes possible](fo4_after_ck_ideas.md) | Ideas only |
| [Appearance comparison](appearance_compare_tool.md) | Plan only |

## <a id="inherited"></a>The inherited Skyrim converter

<a id="character"></a><a id="stability"></a><a id="performance"></a><a id="standalone-play"></a>This
repository started as a copy of a Morrowind and Oblivion → Skyrim converter,
and that code is still here. Its plans (character systems, stability,
performance, standalone play) are about the Skyrim target, not this
project. Their last status is in the [development log](dev_log.md#character).

## Where the details live

| Doc | Holds |
|---|---|
| [dev_log.md](dev_log.md) | The history, and the detail this page no longer carries |
| [fo4_issue_plan.md](fo4_issue_plan.md) | The open issues, sized and in working order, and the group plans (`fo4_plan_*.md`) |
| [fo4_pipeline.md](fo4_pipeline.md) | How the build works, and each system built on it |
| [fo4_drift.md](fo4_drift.md) | Where play differs from New Vegas |
| [fo4_gui.md](fo4_gui.md) | The conversion app |
| [fo4_plugin_layout.md](fo4_plugin_layout.md) | The plugins, the DLC builds and FormIDs |
| [fo4_fo3_plan.md](fo4_fo3_plan.md) | Fallout 3 |
| [fo4_spikes.md](fo4_spikes.md) | The first experiments, and many findings since |
| [fo4_story_tests.md](fo4_story_tests.md) | Story runs and the test machine |
| [fo4_test_layers_plan.md](fo4_test_layers_plan.md) | Testing in layers |
| [fo4_regression.md](fo4_regression.md) | Catching regressions |
| [fo4_autoplay.md](fo4_autoplay.md) | Unattended play-test runs |
| [fo4_preflight.md](fo4_preflight.md) | The checks run on every build |
| [fo4_menu_audit.md](fo4_menu_audit.md) | The dialogue menu audit |
| [fo4_timing_audit.md](fo4_timing_audit.md) | The progress timing audit |
| [fo4_build_resources.md](fo4_build_resources.md) | How much of the PC a build uses, and its time estimate |
| [fo4_idle_review.md](fo4_idle_review.md) | Idles from every authored place |
| [fo4_regions.md](fo4_regions.md) | Region tests |
| [fo4_scene_driving_plan.md](fo4_scene_driving_plan.md) | Scenes on Fallout 4's engine |
| [fo4_facegen_plan.md](fo4_facegen_plan.md) | Our own FaceGen |
| [fo4_own_rig.md](fo4_own_rig.md) | Creatures on their own skeletons |
| [fo4_creature_audit.md](fo4_creature_audit.md) | Every creature field and where it goes |
| [fo4_perks.md](fo4_perks.md) | Perks and traits |
| [fo4_condition.md](fo4_condition.md) | Item condition, repair and jams |
| [fo4_hardcore.md](fo4_hardcore.md) | Hardcore mode |
| [fo4_radio.md](fo4_radio.md) | Radio |
| [fo4_pipboy_tabs.md](fo4_pipboy_tabs.md) | The Pip-Boy tabs |
| [fo4_look.md](fo4_look.md) | Grass, lighting and color |
| [fo4_casino_plan.md](fo4_casino_plan.md) | The casino games and Caravan |
| [fo4_level_up_plan.md](fo4_level_up_plan.md) | Our own level-up menu |
| [fo4_crafting_plan.md](fo4_crafting_plan.md) | Crafting |
| [fo4_mod_builds.md](fo4_mod_builds.md) | Converting New Vegas mods |
| [fo4_ck_replacements.md](fo4_ck_replacements.md) | The build without the Creation Kit |
| [fo4_script_compile.md](fo4_script_compile.md) | Converted scripts that failed to compile, and why each now does |
| [fo4_hotfix.md](fo4_hotfix.md) | Script hotfixes between builds |
| [nvse_script_language.md](nvse_script_language.md) | NVSE's script language in converted scripts |
| [kill_cams.md](kill_cams.md) | Kill cams and killmoves |
| [spin_offs.md](spin_offs.md) | Parts of the project released as mods |
| [dialogue_menu_mod.md](dialogue_menu_mod.md) | The dialogue menu as a standalone mod |
| [swf_framework.md](swf_framework.md) | Our Flash menu toolkit |
| [dynamic_collision_mod.md](dynamic_collision_mod.md) | Collision that changes size while playing |
| [fo4_tool_audit.md](fo4_tool_audit.md) | The converter audit before the whole-map build |

Group plans from the [issue plan](fo4_issue_plan.md):
[animation](fo4_plan_animation.md),
[dialogue reach](fo4_plan_dialogue_reach.md),
[our own dialogue menu](fo4_dialogue_menu_plan.md),
[effects](fo4_plan_effects.md),
[NPC behavior](fo4_plan_npc_behavior.md),
[release](fo4_plan_release.md),
[stand-in leftovers](fo4_plan_standin_leftovers.md),
[world look](fo4_plan_world_look.md).

Inherited from the Skyrim fork: [character.md](character.md),
[standalone_play.md](standalone_play.md),
[preflight audits design](done/preflight_audits.md).

Research: [Fallout 4 as the target](research/fo4_target.md),
[the FNV decompilation](research/fnv_decomp.md),
[NVSE features](research/nvse_port.md),
[AnimTextData](research/anim_text_data.md),
[lip files](research/lip_format.md),
[damage threshold reference](research/fo4_damage_threshold_reference.md),
[dynamic collision](research/fo4_dynamic_collision.md),
[light plugins](research/fo4_light_plugins.md),
[precombines and previs](research/fo4_precombines_previs.md),
[character findings](research/character_findings.md),
[dialogue robustness](research/fo4_dialogue_robustness.md),
[our own FNV NIF reader](research/fnv_nif_reader.md),
[creature rig prior art](research/fo4_creature_rig_prior_art.md)
([community ports](research/fo4_creature_rig_prior_art/fnv_fo3_creature_ports.md),
[technique](research/fo4_creature_rig_prior_art/fo4_creature_technique.md),
[Havok tools](research/fo4_creature_rig_prior_art/fo4_havok_tools.md),
[new-creature mods](research/fo4_creature_rig_prior_art/fo4_new_creature_mods.md)),
[FO4 animation replacer port](research/fo4_oar_port.md),
[open frameworks and tools survey](research/fo4_open_landscape.md),
[CommonLibF4 forks](research/commonlibf4_forks.md).
