# Changelog

What changed in each release of the app, newest first. Every release is an
alpha. Download the zip named `fo3fnv-in-fo4-<release>.zip` from the
[Releases page](https://github.com/ThyMrMan/fo3fnv-in-fo4/releases), not
"Source code".

## f3nv-0.15 (2026-11-26)

**After upgrading:** a DLC whose faces failed in 0.14 gets them on its next
"Rebuild what changed".

### Fixed
- **A DLC's faces no longer fail when Mod Organizer's selected profile
  leaves its game off** (a New Vegas DLC converted with a Fallout 3 profile
  selected). The faces stage looked for the game's plugin only in that
  profile, so every head failed and the stage stopped looking for
  `FalloutNV.esm`. It now first looks in the game folder the build itself
  used.

## f3nv-0.14 (2026-11-26)

### Fixed
- **A DLC no longer fails with "Conversion did not finish" after its game
  moved to a new output folder.** A DLC last built against the game's old
  folder made "Rebuild what changed" go back to that old copy and stop
  (exit code 7) when an older release had built it. Such a DLC now converts
  in full against the game's current folder: Build is ticked, and Rebuild
  what changed says which copy it was built against.

## f3nv-0.13 (2026-11-26)

**After upgrading:** rebuild your converted games and DLC ("Rebuild what
changed"), because the creature, weapon, armor, crafting, effect and
idle-marker code changed. Saves keep working: no existing record moved.

### New
- **Creatures with no rule convert.** A creature folder nobody wrote a rule
  for (the Fallout 3 DLC's, and any mod's) now picks a route itself: the rule
  of a folder with the same skeleton, else a rig built from its own files,
  else a stand-in by creature type. Anchorage's chimera and spider mines and
  Point Lookout's swamp folk get rigs of their own; Broken Steel's
  Bonecrusher plays as a super mutant.
- **Weapons with no rule convert.** Each weapon takes the first route that
  works: its hand entry, a listed weapon with the same model, its own mesh
  (if it passes the muzzle and rifle-aim checks), the Fallout 4 gun's mesh,
  else a stand-in by animation type. Each build writes a
  `<plugin>.weapons.tsv` report of every weapon's route.
- **Semi-automatic guns fire at their own rate**, from the source's shots
  per second.
- **An unlisted projectile** takes a stand-in of its kind (bullet, missile,
  grenade, beam, flame).
- **Armor in any slot.** Gloves, backpacks, Pip-Boy items, hair pieces and
  face jewelry no rule covered now convert, on their own mesh or with no worn
  model, each in a slot of its own; never the player's Pip-Boy slot.
- **Mod crafting categories.** Recipes in a mod's own category, and the
  benches that open it, convert (Dead Money's vending machines: 49 recipes).
- **Mod consumable effects.** A new effect that changes a stat becomes Fallout
  4's effect on the same stat (New Vegas' Rebound now gives its 5 AP).
- **Mod explosions, debris, effect shaders and idle markers** route to the
  nearest listed one, or convert as themselves, instead of being left out.
- **Terrain LOD from the land itself** (off by default; set
  `F3NV_TERRAIN_FROM_LAND=1`): distant land built from each cell's heights,
  with tile edges that meet.

### Fixed
- **The Pitt's reference check.** Its trogs and the marker creatures built on
  them were skipped, leaving 10 references naming records never written.
- **Hardcore's last stage** of thirst, hunger and sleep loss kills, as in New
  Vegas; its damage was dropped.

### Known
- Not played in game yet. Automatic guns keep the Fallout 4 gun's fire rate.

## f3nv-0.12 (2026-11-26)

### New
- **Queue several conversions.** "Add <plugin> to queue", beside Convert,
  lines up the chosen game, DLC or mod with its ticked stages. Queued
  targets convert one after another once the running build ends, or when
  you click Run queue. A DLC queued behind its game builds once the game
  is done. A failure or Stop keeps the rest queued; the Finished screen
  lists every target's stages.

## f3nv-0.11 (2026-11-26)

**After upgrading:** "Rebuild what changed" rebuilds your converted games
once, because the dialogue and package code changed. Saves keep working: no
existing record moved.

### New
- **More packages run** (29 Fallout 3 packages that were left out):
  - NPCs sent to find another NPC go to one and stay near it: Leroy
    Walker's attack on the Temple of the Union (which also unlocks its
    gate), Andy fighting the radroaches in Vault 101, Janice Kaplinski and
    Anthony Ling around Rivet City, and the random encounters' dead-brahmin
    finds, Enclave eyebot, radscorpion hunter and arguing pilgrims.
  - The slaver encounter's slaver leads the slaves to his marker.
  - In Fallout 3 a "find" ended once the NPC was found; here the NPC stays
    near it until the package's own schedule or conditions end it.

### Fixed
- **Tenpenny Tower's intercom lets you back in.** The guard's replies to
  "Let me in" on a return visit were left out, so the gate stayed shut;
  lines that name the speaker by faction now play through a talking
  activator speaking as a member.

### Known
- Not played in game yet. Whether Fallout 4 lets these Follow and Escort
  packages act on an NPC they found, rather than a placed one, is untested.

## f3nv-0.10 (2026-11-26)

**After upgrading:** "Rebuild what changed" rebuilds your converted games
once, because the dialogue, package and script code changed. Saves keep
working: no existing record moved.

### New
- **Disposition.** Fallout 3's NPCs keep how they feel about you again.
  `ModDisposition` (40 calls, mostly in line results) moves a per-NPC value, built from the game's own settings and each NPC's
  Charisma. Lines that test it now play: Moriarty's, Moira's, MacCready's,
  Scribe Rothchild's, the generic friendly greetings and Lucas Simms' "friend"
  lines (30 lines).
- **Crime counts.** Murders, assaults, thefts, pickpocketing and trespassing
  are counted against each faction that tracks crime, so NPCs who react to
  your record do (52 Fallout 3 lines: Megaton, Rivet City security, Little
  Lamplight, Tenpenny Tower, Dukov).
- **Items get picked up.** Packages that send an NPC to fetch an item now do
  it: Dogmeat's fetching, Crowley's T-51b, the Evergreen Mills slaves.
- **More packages run:**
  - NPCs sit at furniture named by type or model (the Oasis morning rituals,
    Vault 101 chairs) and at terminals (Li at the door, Moira's entry).
  - Pets, brahmin, Regulators and Talon mercenaries from random encounters
    follow their leaders.
- **More lines play:**
  - Lines for NPCs that only a script spawns: Fallout 3's free-form
    encounters, 84 lines.
  - Lines that name a group of cells: Big Town, Little Lamplight, Tenpenny,
    Vault 101 (more than 1,100 lines).
  - Lines that check what an NPC is doing: the packages they test are made
    first (42 lines).
  - The Mesmetron slave lines.
  - Sarah Lyons' karma lines and the Chesterbrook paladin's.
  - Player grunts in combat use Fallout 4's player voice.
- **The target list names the release** that built each plugin ("with
  f3nv-0.9", or "a development build").

### Fixed
- **A force greeting plays once** even after a mod is added or removed:
  each one is numbered by its own record, not by build order.
- Anchorage scripts that failed to compile (a variable named like a
  built-in property, a comparison of two script types) now compile.
- Dead Mirelurks in Broken Steel lie in a natural pose.
- Face fitting no longer fails on a face that is the base texture.

## f3nv-0.9 (2026-11-25)

### Fixed
- **Reconverting a DLC no longer fails on a build made elsewhere.** "Rebuild
  what changed" now always reads the exports and scripts in this app's work
  folder. Before, it reused the folders recorded by the plugin's last build,
  so a plugin built by another release or from the command line failed to
  find its export (an Anchorage reconvert stopped looking for the world
  `Wasteland`).
- **A DLC asks for its game first.** Converting a DLC now needs its game
  converted with the same work folder, since the build reads the game's
  records too. The Convert screen says so instead of starting a build that
  cannot finish.

## f3nv-0.8 (2026-11-25)

**After upgrading:** "Rebuild what changed" rebuilds your converted games
once, because the challenge and script code changed.

### New
- **Explosive kills count for challenges.** A kill by a New Vegas grenade,
  missile launcher or other weapon whose shot explodes now counts for that weapon's
  challenges, as a direct hit already did.
- **Animations on linked objects play.** Scripts that animate an object they
  are linked to now play its animation and wait for its real length: the
  Hoover Dam turbines and screens in New Vegas, and every Fallout 3
  vertibird landing, take-off and flyover.
- **Stage times read in minutes and hours** on the Finished screen
  (`12m 34s`, `1h 05m 03s`).

### Fixed
- **Converting a DLC no longer fails after its game was built.** Exporting a
  DLC such as Anchorage made its game look out of date, and the rebuild the
  app then started died without a word, ending in "Conversion did not
  finish". The game now stays current, and a build started by the app writes
  its output and errors into the app's log.
- **Clearer endings.** The Finished screen names the stage that failed and
  its exit code, and says where the log is saved. "Rebuild what changed"
  says when every plugin is already up to date.
- **Doors read their state while they move** in scripts that wait on a
  door's animation (the Vault 11 gear door).

## f3nv-0.7 (2026-11-25)

**After upgrading:** the first build makes every face and distant-terrain
texture once more, because the texture compressor changed. Everything else
in your `F3NV Work` folder is reused.

### New
- **Fallout 3's intro movie plays** after character creation, before the
  birth scene.
- **Old faces keep Fallout 3's wrinkles.** Elders such as Tenpenny show the
  forehead furrows and cheek and neck lines their old race had, instead of
  smooth skin.
- **More old script commands work.** Commands with a Fallout 4 function of
  the same meaning now call it (combat styles, names, gold values, saving,
  the barber menu and more). Unconverted commands in the New Vegas scripts
  drop from 659 to 510.
- **No more Creation Kit tools during a build.** Mesh physics and faces are
  now made entirely by the converter, so the build no longer runs Elric or
  the Creation Kit's FaceGen. You still need the Creation Kit installed for
  its script sources.

### Fixed
- **Vault 101:** the Overseer's terminal is usable, the atrium door closes
  again, Butch waits for Amata, the Holdens run when they flee, Dad kneels
  at the bible properly, Jonas holds his camera, and doors marked
  Inaccessible stay shut.
- **Megaton:** stairs and ramps climb normally, no invisible ramp or
  glowing faces, Moriarty's radio starts on, and Stockholm stays on his
  perch.
- **Combat:** Fallout 3 armor no longer makes security officers nearly
  unkillable, and NPCs no longer drop melee weapons for their fists.
- **Weapons:** the BB gun has its own sounds, lever cycle, sights and
  reload; every converted gun gets its own shot sounds; Fallout 3's assault
  rifles and combat shotguns use their own meshes.
- **Picking up an item no longer runs its "dropped" script** (picking up a
  giant mantis leg killed the mantis).
- **Scripts:** one script that the fast compiler can't read no longer sends
  its whole folder to Fallout 4's slower compiler.
- **Dialogue choices sit above the subtitles**, where Fallout 4's own do.

### Improved
- **Faster, lighter builds.** Voice lines encode about twice as fast, face
  textures compress about 8 times faster, and each face worker starts with
  about 1 GB less memory, so smaller PCs run more faces at once. Weapon
  animation workers also use less memory.
- **Disk space is cleaned up.** Builds remove leftover archive staging and
  faces from older builds.
- **The README gives real disk sizes:** about 70 GB free per game you
  convert (about 140 GB for both), not counting the games themselves.

### Known
- Fallout 3 is experimental past Vault 101, and these Fallout 3 fixes are
  not played through yet.

## f3nv-0.6 (2026-11-24)

### New
- **Our own voice encoder.** Voice lines and sounds are compressed by an
  open-source encoder that ships in the zip. The launcher no longer asks
  you to download Microsoft's 600 MB DirectX SDK.
- **The Black Landscape Fix mod is no longer needed.**
- **The app shows when a quiet build is still working:** the Convert
  screen shows CPU use under the time estimate.

### Fixed
- Fallout 3's distant terrain around the Washington Monument was drawn in
  the wrong place.
- `invalid enum value` warnings in Fallout 3 builds.
- A voice stage crash when two lines share one recording.

### Improved
- Voice files are kept between builds, and recordings are decoded in
  batches.

### Known
- Dialogue: 22,182 of New Vegas's 23,247 lines are built; most of the rest
  are barks Fallout 4 has no slot for, test quests, or lines unused in New
  Vegas too.

## f3nv-0.5

### Fixed
- Helper scripts were missing from the zip, so script compiling was slow.
- Conversation menus shared by several NPCs keep their choices.

### Improved
- About 1 GB less memory during a build.
- A quieter log and a steadier time estimate.

## f3nv-0.4

- The `F3NV Work` folder now sits beside the app, so a new release reuses
  the old one's export and caches.
- Work from 0.3 carries over.
- "Rebuild what changed" works after an upgrade.

## f3nv-0.3

- Faces work on a fresh install: their calibration is measured on your PC.
- Every convert writes a log.
- DLC folders are named by game.

## f3nv-0.2

- A fresh download can convert.
- The app has a small download of its own instead of the whole repository.

## f3nv-0.1

- First alpha, source code only.
