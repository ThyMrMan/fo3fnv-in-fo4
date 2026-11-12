# Roadmap and status

What works in **fo3fnv-in-fo4** today, what is built but nobody has played
yet, and what is still missing. This page shows only the current state. How
each system got here, with dates and measurements, is in the
[development log](dev_log.md) and in the docs each row links.

## <a id="fo4-state"></a><a id="alpha"></a>Alpha

New Vegas is playable on Fallout 4 from Doc Mitchell's house onward, with
its four story DLC and the five add-on packs. Nearly every system is built.
Much of it has never been played, so most of what is left is play-testing
and fixing what testers find. The casino games and Caravan are being built.
Fallout 3 has a first spike, Vault 101 and its opening, not yet played
([FO3 spike](fo4_fo3_plan.md)). Install steps are in the
[README](../../README.md#install).

The page describes build 1107i of `FalloutNV.esm`, `FalloutHelpers.esl` and
`F3NV.dll`, and the DLC and pack plugins built on it.

**States:**

| State | Means |
|---|---|
| Works | Played and working |
| Built, not played | Converted and in the build, but nobody has tried it in game yet |
| Partial | Some of it works or is converted, some is missing |
| Broken | In the build, but a player will hit a bug |
| Not built | Not converted yet |

## <a id="fo4"></a>Status by area

### The world

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Mojave landscape | The Mojave's ground, roads and land textures, built from New Vegas's own world | Works | Needs the Black Landscape Fix mod, listed in the install steps; without it a Fallout 4 engine bug turns some bare ground black. Soft land seams in a few places. | [exterior](fo4_spikes.md#spike-4-exterior) |
| Distant terrain (LOD) | The far-off hills you see before you get close | Partial | Distant water (Lake Mead, the Colorado) shows as water. Some land seams show at a distance; holes and dark blocks that close up as you approach aren't rechecked. | [terrain LOD](fo4_pipeline.md#terrain-lod) |
| Distant objects (LOD) | Low-detail buildings and landmarks seen from far away | Partial | Buildings work. Distant trees are built, not played. | [object LOD](fo4_pipeline.md#object-lod) |
| Pip-Boy world map | The Mojave map in the Pip-Boy, with New Vegas's markers | Partial | The Mojave and Freeside maps show, at the larger size. Markers sat below their places; fixed, not built. | [world map](fo4_pipeline.md#world-map) |
| Worldspaces and exteriors | The whole Mojave plus Freeside, the Strip and the other separate areas, with their doors | Partial | Trap triggers, stand-in smoke and damage stages (burning cars, their explosions) are built, not played. The skipped statics are audio markers, built as music regions. | [whole map](fo4_pipeline.md#whole-map) |
| Interiors | Buildings and dungeons with New Vegas's layout, objects, furniture and lighting | Works | | [interiors](fo4_pipeline.md#interiors) |
| Room culling | Hiding the parts of an interior you can't see, for speed | Partial | 29 interiors draw everything at once because some doorways lead to no room. | [rooms](fo4_pipeline.md#rooms) |
| Water | Water heights, plus pools, springs and puddles you can drink from | Partial | Nearby water works. Water types use the nearest Fallout 4 type, with two radiation grades instead of five. | [water](fo4_pipeline.md#placeable-water) |
| Navmesh | The paths NPCs and creatures walk | Partial | NPCs walk and follow you. No cover or island data; NPCs sometimes catch on steps. | [navmesh](fo4_pipeline.md#exterior-navmesh) |
| Weathers and climate | New Vegas's weathers, sun and sky colors, and region weather | Partial | Weathers play and night and noon brightness match. Clouds are Fallout 4's, recolored. The amber tint now rides in each weather's color grade (built, not played). | [weathers](fo4_pipeline.md#weathers) |
| Grass | Grass where New Vegas grows it, at its density | Built, not played | Fixes for the triangle at the tips and the dark flecks (the texture now clamps, as New Vegas does) and for the color (vertex tint on) are built. Swapping in Fallout 4's grass was ruled out. | [grass](fo4_look.md#grass) |
| Lights and glow | Lamps, windows, lanterns and animated signs | Built, not played | Lanterns and lamps work. Fixes for the dim OPEN and SAL signs and the Strip's night horizon glow are built. The saloon window is still far too yellow; it needs a shot from the next build. | [neon](fo4_look.md#route-neon) |
| Overall color tone | New Vegas's color grading and warmth | Built, not played | Fallout 4's tone curve and bloom with New Vegas's tint and saturation on top, at a fixed exposure that keeps New Vegas's mid-tones (decided 2026-11-09). | [FO4 route](fo4_look.md#fo4-route) |
| Modern lighting and the Classic switch | Shadow-casting main lights and Fallout 4's light types, picked by each light's New Vegas role; an optional plugin restores the classic flat look | Built, not played | Up to 6 main lights per interior cast shadows, starting 64 units out so a ceiling fixture does not shadow its own light. The Classic Look plugin is an optional app step. | [plan](fo4_look.md#route-lights) |
| Precombines and previs | Fallout 4's merged meshes and visibility data for dense areas | Not built | | [precombines](fo4_pipeline.md#before) |
| Frame rate | Smooth play across the Mojave | Partial | Goodsprings to Primm holds the frame cap. Freeside, the Strip and Novac aren't measured. | [measured](fo4_pipeline.md#region-measured) |
| Intro movie | New Vegas's intro, with sound | Works | | [play test](bink_movies.md#play-test) |

### NPCs

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Faces | Each NPC's face rebuilt with Fallout 4's face sliders to match New Vegas | Works | | [sculpt](fo4_spikes.md#spike-2-sculpt) |
| Hair and eyes | The closest Fallout 4 hair, beard and eyes for each NPC | Works | The match by hairstyle works. The fix for stretched long hair isn't checked. | [hair](fo4_spikes.md#hair-styles) |
| Outfits and clothing | New Vegas's clothes and armor fitted onto Fallout 4's body | Partial | 21 of 98 armors use Fallout 4 stand-in models. The wrist seam shows, loose cloth sits off the body, and cut-off limbs don't cut the clothes. | [clothing](fo4_build_next.md#human-clothing) |
| Headgear | Hats, masks and glasses on New Vegas's own models | Works | | [headgear](fo4_spikes.md#spike-4-headgear) |
| Own FaceGen heads and hair | New Vegas's full face shape, face color and own hairstyles, written without the Creation Kit | Planned | Faces read rounder and more generic than New Vegas's: the sliders reach about 70% of the shape. | [facegen plan](fo4_facegen_plan.md) |
| Body choice (CBBE, BodySlide) | Choosing which body converted outfits fit | Not built | Only the vanilla body. With CBBE installed, bare skin in converted outfits looks scrambled. | [body plan](fo4_bodies_cbbe.md) |
| Super mutants and nightkin | New Vegas's mutants in their own armor | Partial | Fallout 4's mutant body and head, tinted, under New Vegas's armor. Pistols, the Multiplas rifle, shotguns, the gatling laser and the railway rifle map to super mutant animations (built, not played); grenade launchers still fight unarmed. | [super mutants](fo4_build_next.md#super-mutants) |
| Ghouls and glowing ones | Feral ghouls, and glowing ones with their aura and healing | Works | | [ghouls](fo4_creature_audit.md#ghouls) |
| Ghost People and holograms | Dead Money's enemies | Built, not played | | [Dead Money](fo4_spikes.md#dead-money-humans) |
| Daily routines | NPCs sandboxing, sitting, sleeping, eating, guarding and patrolling | Partial | 85 routines are missing, prospectors' looting among them. Most NPCs drop their routine in combat. | [packages](fo4_pipeline.md#packages) |
| Scripted routines | Routines quest scripts hand out, and patrol-point actions | Partial | Scripted routines work; patrol-point actions aren't played. | [patrol points](fo4_pipeline.md#patrol-points) |
| Standing idles | Gestures in conversations and from scripts | Works | | [standing](fo4_idles.md#standing) |
| Ambient idles | Smoking, scratching, drunk walks and other habits | Built, not played | Weapon-out idles aren't built. | [trees](fo4_idles.md#trees) |
| Seated idles | Idles while sitting, such as Doc Mitchell's | Partial | Only the tested scripted ones are on; the rest are left out after earlier crashes. | [furniture](fo4_idles.md#furniture) |
| Idle props | The cigarette, clipboard, Doc's mirror and other held props | Built, not played | | [props](fo4_idles.md#props) |
| Idle markers | Spots where NPCs lean, sit or work | Built, not played | All 1,424 are placed. The 6 whose idles Fallout 4 has nothing like (watering flowers, singing, mourning and 3 others) are empty markers, so NPCs stand there without the gesture. | [markers](fo4_pipeline.md#audit-fixes) |
| Animated objects | Objects that play their own animation (windows, the Lucky 38 lights) | Built, not played | A script now sees an animation it started as playing until the mesh's own length runs out. One it didn't start, or started on an object held in a variable (some vertibirds, the Vault 11 gear door's linked panel), still reads as not playing. | [plan](fo4_plan_script_functions.md#phases) |

### Creatures

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Own-rig creatures | Geckos, nightstalkers, giant mantises and cazadors on New Vegas's own skeletons and animations | Works | | [own rig](fo4_own_rig.md#mantis) |
| Own-rig creatures, the rest | Giant rats, ants, the ant queen, spore carriers, centaurs, spore plants, ravens | Built, not played | Fire ants', centaurs' and spore plants' ranged attacks work. | [remaining](fo4_own_rig.md#remaining) |
| Own-rig reactions | Reactions and moves for own-rig creatures | Partial | No hit reactions, staggers, jumps, side or back moves, or kill moves. No hit, idle or alert sounds. | [idles](fo4_own_rig.md#idles) |
| Stand-in creatures | Deathclaws, dogs, mole rats, radscorpions and robots shown as their Fallout 4 counterpart, with New Vegas stats | Partial | They work. Turning off Fallout 4-only moves (burrowing, robot self-destruct, the deathclaw's roar and dirt throw) isn't played. | [race abilities](fo4_creature_audit.md#race-abilities) |
| Creature attacks | Each creature's attacks, speeds and knockdowns | Partial | See own-rig reactions. | [attacks](fo4_pipeline.md#creature-attacks) |
| Spawns | Leveled spawns, including New Vegas's chance that nothing spawns | Built, not played | | [void](fo4_creature_audit.md#void) |
| Corpse poses | Dead-at-start bodies lying as New Vegas placed them | Partial | Most humans and mutants work. Robots and about 31 others ragdoll where they lie. REPCON's dead mutants aren't played. | [poses](fo4_spikes.md#creature-poses) |
| Talking machines | Mr. House's screen, Yes Man, Festus | Partial | Mr. House's screen talks. The fix for its blank image, Yes Man and Festus aren't played. | [machines](fo4_creature_audit.md#talking-machines) |
| Securitrons | Victor and the Strip's securitrons | Partial | They move, talk and fire both guns. Their face screen isn't played; the Lucky 38 elevator prompt isn't confirmed. | [screens](fo4_build_next.md#screens) |
| Think Tanks | Old World Blues' scientists on their own rig | Built, not played | | [think tank](fo4_own_rig.md#think-tank) |

### Dialogue

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Conversation menus | Talking opens New Vegas's full list of topics, through Extended Dialogue Interface | Works | | [menus](fo4_spikes.md#spike-1-design) |
| Dialogue lines | All of New Vegas's NPC lines, with the conditions that decide when each shows | Partial | About 350 lines are left out, mostly ones tied to item counts, casino winnings, NPC class or the player's own barks. | [conditions](fo4_pipeline.md#dialogue-conditions) |
| Choices with shared answers | Menu options whose reply New Vegas shares between topics | Partial | Most get their reply; 236 choices still have no line. | [shared infos](fo4_pipeline.md#shared-infos) |
| Say Once topics | A topic disappears once heard | Works | | [say once](fo4_pipeline.md#say-once) |
| Skill checks | `[Speech 50]`-style options that pass or fail on your skill | Works | | [speech tag](fo4_build_next.md#speech-tag) |
| NPC voices | Every NPC speaks their own New Vegas recordings | Works | | [voice types](fo4_pipeline.md#voice-types) |
| Silent player | The player has no voice, as in New Vegas | Built, not played | | [voice](fo4_spikes.md#spike-1-voice) |
| Lip sync | Mouths move with New Vegas's own lip data | Built, not played | | [lips](research/lip_format.md#built) |
| Greetings | The line an NPC says when you start talking | Built, not played | Greetings play; the special first-meeting lines aren't checked. | [first meeting](fo4_pipeline.md#talked-to-pc) |
| Force greets | NPCs who walk up and start talking (Ringo, the Primm trooper) | Partial | Ringo and the Primm trooper work; the rest is untested. | [greet trigger](fo4_pipeline.md#greet-trigger) |
| Barks | One-off lines shouted in combat or as you pass | Partial | Built, not listened for. The player's own barks are left out. | [barks](fo4_pipeline.md#barks) |
| Companion barks | Companions remarking on low health, waking up or no ammo | Partial | 77 lines built, not heard. 91 others depend on things Fallout 4 doesn't track. | [companion barks](fo4_pipeline.md#companion-barks) |
| Ambient chats | Two NPCs talking to each other | Built, not played | | [chats](fo4_pipeline.md#actor-dialogue) |
| Scenes | Scripted conversations between several people | Partial | Basic scenes work. Looping and branching scenes, and Cato's and Benny's talks, are untested. | [scenes](fo4_pipeline.md#scene-loops) |
| Talking activators | Intercoms, loudspeakers and recordings | Built, not played | The REPCON intercom works. | [talkers](fo4_pipeline.md#talker-says) |

### Quests and scripts

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| New game | The intro movie, waking at Doc Mitchell's, name, face, S.P.E.C.I.A.L., the word test and tag skills | Works | | [new game](fo4_pipeline.md#new-game) |
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

### Radio

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Radio New Vegas, Mojave Music Radio | Pip-Boy stations with Mr. New Vegas, news and songs | Works | | [radio](fo4_radio.md#steps-model) |
| Black Mountain, lounge stations | Rhonda and Tabitha's station and casino lounge music | Built, not played | Black Mountain's scripted event lines aren't built. | [radio](fo4_radio.md#steps-model) |
| Placed radios | Radios in the world you can turn on | Works | | [receivers](fo4_radio.md#receivers) |
| Broadcasts scripts start | The Tops stage acts, Hanlon's broadcast, Dead Money's radios | Built, not played | Lily's recording has no radio to play through. | [start radio](fo4_radio.md#start-radio-conversation) |

### The character

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| S.P.E.C.I.A.L. | Setting your seven stats with the Vit-o-matic | Works | | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Tag skills | Doc's questionnaire suggests three skills to tag | Works | | [vcg01](fo4_spikes.md#spike-2-vcg01) |
| Skills | New Vegas's 13 skills, shown in the Pip-Boy | Works | | [tabs](fo4_pipboy_tabs.md#how) |
| XP and level-ups | Earning XP and picking perks and skill points | Works | Skill points and perk picks both work. | [level-up](fo4_perks.md#hasperk) |
| Perks | New Vegas's 176 perks and ranks | Partial | Not played. 29 effects have no Fallout 4 equivalent (attack and equip speed, unarmed specials, Miss Fortune, Long Haul, some DT perks). | [census](fo4_perks.md#census) |
| Traits | Optional traits with an upside and a downside | Partial | Picking works; effects aren't played. | [drift](fo4_drift.md#recorded) |
| Companion perks | Perks your companions give you | Built, not played | | [teammate perks](fo4_perks.md#teammate-perks) |
| Skill books | Reading one raises a skill and uses up the book | Built, not played | The Comprehension perk's extra point is missing. | [books](fo4_pipeline.md#skill-books) |
| Skill magazines | Reading one gives a short skill boost | Works | Picking one up in the world shows it as if being read, which does nothing; the boost comes from using it. | [consumables](fo4_pipeline.md#consumable-effects) |
| Intense Training | A perk that raises one stat by 1 | Built, not played | 1108d's missing box: the box now waits until the Pip-Boy has closed. | [intense training](fo4_pipeline.md#intense-training) |
| Karma | Good and evil standing | Partial | The tab and kill karma work; theft karma is untested. | [standings](fo4_pipeline.md#standings) |
| Reputation | Fame and infamy with each faction, and their titles | Built, not played | The title-change box has no text. | [reputation](fo4_pipeline.md#reputation-messages) |
| Challenges | New Vegas's challenges and their rewards | Partial | 61 of 105 are counted; damage, body-part, cripple, casino and caravan challenges are missing. | [left out](fo4_pipeline.md#challenges-left-out) |
| Hardcore mode | Thirst, hunger, sleep, ammo weight, slow healing | Built, not played | Missing: companions dying only in Hardcore, the ending's reward, a settings-menu switch (an aid item turns it on). | [Hardcore](fo4_hardcore.md#built) |
| Chem addiction | Getting hooked and going through withdrawal | Partial | Withdrawal effects are Fallout 4's; some chems never addict. | [addiction](fo4_pipeline.md#chem-addiction) |
| Fatigue and knockouts | Being knocked out by gas, boxing or cattle prods | Built, not played | | [fatigue](fo4_pipeline.md#fatigue) |
| Disguises | Faction armor that lets you pass as NCR, Legion and others | Built, not played | | [disguises](fo4_pipeline.md#disguises) |
| Sex change | Choosing or changing your character's sex | Works | | [sex change](fo4_pipeline.md#sex-change) |
| Pip-Boy SKILLS, REPUTATION, KARMA | New Vegas's STATS pages in the Pip-Boy | Works | | [tabs](fo4_pipboy_tabs.md#how) |
| Pip-Boy CHALLENGES | Challenge progress in the Pip-Boy | Works | It shows a number, not "3/10". | [data](fo4_pipboy_tabs.md#data) |

### Combat

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

### Items

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Consumables | Food, drinks, chems and their effects | Partial | Basic effects work. Script-driven ones (Cateye, Steady, Stealth Boy and others) aren't played; Rebound and a few others are dropped. | [consumables](fo4_pipeline.md#consumable-effects) |
| Crafting | Recipes at workbenches, campfires and the reloading bench | Partial | The reloading bench put the player on the wrong side at Primm and Goodsprings; each open side is now its own bench, fixed, not built. | [stations](fo4_pipeline.md#station-entry) |
| Caps | The Mojave's currency | Works | | [items](fo4_casino_plan.md#items-built) |
| Other money and cards | NCR dollars, Legion coins, casino chips, Caravan cards | Built, not played | Items only, until the casino games are built. | [items](fo4_casino_plan.md#items-built) |
| Item models | New Vegas's own models for items | Partial | Many aid items (the Stimpak among them) and some armor show Fallout 4's. | [drift](fo4_drift.md#recorded) |

### Casino games

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Slots | The Strip's and the Sierra Madre's slot machines, on our own 2D menu | Works | Spins pay out and take chips. Luck, comps levels, the floor managers' dialogue and the Sierra Madre's machines aren't checked. Spins don't count toward the challenge yet. | [slots](fo4_casino_plan.md#slots-built) |
| Roulette | The Strip's and the Sierra Madre's roulette tables, on our own 2D menu | Built, not played | Click a spot to bet, click it again to take the chips off. Pays as New Vegas does, its 0 and 00 quirks included. No spin animation or sounds; no gamepad cursor over the board. Spins don't count toward the challenge yet. | [roulette](fo4_casino_plan.md#roulette-built) |
| Blackjack | The Strip's and the Sierra Madre's blackjack tables | Not built | A table says the game isn't playable yet; the casino's ban and the anti-cheat wait already apply. | [plan](fo4_casino_plan.md#records-built) |
| Casino menu test | A console test screen for the new menu (`cqf FNV_Casino Spike`) | Works | Keys, mouse, text and images work in a menu of our own. Drawing it in your HUD color is built, not played (white without F3NV.dll). | [spike](fo4_casino_plan.md#toolchain-found) |
| Caravan | New Vegas's card game | Not built | Picked-up cards join your collection; asking to play says the game isn't playable yet (or that you need 30 cards). | [plan](fo4_casino_plan.md#records-built) |

### DLC and add-on packs

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Story DLC | Dead Money, Honest Hearts, Old World Blues, Lonesome Road | Built, not played | Dead Money's casino games are missing; its vending machines' chips aren't played. When two DLC change the same thing, the last one loaded wins. | [DLC](fo4_plugin_layout.md#dlc-build) |
| Gun Runners' Arsenal and courier packs | The weapon and gear packs | Built, not played | | [packs](fo4_plugin_layout.md#courier-packs) |

### <a id="fo4-app"></a>The app and installing

| Feature | What it is | State | Notes | Doc |
|---|---|---|---|---|
| Conversion app | Converts your New Vegas install for Fallout 4 | Partial | Setup, Convert and Replacements screens are built, not tested end to end. DLC and mod folders convert from the app too ([DLC and mods](fo4_gui.md#addons)); the Finished screen checks the install, sets the output up in Mod Organizer and plays ([buttons](fo4_gui.md#mo2-setup)), and the F4SE plugin and faces are stages. None of this run from the app yet. | [phases](fo4_gui.md#phases) |
| Installing | The README's steps for testers | Built, not played | Never followed end to end on a clean machine. | [install](../../README.md#install) |
| Replacements | Swapping converted items or creatures for Fallout 4's or other mods' versions | Partial | The table and its screen work, empty by default. Named profiles and a Wabbajack modlist aren't built. | [replacements](fo4_replacements.md#direction) |
| Fallout 3 | Converting Fallout 3 the same way | Partial | A scoped spike: Vault 101 and the opening (born in `CG00`) through the vault door, built into a scratch folder, not played. The rest of the Capital Wasteland is not built. Tale of Two Wastelands judged, not built. | [FO3 spike](fo4_fo3_plan.md) |

## Known bugs a player will see

- Holes and dark blocks in distant land, closing up as you approach.
  ([terrain LOD](fo4_pipeline.md#terrain-lod))
- The reloading bench puts you on its wall side at Primm and Goodsprings (fix
  not built). ([stations](fo4_pipeline.md#station-entry))
- Scripts that wait for an animated window or the Lucky 38 lights do nothing. ([census](fo4_idles.md#census))
- NPCs and the player catch on some stairs (the Novac motel, Vikki and
  Vance's steps). ([stairs](fo4_pipeline.md#stair-helper-pitch))
- Super mutants holding grenade launchers fight unarmed (the other guns'
  fix is built, not played). ([super mutants](fo4_build_next.md#super-mutants))
- Your left hand briefly leaves the rifle when you aim.
  ([guns](fo4_gun_animation.md#order))
- Explosives-kill challenges count only while an explosive is equipped.
  ([challenges](fo4_pipeline.md#challenges-left-out))
- With CBBE installed, bare skin in converted outfits looks scrambled.
  ([body plan](fo4_bodies_cbbe.md))
- Blackjack and Caravan aren't playable yet.

Please report what you find in
[the issues](https://github.com/ThyMrMan/fo3fnv-in-fo4/issues).

## <a id="fo4-next"></a>Planned work

- **Play-testing** everything marked "Built, not played", and fixing what
  turns up.
- **Casino games and Caravan**, in progress ([plan](fo4_casino_plan.md)).
- **Fixes for the known bugs** above, in the order of the
  [issue plan](fo4_issue_plan.md): play tests first, then by size.
- **Gun animation:** New Vegas's third-person clips and grip
  ([plan](fo4_gun_animation.md#order)).
- **Creatures:** reactions, staggers and sounds on own rigs
  ([own rig](fo4_own_rig.md)).
- **Body choice:** CBBE and BodySlide bodies for converted outfits
  ([plan](fo4_bodies_cbbe.md)).
- **The look:** grass color, Strip neon, the night horizon glow, New Vegas's
  color tone, distant trees and water ([plan](fo4_look.md)).
- **Precombines** for Freeside and the Strip.
- **Script speed:** the remaining Papyrus cost fixes
  ([performance](performance.md#papyrus)).
- **The app:** Mod Organizer setup, Play, and the DLC, DLL, movie and face
  steps ([phases](fo4_gui.md#phases)).
- **Build checks:** the dialogue menu audit and the rest of the timing audit
  ([menu](fo4_menu_audit.md), [timing](fo4_timing_audit.md)).
- **Mod builds:** convert one mod against a built game
  ([plan](fo4_mod_builds.md)).
- **Load order:** converted mods in the user's FNV order, a conflict report,
  a merged patch and LOOT rules ([plan](fo4_load_order.md)).
- **Build time:** faster face fits, caches that survive unrelated edits, mod
  builds that reuse the game build ([plan](fo4_build_speed.md)).
- **Differences from New Vegas** that could be closed later: attack and equip
  speed perks, looting routines, per-pellet DT, Long Haul and Miss Fortune
  ([drift](fo4_drift.md)).
- **Fallout 3:** play the Vault 101 spike, then the whole Capital Wasteland,
  then Mart's Mutant Mod ([FO3 spike](fo4_fo3_plan.md#next)).

## <a id="parked"></a>Parked

| Item | Why |
|---|---|
| A choice between New Vegas and Fallout 4 combat | An idea, not planned |
| Other languages' movie tracks | Only English is checked ([Bink](bink_movies.md)) |
| [Graphics research](research/graphics_options.md) | Notes to revisit later |
| [Spin-off mods](spin_offs.md) from F3NV.dll (framework, content mods, dynamic collision) | Planned, not started; the dialogue menu goes first. [Strategy](spin_offs.md#strategy): open, drop-in replacements for XDI, then HUDFramework; waiting on the author's reply about licenses |
| [Dialogue menu as its own mod](dialogue_menu_mod.md) (XDI replacement) | Planned, not started; first step is the own-movie spike |
| [Our own Flash menu framework](swf_framework.md) (dialogue, casino, Pip-Boy) | Spikes 1, 2b and 3 played (spike 1: the casino on `mxmlc` and the first `f3ui` classes). The dialogue menu's own movie played (looks the same as before), then moved onto `mxmlc` and `f3ui` (built, not played; FFDec build route deleted). Spike 5 (translation files, named after FalloutHelpers.esl) played: translation works, an untranslated key shows raw, `$` text needs `Text.show`. Spike 4 (our movie loaded into the Pip-Boy by F3NV.dll, one item-card line) played under the vanilla Pip-Boy; FallUI Inventory read (same item card; the list takes its color, typed search keys ignored), not played. Spike 5 test lines removed; a translation key check runs in preflight. Our menus' fixed English (dialogue [LEAVE], the Pip-Boy's CND, hints, lists and notes) moved into $F3NV_ keys, with English installed under every game language as the fallback (built, not played). Level-up menu groundwork: every build stages FNV/FO3 perk, skill and SPECIAL images (FNV 156, FO3 91) for MountImage (built, not shown yet). Pip-Boy framework: the movie draws the CND line, the repair and ammo lists (a pop-up over the item card) and other mods' item-card lines (F3NV_ItemCard.SetLine) from F3NV.dll's data (built, not played) |
| [Dynamic collision](dynamic_collision_mod.md) (smaller collision when crouching, like Skyrim's DCA) | Planned, not started; first spike is a vanilla sneak-headroom test |
| [The build without the Creation Kit](fo4_ck_replacements.md) (own BA2, Caprica only, AnimTextData, FaceGen, collision) | Texture BA2 without Archive2 and loudness lips built, not built in game; Caprica only is blocked by one Caprica gap; the rest are ideas |

## <a id="inherited"></a>The inherited Skyrim converter

<a id="character"></a><a id="stability"></a><a id="performance"></a><a id="standalone-play"></a>This
repository started as a copy of a Morrowind and Oblivion → Skyrim converter,
and that code is still here. Its plans (character systems, stability,
performance, standalone play) are about the Skyrim target, not this
project. Their last status is in the [development log](dev_log.md#character).

## Where the details live

| Doc | Holds |
|---|---|
| [fo4_issue_plan.md](fo4_issue_plan.md) | The open issues, sized and in working order, and the eight group plans (`fo4_plan_*.md`) |
| [fo4_pipeline.md](fo4_pipeline.md) | How the build works, and each system built on it |
| [fo4_drift.md](fo4_drift.md) | Where play differs from New Vegas, and which game's system each area uses |
| [fo4_spikes.md](fo4_spikes.md) | The first experiments that showed the conversion works |
| [fo4_plugin_layout.md](fo4_plugin_layout.md) | The plugins, the DLC builds and FormIDs |
| [fo4_own_rig.md](fo4_own_rig.md) | Creatures on their own skeletons |
| [fo4_creature_audit.md](fo4_creature_audit.md) | Every creature field and where it goes |
| [fo4_perks.md](fo4_perks.md) | Perks and traits |
| [fo4_condition.md](fo4_condition.md) | Item condition, repair and jams |
| [fo4_hardcore.md](fo4_hardcore.md) | Hardcore mode |
| [fo4_radio.md](fo4_radio.md) | Radio |
| [fo4_pipboy_tabs.md](fo4_pipboy_tabs.md) | The Pip-Boy tabs |
| [fo4_look.md](fo4_look.md) | Grass, lighting and color |
| [fo4_preflight.md](fo4_preflight.md) | The checks run on every build |
| [fo4_gui.md](fo4_gui.md) | The conversion app |
| [nvse_script_language.md](nvse_script_language.md) | NVSE's script language in converted scripts |
| [fo4_hotfix.md](fo4_hotfix.md) | Script hotfixes between builds |
| [kill_cams.md](kill_cams.md) | Kill cams and killmoves for converted weapons |
| [spin_offs.md](spin_offs.md) | Releasing parts of F3NV.dll as mods anyone can use |
| [dialogue_menu_mod.md](dialogue_menu_mod.md) | The dialogue menu as a standalone XDI replacement |
| [swf_framework.md](swf_framework.md) | One Flash toolkit for our menus, and a Pip-Boy framework |
| [dynamic_collision_mod.md](dynamic_collision_mod.md) | Collision that changes size while playing (crouch, swim) |
| [fo4_tool_audit.md](fo4_tool_audit.md) | The converter audit before the whole-map build |
| [dev_log.md](dev_log.md) | The development history up to the alpha |

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
