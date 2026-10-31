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
| [bink_movies.md](bink_movies.md) | Source-game Bink 1 movies on Fallout 4: census (36 movies), playback, plan, play test |
| [research/](research/) | Findings and notes that are not plans: [character findings](research/character_findings.md), [graphics options](research/graphics_options.md), [Fallout 4 as the target](research/fo4_target.md), [dynamic collision for FO4 (parked mod idea)](research/fo4_dynamic_collision.md), [NVSE features for FO4](research/nvse_port.md), [FO4 creature rig prior art](research/fo4_creature_rig_prior_art.md), [Damage Threshold reference (Zoltanite)](research/fo4_damage_threshold_reference.md) |
| [done/](done/) | Plans that are built, kept as their design record: [preflight audits](done/preflight_audits.md) |
| [fo4_spikes.md](fo4_spikes.md) | The spikes that showed FO3/FNV on Fallout 4 buildable (done), and the findings they made |
| [fo4_pipeline.md](fo4_pipeline.md) | The plan from the spike to the whole of FNV: the base it grows on, what to build and research first, speed, stability, order |
| [fo4_tool_audit.md](fo4_tool_audit.md) | The converter audit before the whole-map build (2026-10-15): bugs, speed, overlooked issues, with counts |
| [fo4_preflight.md](fo4_preflight.md) | The preflight audits on the FO4 build (`--fo4`): scene dialogue model, assets, the condition differential, first results |
| [fo4_timing_audit.md](fo4_timing_audit.md) | Plan: the progress timing audit (each fact's start value, writers and prerequisites against FNV's, so quests, stages, topics and options unlock no sooner or later than in FNV; first measurements) |
| [fo4_menu_audit.md](fo4_menu_audit.md) | Plan: the dialogue menu audit (exact checks on the pieces the build adds to make menus: structure, one option per topic, option gates, effects; both games' rules from XDI and the exes; menus logged in play) |
| [fo4_creature_audit.md](fo4_creature_audit.md) | Every FNV creature field through the export and each converter path into FO4: what is carried, dropped or left over from the cloned stand-in (audit 2026-10-27; void list entries, scripts on bases and the Unique leak fixed, built in F3NV Rig Test and played; template slots built and played; inventories built and played; placed-actor scale, No AI Acquire and actor links built, not played; template actors' own speed and size built and played; Base Data and death item chains, Invulnerable and Is Ghost built, not played; the stand-in leftover check built; ghouls: glowing ones on FO4 glowing ones, ghoul radiation healing and script-effect abilities built and played; refraction surfaces built, not played; FNV attack spells (EITM) built, deathclaw knockdown as a player stagger played; the whole map not rebuilt) |
| [fo4_replacements.md](fo4_replacements.md) | The user-editable replacement table (items, then creatures: FO4 records, FNV stats, FNV meshes on FO4 rigs, other mods' records), its profiles and GUI, and the Wabbajack modlist as a soft requirement for the full experience |
| [fo4_idles.md](fo4_idles.md) | FNV idle animations on Fallout 4: `.kf` clips retargeted to FO4's skeleton, IDLE records as dynamic idles, idle trees, seated idles |
| [fo4_perks.md](fo4_perks.md) | FNV perks and traits on Fallout 4: the entry-point census, the plan, `HasPerk` |
| [fo4_drift.md](fo4_drift.md) | Where play on Fallout 4 differs from FO3/FNV, and which game's system each area uses |
| [fo4_build_next.md](fo4_build_next.md) | Plan: the items left on Fallout 4, in order, with what research found for each |
| [fo4_plugin_layout.md](fo4_plugin_layout.md) | Plan: the plugin layout (game, rules, per-DLC, mod patch plugins), FormIDs across plugins, and incremental record builds |
| [fo4_condition.md](fo4_condition.md) | Item condition: wear, repair, the Pip-Boy repair and ammo lists, jams, vendor repair (the F3NV F4SE plugin) |
| [fo4_radio.md](fo4_radio.md) | FNV's radio stations as Fallout 4 radio |
| [fo4_look.md](fo4_look.md) | The plan for FNV's look: grass (density, where it grows, flecks) and lighting (weather haze, clouds, night, glow, lights, tone) |
| [fo4_pipboy_tabs.md](fo4_pipboy_tabs.md) | The Pip-Boy's SKILLS, REPUTATION, KARMA and CHALLENGES tabs, drawn by our plugin |
| [fo4_gui.md](fo4_gui.md) | The FO3/FNV conversion app: user-chosen locations, mod sources from any folder (MO2 optional), the two-column Replacements screen with 3D previews, Windows/macOS/Linux |

## <a id="fo4-systems"></a>Fallout 4: where each FNV system stands (2026-10-29)

Built into `FalloutNV.esm` (MO2 mod "F3NV - Fallout New Vegas") and played in
the Goodsprings to Primm region unless it says otherwise. Where play differs
from FNV is in [fo4_drift.md](fo4_drift.md); what is left is
[below](#fo4-next). The rows under the next heading are the history that led
here.

**Deployed build (2026-10-30 08:36):** the whole map with every change below and build-next items 1 to 4,
a pure build (no other mods' records), not yet played. Committed: through
`52c14e64` (guns, Papyrus tracing, rig research); everything since, from the
sound archive writer on, is uncommitted.

| System | Status |
|---|---|
| World, NPCs, dialogue, quests | Built and played in the region. **Whole map rebuilt 2026-10-29, deployed, not played** ([whole map](fo4_pipeline.md#whole-map)): WastelandNV and every worldspace a door reaches; 2,245 NPCs (910 template actors), 113,921 dialogue lines, 4,700 navmeshes, 13,511 of 13,511 scripts compile, a 438 MB plugin, 0 FormIDs moved against the morning's build. 47 placed creatures of 14 kinds are left out (super mutants, nightkin, REPCON ghouls; 1,036 of 121 kinds on 2026-10-24, before every creature had a rig): a converter bug, as they take their model from a template without its traits ([no base](fo4_build_next.md#no-base)). Sounds and voices in `FalloutNV - Main.ba2` ([sound archive](fo4_pipeline.md#sound-archive)). **Terrain LOD built 2026-10-24, not played** ([terrain LOD](fo4_pipeline.md#terrain-lod)); object LOD not started |
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
| Hardcore needs ([survival needs](fo4_pipeline.md#survival-needs)) | FNV's food, drink and caffeine feed Survival's needs: built, not played |
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
| FNV DLC ([DLC build](fo4_plugin_layout.md#dlc-build)) | Gun Runners' Arsenal as `GunRunnersArsenal.esm` on FalloutNV.esm, its own data folder and MO2 mod (`F3NV - Gun Runners Arsenal`): built 2026-10-30, gaps closed 2026-10-31 (its own subgraph race; the Ammo Type, condition and challenges quests merged row by row), not played. Open: the build still writes 4,190 copies of the game's files (left out at deploy); two DLCs overriding one list or quest, the last wins |
| Not started | See [what is left](#fo4-next) |
| Look pass ([fo4_look.md](fo4_look.md)) | **Played 2026-10-23/24:** weathers graded by FNV's worldspace imagespace and weather tints, vanilla clouds in FNV's colours, exterior depth of field; night and noon match FNV after each weather's directional ambient took FNV's ambient ([night](fo4_look.md#night)); windows; the saloon's flickering "SAL" (looping activators made statics, no box from blended unlit tubes); the "ON" bulbs and the graveyard lantern ([lanterns](fo4_look.md#lanterns)). Glows follow vanilla's ranges per kind ([emissive](fo4_look.md#emissive)); neon ("O", OPEN) parked until the Strip is converted. **Built, not played:** grass density (1/16), grass placement (grassy textures kept past the 4-texture limit, [grass-ground](fo4_look.md#grass-ground)), soft light-ray cones. Open: the grass shards; FNV's horizon glow at night |
| Needs one play test | The silent player voice; ambient two-NPC conversations |

### <a id="fo4-next"></a>What is left (2026-10-29)

**Play first.** Nothing from 2026-10-29 has been played. In the order a play
test meets them: the new game (health 200 at Endurance 5, run speed), a
gunfight (FNV's cone, criticals, Damage Threshold, sneak attacks, V.A.T.S. at
2%), chems (addiction and withdrawal), poisons on a melee weapon, the perks
picked at level 2. Then the rows above marked not played:
challenges, reputation, disguises, weapon mods, combat styles, ammo,
survival needs, lockpicking, vendor repair, the whole map itself.

**Verify, cheaply, in that play test:** FO4's aim cone is a half-angle as
FNV's (fire at a wall at a known distance); V.A.T.S. at 2% brings no stuck
slow-motion audio; the CarryWeight nudge makes the SpeedMult take; the
Creation Kit's archive wait is shorter.

**Build next** (the plan, in order: [fo4_build_next.md](fo4_build_next.md#order)):

| Item | Size | Notes |
|---|---|---|
| Items 1 to 4: creatures with no base, the `[Speech 50]` tag, creatures' Combat skill, scoped sway | — | **Built 2026-10-30**; the skill tag played 2026-10-31 (`[Barter 20]` on a Trudy line), the rest not yet ([no base](fo4_build_next.md#no-base), [speech tag](fo4_build_next.md#speech-tag), [creature skill](fo4_build_next.md#creature-skill), [sway](fo4_build_next.md#sway)) |
| Built-in scopes at FNV's zoom | S | Built 2026-10-31, not played ([scope zoom](fo4_build_next.md#scope-zoom)) |
| FNV's super mutant mesh on FO4's skeleton | S-M | After item 1 ([super mutants](fo4_build_next.md#super-mutants)) |
| Object LOD | L | Not started; terrain LOD built |
| Commit today's work | S | Everything after `52c14e64`, once played |
| Dialogue menu audit phase 2, timing audit phases 3 to 6 | M | Planned ([menu](fo4_menu_audit.md), [timing](fo4_timing_audit.md)) |
| Preflight findings | M | 801 errors and 128 to review on the 2026-10-25 build, none acted on ([preflight](fo4_preflight.md#results)) |
| Casino games and Caravan | L | Not started |
| Kill cams | M | Not started ([kill cams](kill_cams.md)) |
| The rest of the look pass | M | Grass shards, FNV's horizon glow at night, neon on the Strip ([fo4_look.md](fo4_look.md)) |
| Papyrus cost 2 to 4 | M | GameMode loops, dialogue state, patrol checks ([performance](performance.md#papyrus)) |
| Conversion app phase 7 | M | MO2 setup, Play, modlist status ([phases](fo4_gui.md#phases)) |
| Creature screens and the Lucky 38 elevator | M | Animated securitron and Mr. House screens ([own rig](#own-rig)) |

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
| [Idle animations](fo4_idles.md) | **Planned and spiked 2026-10-19** ([plan](fo4_idles.md)): FNV's human `.kf` clips retargeted onto FO4's skeleton and written as Havok 2014 clips ([clips](fo4_idles.md#clips)); the idles a build's scripts and lines use as FO4 dynamic idles on FNV's FormIDs, with FNV's conditions; lines carry FNV's speaker and listener idles, now in the export ([records](fo4_idles.md#records)); seated clips crashed on both the root and the furniture graph and are left out ([seated](fo4_idles.md#furniture)). **Played 2026-10-19:** with seated idles left out, Doc's intro gets past "How'd I do?" and his chair stand-up. A seated clip played by script on the chair's furniture graph works: Doc's mirror hand-over played, no crash ([seated](fo4_idles.md#furniture)). Played by script at every line's start, seated idles played through the psych test, then crashed in a later graph update; removed. Doc's card points, shrug and "Whoa there" play nothing ([seated](fo4_idles.md#furniture)). **Switched off 2026-10-19** ([off](fo4_idles.md#off)): the scripted mirror alone still crashed once later, so the clip encoder is the suspect; builds write no FNV idles. A scale channel vanilla never has was fixed, unproven. **Encoder test played 2026-10-19/20** ([encoder test](fo4_idles.md#encoder-test)): the encoder is cleared; the crash was FNV clips naming their annotation tracks, which vanilla leaves blank. Blank, Doc's FNV mirror clip plays without a crash. Standing idles back on 2026-10-21, played ([standing](fo4_idles.md#standing)). Next: idle trees, props, creature clips |
| <a id="own-rig"></a>[Creatures on their own rig](fo4_own_rig.md) | **Gecko played 2026-10-27 in a test plugin** ([ragdoll](fo4_spikes.md#own-rig-ragdoll)): moves, attacks, dies with a ragdoll, knocked down and up. **Converter mode `rig` built 2026-10-27, not built into a plugin or played** ([parity](fo4_own_rig.md#parity)): Havok 2014 packfile reader, writer and graph builder (`fo4_import/havok`), the rig table and `fo4_import/rig` (skeleton, clips, skeleton.nif, bodies, behaviour, records) reproducing the played gecko's files; the Creation Kit writes the animation data after the plugin ([anim info](fo4_own_rig.md#anim-info)); `creatures\nvgecko` defaults to it. Built into F3NV Rig Test and played 2026-10-27: geckos work. **FNV size, sounds and abilities for every creature mode built 2026-10-27, not played** ([sounds](fo4_own_rig.md#sounds), [abilities](fo4_perks.md#records)). Nightstalker played 2026-10-27. **Giant mantis played 2026-10-27** ([mantis](fo4_own_rig.md#mantis)): looks right, moves, attacks, ragdolls. **Cazador played 2026-10-27** ([cazador](fo4_own_rig.md#cazador)): moves, attacks, its poison and FNV's woozy effect land; own-rig attack spells built (nightstalker and golden gecko not yet played). **Every other FNV creature built 2026-10-27, not played** ([remaining](fo4_own_rig.md#remaining)): rigs for giant rats, ants, the queen ant, spore carriers, centaurs, spore plants, ravens; turrets and robobrains on FO4 stand-ins. **FNV's talking machines built 2026-10-27, Mr. House's penthouse screen played (talks; its screen image waits on screen animation)** ([talking machines](fo4_creature_audit.md#talking-machines)): Mr. House's screen and pod, Yes Man, Festus as unseen speakers beside their FNV models. **Securitrons played 2026-10-28** ([ranged](fo4_own_rig.md#ranged), [talk](fo4_own_rig.md#talk)): on `ProtectronRace`, Victor talks (Goodsprings) and fires his SMG steadily while walking, the shot an arm layer like FO4's robots; **each gun in its own equip slot played 2026-10-28**: force-equipped by an actor mod as FO4's turrets do, its slot naming a gun node on FNV's fire node, Victor switches between SMG and rockets, rockets level from the left arm; face screen missing. the Mk II's laser and missiles played; **creature ranged attacks played 2026-10-28**: fire ants flame, centaurs and spore plants spit (FO4 creature guns, each node aimed level ahead at its shot). Next: other ranged creatures, rigid parts on rig bodies, animated screens, the Lucky 38 elevator box |
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

- **Play-test backlog:** every "not played" row above.
- **Preflight audits on the FO4 build:** built 2026-10-25, not committed
  (`py -3.14 -m tools.validate.preflight --fo4 <plugin>`, [fo4_preflight.md](fo4_preflight.md)):
  quest, start, dialogue, packages, world, assets and build on the FO4 plugin,
  plus a condition differential (each built line against its FNV line). First
  run on the whole-map build: 801 errors and 128 to review, none acted on yet
  (the 20 condition findings were the audit's own stale-ledger mistake, fixed)
  ([results](fo4_preflight.md#results)). Script health and log triage stay
  Skyrim-only.
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
- **[Kill cams and killmoves](kill_cams.md):** not started. Killmoves misfire
  on converted weapons (FO3/FNV's baton plays a sword killmove). Options
  recorded; first step is the census of the vanilla killmove conditions.

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
