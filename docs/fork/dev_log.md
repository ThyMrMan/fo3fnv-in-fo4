# Development log

The project's history: what was built, played or dropped, and when, with the
counts and measurements behind it. Kept as the record. **It is not the
status.** The current state of every feature is in [ROADMAP.md](ROADMAP.md);
the detail it no longer carries moves here as a dated section, newest first
([2026-11-23](#roadmap-2026-11-23)).

**Focus:** standalone play of each converted world, stability, performance.
Staying equivalent to upstream is not a goal; staying mergeable with it is, so
the fork's docs live in `docs/fork/` and upstream's plans stay in
`docs/plans/`, unedited.

| File | Holds |
|---|---|
| [character.md](character.md) | Attributes, skills, leveling, perks, standings and the stats menu, for all four games |
| [standalone_play.md](standalone_play.md) | Setup, MO2 integration, per-world profiles, launcher, world picker |
| [performance.md](performance.md) | Rules for new systems, Papyrus runtime cost, FO3/FNV occlusion |
| [kill_cams.md](kill_cams.md) | Kill cams and killmoves on converted weapons in Skyrim; a play-test check for Fallout 4 |
| [bink_movies.md](bink_movies.md) | Source-game Bink 1 movies on Fallout 4: census (36 movies), playback, plan, play test |
| [script_markers.md](script_markers.md) | FNV functions the script converter left as `;NE:` markers: census (2,156 markers, 134 functions), ranking by gameplay effect, the 19 now converted (built 2026-10-31, not played), what is left |
| [research/](research/) | Findings and notes that are not plans: [character findings](research/character_findings.md), [graphics options](research/graphics_options.md), [Fallout 4 as the target](research/fo4_target.md), [dynamic collision for FO4 (parked mod idea)](research/fo4_dynamic_collision.md), [NVSE features for FO4](research/nvse_port.md), [FO4 creature rig prior art](research/fo4_creature_rig_prior_art.md), [Damage Threshold reference (Zoltanite)](research/fo4_damage_threshold_reference.md) |
| [done/](done/) | Plans that are built, kept as their design record: [preflight audits](done/preflight_audits.md) |
| [fo4_spikes.md](fo4_spikes.md) | The spikes that showed FO3/FNV on Fallout 4 buildable (done), and the findings they made |
| [fo4_pipeline.md](fo4_pipeline.md) | The pipeline from the spike to the whole of FNV, and the record of each system built on it: what it does, measurements, play results |
| [fo4_tool_audit.md](fo4_tool_audit.md) | The converter audit before the whole-map build (2026-10-15): bugs, speed, overlooked issues, with counts |
| [fo4_preflight.md](fo4_preflight.md) | The preflight audits on the FO4 build (`--fo4`): scene dialogue model, assets, the condition differential, first results |
| [fo4_timing_audit.md](fo4_timing_audit.md) | The progress timing audit (phases 1 and 2 built) (each fact's start value, writers and prerequisites against FNV's, so quests, stages, topics and options unlock no sooner or later than in FNV; first measurements) |
| [fo4_menu_audit.md](fo4_menu_audit.md) | Plan: the dialogue menu audit (exact checks on the pieces the build adds to make menus: structure, one option per topic, option gates, effects; both games' rules from XDI and the exes; menus logged in play) |
| [fo4_creature_audit.md](fo4_creature_audit.md) | Every FNV creature field through the export and each converter path into FO4: what is carried, dropped or left over from the cloned stand-in (audit 2026-10-27; void list entries, scripts on bases and the Unique leak fixed, built in F3NV Rig Test and played; template slots built and played; inventories built and played; placed-actor scale, No AI Acquire and actor links built, not played; template actors' own speed and size built and played; Base Data and death item chains, Invulnerable and Is Ghost built, not played; the stand-in leftover check built; ghouls: glowing ones on FO4 glowing ones, ghoul radiation healing and script-effect abilities built and played; refraction surfaces built, not played; FNV attack spells (EITM) built, deathclaw knockdown as a player stagger played; the whole map not rebuilt) |
| [fo4_replacements.md](fo4_replacements.md) | The user-editable replacement table (items, then creatures: FO4 records, FNV stats, FNV meshes on FO4 rigs, other mods' records), its profiles and GUI, and the Wabbajack modlist as a soft requirement for the full experience |
| [fo4_idles.md](fo4_idles.md) | FNV idle animations on Fallout 4: `.kf` clips retargeted to FO4's skeleton, IDLE records as dynamic idles, idle trees, seated idles |
| [fo4_perks.md](fo4_perks.md) | FNV perks and traits on Fallout 4: the entry-point census, the plan, `HasPerk` |
| [fo4_drift.md](fo4_drift.md) | Where play on Fallout 4 differs from FO3/FNV, and which game's system each area uses |
| [fo4_build_next.md](fo4_build_next.md) | The 2026-10-30 list of items left on Fallout 4, in order, with what research found for each (items 1 to 4 built) |
| [fo4_plugin_layout.md](fo4_plugin_layout.md) | The plugin layout (game, DLC and pack plugins built) (game, rules, per-DLC, mod patch plugins), FormIDs across plugins, and incremental record builds |
| [fo4_condition.md](fo4_condition.md) | Item condition: wear, repair, the Pip-Boy repair and ammo lists, jams, vendor repair (the F3NV F4SE plugin) |
| [fo4_radio.md](fo4_radio.md) | FNV's radio stations as Fallout 4 radio |
| [fo4_look.md](fo4_look.md) | The plan for FNV's look: grass (density, where it grows, flecks) and lighting (weather haze, clouds, night, glow, lights, tone) |
| [fo4_pipboy_tabs.md](fo4_pipboy_tabs.md) | The Pip-Boy's SKILLS, REPUTATION, KARMA and CHALLENGES tabs, drawn by our plugin |
| [fo4_gui.md](fo4_gui.md) | The FO3/FNV conversion app: user-chosen locations, mod sources from any folder (MO2 optional), the two-column Replacements screen with 3D previews, Windows/macOS/Linux |
| [fo4_casino_plan.md](fo4_casino_plan.md) | Plan: blackjack, roulette, slots and Caravan on 2D tables (inventory with counts, FNV's engine rules, design, phases, open questions); 3D tables later |
| [fo4_regions.md](fo4_regions.md) | Plan: FNV region tests (the NCR support area, the reputation events' "wasteland only" area, scripts' map-region tests) as a polygon watch quest setting one global per region |
| [fo4_thrown_weapons.md](fo4_thrown_weapons.md) | FNV grenades, mines, placed explosives and thrown melee as real items on FO4 grenade and mine templates, with FNV's explosions, fuses and effects (built 2026-11-06) |
| [fo4_mod_builds.md](fo4_mod_builds.md) | Plan: converting one FNV mod against an already-built game (MO2 answers not files, overrides that don't stack, the master kit, Creation Kit steps without MO2); step 1 built |
| [fo4_combat_feel.md](fo4_combat_feel.md) | FNV's aim cone, health, run speed and V.A.T.S. on Fallout 4 (first pass built 2026-10-29) |
| [fo4_gun_animation.md](fo4_gun_animation.md) | Plan: converted guns' grip, third-person clips and FNV feel |
| [fo4_own_rig.md](fo4_own_rig.md) | FNV creatures on their own Havok 2014 rigs: skeleton, clips, ragdoll, behavior, the rig table |
| [fo4_hotfix.md](fo4_hotfix.md) | Shipping changed scripts between builds (`tools.release.fo4_hotfix`) |
| [fo4_bodies_cbbe.md](fo4_bodies_cbbe.md) | Plan (2026-11-07, nothing built): a Body choice (vanilla default, CBBE or a male BodySlide body opt-in) for converted outfits; fits to the chosen body, BodySlide projects the player builds, FNV's underwear as clothing; CBBE active today scrambles converted outfits' bare skin (its own UVs) |

## <a id="roadmap-2026-11-23"></a>The roadmap's notes, as of 2026-11-23

The detail the roadmap carried until 2026-11-23, when it was cut down to a short status page: the
build dates, counts and history behind each row. Copied as they stood; the roadmap holds the current
state.

### What the 2026-11-21 builds held

New Vegas is playable on Fallout 4 from Doc Mitchell's house onward, with
its four story DLC and the five add-on packs. Nearly every system is built.
Much of it has never been played, so most of what is left is play-testing
and fixing what testers find. All four casino games and Caravan are built.
Fallout 3's opening, Vault 101 from the birth to the vault door, is built
and played by our automated story runs ([FO3 spike](fo4_fo3_plan.md),
[story runs](fo4_story_tests.md)). Install steps are in the
[README](../../README.md#install).

The page describes the 2026-11-21 builds of `FalloutNV.esm` (the whole map)
and of Fallout 3's opening. The 33 DLC, pack and mod plugins were last
rebuilt in full on 2026-11-15, when every script in them compiled but one;
every face is made by our own FaceGen. Since then:

- the 2026-11-19 play-test batch (NPC health and armor, Vault 101's rooms,
  text encoding, terminal prompts, guards at their posts, chair seating,
  one mesh per gun) and the world pausing while a talk's choices wait;
- the idle markers' idle lists read from the export, and package idle
  lists written into FO4's PACK idle list, standing idles only (built
  2026-11-22, not played);
- Fallout 3's stage sweep fixes and projectiles for its guns;
- own-rig crippled-limb reactions and backward walks, projector slides
  (the G.O.A.T.), the shading-overlay fix, and Mr. House's idle on his
  screen and pod (built 2026-11-21, not played);
- race look skins for every look race, rebuilt 2026-11-22 in
  FalloutNV.esm, Fallout3.esm and 13 add-ons (FNV's raiders played);
- FaceGen of their own for mod overrides that change a face (YUP's 22,
  faces rebuilt 2026-11-22, not played);
- distant objects in the 14 DLC and mod worlds that had none (Honest
  Hearts, Lonesome Road, Old World Blues, Bounties II and III and Russell
  rebuilt 2026-11-22, not played).

### Each area's notes

#### The world

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Mojave landscape | The Mojave's ground, roads and land textures, built from New Vegas's own world | Works | Needs the Black Landscape Fix mod, listed in the install steps; without it a Fallout 4 engine bug turns some bare ground black. Soft land seams in a few places. | [exterior](fo4_spikes.md#spike-4-exterior) |
| Distant terrain (LOD) | The far-off hills you see before you get close | Partial | Distant water (Lake Mead, the Colorado) shows as water. Tiles now hang vanilla-depth skirts over the seams between them (none left open around Goodsprings, [measured offline](fo4_terrain_lod_plan.md#p0)); not yet seen in game. | [terrain LOD](fo4_pipeline.md#terrain-lod) |
| Distant objects (LOD) | Low-detail buildings and landmarks seen from far away | Partial | Buildings work. Distant trees are built, not played. The 14 DLC and mod worlds that had none (LODGen could not find their masters' LOD meshes) now bake 299 tiles (built 2026-11-22, not played). | [object LOD](fo4_pipeline.md#object-lod-masters) |
| Pip-Boy world map | The Mojave map in the Pip-Boy, with New Vegas's markers | Partial | The Mojave and Freeside maps show, at the larger size. Markers sat below their places; fixed and built, not played. | [world map](fo4_pipeline.md#world-map) |
| Worldspaces and exteriors | The whole Mojave plus Freeside, the Strip and the other separate areas, with their doors | Partial | Trap triggers, stand-in smoke and damage stages (burning cars, their explosions) are built, not played. The skipped statics are audio markers, built as music regions. | [whole map](fo4_pipeline.md#whole-map) |
| Interiors | Buildings and dungeons with New Vegas's layout, objects, furniture and lighting | Works | | [interiors](fo4_pipeline.md#interiors) |
| Room culling | Hiding the parts of an interior you can't see, for speed | Partial | 29 interiors draw everything at once because some doorways lead to no room. | [rooms](fo4_pipeline.md#rooms) |
| Water | Water heights, plus pools, springs and puddles you can drink from | Partial | Nearby water works. Water types use the nearest Fallout 4 type, with two radiation grades instead of five. | [water](fo4_pipeline.md#placeable-water) |
| Navmesh | The paths NPCs and creatures walk | Partial | NPCs walk and follow you. No cover or island data; NPCs sometimes catch on steps. | [navmesh](fo4_pipeline.md#exterior-navmesh) |
| Weathers and climate | New Vegas's weathers, sun and sky colors, and region weather | Partial | Weathers play and night and noon brightness match. Clouds are Fallout 4's, recolored. The amber tint now rides in each weather's color grade (built, not played). | [weathers](fo4_pipeline.md#weathers) |
| Grass | Grass where New Vegas grows it, at its density | Built, not played | Fixes for the triangle at the tips and the dark flecks (the texture now clamps, as New Vegas does) and for the color (vertex tint on) are built. Swapping in Fallout 4's grass was ruled out. | [grass](fo4_look.md#grass) |
| Lights and glow | Lamps, windows, lanterns and animated signs | Built, not played | Lanterns and lamps work. Fixes for the dim OPEN and SAL signs and the Strip's night horizon glow are built. The saloon window is still far too yellow; it needs a shot from the next build. | [neon](fo4_look.md#route-neon) |
| Projector slides and shading overlays | Screens that change picture by sliding a strip (the G.O.A.T. projector), and multiply-blended shading overlays | Built, not played | The strip is cut into one shape per slide, shown in turn, since Fallout 4 drew none of a long strip; checked in the test instance and by the G.O.A.T. story cases. Multiply overlays lose New Vegas's falloff, which made Fallout 4 draw nothing (1,411 meshes). | [slides](fo4_pipeline.md#slide-strips) |
| Overall color tone | New Vegas's color grading and warmth | Built, not played | Fallout 4's tone curve and bloom with New Vegas's tint and saturation on top, at a fixed exposure that keeps New Vegas's mid-tones (decided 2026-11-09). | [FO4 route](fo4_look.md#fo4-route) |
| Modern lighting and the Classic switch | Shadow-casting main lights and Fallout 4's light types, picked by each light's New Vegas role; an optional plugin restores the classic flat look | Built, not played | Up to 6 main lights per interior cast shadows, starting 64 units out so a ceiling fixture does not shadow its own light. The Classic Look plugin is an optional app step. | [plan](fo4_look.md#route-lights) |
| Precombines and previs | Fallout 4's merged meshes and visibility data for dense areas | Not built | Researched: every precombine format is decoded, so we could write them ourselves; previs is a licensed Umbra file only the Creation Kit writes. Without either the game draws each object on its own, which costs speed only in dense places. | [research](research/fo4_precombines_previs.md#own-precombines) |
| Frame rate | Smooth play across the Mojave | Partial | Goodsprings to Primm holds the frame cap. Freeside, the Strip and Novac aren't measured. | [measured](fo4_pipeline.md#region-measured) |
| Intro movie | New Vegas's intro, with sound | Works | | [play test](bink_movies.md#play-test) |

#### NPCs

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Faces | Each NPC's face rebuilt with Fallout 4's face sliders to match New Vegas | Works | | [sculpt](fo4_spikes.md#spike-2-sculpt) |
| Hair and eyes | The closest Fallout 4 hair, beard and eyes for each NPC | Works | The match by hairstyle works. The fix for stretched long hair isn't checked. | [hair](fo4_spikes.md#hair-styles) |
| Outfits and clothing | New Vegas's clothes and armor fitted onto Fallout 4's body | Partial | 21 of 98 armors use Fallout 4 stand-in models. The wrist seam shows, loose cloth sits off the body, and cut-off limbs don't cut the clothes. | [clothing](fo4_build_next.md#human-clothing) |
| Headgear | Hats, masks and glasses on New Vegas's own models | Works | | [headgear](fo4_spikes.md#spike-4-headgear) |
| Own FaceGen heads and hair | Each NPC's face files written by the build itself instead of the Creation Kit, plus mods' own hairstyles | Built, not played | The 2026-11-13 build's faces are all ours: 2,382 heads and their face textures, none failed, so the Creation Kit fallback never ran (869 s with the work cache, against 39 minutes to 4.3 hours for the Creation Kit). Offline they match the Creation Kit's within a median 0.076 units and about 1 to 3 of 255 in color. Still the Creation Kit's: `texconv` for the face textures. Not built: mods' own hairstyles. The remaining Fallout 4 face shape is accepted drift (Willow, 2026-11-11). | [own stage](fo4_facegen_plan.md#own-stage) |
| DLC and mod faces | Face files for the NPCs the story DLC, packs and mods add | Built, not played | `build_plan` runs the faces stage for every built plugin with converted faces (all four story DLC, Gun Runners' Arsenal and 17 mods have run), and again after a master's faces change. An NPC a mod overrides takes its master's patched skin tone and sliders, matching the FaceGen the game draws (YUP 209, Goodies 21). An override that changes the face itself (YUP 22, hair length or eyes) gets FaceGen of its own under its master's name in the mod (built 2026-11-22, not played). The skin step is kept per NPC, so a rebuild redraws only changed faces. | [DLC and mods](fo4_facegen_plan.md#addon-faces), [skin cache](fo4_facegen_plan.md#skin-cache) |
| Race looks | Raider grime, tribal paint, Marked Men burns and mods' race skins, on Fallout 4's own skin and face system | Partial | Faces fade their extras out before the neck. FNV's raiders' body skin works (314 NPCs). Every other look race's skin is built, not played: Fallout 3's raiders, Honest Hearts' tribes, the Marked Men (ghoul and human) and the mods' races, 1 to 5 skins in each of 15 plugins. Outfits keep Fallout 4's clean bare skin, as vanilla raiders do. | [plan](fo4_look_races_plan.md#body) |
| Body choice (CBBE, BodySlide) | Choosing which body converted outfits fit | Partial | Only the vanilla body in the build. Researched: the cause of the scrambled bare skin with CBBE is found; a hook fits outfits to any body's mesh, and a writer makes BodySlide projects that BodySlide 5.9.1 builds without clicks. Neither is in the build yet. | [body plan](fo4_bodies_cbbe.md) |
| Super mutants and nightkin | New Vegas's mutants in their own armor | Partial | Fallout 4's mutant body and head, tinted, under New Vegas's armor. Pistols, the Multiplas rifle, shotguns, the gatling laser and the grenade launcher map to super mutant animations; the 2026-11-22 build gives each a super mutant entry (built, not played). | [super mutants](fo4_build_next.md#super-mutants) |
| Ghouls and glowing ones | Feral ghouls, and glowing ones with their aura and healing | Works | | [ghouls](fo4_creature_audit.md#ghouls) |
| Ghost People and holograms | Dead Money's enemies | Built, not played | | [Dead Money](fo4_spikes.md#dead-money-humans) |
| Daily routines | NPCs sandboxing, sitting, sleeping, eating, guarding and patrolling | Partial | 85 routines are missing, prospectors' looting among them. Most NPCs drop their routine in combat. | [packages](fo4_pipeline.md#packages) |
| Scripted routines | Routines quest scripts hand out, and patrol-point actions | Partial | Scripted routines work; patrol-point actions aren't played. | [patrol points](fo4_pipeline.md#patrol-points) |
| Standing idles | Gestures in conversations and from scripts | Works | | [standing](fo4_idles.md#standing) |
| Ambient idles | Smoking, scratching, drunk walks and other habits | Built, not played | Weapon-out idles aren't built. | [trees](fo4_idles.md#trees) |
| Seated idles | Idles while sitting, such as Doc Mitchell's | Partial | Every seated idle plays on the chair's own graph as a flavor idle, the way Fallout 4's seated idles do (FalloutNV 18, Fallout 3 8, each DLC and mod 1 to 15; built 2026-11-23). The 356-case FalloutNV stage sweep ran with them and nothing crashed; not watched in game yet. | [furniture](fo4_idles.md#furniture) |
| Idle props | The cigarette, clipboard, Doc's mirror and other held props | Built, not played | | [props](fo4_idles.md#props) |
| Idle markers | Spots where NPCs lean, sit or work | Built, not played | All 1,424 are placed. The 6 whose idles Fallout 4 has nothing like (watering flowers, singing, mourning and 3 others) are empty markers, so NPCs stand there without the gesture. | [markers](fo4_pipeline.md#audit-fixes) |
| Animated objects | Objects that play their own animation (windows, the Lucky 38 lights) | Built, not played | A script now sees an animation it started as playing until the mesh's own length runs out. One it didn't start, or started on an object held in a variable (some vertibirds, the Vault 11 gear door's linked panel), still reads as not playing. | [plan](fo4_plan_script_functions.md#phases) |

#### Creatures

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Own-rig creatures | Geckos, nightstalkers, giant mantises and cazadors on New Vegas's own skeletons and animations | Works | | [own rig](fo4_own_rig.md#mantis) |
| Own-rig creatures, the rest | Giant rats, ants, the ant queen, spore carriers, centaurs, spore plants, ravens | Built, not played | Fire ants', centaurs' and spore plants' ranged attacks work. | [remaining](fo4_own_rig.md#remaining) |
| Own-rig reactions | Reactions and moves for own-rig creatures | Partial | Crippled-limb hit reactions (nine rigs) and backward walks (seven) built, not played. No staggers, jumps, side moves or kill moves (New Vegas has no clips for them). No hit, idle or alert sounds. | [hit reactions](fo4_own_rig.md#hit-reactions) |
| Stand-in creatures | Deathclaws, dogs, mole rats, radscorpions and robots shown as their Fallout 4 counterpart, with New Vegas stats | Partial | They work. Turning off Fallout 4-only moves (burrowing, robot self-destruct, the deathclaw's roar and dirt throw) isn't played. | [race abilities](fo4_creature_audit.md#race-abilities) |
| Creature attacks | Each creature's attacks, speeds and knockdowns | Partial | See own-rig reactions. | [attacks](fo4_pipeline.md#creature-attacks) |
| Spawns | Leveled spawns, including New Vegas's chance that nothing spawns | Built, not played | | [void](fo4_creature_audit.md#void) |
| Corpse poses | Dead-at-start bodies lying as New Vegas placed them | Partial | Most humans and mutants work. Robots and about 31 others ragdoll where they lie. REPCON's dead mutants aren't played. | [poses](fo4_spikes.md#creature-poses) |
| Talking machines | Mr. House's screen and pod, Yes Man, Festus | Partial | Mr. House's screen talks and shows his face, animated (seen in the test instance). Each machine now loops New Vegas's idle on its parts: the pod's breathing, heartbeat, blinks and helmet, and the lights (built 2026-11-21, not played). Yes Man and Festus aren't played. | [machines](fo4_creature_audit.md#talking-machines), [idle](fo4_creature_audit.md#talking-machine-clips) |
| Securitrons | Victor and the Strip's securitrons | Partial | They move, talk and fire both guns. Their face screen isn't played; the Lucky 38 elevator prompt isn't confirmed. | [screens](fo4_build_next.md#screens) |
| Think Tanks | Old World Blues' scientists on their own rig | Built, not played | | [think tank](fo4_own_rig.md#think-tank) |

#### Dialogue

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Conversation menus | Talking opens New Vegas's full list of topics, through Extended Dialogue Interface | Works | | [menus](fo4_spikes.md#spike-1-design) |
| Dialogue lines | All of New Vegas's NPC lines, with the conditions that decide when each shows | Partial | 83 lines are left out by a condition (2026-11-12 build); about 50 are dead in New Vegas too (actors it never places). Race, class and empty-actor tests are fixed, not yet built. Still out: GetDisposition (14), lines counting items the build does not make, the player's own grunts (Fallout 4 voices its own). | [census](fo4_dialogue_gaps.md#census) |
| Choices with shared answers | Menu options whose reply New Vegas shares between topics | Partial | 18 choices have no line (2026-11-12 build); 9 belong to actors New Vegas never places, 2 are fixed (built, not played), 5 wait on items the build does not make. | [census](fo4_dialogue_gaps.md#census) |
| Say Once topics | A topic disappears once heard | Works | | [say once](fo4_pipeline.md#say-once) |
| Skill checks | `[Speech 50]`-style options that pass or fail on your skill | Works | | [speech tag](fo4_build_next.md#speech-tag) |
| NPC voices | Every NPC speaks their own New Vegas recordings | Works | | [voice types](fo4_pipeline.md#voice-types) |
| Silent player | The player has no voice, as in New Vegas | Built, not played | | [voice](fo4_spikes.md#spike-1-voice) |
| Lip sync | Mouths move with New Vegas's own lip data | Built, not played | | [lips](research/lip_format.md#built) |
| Greetings | The line an NPC says when you start talking | Built, not played | Greetings play; the special first-meeting lines aren't checked. | [first meeting](fo4_pipeline.md#talked-to-pc) |
| Force greets | NPCs who walk up and start talking (Ringo, the Primm trooper) | Partial | Ringo and the Primm trooper work; the rest is untested. | [greet trigger](fo4_pipeline.md#greet-trigger) |
| Talking next to a fight | New Vegas and Fallout 3 stop the world while you talk; Fallout 4 doesn't, so an attacker keeps hitting you mid-conversation | Built, not played | The world pauses while the choices wait, through the game's own pause for an open menu. NPC lines still play on game time. | [built](fo4_talk_in_combat_plan.md#built) |
| Barks | One-off lines shouted in combat or as you pass | Partial | Built, not listened for. The player's own barks are left out. | [barks](fo4_pipeline.md#barks) |
| Companion barks | Companions remarking on low health, waking up or no ammo | Partial | 77 lines built, not heard. 91 others depend on things Fallout 4 doesn't track. | [companion barks](fo4_pipeline.md#companion-barks) |
| Ambient chats | Two NPCs talking to each other | Built, not played | | [chats](fo4_pipeline.md#actor-dialogue) |
| Scenes | Scripted conversations between several people | Partial | Basic scenes work. Looping and branching scenes, and Cato's and Benny's talks, are untested. | [scenes](fo4_pipeline.md#scene-loops) |
| Talking activators | Intercoms, loudspeakers and recordings | Built, not played | The REPCON intercom works. | [talkers](fo4_pipeline.md#talker-says) |

#### Quests and scripts

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| New game | The intro movie, waking at Doc Mitchell's, name, face, S.P.E.C.I.A.L., the word test and tag skills | Works | Two fixes built, not played: Doc's long pause before the psych test (sitting down now counts as at the chair), and Sunny, Victor and the light outside Doc's house running late (a goodbye line now ends the talk Fallout 4 kept up for about 15 s, which held back quest starts). | [seated](fo4_pipeline.md#furniture-seated), [goodbye](fo4_pipeline.md#goodbye-ends-talk) |
| Quests | New Vegas's quests, objectives and stage scripts | Partial | Played from Goodsprings to Primm; the rest is untested. | [preflight](fo4_preflight.md#results-2026-11-07) |
| Script converter | New Vegas's scripts rewritten as Fallout 4 scripts | Partial | Every script compiles. About 1,276 calls the converter can't translate do nothing. | [scripts](fo4_spikes.md#spike-3-gate) |
| Unconverted functions | Script commands with no Fallout 4 equivalent | Partial | Combat-style changes, package timers, renaming, inventory resets and music cues do nothing. | [not built](script_markers.md#not-built) |
| Script condition reads | Checks such as "has the NPC talked to you" or "is the DLC installed" | Built, not played | | [reads](script_markers.md#native-read-follow-ups) |
| Triggers | Invisible boxes that start events when you walk in | Built, not played | Ringo's trigger fires. Arriving through a door straight into a box (156 places) is untested. | [trace](fo4_pipeline.md#trace) |
| Region tests | Scripts and lines that check which part of the Mojave you are in | Built, not played | | [regions](fo4_regions.md#built) |
| Companions | Hiring Cass, Boone and the others | Partial | Fallout 4's follower system, with no companion wheel. Hiring, trading and gear return are untested. "Let's get going." shows only after "Wait here.", as in New Vegas. | [drift](fo4_drift.md#candidates) |
| Terminals | Computers with menus, notes and switches | Works | | [terminals](fo4_pipeline.md#terminals) |
| Locks and hacking | Fallout 4's minigames, gated by New Vegas's Lockpick and Science | Built, not played | Password notes open terminals directly. | [locks](fo4_pipeline.md#lock-script) |
| Message boxes | Pop-up choices (repairing an elevator, Doc's sex choice) | Works | | [buttons](fo4_pipeline.md#message-buttons) |

#### Radio

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Radio New Vegas, Mojave Music Radio | Pip-Boy stations with Mr. New Vegas, news and songs | Works | | [radio](fo4_radio.md#steps-model) |
| Black Mountain, lounge stations | Rhonda and Tabitha's station and casino lounge music | Built, not played | Black Mountain's scripted event lines aren't built. | [radio](fo4_radio.md#steps-model) |
| Placed radios | Radios in the world you can turn on | Works | | [receivers](fo4_radio.md#receivers) |
| Broadcasts scripts start | The Tops stage acts, Hanlon's broadcast, Dead Money's radios | Built, not played | Lily's recording has no radio to play through. | [start radio](fo4_radio.md#start-radio-conversation) |

#### The character

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| S.P.E.C.I.A.L. | Setting your seven stats with the Vit-o-matic | Works | | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Tag skills | Doc's questionnaire suggests three skills to tag | Built, not played | "Works" was the old LevelUpMenuEx menu; tags now open Cleanroom UI's CRUI_LevelUp in its tags mode (built 2026-11-12), never played | [special](fo4_opening_progression_plan.md#special-built) |
| Skills | New Vegas's 13 skills, shown in the Pip-Boy | Works | | [tabs](fo4_pipboy_tabs.md#how) |
| XP and level-ups | Earning XP and picking perks and skill points | Works | Skill points and perk picks both work in LevelUpMenuEx. Our own level-up menu now opens in its place (requirements shown, points kept for later, every DLC's perks listed), and is the tag-skill and trait menu too; perks per level, skill points, the skill cap, a show-all filter and a hotkey are set in MCM; other mods can open its menus, add perks and hear its events; LevelUpMenuEx is no longer required; built, not played. | [level-up](fo4_perks.md#hasperk), [our menu](fo4_level_up_plan.md#menu) |
| Perks | New Vegas's 176 perks and ranks | Partial | Not played. 29 effects have no Fallout 4 equivalent (attack and equip speed, unarmed specials, Miss Fortune, Long Haul, some DT perks). | [census](fo4_perks.md#census) |
| Traits | Optional traits with an upside and a downside | Partial | Picking works; effects aren't played. | [drift](fo4_drift.md#recorded) |
| Companion perks | Perks your companions give you | Built, not played | | [teammate perks](fo4_perks.md#teammate-perks) |
| Skill books | Reading one raises a skill and uses up the book | Built, not played | The Comprehension perk's extra point is missing. | [books](fo4_pipeline.md#skill-books) |
| Skill magazines | Reading one gives a short skill boost | Works | Picking one up in the world shows it as if being read, which does nothing; the boost comes from using it. | [consumables](fo4_pipeline.md#consumable-effects) |
| Intense Training | A perk that raises one stat by 1 | Built, not played | 1108d's missing box: the box now waits until the Pip-Boy has closed. | [intense training](fo4_pipeline.md#intense-training) |
| Karma | Good and evil standing | Partial | The tab and kill karma work; theft karma is untested. | [standings](fo4_pipeline.md#standings) |
| Reputation | Fame and infamy with each faction, and their titles | Built, not played | The title-change box has no text. | [reputation](fo4_pipeline.md#reputation-messages) |
| Challenges | New Vegas's challenges and their rewards | Partial | 67 of 105 are counted. The casino and Caravan game challenges count each round and Caravan game (built 2026-11-23, not played); damage, body-part and cripple challenges are missing. | [left out](fo4_pipeline.md#challenges-left-out) |
| Hardcore mode | Thirst, hunger, sleep, ammo weight, slow healing | Built, not played | Missing: companions dying only in Hardcore, the ending's reward, a settings-menu switch (an aid item turns it on). | [Hardcore](fo4_hardcore.md#built) |
| Chem addiction | Getting hooked and going through withdrawal | Partial | Withdrawal effects are Fallout 4's; some chems never addict. | [addiction](fo4_pipeline.md#chem-addiction) |
| Fatigue and knockouts | Being knocked out by gas, boxing or cattle prods | Built, not played | | [fatigue](fo4_pipeline.md#fatigue) |
| Disguises | Faction armor that lets you pass as NCR, Legion and others | Built, not played | | [disguises](fo4_pipeline.md#disguises) |
| Sex change | Choosing or changing your character's sex | Works | | [sex change](fo4_pipeline.md#sex-change) |
| Pip-Boy SKILLS, REPUTATION, KARMA | New Vegas's STATS pages in the Pip-Boy | Works | | [tabs](fo4_pipboy_tabs.md#how) |
| Pip-Boy CHALLENGES | Challenge progress in the Pip-Boy | Works | It shows a number, not "3/10". | [data](fo4_pipboy_tabs.md#data) |

#### Combat

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Guns and their animations | New Vegas guns with their first-person animations | Partial | Third-person animations are Fallout 4's. The left hand briefly leaves rifles when aiming. | [guns](fo4_gun_animation.md#order) |
| Ammo types | Switching ammo (hollow point, armor piercing) on a hotkey | Works | A Favorites-wheel item. NPCs always fire a gun's first ammo. | [ammo](fo4_pipeline.md#ammo-switch) |
| Weapon mods | Scopes, extended magazines and other attachments | Partial | Fitted at the workbench, not played. 9 mods do nothing. | [mods](fo4_pipeline.md#weapon-mods) |
| Scopes | Built-in scopes at New Vegas's zoom | Works | Checked on some guns so far. | [zoom](fo4_build_next.md#scope-zoom) |
| Condition and repair | Gear wears out and is repaired with kits or spare copies | Works | | [condition](fo4_condition.md#built) |
| Vendor repair | Paying a merchant to repair gear | Built, not played | | [vendor](fo4_condition.md#vendor-repair) |
| Weapon jams | Worn guns can jam on reload | Works | | [jams](fo4_condition.md#jams) |
| Critical hits | Per-weapon random critical chance and damage | Works | New Vegas's roll on every hit, in and out of V.A.T.S. Fallout 4's V.A.T.S. critical meter also stays. | [criticals](fo4_pipeline.md#random-criticals) |
| Damage Threshold | Armor ignores a flat amount of each hit | Built, not played | Per-pellet DT and 6 armors' DR built 2026-11-08 (the 3 FO3-format armors keep DR as rating); defender DT perks and ammo DR not converted. | [DT](fo4_pipeline.md#damage-threshold) |
| Sneak attacks | Extra damage when attacking unseen | Works | | [sneak](fo4_pipeline.md#sneak-attacks) |
| Weapon poisons | Coating a melee weapon with poison | Built, not played | Applies to your next melee hit, not to one weapon. | [poisons](fo4_pipeline.md#weapon-poisons) |
| V.A.T.S. and combat feel | New Vegas's aim, health, run speed and V.A.T.S. damage | Works | V.A.T.S. slows time instead of pausing. Sprint stays. | [feel](fo4_combat_feel.md#built) |
| Thrown weapons and explosives | Grenades, mines, C4, dynamite, throwing spears | Works | | [thrown](fo4_thrown_weapons.md#built) |
| Melee and unarmed | Bats, knives and fists | Partial | Animations are Fallout 4's; unarmed special moves are missing. | [melee](fo4_spikes.md#spike-4-melee) |
| Projectiles | Bullets, lasers and explosions at New Vegas's range, speed and damage | Built, not played | Looks and sounds are Fallout 4 stand-ins. | [projectiles](fo4_pipeline.md#projectile-copies) |
| Combat styles | How each kind of NPC fights | Built, not played | Rushing and fleeing are dropped: Fallout 4's styles have no field for them. | [styles](fo4_pipeline.md#combat-styles) |
| No combat sprinting | NPCs don't sprint at you, as in New Vegas | Works | Applies to Fallout 4's own NPCs too. | [sprint](fo4_pipeline.md#combat-sprint) |
| Allies join a fight | When a script turns an NPC on you, his allies and friends join in, as New Vegas's combat groups do | Built, not played | Fallout 4 left them standing (the Vegas Boulevard monorail troopers). Covers 738 scripted attacks on the player in 347 scripts. | [allies](fo4_pipeline.md#allies-join) |

#### Items

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Consumables | Food, drinks, chems and their effects | Partial | Basic effects work. Script-driven ones (Cateye, Steady, Stealth Boy and others) aren't played; Rebound and a few others are dropped. | [consumables](fo4_pipeline.md#consumable-effects) |
| Crafting | Recipes at workbenches, campfires and the reloading bench | Partial | The reloading bench put the player on the wrong side at Primm and Goodsprings; each open side is now its own bench (built, not played). Dead Money's vending machines and DLC recipes with quest or item conditions aren't built. Planned: New Vegas's own recipe menu, opened where you stand, with skill requirements and quantity. | [stations](fo4_pipeline.md#station-entry), [plan](fo4_crafting_plan.md#recommendation) |
| Caps | The Mojave's currency | Works | | [items](fo4_casino_plan.md#items-built) |
| Other money and cards | NCR dollars, Legion coins, casino chips, Caravan cards | Built, not played | Items only, until the casino games are built. | [items](fo4_casino_plan.md#items-built) |
| Item models | New Vegas's own models for items | Partial | Many aid items (the Stimpak among them) and some armor show Fallout 4's. | [drift](fo4_drift.md#recorded) |

#### Casino games

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Slots | The Strip's and the Sierra Madre's slot machines, on our own 2D menu | Works | Spins pay out and take chips. Luck, comps levels, the floor managers' dialogue and the Sierra Madre's machines aren't checked. Spins don't count toward the challenge yet. | [slots](fo4_casino_plan.md#slots-built) |
| Roulette | The Strip's and the Sierra Madre's roulette tables, on our own 2D menu | Works | Click a spot to bet, click it again to take the chips off. Pays as New Vegas does, its 0 and 00 quirks included. No spin animation or sounds; no gamepad cursor over the board. Spins don't count toward the challenge yet. | [roulette](fo4_casino_plan.md#roulette-built) |
| Blackjack | The Strip's and the Sierra Madre's blackjack tables, on our own 2D menu | Works | Plays as New Vegas does, from each casino's decks, payout and soft-17 rule, its quirks included (kings split; a split 21 pays both hands as naturals). Luck above 10 helps no more than 10. No felt texture, dealing animation or sounds; no gamepad cursor. Rounds don't count toward the challenge yet. | [blackjack](fo4_casino_plan.md#blackjack-built) |
| Casino menu test | A console test screen for the new menu (`cqf FNV_Casino Spike`) | Works | Keys, mouse, text and images work in a menu of our own, drawn in your HUD color (white without F3NV.dll). Level-up images (DXT3, DXT5) beside the card are built, not played. | [spike](fo4_casino_plan.md#toolchain-found) |
| Caravan | New Vegas's card game, on our own 2D menu | Built, not played | Bet with caps and NCR or Legion money, build a deck from your collection, play the opponent's deck against New Vegas's own AI; FNV's rules and quirks kept. The opening ends once all six caravans have a card (New Vegas could get stuck there). Raise goes up in steps. No tutorial, animation or sounds; no gamepad cursor. Games don't count toward the challenges yet. | [caravan](fo4_casino_plan.md#caravan-built) |
| Lucky Horseshoes | Festus's card game at Sunset Sarsaparilla, on the blackjack table's layout | Built, not played | Say "Lucky Horseshoes" to Festus: the talk ends and the menu opens. New Vegas's rules from its dialogue (aces to tens, nearest 21 wins once the other holds or goes over, ties push the other up one, Festus holds when leading within 4). No bet; a win gives New Vegas's reward (a star cap, a Caravan card or a few caps). Cards are drawn plain; no sounds or Festus voice lines in the menu. | [Lucky Horseshoes](fo4_casino_plan.md#lucky-horseshoes) |

#### DLC and add-on packs

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Story DLC | Dead Money, Honest Hearts, Old World Blues, Lonesome Road | Built, not played | The Sierra Madre's blackjack, roulette and slots open the same menus as the Strip's (its casino data, comps quest and chip are in the build), not played; its vending machines' chips aren't played. Their own NPCs have our own FaceGen (see DLC and mod faces). When two DLC change the same thing, the last one loaded wins. Every DLC, pack and mod now rebuilds in its own MO2 folder through `build_plan`, only when something it read changed. | [DLC](fo4_plugin_layout.md#dlc-build), [build plan](fo4_plugin_layout.md#build-plan) |
| Gun Runners' Arsenal and courier packs | The weapon and gear packs | Built, not played | | [packs](fo4_plugin_layout.md#courier-packs) |

#### The app and installing

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Conversion app | Converts your New Vegas install for Fallout 4 | Partial | Setup, Convert and Replacements screens are built, not tested end to end. DLC and mod folders convert from the app too ([DLC and mods](fo4_gui.md#addons)); the Finished screen checks the install, sets the output up in Mod Organizer and plays ([buttons](fo4_gui.md#mo2-setup)), and the F4SE plugin and faces are stages. Faces are our own FaceGen, as the chain's; Rebuild what changed runs the chain's build plan (replay, then the mods built on the target) ([rebuild](fo4_gui.md#rebuild)). None of this run from the app yet. | [phases](fo4_gui.md#phases) |
| Installing | The README's steps for testers | Built, not played | Never followed end to end on a clean machine. | [install](../../README.md#install) |
| Replacements | Swapping converted items or creatures for Fallout 4's or other mods' versions | Partial | The table and its screen work, empty by default. Named profiles and a Wabbajack modlist aren't built. | [replacements](fo4_replacements.md#direction) |
| Fallout 3 | Converting Fallout 3 the same way | Partial | A scoped spike: Vault 101 and the opening (born in `CG00`) through the vault door, built into its own MO2 profile (last 2026-11-21), with crime ignored during character creation and projectiles for its guns. The story runs play the opening strict on the test machine: the G.O.A.T. cases pass; the walk to the vault door in CG04 still sticks on its path. The stage sweep went from 267 to 56 failed checks over five runs, and what is left is waits the sweep cannot meet ([triage](fo4_test_layers_plan.md#unmet-waits)). 6 of its 4,721 scripts don't compile, none of the opening's ([build](fo4_fo3_plan.md#build)). The whole Capital Wasteland and all five DLC (Operation: Anchorage, The Pitt, Broken Steel, Point Lookout, Mothership Zeta) build from the command line (2026-11-23, each in its own `F3NV - <name>` mod), not played past the opening and not in the app yet. Tale of Two Wastelands judged, not built. The child player is planned: scale at age 1 (converted), a child race of our own at 10 and in Tranquility Lane, whose in-game check (`F3NV_ChildRaceTest.esl`) is built, not played. | [FO3 spike](fo4_fo3_plan.md), [child player](fo4_fo3_child_player.md), [scenes on FO4's engine](fo4_scene_driving_plan.md) |

### Planned work, in full

- **Play-testing** everything marked "Built, not played", and fixing what
  turns up.
- **Unattended play-test runs:** a harness that starts the game under its
  own MO2 profile and visits every cell, quest stage, NPC line and item by
  itself, reporting crashes, Papyrus errors and stuck quests into the
  preflight ([plan](fo4_autoplay.md#order)). The stage sweep (every quest
  stage set from a start save, its waits and errors checked) is built and
  has run five times on Fallout 3 ([layer 1](fo4_test_layers_plan.md#l1-built)).
- **Story runs:** the openings played by themselves in a hidden, muted copy
  of the game, as upstream does for Morrowind and Oblivion: each line heard
  checked by its source INFO, each stage waited for. Built: the hidden test
  instance, story cases played as a player does (aimed activates, talks,
  walks), and runs on a separate test machine; the Fallout 3 opening's
  cases run strict. Next: recording the actors' facing, idles and seating,
  then diffing against a recording of the source game itself
  ([plan](fo4_story_tests.md#order), [test machine](fo4_story_tests.md#laptop)).
- **Regression checks:** compare each build with the last one the user
  played and called good (records, scripts, meshes, faces, voice), keep each
  fixed bug as a small test, and bisect a break to its commit with scoped
  rebuilds; planned ([plan](fo4_regression.md#order)).
- **Casino games and Caravan:** all built; Caravan not yet played
  ([plan](fo4_casino_plan.md)).
- **Our own FaceGen as the default:** play the DLC and mod faces, then drop
  the Creation Kit fallback ([own stage](fo4_facegen_plan.md#own-stage)).
- **Crafting on our own menu:** New Vegas's recipe menu with skill
  requirements and quantity ([plan](fo4_crafting_plan.md#recommendation)).
- **Fallout 3's child player:** play the child-race test, then build the age
  10 and Tranquility Lane race ([plan](fo4_fo3_child_player.md#spike-test)).
- **Fixes for the known bugs** above, in the order of the
  [issue plan](fo4_issue_plan.md): play tests first, then by size.
- **Gun animation:** New Vegas's third-person clips and grip
  ([plan](fo4_gun_animation.md#order)).
- **Creatures:** play the own rigs' crippled-limb reactions and backward
  walks; then staggers and sounds ([own rig](fo4_own_rig.md#hit-reactions)).
- **Body choice:** CBBE and BodySlide bodies for converted outfits
  ([plan](fo4_bodies_cbbe.md)).
- **Race looks:** play the look races beyond FNV's raiders; optionally,
  test LooksMenu overlays for race looks on outfits' bare skin
  ([plan](fo4_look_races_plan.md#order)).
- **The look:** grass color, Strip neon, the night horizon glow, New Vegas's
  color tone, distant trees and water ([plan](fo4_look.md)).
- **Terrain LOD of our own:** skirts first to close the gaps between
  distant tiles, then tiles built from the land with matching edges and
  more detail than vanilla ([plan](fo4_terrain_lod_plan.md)).
- **Precombines** for Freeside and the Strip, written by our own code
  (previs stays the Creation Kit's) ([research](research/fo4_precombines_previs.md#own-precombines)).
- **Script speed:** the remaining Papyrus cost fixes
  ([performance](performance.md#papyrus)).
- **The app:** Mod Organizer setup, Play, and the DLC, DLL, movie and face
  steps ([phases](fo4_gui.md#phases)).
- **Build checks:** the dialogue menu audit and the rest of the timing audit
  ([menu](fo4_menu_audit.md), [timing](fo4_timing_audit.md)).
- **Mod builds:** about 20 New Vegas mods (YUP, NVMIM, Willow, the New Vegas
  Bounties series, JSawyer Ultimate and others) convert against the built game
  and rebuild through `build_plan` in their own MO2 folders; played only in
  Doc Mitchell's house so far ([plan](fo4_mod_builds.md)). Overlay plugins (NVTUP and NVMIM) rebuild
  through it too. The first play with the whole mod list (2026-11-14), from
  Doc Mitchell's house, found three bugs, all fixed: a crash as Doc walked
  past NVMIM's end table (see the collision note in Parked), JSawyer
  Ultimate's "Loaded" message repeating (its scripts now find the
  references their masters own), and a mod that built before its masters
  in one run. Its Papyrus log shows the mod bugs under Known bugs.
- **Load order:** converted mods in the user's FNV order, a conflict report,
  a merged patch and LOOT rules ([plan](fo4_load_order.md)).
- **Build time:** with warm caches the game builds in about 9 minutes and
  its faces in about 15. Converted voice lines, finished meshes, face fits,
  faces and the land texture step are cached; a build that writes the same
  archive bytes leaves the archive alone; mod builds reuse their masters'
  finished meshes. A Low/Balanced/Full setting limits cores and memory, and
  the build prints an estimated time ([resources](fo4_build_resources.md)).
  Named stages can be profiled (`F3NV_PROFILE_STAGES`). Each build records
  what every part (archives, meshes, scripts) ran and read, so a change to
  only that part's code replays it instead of rebuilding the plugin
  ([replay](fo4_plugin_layout.md#replay)), and a mod rebuilds only its
  changed cells. Idle, pose and gun clips, guns, worn creature bodies and
  the animation data are kept between builds too
  ([guns](fo4_build_speed.md#gun-cache), [creatures](fo4_build_speed.md#creature-bodies),
  [clips](fo4_idles.md#clip-cache), [animation data](research/anim_text_data.md#skip)),
  and the main archive knows our own written files without reading them
  ([touched](fo4_pipeline.md#touched)). On the 2026-11-15 build, still
  filling those caches, the mods built 12% faster than the build before. The
  goal is a small fix to a play test in 10 to 20 minutes. Still to come:
  moving the hot spots to native code ([plan](fo4_build_speed.md)).
- **Build safety:** a build chain that checks the setup first, watches every
  step for stalls, reruns faces after any base rebuild, stops on a hidden
  link between plugins and resumes where it stopped
  (`tools.release.fo4_chain`). A Creation Kit that writes nothing in 30
  minutes is closed, and `build_plan` stops instead of rebuilding a plugin
  twice, unless one of its masters built after it
  ([build plan](fo4_plugin_layout.md#build-plan)). `F3NV.dll` keeps each
  play test's logs, tagged with the build they ran on
  ([run archive](fo4_condition.md#run-archive)).
- **Differences from New Vegas** that could be closed later: attack and equip
  speed perks, looting routines, per-pellet DT, Long Haul and Miss Fortune
  ([drift](fo4_drift.md)).
- **Fallout 3:** finish the opening's story runs (the CG04 walk to the vault
  door) and play it, then the whole Capital Wasteland, then Mart's Mutant
  Mod ([FO3 spike](fo4_fo3_plan.md#next)).
- **Idles from every authored place:** own idle markers, held idles on
  FO4's loop event so its graph releases them, and seated idles (the
  G.O.A.T. students) on furniture subgraphs. Package event idles (FO3's
  birth scene) and standing package idle lists (the Overseer's waits) are
  built, not played ([review](fo4_idle_review.md#plan)).

### Parked, in full

| Item | Why |
|---|---|
| A choice between New Vegas and Fallout 4 combat | An idea, not planned |
| Other languages' movie tracks | Only English is checked ([Bink](bink_movies.md)) |
| [Graphics research](research/graphics_options.md) | Notes to revisit later |
| [Spin-off mods](spin_offs.md) from F3NV.dll (framework, content mods, dynamic collision) | Split into Cleanroom UI (`ThyMrMan/cleanroom-ui`); the converter moves onto it in [six steps](spin_offs.md#move), steps 1 to 3 (the dialogue menu; the level-up and `CleanroomUI.esl`; the framework DLL and Pip-Boy movie, F3NV.dll cut to FNV's rules) built 2026-11-13, not played. [Strategy](spin_offs.md#strategy): open, drop-in replacements for XDI, then HUDFramework; waiting on the author's reply about licenses |
| [f3ui as a menu library](spin_offs.md) (our AS3 menu toolkit for other mods, no DLL) | Every planned class is built; the release is not started |
| [Our level-up menu as its own mod](spin_offs.md#level-up) (LevelUpMenuEx replacement, with an API for other mods) | Built for the conversion and no longer needs LevelUpMenuEx, not played; reading LevelUpMenuEx's INI lists and perk tables for any load order not started |
| [Casino games and Caravan as a content mod](spin_offs.md#casino) | Idea; all four games are built for the conversion |
| [Modder tools from the replaced CK steps](spin_offs.md#tools) (dark-face fixer, AnimTextData, lips, archive check, collision, Caprica fixes) | Ideas only ([picks](fo4_after_ck_ideas.md#picks)) |
| [Write-ups for the community](spin_offs.md#write-ups) (first: how the CK bakes faces) | Findings written in our docs; no public page yet |
| [Dialogue menu as its own mod](dialogue_menu_mod.md) (XDI replacement) | Phase 1 done (our own movie, played); phase 2 partly (the list on `mxmlc` with a hint bar and gamepad input through f3ui, not played); the standalone DLL is Cleanroom UI's `CleanroomDialogue.dll`, which the converter ships since 2026-11-13 (not played); later phases not started |
| [Our own Flash menu framework](swf_framework.md) (dialogue, casino, Pip-Boy) | **Played:** spikes 1-5: the casino on `mxmlc` and `f3ui`, the HUD color in our own menu, the dialogue menu on its own movie, our movie in the vanilla Pip-Boy, translation files. **Built, not played:** the Pip-Boy framework (CND line, repair and ammo lists, F3NV_ItemCard.SetLine), FallUI support, the dialogue menu on `mxmlc`, our words as `$F3NV_` keys with English under every language, the level-up images and their spike, PRKF.dll's state in Papyrus (Cleanroom UI's CRUI_LevelUp, older saves' F3NV_LevelUp state moved over once), our own level-up menu (skills, perks, taken) opened from Papyrus in place of LevelUpMenu, Input and HintBar with the casino and dialogue menu moved onto them (keys, controls and hints the same on keyboard and gamepad), ScrollList and Modal with the dialogue list and the Pip-Boy's repair and ammo lists moved onto them, Images (texture paths, a missing file caught by F3NV.dll's new TextureExists) with the casino on it: every planned library class is built. **Not started:** gamepad play, the level-up menu's traits and tags, the HUD widget, the container and barter on a movie, the release. Piece by piece: [where each piece stands](swf_framework.md#where); order: [next](swf_framework.md#next) |
| [Dynamic collision](dynamic_collision_mod.md) (smaller collision when crouching, like Skyrim's DCA) | Planned. Second shape slot read (free for us); next: the vanilla sneak test and a repo with a plugin that loads ([build-out](dynamic_collision_mod.md#build-out)) |
| [The build without the Creation Kit](fo4_ck_replacements.md) (own BA2, Caprica only, AnimTextData, FaceGen, collision) | In progress. Built: our own texture BA2 writer, loudness lips, and AnimTextData (in every build since 2026-11-12; the first run filled its cache). Every New Vegas script compiles in our patched Caprica. Our own collision writer runs ahead of Elric for convex shapes, triangle meshes on still or keyframed bodies, spheres, capsules and list shapes; ragdoll joints and flat shapes still go to Elric. First played 2026-11-14: a triangle naming one corner twice crashed the game (the game reads it as another kind of shape), and mesh sections now number their triangles as Elric does; both fixed, every build rebuilt. Our own FaceGen made every face of the 2026-11-13 build with no Creation Kit run (see Own FaceGen heads above); it is still behind `--own-facegen`, with the Creation Kit as fallback. Precombines researched: ours look doable, previs stays the Creation Kit's |
| [Ideas the build without the CK makes possible](fo4_after_ck_ideas.md) (a dark-face fixer for any load order, rebuilding only what changed, a face comparison gallery, Caprica fixes upstream, an archive check, AnimTextData for any mod, and ideas for every replaced step) | Ideas only, nothing built |
| [Appearance comparison](appearance_compare_tool.md) (two load orders' NPCs side by side, such as two character replacers, plus a dark-face check) | Plan only, no code |

## <a id="fo4-state"></a>Fallout 4: current state (2026-11-08)

What is broken, missing, partial, and built but never played, across the
fork's docs and the build's own counts. Counts are the base game's from the
2026-11-05 whole-map build (`temp/build_1105i.log`) unless a row says
otherwise. Each row links where the detail lives; fix the row here when the
item moves.

<a id="alpha"></a>**Alpha (2026-11-08).** FNV is playable on Fallout 4 from
Doc Mitchell's house onward, with its DLC and packs, and nearly every system
is built. What is left is mostly play-testing the "built, never played" list
below, and the casino games and Caravan, which are being built. FO3 is not
started. The install steps for testers are in the
[README](../../README.md#install).

**Builds.** Deployed 2026-11-07 as build 1107i (`temp/build_1107i.log`):
`FalloutNV.esm` (whole map), `FalloutHelpers.esl` and `F3NV.dll`, every
script compiling. It holds everything built through 2026-11-07: the
2026-11-06 items (Fallout4.esm names as text, sound properties, creature-type
and DLC script reads, cards, money and chips, brahmin and mole rat poses,
withdrawal cures, thrown weapons, FO3/FNV's own lip files, region tests),
Hardcore mode, the void-chance spawns ([void](fo4_creature_audit.md#void)),
ant workers fighting back and the Pip-Boy map border
([world map](fo4_pipeline.md#world-map)). The nine DLC and pack plugins were
last deployed 2026-11-05, and rebuilt on 1107i on 2026-11-08.

### <a id="fo4-broken"></a>Broken: known bugs not fixed

| Area | Bug | Where |
|---|---|---|
| Triggers | A player who arrives by door inside a scripted trigger box may never get `OnTriggerEnter` (Ringo's gas-station trigger never fired; 156 FNV door arrivals land in a scripted box) | [trace](fo4_pipeline.md#trace) |
| Script guards | Every dropped read of the census converts since 2026-11-06, not played: region tests, GetCurrentAIProcedure, GetTalkedToPC, IsLimbGone, and last GetIsCreatureType and IsDLCInstalled | [native reads](script_markers.md#native-read-follow-ups), [creature type](script_markers.md#creature-type), [AI procedure](fo4_pipeline.md#ai-procedure) |
| Animated objects | Scripts that play or wait on a NIF sequence do nothing: `IsAnimPlaying` always reads 0 (69 checks in 34 scripts; window and Lucky 38 light scripts) | [log noise](fo4_pipeline.md#log-noise), [idles](fo4_idles.md#census) |
| Saves | Saves that heard a Say Once line under the first build keep its huge marker stage, and a heard line can show once more | [say once](fo4_pipeline.md#say-once) |
| Radio | Saves from before the Host fix have Radio New Vegas off | [radio](fo4_radio.md#programming) |
| Corpses | REPCON's dead-at-start super mutants T-pose | [super mutants](fo4_build_next.md#super-mutants) |
| Movement | Novac motel stairs' stuck spot; NPCs catching on steps (Vikki and Vance, 2 of 6) | [stair pitch](fo4_pipeline.md#stair-helper-pitch), [parked](fo4_pipeline.md#parked) |
| Guns | The left hand leaves the rifle for a moment going into aim. Placed guns lying wrong (the .22 on its grip): turned back as their mesh since 2026-11-06, not played | [parked](#parked), [placed guns](fo4_spikes.md#placed-guns) |
| Landscape | Black hill triangles (FO4 engine bug; the Black Landscape Fix mod); 67 land seam vertices with no common texture; LOD holes that close up as the player nears (reported 2026-11-06) | [exterior](fo4_spikes.md#spike-4-exterior), [parked](#parked) |
| Scripts | 76 casino property lines stay empty; script properties of Topics whose quest is not built (86) stay empty. Sound properties filled since 2026-11-06 ([sound properties](fo4_pipeline.md#sound-properties)) | [casino](fo4_casino_plan.md#today), [preflight](fo4_preflight.md#results) |
| Quests | Preflight errors not acted on: VCG00 (14), Poindexter's scene; CG00, CG02, VT74 reached but not built | [preflight](fo4_preflight.md#results) |

### <a id="fo4-missing"></a>Missing or partial: not converted, or only some of it

| Area | What | Where |
|---|---|---|
| Casino and Caravan | **Being built from 2026-11-08** (the plan's phases in order). Before that, nothing built: blackjack, roulette, slots, Caravan; no casino, chip, money, card or deck records (Dead Money's 621 chips and 21 card records skipped; 56 of its 77 vending recipes lack the Sierra Madre chip); comps (`GetCasinoWinningsLevel` reads 0); 41 script calls left as markers | [casino plan](fo4_casino_plan.md) |
| Region tests | **Built 2026-11-06, deployed 2026-11-07, not played:** FNV's polygons tested by a watch quest per plugin, one global per tested region (41), read by conditions and converted scripts ([as built](fo4_regions.md#built)) | [regions](fo4_regions.md) |
| Script functions | 1,276 of 2,156 `;NE:` markers left (SetCombatStyle, SetPackDuration, GetCurrentAIProcedure, SetActorFullName, ResetInventory: 117 sites; StartRadioConversation, PlayMusic) | [script markers](script_markers.md#not-built) |
| Dialogue | 378 lines left out in the 2026-11-05 build, about 354 after the 2026-11-06 fixes. The 163 on a GetIsID never true are of actors FNV never places (DoctorBarrows, the Forlorn Hope injured troopers, RL3Follower, V22Bohr); 49 GetItemCount, 37 GetCasinoWinningStage; GetIsClass (no CLAS records); 236 menu choices with no line, among them the follower choices (Fired yes/no, Let's go, Keep close) in other quests' copies of `VNPCFollowers` menus (cause not found); 62 Choice topics unanswered; 91 companion status barks with no state FO4 tracks; the player's barks (GenericPlayer, grenade and mine barks); Lily's child-race tests, GetDisposition. Not yet built (2026-11-07): `TES4Talk_` scenes a later quest's script names (16, Cato's morning talk; [talk order](fo4_pipeline.md#talk-order)) and scripted furniture (16, Nero's couch adds Big Sal's force greet; [furniture scripts](fo4_pipeline.md#furniture-scripts)) and talking activators saying their own topics (Vault 11's chamber, Curtis's radio, the monorail recording; [talker says](fo4_pipeline.md#talker-says)) | [dialogue conditions](fo4_pipeline.md#dialogue-conditions), [bark replies](fo4_pipeline.md#bark-replies), [barks](fo4_pipeline.md#barks) |
| AI packages | 85 left out (30 Find: looting has no FO4 procedure); Continue During Combat kept only on Guards; actors carry no enable parent (647 FNV actors have one); no navmesh cover, door links (XNDP) or islands | [packages](fo4_pipeline.md#combat-override), [parents](fo4_pipeline.md#parents), [navmesh](fo4_pipeline.md#exterior-navmesh) |
| Creatures | Dead-at-start actors without a ragdoll pose: robots 19, no FNV pose 22, 9 other creatures (brahmin and mole rats posed since 2026-11-06, not played: [creature poses](fo4_spikes.md#creature-poses)); own rigs lack hit reactions, staggers, idles while moving or fighting, side and back moves, jumps and kill moves; Hit, Idle and Aware sounds; own-rig attack spells; flags with no FO4 counterpart (Can't Open Doors 563, Allow PC Dialogue 170, Immobile 50); FO3's creatures | [creatures](fo4_spikes.md#spike-4-creatures), [own rig](fo4_own_rig.md), [creature audit](fo4_creature_audit.md) |
| Idles | Idle trees other than the ambient one (dialogue gestures, hit reactions, V.A.T.S.: FO4's own graphs play these), the ambient tree's weapon-out and `SIRelaxed` branches; seated line idles; props' own visibility keys and motion below their chain; creature clips not on an own rig; 108 of 1,424 idle markers (protectron 55) | [idles](fo4_idles.md), [audit fixes](fo4_pipeline.md#audit-fixes) |
| Perks | 29 entry points with no FO4 counterpart: attack and equip speed (a DLL), unarmed specials, Miss Fortune, Long Haul, detection; Comprehension; defender DT perks, per-pellet DT, ammo DR | [perks census](fo4_perks.md#census), [damage threshold](fo4_pipeline.md#damage-threshold) |
| Gun animation | Nothing built of the plan: FNV third-person clips, entry variants and power armor, left hand in cover, sighting time and recoil from FNV data | [gun animation](fo4_gun_animation.md) |
| Clothing | FNV's own weights for clothes and wrists, dismemberment cuts; CBBE and BodySlide opt-in; 21 of 98 armors stay on the template's models | [human clothing](fo4_build_next.md#human-clothing), [audit fixes](fo4_pipeline.md#audit-fixes) |
| Items | Caravan cards, NCR and Legion money and casino chips convert as MISC items since 2026-11-06, not played (the 281 `item skipped (not exported)`; [items built](fo4_casino_plan.md#items-built)); 321 creature items left out; 550 statics skipped; 9 weapon mod effects with no FO4 effect | build log |
| World | Lucky38Penthouse (no door leads in); maps of Freeside, the Strip and other worldspaces; LOD water; tree LOD; FNV's weather imagespace modifiers; damage stages and smoke add-ons; the bear trap's trigger; 806 portals to no room (29 interiors lose room culling) | [world map](fo4_pipeline.md#world-map), [terrain LOD](fo4_pipeline.md#terrain-lod), [parked](fo4_pipeline.md#parked), [rooms](fo4_pipeline.md#rooms) |
| Look | Grass color and sway, grass shards, FNV's cloud layers, the night horizon glow, Strip neon, the overall tone | [look](fo4_look.md) |
| Audits | Menu audit phases 1 to 6; timing audit phases 3 to 6; preflight and tool-audit findings not acted on | [menu](fo4_menu_audit.md), [timing](fo4_timing_audit.md), [preflight](fo4_preflight.md#results), [tool audit](fo4_tool_audit.md) |
| Build and app | Builds of only what changed (Part E: step 1 built); converting one mod against the built game (steps 2 to 7); the rules plugin; the app's phase 7 (MO2 setup, Play) and its DLL, Bink and FaceGen stages | [plugin layout](fo4_plugin_layout.md#which-builds), [mod builds](fo4_mod_builds.md#order), [app](fo4_gui.md#phases) |
| Performance | Papyrus cost 2 to 4; frame rate in Freeside, the Strip and Novac not measured (precombines open) | [performance](performance.md#papyrus), [before](fo4_pipeline.md#before) |

### <a id="fo4-unplayed"></a>Built, never played

The play-test list. Everything here is in the deployed build unless marked.

| Area | Built |
|---|---|
| Combat | FNV's critical roll, crit damage and effects, AP costs, weapon skills, Strength and skill spread, sneak attacks, weapon poisons, the DT hook, the combat feel pass (aim cone, health, run speed, V.A.T.S.), combat styles, creature attack lists and speeds, knockdowns |
| Thrown weapons | All parts, built 2026-11-06, deployed: grenades, mines and C4 as items with FNV's explosions and fuses, thrown melee on a sticking spike, stun and flashbang effects ([as built](fo4_thrown_weapons.md#built)) |
| Ammo and guns | Ammo subtypes and the Ammo Type hotkey, ammo effects, casings, projectile copies, weapon mods, scopes at FNV's zoom, condition's break at 0, wear perks and the ammo list (V) |
| Character | 207 perks and the level-up list, teammate perks, stat abilities, skill gates on locks and terminals, Intense Training (no box in play 2026-11-07; quests keep FNV's Allow Repeated Stages, deployed, [why](fo4_pipeline.md#intense-training)), challenges and their tab, reputation messages, disguises, survival needs, chem addiction, Fatigue and knockouts, the sex change |
| Dialogue | First-meeting greetings (2026-11-05), ambient NPC chats, named barks and bark replies, scene loops and joins, shared infos, script-named force greets, greet holds and distances, Doc Mitchell's caps pair, talking activators |
| World | Terrain and object LOD fixes, imposters, the WastelandNV map, outfit slots, wall leans, mesh fixes (overlays, rest alpha, controllers, emissive), destroyed doors locked, freed captives re-evaluating |
| Creatures | The full set of own rigs (rats, ants, centaurs, spore plants, ravens), securitron screens and expressions, Dead Money's Ghost People and holograms, creature flags and death items, gun nightkin re-cloaking between shots (the GetAnimAction fix, 2026-11-01) |
| DLC | Every DLC and pack plugin; `FalloutNV.esm` as a master |
| Hardcore | FNV's Hardcore mode in place of Survival's needs, with ammo weight and the H2O/FOD/SLP HUD in `F3NV.dll` (deployed 2026-11-07) |
| Spawns | The void-chance roll on 1,147 placed actors in place of void list entries; the Pip-Boy map's border (deployed 2026-11-07) |
| Other | Lip files, the conversion app's phases 1 to 6, the README's install steps end to end on a clean machine |

### <a id="fo4-system-rows"></a>Each system's row (last updated 2026-10-29)

Built into `FalloutNV.esm` (MO2 mod "F3NV - Fallout New Vegas") and played in
the Goodsprings to Primm region unless it says otherwise. Where play differs
from FNV is in [fo4_drift.md](fo4_drift.md). The current state is
[above](#fo4-state); this table is kept for its per-system detail and links.

| System | Status |
|---|---|
| World, NPCs, dialogue, quests | Built and played in the region. **Whole map rebuilt 2026-10-29, deployed, not played** ([whole map](fo4_pipeline.md#whole-map)): WastelandNV and every worldspace a door reaches; 2,245 NPCs (910 template actors), 113,921 dialogue lines, 4,700 navmeshes, 13,511 of 13,511 scripts compile, a 438 MB plugin, 0 FormIDs moved against the morning's build. 47 placed creatures of 14 kinds are left out (super mutants, nightkin, REPCON ghouls; 1,036 of 121 kinds on 2026-10-24, before every creature had a rig): a converter bug, as they take their model from a template without its traits ([no base](fo4_build_next.md#no-base)). Sounds and voices in `FalloutNV - Main.ba2` ([sound archive](fo4_pipeline.md#sound-archive)). **Terrain LOD built 2026-10-24, not played** ([terrain LOD](fo4_pipeline.md#terrain-lod)); object LOD in the 2026-10-31 build; its glowing rocks and the Freeside crash fixed, not rebuilt ([object LOD](fo4_pipeline.md#object-lod)) |
| Build time | **128 → 34 min, 2026-10-29** for a whole-map rebuild: our own sound BA2 writer reusing unchanged files ([sound archive](fo4_pipeline.md#sound-archive)) and a decoded-clip cache ([clip cache](fo4_pipeline.md#clip-cache)); about 70 min when every script recompiles. The BA2 staging cache (293k files, 9.3 GB) moved out of the Data folder into `output/fo4_cache/ba2`, so MO2 no longer lists it and the Creation Kit's "Initializing Archive" wait should shrink (not yet timed) |
| Replacements ([replacements](fo4_replacements.md)) | **Off for the pure build, 2026-10-29:** `replacements/falloutnv.json` empty, the earlier table kept as `falloutnv.with_mods.json` |
| Required mods | F4SE, Address Library, LevelUpMenuEx, XDI; Garden of Eden no longer: `SexChange` is native in `F3NV.dll` ([sex change](fo4_pipeline.md#sex-change), deployed, not played) |
| Combat rules | **Built 2026-10-29, deployed, not played**, on the hidden `FNV_CombatRules` perk every NPC and the player hold, and the F3NV plugin: FNV's random critical roll with each weapon's crit chance, damage, effect and V.A.T.S. AP cost ([weapon criticals](fo4_pipeline.md#weapon-criticals), [random criticals](fo4_pipeline.md#random-criticals)); weapon skill damage and spread ([weapon skills](fo4_pipeline.md#weapon-skills)); Strength and skill requirement spread ([requirement spread](fo4_pipeline.md#requirement-spread)); sneak attacks ([sneak attacks](fo4_pipeline.md#sneak-attacks)); weapon poisons ([weapon poisons](fo4_pipeline.md#weapon-poisons)); Damage Threshold through a DLL hook on FO4's resistance curve, credit to Zoltanite's reference ([damage threshold](fo4_pipeline.md#damage-threshold)); knockdown criticals as FNV's converted spells |
| FNV combat feel ([plan](fo4_combat_feel.md)) | **First pass built 2026-10-29, deployed, not played** ([built](fo4_combat_feel.md#built)): each gun's aim model a fixed cone of FNV's Min Spread; FNV's player health formula and run speed; V.A.T.S. at 2% time, FNV's 0.75 damage taken, a skill term on the hit chance; difficulty already FNV's; sprint FO4's with its AP drain |
| Consumables ([consumable effects](fo4_pipeline.md#consumable-effects)) | Played 2026-10-21. **Since 2026-10-29, deployed, not played:** effects FO4 has no match for run their converted FNV scripts (Cateye, antivenom, Steady, Super Stimpak, Stealth Boy), critical chance raises the roll's helper, and 27 chems carry FO4's addiction for their withdrawal ([chem addiction](fo4_pipeline.md#chem-addiction)) |
| Projectiles ([projectile copies](fo4_pipeline.md#projectile-copies)) | Stand-ins since 2026-10-28; **since 2026-10-29, deployed, not played:** 49 copies with FNV's range, flying ones with its speed and gravity, 8 explosions with FNV's damage, force and radius |
| Build checks ([reference check](../reference/python_tools.md#fo4-ref-check)) | Script properties naming a record never written are cleared after each build (`base/dangling_scripts.py`; 1,080 on the whole map). `tools/validate/fo4_ref_check.py` finds unresolved references headless in 5 s and matched FO4Edit's 76 on the whole map; FO4Edit (`fo4_check --timeout`) stays for structural checks and waits for its developer-message dialog when unattended |
| Item condition ([condition](fo4_condition.md)) | **Played:** weapon and armor wear, the Pip-Boy CND line and repair list (G), transfer and barter CND, starting condition (COED), Jury Rigging, reload jams (briefly). **Not played:** vendor repair (no repairer in the region), the Pip-Boy ammo list (V). NPC weapon wear: FNV has none |
| Pip-Boy tabs ([tabs](fo4_pipboy_tabs.md)) | SKILLS, REPUTATION, KARMA played; CHALLENGES not played. Pip-Boy Tabs dropped |
| Challenges ([challenges](fo4_pipeline.md#challenges)) | Built, not played: 61 of 105 |
| Hardcore ([Hardcore](fo4_hardcore.md#built)) | FNV's own Hardcore mode in place of Survival's needs, with ammo weight and the HUD needs in `F3NV.dll`: built and deployed 2026-11-07, not played |
| Karma, infamy ([standings](fo4_pipeline.md#standings)) | Built; kill karma played |
| Reputation ([reputation](fo4_pipeline.md#reputation)) | Built, not played |
| NPC skills ([vendor repair](fo4_condition.md#vendor-repair)) | Built, not played |
| Disguises ([disguises](fo4_pipeline.md#disguises)) | Built, not played |
| Weapon mods ([weapon mods](fo4_pipeline.md#weapon-mods)) | Built, not played |
| Combat styles ([combat styles](fo4_pipeline.md#combat-styles)) | Each FNV style converted to its own FO4 style from both exes' formulas: built 2026-10-25, not played |
| Ammo subtypes, effects, casings, the Ammo Type hotkey ([ammo](fo4_pipeline.md#nv-ammo)) | Built, not played |
| Guns ([gun clips](fo4_spikes.md#spike-4-gun-clips)) | FNV guns on their own meshes and first-person clips: played 2026-10-28/29, good enough for now; polish [parked](#parked) |
| Gun and ammo projectiles from FNV data ([projectiles](fo4_pipeline.md#nv-projectiles)) | Built, not played |
| Lockpicking and hacking on FNV's skills | Built, not played |
| Perks, traits, teammate perks ([perks](fo4_perks.md)) | Built, not played. Since 2026-10-29: reload speed, AP regeneration, run speed, Lead Belly and defender DT as abilities ([stat abilities](fo4_perks.md#stat-abilities)); attacker DT on FO4's target resistance |
| Terminals ([terminals](fo4_pipeline.md#terminals)) | Played. FNV's computer hum left out: FO4 reads a terminal's Looping Sound field as marker data and crashed on load (2026-10-30; [drift](fo4_drift.md#recorded)) |
| Radio ([radio](fo4_radio.md)) | Played: Mojave Music Radio, Radio New Vegas, Trudy's radio. Not played: Black Mountain, the lounges |
| Idles ([idles](fo4_idles.md#standing)) | Standing idles played; seated ones only where listed |
| Bink movies ([bink](bink_movies.md)) | Built; the FNV intro played |
| Names ([names](fo4_pipeline.md#f3nv-names)) | `F3NV_` scripts, `FalloutHelpers.esl`, `F3NV.dll`, `FalloutNV.esp` (2026-10-23, 0 FormIDs moved); `FalloutNV.esm`, flagged master, since 2026-10-30 ([layout](fo4_plugin_layout.md#layout)) |
| FNV DLC ([DLC build](fo4_plugin_layout.md#dlc-build)) | Gun Runners' Arsenal as `GunRunnersArsenal.esm` on FalloutNV.esm, its own data folder and MO2 mod (`F3NV - Gun Runners Arsenal`): built 2026-10-30, gaps closed 2026-10-31 (its own subgraph race; the Ammo Type, condition and challenges quests merged row by row), not played. Since 2026-10-31 the build leaves out the game's own files ([master copies](fo4_plugin_layout.md#master-copies)), not rebuilt yet. Open: two DLCs overriding one list or quest, the last wins |
| Not started | See the [current state](#fo4-missing) |
| Look pass ([fo4_look.md](fo4_look.md)) | **Played 2026-10-23/24:** weathers graded by FNV's worldspace imagespace and weather tints, vanilla clouds in FNV's colours, exterior depth of field; night and noon match FNV after each weather's directional ambient took FNV's ambient ([night](fo4_look.md#night)); windows; the saloon's flickering "SAL" (looping activators made statics, no box from blended unlit tubes); the "ON" bulbs and the graveyard lantern ([lanterns](fo4_look.md#lanterns)). Glows follow vanilla's ranges per kind ([emissive](fo4_look.md#emissive)); neon ("O", OPEN) parked until the Strip is converted. **Built, not played:** grass density (1/16), grass placement (grassy textures kept past the 4-texture limit, [grass-ground](fo4_look.md#grass-ground)), soft light-ray cones. Open: the grass shards; FNV's horizon glow at night |
| Needs one play test | The silent player voice; ambient two-NPC conversations; built and deployed 2026-11-04, not played: the faster talk opening and script-package release ([release](fo4_pipeline.md#script-package-release)), force greets waiting where the actor is ([greet wait](fo4_pipeline.md#greet-wait)), reputation messages ([messages](fo4_pipeline.md#reputation-messages)), the trace switch plugin ([trace](fo4_pipeline.md#trace)); deployed 2026-11-05, not played: 38 guns' broken shader controller links fixed, the Incinerator crash in The Bison Steve Hotel ([gun controllers](fo4_pipeline.md#gun-controllers)); hotfixed 2026-11-05, not played: locked terminals no longer throw the player out ([lock script](fo4_pipeline.md#lock-script)); a freed actor re-evaluates its packages, for Deputy Beagle staying seated (cause not confirmed, traced as `restrained`; [restrained](fo4_pipeline.md#restrained)); deployed 2026-11-05, not played: message box buttons keep FNV's conditions (the Bison Steve elevator's Repair 35; 9 of the base game's 136 gated buttons still show always: the NCR emergency radio's support region and the trap computer's grenades, which convert as statics: [message buttons](fo4_pipeline.md#message-buttons)), destroyed doors locked Inaccessible ([destroyed doors](fo4_pipeline.md#destroyed-doors)) |
| Lip sync from FO3/FNV's own lips ([lips](research/lip_format.md#built)) | **Built 2026-11-06, not built into a game build, not played:** each voice line's own `.lip` converted to Fallout 4's layout (2 ms a line in place of LipGenerator); LipGenerator only for lines without one; exports now keep `.lip` files |
| AnimTextData without the CK ([writer](research/anim_text_data.md#writer)) | **Writer built and wired into the build 2026-11-06, not yet in a game build, not played:** 5,154 third-person gun entries (98% of the CK's 1.35 GB) copied from their vanilla templates; first-person entries and own-rig creatures stay with the CK. The time saved depends on the CK skipping deployed files (not yet measured) |
| Script hotfixes ([hotfix](fo4_hotfix.md)) | Built 2026-11-04: `tools.release.fo4_hotfix` ships changed scripts to the `F3NV - Hotfix` MO2 mod in about 30 s; a deploy clears them. Records still need a build |

### <a id="fo4-next"></a>Planned work

What is broken, missing and unplayed is [above](#fo4-state). This section
holds the planned items and their plans.

**Verify, cheaply, in the next combat play test:** FO4's aim cone is a
half-angle as FNV's (fire at a wall at a known distance); V.A.T.S. at 2% brings
no stuck slow-motion audio; the CarryWeight nudge makes the SpeedMult take;
the Creation Kit's archive wait is shorter.

**Played 2026-11-01/02** (committed `a20ae56c`): Ringo's force greet, corpses posed instead of
T-posed, the LOD dots, Freeside loading, casino weapon checks, the transceiver's `<Say nothing.>`
option (XDI shows option text as HTML; prompts and player lines are escaped), super mutant armor
over FO4's body and the head tinted to match, greetings no longer stuck on "dialogueentry" (a
stuck greeting scene is stopped first; the `xdi_menus` preflight check), the REPCON intercom's one
exit, the Freeside gate securitrons' guns (templated creatures with their own inventory lost them;
eight such creatures), the gate tourist's clothes (38 NPCs take listed template parts). **Built,
not yet seen in play:** the nightkin's re-cloak between shots.

**Build next** (the plan, in order: [fo4_build_next.md](fo4_build_next.md#order)):

| Item | Size | Notes |
|---|---|---|
| Items 1 to 4: creatures with no base, the `[Speech 50]` tag, creatures' Combat skill, scoped sway | — | **Built 2026-10-30**; the skill tag played 2026-10-31 (`[Barter 20]` on a Trudy line), the rest not yet ([no base](fo4_build_next.md#no-base), [speech tag](fo4_build_next.md#speech-tag), [creature skill](fo4_build_next.md#creature-skill), [sway](fo4_build_next.md#sway)) |
| Built-in scopes at FNV's zoom | S | Built 2026-10-31, not played ([scope zoom](fo4_build_next.md#scope-zoom)) |
| Human clothing on FO4's body | S-M | Planned 2026-11-02: FNV's own weights for clothes, wrists, dismemberment; FNV's body on FO4's skeleton dropped after the super mutants; CBBE and BodySlide as an opt-in ([human clothing](fo4_build_next.md#human-clothing)) |
| FNV's super mutants on Fallout 4 | S-M | **Played 2026-11-02: FO4's body and head under FNV's armor.** FNV's head on FO4's body left a gap and a second head showing (FO4's neck is built for its low, forward head), so super mutants and nightkin now wear FO4's body and head, tinted to FNV's skin (an MSWP on the body, a tinted face set as FTST), with FNV's armor over them; the armor addon takes FX slot 61 so it draws beside the body addon (armor and head tint played). Head gear moves from FNV's head box onto FO4's. The captain (skin and armor in one shape) keeps FNV's whole body. Nightkin unarmed fixed by an additive subgraph race (2026-11-01). Not yet checked in play: nightkin re-cloaking between shots. Dead-at-start actors take FNV's ragdoll pose: 298 of 396, played (no T-pose); brahmin, mole rats and 7 other creatures (57) have no bone match and robots (19) no FO4 ragdoll ([super mutants](fo4_build_next.md#super-mutants), [mesh](fo4_spikes.md#spike-4-creatures)) |
| Gun animation: grip, third person, FNV feel | M-L | Planned 2026-10-31 ([plan](fo4_gun_animation.md#order)): measure fall-through clips first, then FNV's own third-person clips, every entry variant and power armor, left-hand IK in the other third-person states, AnimTextData from the CK, FNV's on-screen size, records from FNV data. Clips only, no edited base graphs |
| Object LOD | L | **Played 2026-11-01: the bright dots and the Freeside crash are fixed** (specular at install; terrain LODSettings sized to a power-of-two tile grid) ([object LOD](fo4_pipeline.md#object-lod), [terrain LOD](fo4_pipeline.md#terrain-lod)): STATs keep the distant flag and `MNAM`; the build writes LODGen's list and runs it headless in FO4 mode with an atlas, cached and time-bounded. A scratch WastelandNV run made 399 `.bto` in vanilla's layout. Trees later |
| Bark lines in generic quests | M | **In the game builds since 2026-11-01** (357 quests, 123,554 lines), not listened for in play: FNV's engine barks as FO4 barks, and the generic quests that pick speakers by faction or voice type (nightkin, super mutants, `CreatureHits`, the NCR, Legion and Freeside greetings) ([barks](fo4_pipeline.md#barks), [speaker tests](fo4_pipeline.md#quest-scope)). `GenericPlayer` stays out |
| Dialogue left open | M | **Built 2026-11-02, in the 2026-11-05 build, not played:** [bark replies and named barks](fo4_pipeline.md#bark-replies) (153 lines), [conditions](fo4_pipeline.md#dialogue-conditions) on the player, missing objectives, packages and form lists (69+ lines), [script-named force greets](fo4_pipeline.md#greeting-scene) (11). [Shared infos](fo4_pipeline.md#shared-infos) (built 2026-11-02, in the 2026-11-05 build): the export now dumps DIAL Shared Infos and the Hub answers 1,624 of the 1,686 Choice topics that had no line (4,074 menu placements). **Built 2026-11-06, not played:** [companion status barks](fo4_pipeline.md#companion-barks) (77 lines: health, waking, no ammo), [`Exists`](fo4_pipeline.md#exists) read as 1 (19 lines), tests of no form read as 0 (5 lines). Open: 91 status barks with no state FO4 tracks; the follower choices missing from other quests' menus; the dialogue audit's dead Fallout 3 leftovers (`HD00RobotsDialog`, `WaterBeggars`, `Vault108DialogueShell`, cut `VES08CampGolf`); thousands of waiting `FALLOUTNV_TIF__001589F0` fragment stacks (Jerry the Punk) in a 2026-11-01 Papyrus log |
| Creatures left open | S-M | 98 dead-start actors without a pose (above); frag mine, dynamite and Multiplas have no super mutant animation; `SetForceSneak 0` has no FO4 match |
| No combat sprint | S | **Built 2026-11-07 in F3NV.dll (`tes_runtime/dist`), not deployed or played:** FNV actors never sprint, and FO4's approach sprint made converted ghouls close about 1.5 to 2.5 times faster than FNV's. F3NV.dll turns `bCombatPathSprinting:Combat` off for every actor, vanilla FO4's included ([combat sprint](fo4_pipeline.md#combat-sprint)) |
| FO4-only robot, deathclaw, behemoth and mirelurk king behavior | S | **Built 2026-11-07, not built into the game or played:** converted robots, deathclaws, behemoths and mirelurk/lakelurk kings carry `F3NV_FalloutCreature`; `FalloutHelpers.esl` gates FO4's robot self-destruct, deathclaw fear roar, behemoth slam explosions and king blur off for it, and runs FNV's robot frenzy in place of the robot script ([race abilities](fo4_creature_audit.md#race-abilities)). A stand-in's ranged gear stays only on a creature with a ranged weapon of its own: FNV deathclaws (56) and behemoths (6) lose the dirt throw and boulder ([deathclaws](fo4_creature_audit.md#deathclaws)). Needs the helper plugin rebuilt (`python -m fo4_import.helpers_plugin --out .../FalloutHelpers.esl`) beside the game build |
| Game style choice | M | Idea 2026-11-07, not planned: let the user pick FNV or FO4 combat, in the converter or the mod. The game-wide changes it would switch: approach sprinting, the DT/DR damage hook, the hidden vanilla perks (`PRKF` `disableVanillaPerks`), the five settings (`uSPECIALPoints`, the health pair, the V.A.T.S. pair), the lowered human collision box. A per-actor sprint fix is in [combat sprint](fo4_pipeline.md#combat-sprint) |
| FNV Hardcore in place of FO4 Survival | M-L | **Built 2026-11-07, not built into the game or played** ([as built](fo4_hardcore.md#built), [plan](fo4_hardcore.md#plan)): FNV's own switch (Doc Mitchell's `SetHardcore`, then a Hardcore Mode aid item showing the needs), needs as helper actor values at FNV's rates, 12 stage potions from FNV's DEHY/HUNG/SLPD records, `IsHardcore` as the `F3NV_Hardcore` global (stimpak and RadAway over time and the Doctor's Bag kept), ammo weight and the HUD's H2O/FOD/SLP from F3NV.dll (DLL approved by the user for both; it compiles, not deployed), sleep keeps limbs; the Survival feed removed. Taken by default, changeable: an FNV character picking Survival gets Hardcore, FO3 food has no needs, TimeScale stays 20. Needs: the helper plugin, `--scripts-only`, the base and DLC imports, and F3NV.dll deployed. Not built: teammates essential outside Hardcore, the ending's reward, a settings-menu switch |
| Dialogue menu audit phase 2, timing audit phases 3 to 6 | M | Planned ([menu](fo4_menu_audit.md), [timing](fo4_timing_audit.md)) |
| Preflight findings | M | First run on the 2026-10-25 build: 801 errors and 128 to review. 2026-11-07 rerun: DLC identical overrides fixed, dialogue 153 → 70 errors, script properties 2,001 → 138 errors and 583 reviews, targets clean, timing 0 errors (OnHit → OnEffectStart now read). Dialogue 59 errors after audit fixes (radio talking activators, lines FNV never passes, per-station radio topics, speech challenge outcomes); Cato's, Big Sal's and Vault 11's 32 lines fixed in the converter, not yet built; the Tops stage acts' 8 radio lines get a quest per act ([stage acts](fo4_radio.md#stage-acts)), and `StartRadioConversation` now starts a station's program, the acts' and Hanlon's and Lily's recordings on demand ([programs a script starts](fo4_radio.md#start-radio-conversation)), not yet built; 3 radio lines are silent in FNV but still counted (the export lacks a response's sound); the rest known gaps or not looked at (~25 single lines). Open: VCG00 stage 14, 3 unbuilt start quests, 7 missing textures; the build audit no longer reads renumbered scene EditorIDs as moved FormIDs (none moved). Removed records (83,370 INFO, 91 DIAL, 19 SCEN from menu speakers, 8 thrown-weapon STAT) accepted as the baseline on 2026-11-07 ([preflight](fo4_preflight.md#results), [2026-11-02](fo4_preflight.md#results-2026-11-02), [2026-11-07](fo4_preflight.md#results-2026-11-07)) |
| Casino games and Caravan | L | Not started; planned 2026-11-04: 2D tables in our own F4SE menu, rules in the menu, Papyrus as the bank ([casino plan](fo4_casino_plan.md)) |
| Kill cams and finishers | — | Nothing planned: [kill_cams.md](kill_cams.md) is Skyrim-only. For FO4, a play-test check that converted weapons get FO4's kill cam and V.A.T.S. finishers as FNV did ([check](kill_cams.md#fallout4)) |
| The rest of the look pass | M | Grass shards, FNV's horizon glow at night, neon on the Strip ([fo4_look.md](fo4_look.md)) |
| Papyrus cost 2 to 4 | M | GameMode loops, dialogue state, patrol checks ([performance](performance.md#papyrus)) |
| Conversion app phase 7 | M | MO2 setup, Play, modlist status ([phases](fo4_gui.md#phases)) |
| Creature screens and the Lucky 38 elevator | M | Animated securitron and Mr. House screens ([own rig](#own-rig)) |
| Build only what changed | M | Planned 2026-11-03 ([Part E](fo4_plugin_layout.md#which-builds)): each build records its inputs (files, programs, its master reads, functions that ran), cache keys by functions that ran, a build plan naming which plugins need a build. Measured: 3 of the last 13 base builds took 105–119 min against 18–38 from one shared-file edit; 7 of 9 DLC rebuilds after a base fix changed nothing |
| Region tests | M | **Built 2026-11-06, not played** ([as built](fo4_regions.md#built)): FNV's polygons tested by `F3NV_RegionWatch` on a quest per plugin, one global per tested region; conditions and the 9 scripts' `IsPlayerInRegion` read them. To check: the NCR radio's support buttons, the reputation messengers away from towns, Victor in Novac |
| Thrown weapons, mines and placed explosives | M | **All parts built 2026-11-06, not yet played** (Part 3: an explosion copy on an effect-less stand-in takes FNV's enchantment as an ENCH, effects converted as attack poisons: stun's Fatigue damage, the flashbang's skill drain, fire over time) ([as built](fo4_thrown_weapons.md#built)): every FNV grenade, mine, placed explosive and thrown melee weapon (game and DLC) has a table entry on an FO4 grenade or mine, and throws its FNV projectile's copy (FNV's explosion numbers and fuse; C4 a 15 s timer). Thrown melee shows FNV's mesh and throws a copy of the Railway Rifle spike with FNV's projectile model, flight, pick-up and pinning, no explosion. Before, dynamite and the mines threw FO4's own projectiles. Next: play test |
| Convert one mod against the built game | M | Planned 2026-11-04 ([plan](fo4_mod_builds.md)). Step 1 built 2026-11-04, through a build 2026-11-05: builds record the answers they got from MO2 and the app settings, not `ModOrganizer.ini`, `modlist.txt` or `fo4_app.json` ([MO2 answers](fo4_mod_builds.md#mo2-answers)). Next: a census of game records a converted plugin overrides only to add to |

**Known drift that could come back later** (each in [fo4_drift.md](fo4_drift.md)):
attack and equip speed perks (Fast Shot, Slayer, Quick Draw; FO4 has no
weapon-speed actor value, so a DLL), looting packages, packages that keep
running in combat, placed corpses' poses (remap FNV's ragdoll bones by name),
the per-pellet share of DT and ammo DR effects (the DLL hook), music beyond
one stem, FNV's sleep amounts, Long Haul and Miss Fortune.

## <a id="fo4"></a>Fallout 4: how it got here

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
| [Step 0: groundwork](fo4_spikes.md#step-0) | **Built 2026-10-05:** FO4 writer + tests, `Fallout4.esm` dump, script sources, compiler checked. FO4Edit's check runs on every build since 2026-10-12 |
| [Spike 1: dialogue](fo4_spikes.md#spike-1) | **1a text-only played 2026-10-05:** greeting opens the menu with all of Doc's options; added topics, Say Once variants, skill checks, sub-menu returns and Goodbye confirmed ([design](fo4_spikes.md#spike-1-design)). **1b played 2026-10-05, passed** ([1b](fo4_spikes.md#spike-1b)): three speakers share one forced-alias scene, each seeing only their own options; `[Leave]` replaces Tab, walking away ends the talk, Random piles vary. The gate is passed: 1b needs no hand work. **Voice played 2026-10-05** ([voice](fo4_spikes.md#spike-1-voice)): Doc's FNV lines as `.fuz` with CK-generated lips. Only the player opens a talk (`GetPlayerActivated`, played). Open: the player's "Hi" |
| [Spike 3: one script](fo4_spikes.md#spike-3) | **Measured 2026-10-05** ([results](fo4_spikes.md#spike-3-measured)): of 199 sampled converted FNV scripts, 81 compile unchanged with FO4's compiler, 54 fail only through our helper scripts, 64 on their own code (update loop, actor values, `SendModEvent` lead). 20 of 554 command rows change; VMAD changes are small. **Target switch built** ([target](fo4_spikes.md#spike-3-target)): Doc Mitchell's script emits as FO4 Papyrus and compiles with FO4's compiler; Skyrim output unchanged. **Corpus gate built** ([gate](fo4_spikes.md#spike-3-gate)): all FNV scripts converted for FO4; **98.5% compile** (17,425 of 17,698) after `RewardXP` → native `RewardPlayerXP` and the character menus → a custom event. **All 16 FO4 helpers compile** ([helpers](fo4_spikes.md#spike-3-helpers)): 3 left out as unneeded, the converter's FO4 rules applied to the shared source, 8 function overrides with a drift guard. **99.9% compile** (17,672 of 17,695) after `OnTrigger`, `SetRestrained`, fast travel, sleep and menu events and the singles ([singles](fo4_spikes.md#spike-3-singles)); a duplicate-name guard and per-game prefixes ([names](fo4_spikes.md#spike-3-names)). The doctors' stage scripts compile since a quest stage's bare call acts on the player ([VDoctors](fo4_spikes.md#spike-3-vdoctors)); **17,676 after the singles** ([singles](fo4_spikes.md#spike-3-else-text)): text after `else` is dropped as FO3/FNV's compiler drops it (18 lines in 13 scripts), a no-value call's `set` stores the empty value. Left: 19, all in scripts nothing attaches. **FO4 VMAD built** ([vmad](fo4_spikes.md#spike-3-vmad)): matches vanilla byte for byte (520 of 521 INFOs, all sampled quests). **End to end played 2026-10-05** ([end to end](fo4_spikes.md#spike-3-end-to-end)): Doc's converted script on his stand-in binds; `setav FNV_Variable01 1` turns the player's controls off and back on. FO4 has no `Variable01`–`10`, so the plugin carries its own. The 8-second wait measured at 8.06 s ([timing](fo4_spikes.md#spike-3-timing)). **Dialogue fragments played 2026-10-05** ([fragments](fo4_spikes.md#spike-3-fragments)): 29 lines carry their converted FNV scripts; paid treatment, stimpaks, water and barter work. The stand-ins' own FO4 greetings and scenes still compete with ours (stand-in only). **Shared helper plugin played 2026-10-05** ([helper plugin](fo4_spikes.md#spike-3-helper-plugin)): `FalloutHelpers.esl` holds Variable01-10, the FO3/FNV skills, the helper quests and `TES4ControlsDisabled`; `AV()` reads it and FO3/FNV skills keep their names on FO4; corpus still 17,672 of 17,695. **VDoctors played 2026-10-05** ([VDoctors](fo4_spikes.md#spike-3-vdoctors)): the doctors quest with its converted stage script, treatment heals and the radiation line clears rads (stages 10 and 30 done). The compile gate now compiles only changed scripts, and their users only when a declaration they compile against changed |
| [Spike 4: Goodsprings and its items](fo4_spikes.md#spike-4-exterior) | **Built 2026-10-07/08, played 2026-10-08:** the 3×3 Goodsprings block ([trees](fo4_spikes.md#spike-4-trees), [sounds](fo4_spikes.md#spike-4-sounds) and [door and container animations](fo4_spikes.md#spike-4-animations) built 2026-10-09, played 2026-10-10); [creature census](fo4_spikes.md#creature-census) 2026-10-10; [Cheyenne on Dogmeat](fo4_spikes.md#spike-4-creatures), FNV's dog mesh on FO4's dog, played 2026-10-10; geckos as FO4 mole rat stand-ins (FNV's gecko on the deathclaw tried and dropped), played 2026-10-10, grass, climbable steps, consumables and ammo ([exterior](fo4_spikes.md#spike-4-exterior)); player collision box at 115, played ([player collision](research/fo4_target.md#player-collision)); weapons and armor on FO4 records ([equipment](fo4_spikes.md#spike-4-equipment)), melee weapons ([melee](fo4_spikes.md#spike-4-melee)) and headgear ([headgear](fo4_spikes.md#spike-4-headgear)) on FNV's meshes, played; the pre-war outfits on FNV's meshes moved onto FO4's body (played; variants as material swaps; CBBE and BodySlide later) ([outfits](fo4_spikes.md#spike-4-outfits)). FNV's guns on FO4 receivers tried twice and parked as experimental: FO4's animations fit only FO4's layouts ([guns](fo4_spikes.md#spike-4-guns)). **Step 1 of the replacement table built** ([replacements](fo4_replacements.md)): guns back on FO4's guns by default |
| [Spike 2: one interior cell](fo4_spikes.md#spike-2) | **Step 1, one static, played 2026-10-06** ([static](fo4_spikes.md#spike-2-static)): an FO4 NIF reader/writer ([nif](fo4_spikes.md#spike-2-nif)), BGSM ([bgsm](fo4_spikes.md#spike-2-bgsm)) and BGEM ([bgem](fo4_spikes.md#spike-2-bgem)), each rebuilding vanilla byte for byte (32,397 meshes, 6,616 BGSMs, 283 BGEMs). Three FNV statics from Doc's house render in QASmoke: a shelf, a Craftsman wall corner (specular maps from FNV's normal-map alpha), a test-tube rack (glass as vanilla's beaker effect material). **Step 2, Doc's house cell, played 2026-10-06** ([cell](fo4_spikes.md#spike-2-cell)): 427 of 434 references (meshes as statics, FNV lighting, lights, a door to QASmoke and back), unlit FNV shapes as inline effect shaders. Looks right; fog and colour judged once it has a standard interior's imagespace. **Step 3, collision, played 2026-10-06** ([collision](fo4_spikes.md#spike-2-collision)): FNV's Havok blocks in FO4's pre-Elric form, the CK's Elric builds the FO4 physics, grafted into our meshes; mesh winding through the shared repair. **Step 4, FaceGen, played 2026-10-06** ([facegen](fo4_spikes.md#spike-2-facegen)): the CK exports FaceGen through MO2; FNV's face shape baked into the exported head (C1 kept; FO4's sliders capture 2.3% of it). **Step 5, the face in FO4's own systems, played 2026-10-06**: FNV's face texture can't hide the hairline ([face texture](fo4_spikes.md#spike-2-face-texture)), so the face is rebuilt from FO4 sculpt regions fitted through the CK (70% of the shape, [sculpt](fo4_spikes.md#spike-2-sculpt)) and face detail layers plus skin tone ([tints](fo4_spikes.md#spike-2-tints)); ST kept. **Step 6, hair, played 2026-10-06** ([hair](fo4_spikes.md#spike-2-hair)): FO4 hair, facial hair and eyes matched by drawn coverage and iris colour, hair colour through both games' shaders, brows in the tint fit (tattoos kept out). **Step 7, imagespace, played 2026-10-06** ([imagespace](fo4_spikes.md#spike-2-imagespace)): FNV's cinematic grading and tone curve baked into an FO4 LUT. **Step 8, blended surfaces, played 2026-10-06** ([transparency](fo4_spikes.md#spike-2-transparency)): FO4 draws no blended lit surface but a decal, so FNV blends become decals, insect-wing or glass effect materials, or cut-outs with their see-through triangles split off. **Step 9, the cell's objects, played 2026-10-06**: misc items, leveled lists and containers ([items](fo4_spikes.md#spike-2-items)); furniture with seats and beds from FNV's markers ([furniture](fo4_spikes.md#spike-2-furniture)), after Elric was found to read FNV's motion types and node rotations in Havok 2014's terms; activators with their converted scripts, messages, triggers and drinkable water ([activators](fo4_spikes.md#spike-2-activators)). **Step 10, navmesh, played 2026-10-06** ([navmesh](fo4_spikes.md#spike-2-navmesh)): FNV's authored navmesh as FO4 NVNM 15 in the NAVI singleton; Doc follows the player through the house. **Step 11, Doc's intro quest (VCG01), built** ([vcg01](fo4_spikes.md#spike-2-vcg01)): the quest and its scripts, Doc's scripted lines, the Reflectron, the psych test as scenes with XDI menus, and Doc's AI packages, played to the door 2026-10-06. Next: Doc after the intro ([his quests](fo4_spikes.md#spike-2-doc-quests), built 2026-10-09: VFreeformGoodsprings and VDoctors, one greeting and topic list for every cell quest); sounds and open/close animation built and played (row above) |
| [Pipeline](fo4_pipeline.md) | **Planned 2026-10-10.** Grows on the Skyrim converter's stack (which already converts all of FalloutNV.esm), not on the spike's `cell.py`. **Step 1 built 2026-10-10:** no FormID is counted any more ([FormIDs](fo4_spikes.md#formids)); FNV's own ids for one-to-one records, hashed ids for generated ones, FalloutNV.esm's ids reserved first. **Step 2, the record census, built 2026-10-10** ([census](fo4_pipeline.md#census)): every FO3/FNV type routed to its FO4 type (`fo4_import/record_routes.py`); 27 types (86% of FNV's records) have a spike converter, 23 are partly converted, 57 (8,472 records, mostly the rules data AI and quests need) are not started. **Step 3, the pipeline skeleton, built 2026-10-10** ([skeleton](fo4_pipeline.md#skeleton)): `fo4_import.pipeline.run` builds the spike block with the export read once, meshes converted on every core into a cache, Elric's output cached, scripts compiled only when changed; byte-identical to the spike's plugin, 362 s → 168 s cold, 108 s rebuilt. **Placed-type converters and `--region` built 2026-10-10** ([converters](fo4_pipeline.md#converters)). **Exterior navmesh built 2026-10-10** ([exterior navmesh](fo4_pipeline.md#exterior-navmesh)): every navmesh in the build, linked across cells with FO4's facing-edge byte; played. **Interiors reached by doors built 2026-10-10** ([interiors](fo4_pipeline.md#interiors)): a build includes every interior its doors lead into (9 for the spike block, 27 for Goodsprings to Primm); played. Script properties now take FO4's engine globals (`GameHour`). **Goodsprings to Primm built 2026-10-10** ([region](fo4_pipeline.md#region)): 252 cells, 27 interiors, 20,725 references, 400 navmeshes, 177 s with meshes cached; played once: interior rooms and portals, ragdoll poses, fog max and height-fog colors fixed after it ([rooms](fo4_pipeline.md#rooms)); interior fog still renders brighter than FNV's. **Region play-tests 2026-10-10/11, played:** collision, joints, locks, lights, lighting templates, emittance, glow, effect animation, particles, add-ons, land texture blending, FNV climate and weathers. In test: enable parents, region emittance. **Order reworked 2026-10-11** ([order](fo4_pipeline.md#order)): close the region's world (frame rate, build time), then the rules records, real NPCs and the opening quests in the region, then the whole Mojave, then LOD; visual parity work is [parked](fo4_pipeline.md#parked). **Step 1 measured 2026-10-11** ([measured](fo4_pipeline.md#region-measured)): the frame rate holds the 118 cap Doc's to Primm (GPU 24%), so no precombines here; the build takes 183 s with a 5.8 GB peak, and about 60% of a cached rebuild is uncached textures, the Elric read-back and the test chest's outfits. **Work cache built 2026-10-12:** those are now cached; rebuild 183 s → 86 s, output byte for byte the same. **Audit 2026-10-12** ([audit](fo4_pipeline.md#audit)): FO4Edit's check and a coverage census now run on a build; links to references never built and the scripts of containers and misc items fixed; the rest of what it found (idle markers, ownership, consumable effects, water, mines, music, looping sounds) placed in steps 2 to 5. **Step 2 started 2026-10-12:** all FNV globals ([globals](fo4_pipeline.md#globals)) and factions ([factions](fo4_pipeline.md#factions)) converted, FO4Edit-clean; dropped dialogue lines now counted by blocking condition (279 of 388 wait on actors, 84 on quests). Ownership (faction and stand-in owners on 74 references and 11 cells) and map markers (15, with FNV's names, types and discovery radius) built 2026-10-12, FO4Edit-clean, played 2026-10-12: owned doors, beds and a Goodsprings house's items show as owned; markers discovered, fast travel works. Locations (a Mojave root plus FNV's 34 map regions; cells by region polygon, interiors through their doors) and the 17 encounter zones built 2026-10-12 ([locations](fo4_pipeline.md#locations)), FO4Edit-clean, not played. Classes, races, combat styles, voice types, leveled NPCs and form lists move into step 3, where NPCs use them. **Step 3 started 2026-10-12** ([npcs](fo4_pipeline.md#npcs)): 84 FNV NPCs (60 male faces fitted) and 90 actors in their own cells, on vanilla bodies with FNV's factions, packages and scripts; lines dropped on the speaker test 279 → 85; conversation ids re-keyed on authored data (approved drift, then stable: all 649 earlier dialogue records keep their ids as lines arrive). FNV outfits and inventories built 2026-10-12 (81 of 84 NPCs dressed, 46 weapons; unlisted armor, guns and melee take rule-based defaults), FO4Edit-clean. FaceGen, voice types (played 2026-10-12), leveled NPCs and the opening quests (Ghost Town Gunfight) followed |
| [Tool audit](fo4_tool_audit.md) | **Audited 2026-10-15**: bugs, speed and silent drops before the whole-map build. **Fixes built 2026-10-17:** a FormID ledger beside the plugin (`<plugin>.formids.tsv`) and authored keys for every counted id ([ledger](fo4_pipeline.md#formid-ledger)); several worldspaces per build, exterior door pairs and `--no-test-cell` ([worldspaces](fo4_pipeline.md#worldspaces)); the source plugin read from the export, not a fixed FalloutNV.esm ([source](fo4_pipeline.md#source-plugin)); FNV's water heights ([water](fo4_pipeline.md#water-heights)); the scripts, items, faces, voice, NPCs, meshes and assets findings ([fixes](fo4_pipeline.md#audit-fixes)). The region rebuilt with 0 FormIDs moved: 13 records added, 131 changed (water in 4 cells, 3 linked references, weapon and headgear meshes, landscape spec names, the new-game alias script); fo4_audit counts unchanged. **Remaining items closed 2026-10-17** ([fixes](fo4_pipeline.md#audit-fixes)): Hub lines indexed by topic; mesh files kept per mesh (a region rebuild's asset step 13.2–13.7 s → 8.1–8.2 s); idle markers by what their idles play (1,316 of FNV's 1,424 placed, 671 before); stale FaceGen pruned (63 staged files); script batches run as many at once as free memory holds, and a script failing with no error of its own is compiled again. Region rebuilt: 18 idle-marker references added, two Quarry Junction deathclaws' patrol packages now reach their markers, 0 FormIDs moved. Not played **Published face fits built 2026-10-17** ([published fits](fo4_pipeline.md#published-face-fits)): the work cache's face fits export to a pickle-free file keyed on the fit code and a hash of each sex's basis arrays, which a user installs instead of fitting ~2,247 faces (1.5–2 h); a region rebuild from an empty face cache took all 133 face keys from it, fitted none, and wrote a byte-identical plugin. Not yet published. **Play-test fixes 2026-10-18, played:** 24-unit stairs climbable ([steps](fo4_spikes.md#spike-4-exterior)); corpses no longer vanish in interiors FNV covers only partly with rooms, whose rooms and portals are left out ([rooms](fo4_pipeline.md#rooms), drift); a topic option shows only when one of its answers passes ([conditions](fo4_pipeline.md#dialogue-conditions)); male outfits' left sleeves no longer snap onto the neck ([outfits](fo4_spikes.md#spike-4-outfits)). Region rebuilt, 0 FormIDs moved. **2026-10-19, played:** quests whose variables a built script writes are built ([quest scope](fo4_pipeline.md#quest-scope): VCG01Test and 8 more); Say Once markers moved to their own quest, as FO4's GetStage reads the highest done stage ([say once](fo4_pipeline.md#say-once)): Doc's intro runs stages 0 to 200 and the psych test tallies the answers. `SetPlayerTagSkill` (the test's tag skills) converted since |
| [Idle animations](fo4_idles.md) | **Planned and spiked 2026-10-19** ([plan](fo4_idles.md)): FNV's human `.kf` clips retargeted onto FO4's skeleton and written as Havok 2014 clips ([clips](fo4_idles.md#clips)); the idles a build's scripts and lines use as FO4 dynamic idles on FNV's FormIDs, with FNV's conditions; lines carry FNV's speaker and listener idles, now in the export ([records](fo4_idles.md#records)); seated clips crashed on both the root and the furniture graph and are left out ([seated](fo4_idles.md#furniture)). **Played 2026-10-19:** with seated idles left out, Doc's intro gets past "How'd I do?" and his chair stand-up. A seated clip played by script on the chair's furniture graph works: Doc's mirror hand-over played, no crash ([seated](fo4_idles.md#furniture)). Played by script at every line's start, seated idles played through the psych test, then crashed in a later graph update; removed. Doc's card points, shrug and "Whoa there" play nothing ([seated](fo4_idles.md#furniture)). **Switched off 2026-10-19** ([off](fo4_idles.md#off)): the scripted mirror alone still crashed once later, so the clip encoder is the suspect; builds write no FNV idles. A scale channel vanilla never has was fixed, unproven. **Encoder test played 2026-10-19/20** ([encoder test](fo4_idles.md#encoder-test)): the encoder is cleared; the crash was FNV clips naming their annotation tracks, which vanilla leaves blank. Blank, Doc's FNV mirror clip plays without a crash. Standing idles back on 2026-10-21, played ([standing](fo4_idles.md#standing)). **Ambient idle tree built 2026-11-06, not played** ([trees](fo4_idles.md#trees)): FNV's `GeneralIdles` under FO4's `ActionIdle` (drunk walk, smoking, swatting, scratching, nose-picking, nail-biting); whether the engine runs it on the human root graph is untested. **Props built 2026-11-07, not played** ([props](fo4_idles.md#props)): 11 FNV prop meshes shown as vanilla objects (cigarette, wrench, Med-X, stimpak, clipboard, pencil, chalk, dish rag, Sandman knife). A prop with no vanilla stand-in is converted ([converted props](fo4_idles.md#converted-props)). It gets an ANIO on FNV's FormID, its mesh hangs from an FO4 prop bone, and the clip's prop-bone track carries FNV's motion of it: Doc's mirror, the Rorschach cards, the Pip-Boy, the guitar, Benny's 9mm, the test paper. Next: creature clips |
| <a id="own-rig"></a>[Creatures on their own rig](fo4_own_rig.md) | **Gecko played 2026-10-27 in a test plugin** ([ragdoll](fo4_spikes.md#own-rig-ragdoll)): moves, attacks, dies with a ragdoll, knocked down and up. **Converter mode `rig` built 2026-10-27, not built into a plugin or played** ([parity](fo4_own_rig.md#parity)): Havok 2014 packfile reader, writer and graph builder (`fo4_import/havok`), the rig table and `fo4_import/rig` (skeleton, clips, skeleton.nif, bodies, behaviour, records) reproducing the played gecko's files; the Creation Kit writes the animation data after the plugin ([anim info](fo4_own_rig.md#anim-info)); `creatures\nvgecko` defaults to it. Built into F3NV Rig Test and played 2026-10-27: geckos work. **FNV size, sounds and abilities for every creature mode built 2026-10-27, not played** ([sounds](fo4_own_rig.md#sounds), [abilities](fo4_perks.md#records)). Nightstalker played 2026-10-27. **Giant mantis played 2026-10-27** ([mantis](fo4_own_rig.md#mantis)): looks right, moves, attacks, ragdolls. **Cazador played 2026-10-27** ([cazador](fo4_own_rig.md#cazador)): moves, attacks, its poison and FNV's woozy effect land; own-rig attack spells built (nightstalker and golden gecko not yet played). **Every other FNV creature built 2026-10-27, not played** ([remaining](fo4_own_rig.md#remaining)): rigs for giant rats, ants, the queen ant, spore carriers, centaurs, spore plants, ravens; turrets and robobrains on FO4 stand-ins. **FNV's talking machines built 2026-10-27, Mr. House's penthouse screen played (talks; its screen image waits on screen animation)** ([talking machines](fo4_creature_audit.md#talking-machines)): Mr. House's screen and pod, Yes Man, Festus as unseen speakers beside their FNV models. **Securitrons played 2026-10-28** ([ranged](fo4_own_rig.md#ranged), [talk](fo4_own_rig.md#talk)): on `ProtectronRace`, Victor talks (Goodsprings) and fires his SMG steadily while walking, the shot an arm layer like FO4's robots; **each gun in its own equip slot played 2026-10-28**: force-equipped by an actor mod as FO4's turrets do, its slot naming a gun node on FNV's fire node, Victor switches between SMG and rockets, rockets level from the left arm; face screen missing. the Mk II's laser and missiles played; **creature ranged attacks played 2026-10-28**: fire ants flame, centaurs and spore plants spit (FO4 creature guns, each node aimed level ahead at its shot). **Think Tanks on their own rig and creature idles on every rig built 2026-11-06, not played** ([think tank](fo4_own_rig.md#think-tank), [idles](fo4_own_rig.md#idles)): Old World Blues' Think Tanks leave Mr. Gutsy for their own skeleton, body, clips and two guns firing from FNV's `Weapon` node; FNV creature idles whose clip is in a rig folder play on that rig as vanilla creatures' `dynamicAnim` idles. Next: other ranged creatures, rigid parts on rig bodies, animated screens, the Lucky 38 elevator box |
| [Perks](fo4_perks.md) | **Census done 2026-10-20** ([census](fo4_perks.md#census)): 176 FNV perks; of 143 entry-point effects 85 map directly onto FO4's, 29 with changes (Damage Threshold, abilities, Activate), 29 have no counterpart; 49 abilities and 20 quest stages carry over; 142 `HasPerk` conditions and 51 script calls wait on them. **PERK records built 2026-10-20, not played** ([records](fo4_perks.md#records)): 207 records (FNV's ranks as FO4 chains, earlier ranks off once the next is held), 41 ability spells, vanilla effects for Computer Whiz, Paralyzing Palm, Concentrated Fire and Grim Reaper's Sprint. FNV's weapon skill, weapon animation and creature type tests are keyword tests on keywords the build stamps on converted weapons and creatures, for perks, lines and idles ([type tests](fo4_perks.md#type-tests)). **Level-up list and `HasPerk` built 2026-10-21, not played** ([HasPerk](fo4_perks.md#hasperk)): LevelUpMenuEx offers FNV's 91 playable perks (traits keep their own menu); perks fill converted scripts' Perk properties; `HasPerk` converts in lines (32 were blocked), recipes (17 now built) and 129 consumable effects. **Teammate perks built 2026-10-22, not played** ([teammate perks](fo4_perks.md#teammate-perks)): the player holds FNV's 6 flagged perks with no effects, and the companion each names holds a perk of its entry points, gated on following and the player's perk (vanilla's CompanionInspirational pattern). Next: the play-test |
| [Gun clips](fo4_spikes.md#spike-4-gun-clips) | **Built and played 2026-10-28/29, good enough for now:** FNV guns convert natively (their own mesh and first-person clips on an FO4 template's graph), no external mod. Near-identical FO4 guns stay FO4's (`"as": "stats"`); uniques and every other gun convert, an unlisted one on the template `gun_choice` picks. Played: 9mm, Assault Carbine, Hunting Rifle, Flamer, Tesla Cannon, Laser Pistol, Varmint, BB Gun, Sniper Rifle (scope zoom), heavy guns, most of the test chest. `tools/nif/gun_quick_convert.py` converts and measures every gun offline; `gun_pose_scene.py` with `blender_pose_scene.py` shows a hold beside FNV's and FO4's. Parked tweaks [below](#parked) |
| [Radio](fo4_radio.md) | **Built 2026-10-22** ([plan](fo4_radio.md#steps)). Played: transmitters in the Pip-Boy; Mojave Music Radio with full songs once each station's Host alias was voiced ([radio dialogue](fo4_radio.md#radio-dialogue)); Trudy's radio in the Prospector Saloon as a receiver ([receivers](fo4_radio.md#receivers)). Every station as step scenes following FNV's Choices ([steps](fo4_radio.md#steps-model)): Radio New Vegas played (news, then songs); not played: Black Mountain (songs and segments) and the casino and Tops lounges on frequencies only their radios tune. Left: topics FNV's scripts say directly (Black Mountain's events, RadioGoodbye) |
| [Item condition](fo4_condition.md) | **Spike played 2026-10-22** ([results](fo4_condition.md#spike-results)): weapon health stores and saves in the engine's own item health through our F4SE plugin, but FO4's condition test and Pip-Boy ignore it on weapons, so effects and display are ours (a hybrid of the plugin and AWC's tier mods). **Built 2026-10-22/23**; status in the table above |
| <a id="fo4-app"></a>[Conversion app](fo4_gui.md) | **Designed and built (phases 1 to 6) 2026-10-24, not played.** A separate PySide6 app for FO3 and FNV: every location chosen by the user, mods read from plain folders (MO2 profile optional), loose-folder output, a two-column Replacements screen with 3D previews on the repo's own NIF readers. **Phase 1 built 2026-10-24, not yet used in a build** ([mod sources](fo4_gui.md#mod-sources)): `fo4_import/app/settings.py` (the choices file, portable or in the OS config folder); `core/game_dirs.py` (install detection through the registry or Steam, on any OS; `install.py` detects the same paths as before on this machine); `core/mod_sources.py` (folder-of-mods, flat and MO2-profile sources; checked read-only against `C:/Modlists/fo3fnv-in-fo4`, where Spike gives 17 folders and 21 plugins); `run.py --mod-sources` and case-blind plugin lookup. **Phase 2 built 2026-10-24** ([replacement data](fo4_gui.md#replacement-data)): `fo4_import/data/replacements.json` by category with `_rules` (creatures by skeleton folder, NPC bodies, armor by biped slot, melee by animation type; formerly code dicts), layers defaults → `--profile` → `--replacements` with each entry's origin, uninstalled plugins fall back with a warning, creature `item` mode (a DLC's or mod's creature as it is), DLC masters first in game order. The spike block (3×3 around Goodsprings, Doc's house, test chest) rebuilt before and after: FormID ledger identical (0 moved), 13,707 records, one differs: the test chest's 104 items in a new order. **Phase 3 built 2026-10-24** ([catalog](fo4_gui.md#replacements-screen)): `fo4_import/app/files.py` (loose then BA2, winning folder first, ignoring case) and `fo4_import/app/catalog.py` (per plugin and category: EditorID, localized name, model, armor's worn model, stats, override owner). Checked read-only on Fallout4.esm, the DLCs and the MO2 mods: 67 plugins, 16,871 entries in 1.4 s with the file index, so no cache; vanilla and mod meshes and textures resolve from their archives. **Phase 4 built 2026-10-24** ([preview](fo4_gui.md#preview)): `fo4_import/app/preview/` reads FO4 NIFs and their BGSM/BGEM or texture sets (diffuse, normal, specular, greyscale palettes) and draws them with moderngl, in a Qt window (`python -m fo4_import.app.preview <mesh>`) or off screen (`--png`). The 10mm pistol, Dogmeat, a converted pre-war outfit and the converted coyote render; the Qt window paints on OpenGL 3.3 core. FO3/FNV raw meshes, gun assembly from OMODs, macOS and Linux not done. **Phase 5, the alpha app, built 2026-10-24** ([as built](fo4_gui.md#app-shape)): `py -3.14 fo4_app.py`; first-run wizard, Setup (every location a choice; settings beside the app or in the OS config folder), Convert (stages as the existing commands, unavailable ones disabled with the reason; test block, region or whole world; live log, Stop), Finished (results, warnings, Open folder, install notes; zip output). Driven off screen: scripts, helpers, build and check of the test block ran to a scratch folder, FO4Edit 0 errors in 13,707 records, the same FormIDs as the command line. Not in the app yet: export folder choice, Wine, F3NV.dll, Bink, FaceGen. **Phase 6, the Replacements screen, built 2026-10-24** ([as built](fo4_gui.md#replacements-screen)): two columns per category: the source forms with what stands in now and why (the converter's own rules; skipped creatures in red), and the records of Fallout 4 + DLC or any installed plugin with the modes the loader allows; Apply and Revert write the user's replacement file. 3D previews of FNV's converted mesh, the stand-in and the pick; FO4 guns assembled from their default parts on their connect points; NPCs on their skins. Checked on the user's 67 plugins (loads in 3.4 s); a mod's gecko (`Geckos.esl`) applied and built: master added, six gecko template actors use it, FO4Edit 0 errors. Not played. The app's Check stage runs the headless [reference check](../reference/python_tools.md#fo4-ref-check); FO4Edit's full check is an optional stage, unticked by default (it waits for its developer-message dialog when unattended). Next: phase 7 (opt-in MO2 setup, Play, modlist status) ([phases](fo4_gui.md#phases)) |
| [Challenges](fo4_pipeline.md#challenges) | **Built 2026-10-23, not yet played:** 61 of FNV's 105 challenges counted by `F3NV_Challenges` from FO4 events (kills, tracked stats, uses, map markers, crippled limbs), FNV's reward scripts cast on completion, a CHALLENGES tab on STAT. Left out: 44 with no FO4 event ([list](fo4_pipeline.md#challenges-left-out)) |

## <a id="inherited"></a>Inherited from the Skyrim fork

The sections below are the `standalone` branch's status for the Skyrim
target, carried over as they were; they say nothing about the Fallout 4
build. Its docs (`character.md`, `standalone_play.md`, `kill_cams.md`,
`done/`, `research/character_findings.md`, `research/graphics_options.md`)
stay unedited so merges from `standalone` stay clean.

## <a id="phases"></a>Phases

1. **Stable ground.** Play everything written but not yet played (below), run
   the preflight audits after every build, and land the two safest Papyrus
   cost fixes.
2. **The stats sheet.** Character pieces T and G1 (data, then a sheet that
   writes nothing), then checks S1 to S3, then F.
3. **Setup without hand work.** Standalone play pieces B, C and D, then H.
4. **Systems with gameplay weight.** Item condition (H; built for Fallout 4, above), level-up and chargen
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

- **Play-test backlog:** [built, never played](#fo4-unplayed).
- **Preflight audits on the FO4 build:** built 2026-10-25, not committed
  (`py -3.14 -m tools.validate.preflight --fo4 <plugin>`, [fo4_preflight.md](fo4_preflight.md)):
  quest, start, dialogue, packages, world, assets and build on the FO4 plugin,
  plus a condition differential (each built line against its FNV line). First
  run on the whole-map build: 801 errors and 128 to review (the 20 condition
  findings were the audit's own stale-ledger mistake, fixed); reruns since are
  in the Preflight findings row ([results](fo4_preflight.md#results)), and
  `--audit properties` (built 2026-11-04) checks unfilled script properties.
  Script health and log triage stay Skyrim-only.
- **[Dialogue menu audit](fo4_menu_audit.md):** planned 2026-10-25, not
  started. Revised the same day: exact checks on what the build adds to make
  menus (structure, one option per topic, option gates, per-line effects) in
  place of trying every state and walking conversations; skill checks and
  reputation paired first (about 2,300 FNV lines no audit judges); FNV's
  rules from its exe, FO4's from XDI's source and its exe; the play log built
  on `fo4_trace`. No FNV game runs (wiki files, GECK, xEdit and
  `PrintNPCDialog` ruled out). Six phases; the first whole-map report comes at
  phase 2.
- **[Progress timing audit](fo4_timing_audit.md):** phases 1 and 2 built
  2026-10-29, not committed (`--audit timing`, about 60 s; [built](fo4_timing_audit.md#built)).
  First run on the 2026-10-29 whole-map build: 13 errors, 104 to review. 3
  topics show too soon (the Freeside vagrant's VMS49 "antique gun" topics), 2
  too late (Regis, Mortimer); 3 quests never complete (VMS38, VMS22, VES34Vault:
  Complete Quest flag dropped with flag-only log entries); 4 blocks dropped
  (`OnFire` x3, Legate's OnActorEquip); 3 MenuMode stage sets on the timer
  and 101 Choice or derived unlocks to review. Phases 3 to 6 not started.
  **Converter fixes made 2026-10-29** ([fixes](fo4_timing_audit.md#fixes)):
  flag-only Complete Quest stages, `OnFire` on weaponFire, an actor's
  OnActorEquip on OnItemEquipped, Fallout Top-level topics never gated (FNV 41,
  FO3 13), greeting-revealed topics kept gated when the greeting waits for more
  (VMS49 x3); Oblivion's unlock plan unchanged. In another session's whole-map
  build of 2026-10-29 22:54 (`temp/profile_data`): timing audit 0 errors, 88
  to review; 0 FormIDs moved, 41 `TES4Unlock_` globals removed (the Top-level
  topics). Not deployed or played. Euclid's C-Finder still needs PlaceAtReticle.
- **[One option per topic](fo4_pipeline.md#one-option-per-topic):** built
  2026-10-26; **Jason Bright's pair played 2026-10-26** (one option at a
  time), Doc Mitchell's caps pair not yet. The whole-map build showed one FNV topic as two
  options at once (Jason Bright's "Not interested." pair, Doc Mitchell's caps
  pair) since `conversation.py` had lost the spike's "no earlier option"
  test. Each option now hides while a line FNV tries first passes (speakers'
  voice types and factions settled, at most 16 OR-groups per option): menus
  able to show two options of one topic fell from 760 (113 topics) to 152
  (8: GOODBYE at the cap, three counted only for lack of speaker facts, four
  with a loose earlier gate). Options' tests grew from 27.9 to 57.1 MB, 95%
  of it GOODBYE; the plugin from 403 to 432 MB.
- **Preflight audits:** built (`python -m tools.validate.preflight`, `--audit
  logs` after a play-test). Open gaps:
  - audit 1 doesn't check stage-item conditions or Say Once lines;
  - audit 2 doesn't evaluate condition-filled aliases, and marks required
    ones for review;
  - audit 4 uses the quest audit's dialogue models rather than the two
    emulators;
  - audit 6 doesn't check that quest actors have a package bringing them to
    their scenes.
- **[Kill cams and killmoves](kill_cams.md) (Skyrim target):** not started.
  Skyrim's killmoves misfire on converted weapons (FO3/FNV's baton plays a
  sword killmove). Options recorded; the first step is the census of the
  vanilla killmove conditions. Fallout 4 has no such issue known, only a
  play-test check ([Fallout 4](kill_cams.md#fallout4)).

## <a id="performance"></a>Performance

| Item | State |
|---|---|
| [Papyrus cost](performance.md#papyrus) 2: GameMode loops | Not started; first, safest |
| Papyrus cost 1: quest poll interval | Built for Fallout 4 2026-10-15 (not timed in game); not started for Skyrim |
| Papyrus cost 3: dialogue state in actor values | Not started |
| Papyrus cost 4: patrol arrival checks | Not started; lowest |
| [FO3/FNV occlusion](performance.md#occlusion) | Fallout 4 copies FNV's rooms, portals and occlusion planes; not started for Skyrim |

## <a id="standalone-play"></a>Standalone play

| Item | State |
|---|---|
| Pieces A to H | Not started. MO2 profiles `FNV`, `FO3` and `Oblivion` exist, made by hand |
| World picker on the main menu | Candidate; needs DLL work |
| Upstream PR #65 | Open, with the plan's earlier copy; the fork's copy has moved on |

## <a id="parked"></a>Parked

| Item | Why |
|---|---|
| [Bink movies](bink_movies.md) | Not parked for FNV any more (status above). **Built 2026-10-12** for the FO4 build ([as built](bink_movies.md#plan)): source movies shipped with their audio as tracks 1-5, `PlayBink` converted, calls to unshipped movies dropped. FNV: the intro converts, 3 dead calls dropped. FNV intro played 2026-10-14 (the new game). Open: FO3 intro, untested (no FO3 build path yet), other languages' track IDs |
| [Gun hold tweaks](fo4_spikes.md#spike-4-gun-clips) | Converted guns work; visual polish only (2026-10-29). 2026-10-31: third person's left hand put on our guns (each gun's own `WPNAssemblyPose`), not played; the Flamer's reload checked to be FNV's own. Still open: the left hand leaves the rifle for a moment going into aim (the local blend measures at most 1.6 units, so the cause is elsewhere); the right hand shows while aiming the lever-actions, single and riot shotguns, BB guns and .22 SMG (20–40% by `gun_quick_convert`'s aim_hand); heavy guns sit low on screen (11–32%; centring the body on the template's folded the arm into the camera, reverted) |
| LOD gaps in the landscape | Reported 2026-11-06 (WastelandNV, near the rail line): distant terrain shows holes and dark blocks that close up as the player nears. Visual polish, for the later look pass with the rest of [object LOD](fo4_pipeline.md#object-lod) and [terrain LOD](fo4_pipeline.md#terrain-lod); not investigated |
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
