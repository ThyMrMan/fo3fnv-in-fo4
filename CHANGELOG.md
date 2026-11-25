# Changelog

What changed in each release of the app, newest first. Every release is an
alpha. Download the zip named `fo3fnv-in-fo4-<release>.zip` from the
[Releases page](https://github.com/ThyMrMan/fo3fnv-in-fo4/releases), not
"Source code".

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
