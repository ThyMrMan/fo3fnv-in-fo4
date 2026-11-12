# fo3fnv-in-fo4

**Fallout: New Vegas, converted to run in Fallout 4.** The whole Mojave,
its DLC and add-on packs: quests, dialogue and voices, NPCs and creatures,
FNV's guns, perks, skills, reputation, karma, Hardcore mode and radio. All of
it is rebuilt from your own copy of New Vegas on your own machine.

> [!WARNING]
> **Alpha.** The game is playable from Doc Mitchell's house onward, and
> nearly every system is built. Much of it has never been played start to
> finish, so expect bugs, and expect updates to need a new game. Back up your
> saves. Fallout 3 is not supported yet.

> [!IMPORTANT]
> **No Bethesda assets are included.** This project ships only code. It reads
> the games you own and converts them locally. **Don't redistribute the
> converted files.**

This project began as a fork of [bryantmh/tes4skyrim](https://github.com/bryantmh/tes4skyrim)
(TES Auto-Convert), by way of [ThyMrMan/tes4skyrim](https://github.com/ThyMrMan/tes4skyrim),
which converts Morrowind and Oblivion to Skyrim. The Fallouts moved to
Fallout 4 because Fallout 4 already has guns, V.A.T.S., crippled limbs,
radiation, terminals, the Pip-Boy and radio, which Skyrim would need rebuilt
by hand. The inherited Skyrim converter is still in this repository. Use
ThyMrMan/tes4skyrim for it.

---

## What you get

| Plugin | What it holds |
|---|---|
| `FalloutNV.esm` | The base game: the Mojave and every interior, 2,000+ NPCs, about 114,000 dialogue lines, every quest script (all compile) |
| `FalloutHelpers.esl` | Shared helper records (actor values, globals, keywords) |
| `FalloutNV - Classic Look.esl` | Optional: FNV's original flat lighting and color (see [Classic Look](#classic-look)) |
| `DeadMoney.esm`, `HonestHearts.esm`, `OldWorldBlues.esm`, `LonesomeRoad.esm`, `GunRunnersArsenal.esm` | The DLC, each on `FalloutNV.esm`, in its own mod folder |
| `CaravanPack.esm`, `ClassicPack.esm`, `MercenaryPack.esm`, `TribalPack.esm` | The add-on packs |
| `F3NV.dll` | The project's F4SE plugin: FNV rules Fallout 4 has no way to express (Damage Threshold, item condition, the Pip-Boy's SKILLS, REPUTATION, KARMA and CHALLENGES tabs, Hardcore's ammo weight and HUD) |

**Converted as FNV has them:**
- **The world:** terrain, objects, interiors, terrain and object LOD, FNV's
  weathers and the Pip-Boy world map.
- **Characters:** NPCs with FNV faces and outfits; creatures on their own FNV
  skeletons and animations (geckos, cazadores, nightstalkers, securitrons and
  more); FNV's leveled spawns.
- **Dialogue and quests:** FNV's own voices and lip sync, through Extended
  Dialogue Interface; scripts converted to Papyrus.
- **Your character:** SPECIAL, the 13 skills, 200+ perks and traits, FNV's
  level-up, tag skill and trait menus (our own, with every DLC's perks;
  options in MCM), reputation, karma, challenges, Hardcore mode, chem
  addiction.
- **Combat:** FNV's guns, ammo subtypes and the Ammo Type hotkey, weapon mods,
  item condition and repair, critical hits, Damage Threshold, sneak attacks,
  grenades and mines, V.A.T.S. tuned toward FNV's.
- **Also:** FNV's radio stations, terminals, lockpicking and hacking by skill,
  and FNV's own intro movie.

Where play differs from FNV, on purpose or not, is listed in
[docs/fork/fo4_drift.md](docs/fork/fo4_drift.md).

### <a id="classic-look"></a>Classic Look

`FalloutNV - Classic Look.esl` switches between two looks for the same
world. It changes only lighting and color, nothing in gameplay or quests.
You can turn it on or off at any time, mid-playthrough, without starting
a new save.

| | Disabled (default) | Enabled |
|---|---|---|
| **Shadows** | The main light in each room (FNV's "Key" lights, up to 6 per cell) casts shadows, so interiors have depth, like Fallout 4's. | No light casts a shadow, as in FNV. Rooms look flatter, the way they did in the original game. |
| **Color and contrast** | FNV's colors drawn through Fallout 4's camera curve: richer contrast, deeper darks, brighter highlights. | FNV's own straight color curve: the softer, washed contrast New Vegas had. Overall brightness stays the same. |

Everything else is the same either way: where lights are, their color and
reach, the weather, glowing signs and neon.

## Not done yet

- **Casino games and Caravan:** blackjack, roulette, slots and Caravan are
  being built now ([plan](docs/fork/fo4_casino_plan.md)). Until then the
  tables do nothing.
- **Fallout 3:** not converted yet.
- **Known gaps:** a few hundred dialogue lines whose conditions Fallout 4
  can't check, some creature animations (hit reactions and staggers on FNV's
  own rigs), FNV's third-person gun animations, precombines in the densest
  areas (Freeside, the Strip), and maps for Freeside and the Strip.

The full list (broken, missing, and built but not yet played) is in
[docs/fork/ROADMAP.md](docs/fork/ROADMAP.md#fo4-state). Please report what you
find in [the issues](https://github.com/ThyMrMan/fo3fnv-in-fo4/issues).

---

## Install

### What you need

- **Windows.** The conversion app also starts on macOS and Linux, but the
  build runs Windows-only tools.
- **Fallout 4**, current Steam version (1.11.240), and the **Fallout 4
  Creation Kit**, free on Steam. The build runs the Creation Kit for
  animation data.
- **Fallout: New Vegas** (Steam or GOG), with any DLC you want converted.
- **[Mod Organizer 2](https://github.com/ModOrganizer2/modorganizer)**
  (recommended: the build runs the Creation Kit through it, and every step
  below assumes it).
- These Fallout 4 mods, installed in MO2:
  - [F4SE](https://f4se.silverlock.org/) for 1.11.240;
  - [Address Library for F4SE Plugins](https://www.nexusmods.com/fallout4/mods/47327);
  - [Mod Configuration Menu](https://www.nexusmods.com/fallout4/mods/21497);
  - [Black Landscape Fix](https://www.nexusmods.com/fallout4/mods/108574)
    (F4SE version): without it, a Fallout 4 engine bug turns some patches
    of the Mojave's bare ground black.

  LevelUpMenuEx is no longer needed. On a save from an older build, keep it
  installed until you have opened the level-up menu once: that moves its
  saved skill and perk points and tagged skills over.
- **A strong PC:** 32 GB of RAM is recommended. Allow about 100 GB of free
  disk: the New Vegas export is about 10 GB, the build caches grow to about
  70 GB, and the output is about 10 GB. The first build converts every mesh
  and sound, so it takes far longer than a rebuild, which takes about 40
  minutes.

**Check your setup** (after step 2 below, and again after adding the output
to MO2): `.venv\Scripts\python.exe -m tools.validate.fo4_install_check`
prints one line per item above, with what to do for anything missing.

### Convert

1. **Download** this repository (the green **Code** button, then **Download
   ZIP**), and unzip it somewhere outside `Program Files`.
2. **Set up Python once:** double-click `TES Auto-Convert.cmd`. It installs
   Python 3.14 if needed and the packages the converter uses, then opens the
   old Skyrim app. Close that window.
3. **Start the Fallout 4 app:** in that folder, run
   ```bash
   .venv\Scripts\python.exe fo4_app.py
   ```
   The first time, a wizard asks for:
   - the game (New Vegas);
   - your New Vegas and Fallout 4 folders (both are detected);
   - your MO2 instance and profile;
   - where the converted files should go.
4. **Convert:** on the **Convert** screen, tick **Export**, **Helper
   plugin**, **Build**, **Install the F4SE plugin** and **Check**, choose
   **Whole**, and click **Start**. Tick **Faces** too for NPC faces made by
   the Creation Kit (slow: hours for the whole game). The **Finished**
   screen shows what was built and any warnings; **Install status** checks
   everything listed above.

The **Replacements** screen can swap converted items and creatures for
Fallout 4's own or other mods' versions. By default the conversion uses
FNV's own.

**The DLC and mods** convert after the base game, each into its own folder:
pick one under **What to convert** on the Convert screen (a DLC is listed
from your New Vegas Data folder; **Add a mod folder...** adds a mod), then
run **Export**, **Build** and **Check** as above. A mod also runs **Import
the mod folder** first.

### Add it to Mod Organizer

The easy way: choose output folders inside your MO2 instance's `mods`
folder (for example **F3NV - Fallout New Vegas**; each DLC gets its own,
such as **F3NV - Dead Money**). Then, with MO2 closed, click **Set up in
MO2** on the Finished screen after each conversion: it enables the mod and
its plugins in your profile, in the right order, and backs up the lists
first.

By hand:

1. In MO2, make an empty mod (for example **F3NV - Fallout New Vegas**) and
   copy the app's output folder into it. Give each DLC its own mod
   (**F3NV - Dead Money** and so on).
2. The **Install the F4SE plugin** stage put `F3NV.dll` in the output's
   `F4SE/Plugins/` folder; if you skipped it, copy `tes_runtime/dist/F3NV.dll`
   there.
3. Enable the mods and their plugins. `FalloutNV.esm` and `FalloutHelpers.esl`
   go after Fallout 4's own plugins, and the DLC after `FalloutNV.esm`.

### Play

Start Fallout 4 through F4SE (**Play** on the Finished screen, MO2's F4SE
entry, or `f4se_loader.exe`) and choose **New**. Fallout 4's intro and character creation run first. Then the
game moves you to Doc Mitchell's house in Goodsprings and plays FNV's intro.
Make your character there as in FNV. If the opening doesn't start, open the
console and type `setstage FNV_NewGame 10`.

**Updating:** download the new version over the old folder, convert again and
replace the mod folders. FormIDs stay stable between builds, but expect an
update to need a new game.

---

## For developers

The pipeline, every system's design and its measurements are in
[docs/fork/](docs/fork/). Start with:
- [fo4_pipeline.md](docs/fork/fo4_pipeline.md): how the build works;
- [ROADMAP.md](docs/fork/ROADMAP.md): status;
- [fo4_gui.md](docs/fork/fo4_gui.md): the app.

[CLAUDE.md](CLAUDE.md) holds the working rules. The command-line build of the
whole map is:

```bash
py -3.14 -m fo4_import.pipeline.run --export export/FalloutNV.esm --out <Data>/FalloutNV.esm --data <Data> --scripts temp/fo4_scripts/FalloutNV.esm --world WastelandNV reached --whole --no-test-cell GSDocMitchellHouse
```

Tests: `py -3.14 -m pytest tests/test_fo4_*.py`.

---

## Credits & License

First things first, I want to give credit to all the wonderful people I used to know on the Morroblivion forum, and those still working hard on Skyblivion and Skywind all these years later. You are an inspiration.

This project's own code is released under the **GNU GPL-3.0** ([LICENSE](LICENSE))
with a modding exception ([EXCEPTIONS](EXCEPTIONS)). The code it started from,
[tes4skyrim](https://github.com/bryantmh/tes4skyrim) by bryantmh and contributors,
stays under the **MIT License**; [NOTICE](NOTICE) says which is which. Everything
under `external/` is third-party and carries its own licensing, below.

| Contributor / Component | Used for | License / Terms |
|--------------------------|----------|-----------------|
| [xEdit and all contributors](https://github.com/TES5Edit/TES5Edit) | ESM record definitions; `BSArch.exe` (BSA packing) and `LODGenx64.exe` (object LOD) in `external/` | MPL-2.0 / GPL-2.0 (xEdit dual license) — redistributed |
| Zilav's Oblivion → Skyrim xEdit conversion scripts | The original inspiration and the information needed to get started | — (reference only, not redistributed) |
| [NifSkope](https://github.com/niftools/nifskope) contributors | NIF format documentation | — (reference only, not redistributed) |
| [Ormin — NIFConverter](https://github.com/Ormin/skyblivion-NIFConverter) | Mesh conversion reference | — (reference only, not redistributed) |
| [Ormin — ScriptConverter](https://github.com/Ormin/skyblivion-ScriptConverter) | OBScript → Papyrus transpilation reference | — (reference only, not redistributed) |
| [russo-2025 — papyrus-compiler](https://github.com/russo-2025/papyrus-compiler) | Papyrus compiler, `external/papyrus-compiler/papyrus.exe` | **MIT** (© 2025 russo-2025) — redistributed; license text in `external/papyrus-compiler/LICENSE` |
| [Orvid — Caprica](https://github.com/Orvid/Caprica) | Fallout 4 Papyrus compiler (v0.3.0), `external/caprica/Caprica.exe`, run before FO4's own | **MIT** (© 2015 Orvid King) — redistributed; license text in `external/caprica/LICENSE` |
| [LvxMagick — DovahNifWorkbench](https://www.nexusmods.com/skyrimspecialedition/mods/183399) | Mopp Bridge, `external/mopp_bridge/dovah_hkp_mesh_mopp_bridge.exe` | No stated license (Nexus-only, no public source). **Statically links Havok** — see the Havok note below |
| [Bad Dog — PyNifly](https://github.com/BadDogSkyrim/PyNifly) | Pure-Python Havok hk_2010 packfile reader + hkaSplineCompressedAnimation codec (vendored in `external/pynifly_hkx/`) — the heart of creature animation conversion | **GPL-3.0** (vendored from PyNifly 27.4.0; local changes marked `# TESConversion:`) — see the GPL note below |
| [OpenMW](https://openmw.org/) | The Morrowind dialogue engine and MWScript interpreter, vendored into `external/openmw/` and linked into `MorrowindRuntime.dll` | **GPL-3.0** — see the GPL note below. Vendored by `tools/generators/vendor_openmw.py`; license text in `external/openmw/LICENSE` |
| [figment — hkxcmd](https://github.com/figment/hkxcmd) | Havok packfile XML↔binary compiler, `external/hkxcmd/hkxcmd.exe`, used to build skeleton/behavior/animation `.hkx` | **BSD-3-Clause** for hkxcmd's own sources (© 2011; text in `external/hkxcmd/LICENSE.TXT`). **Statically links Havok** — see the Havok note below |
| [Monitor221hz — HKX2-Enhanced-Library](https://github.com/Monitor221hz/HKX2-Enhanced-Library) | Skyrim SE 64-bit Havok packfile ↔ XML, `external/hkxconv/hkxconv.exe`, used to patch the vanilla humanoid behavior graphs (`hkxcmd` cannot read 64-bit files). Forked from [ret2end](https://github.com/ret2end/HKX2Library), in turn from [katalash](https://github.com/katalash/DSMapStudio) / [krenyy](https://gitlab.com/HKX2/HKX2Library); bundles `BinaryReaderEx` from [JKAnderson — SoulsFormats](https://github.com/JKAnderson/SoulsFormats) | **No stated license** anywhere in that chain (no LICENSE file upstream) — community project, publicly distributed and freely forked; redistributed here on that basis. Full chain and rebuild steps in `external/hkxconv/README.md` |
| [Microsoft DirectX SDK (June 2010)](https://www.microsoft.com/en-us/download/details.aspx?id=6812) | `external/xwmaencode/xWMAEncode.exe`, xWMA voice compression | Microsoft — **not redistributed**; the launcher fetches it from Microsoft (see [Convert](#convert)) |
| [FFmpeg](https://ffmpeg.org/) | `external/ffmpeg/ffmpeg.exe`, decoding MP3/WAV voice and sound files | **LGPL v2.1 or later** — redistributed; license text in `external/ffmpeg/COPYING.LGPLv2.1`. See the LGPL note below |
| Oblivion banner font ([dafont](https://www.dafont.com/oblivion.font)) | Project banner | *Free for personal use only*, based on Bethesda's trademarked logo. **Not** bundled in this repo; the banner ships as pre-rendered vector outlines. |

> **Note on GPL-3.0:** `external/pynifly_hkx/` (creature animation conversion,
> `asset_convert/havok/hkx_anim.py`) and `external/openmw/` (linked into
> `MorrowindRuntime.dll`) are both GPL-3.0. If you redistribute a build that includes
> either, the GPL's terms apply to that distribution. `MorrowindRuntime.dll` is kept a
> separate DLL for this reason. `TESRuntime.dll` carries a line-for-line port of
> OpenMW's alchemy apparatus formula (`tes_runtime/tes/alchemy.cpp`), so it is
> GPL-3.0 as well.

> **Note on LGPL (FFmpeg):** `external/ffmpeg/ffmpeg.exe` is built from **unmodified**
> FFmpeg 7.1.2 sources under LGPL v2.1, with no GPL components (`--enable-gpl` and
> `--enable-version3` are both off). Because it is statically linked, LGPL §6 requires
> that recipients be able to relink it against a modified FFmpeg — satisfied by
> `tools/generators/build_ffmpeg.py`, which pins the exact upstream tarball and records every
> configure flag used to produce the shipped binary.

> ### ⚠️ Note on Havok
>
> Two bundled binaries — `hkxcmd.exe` and `dovah_hkp_mesh_mopp_bridge.exe` — statically
> link the **proprietary Havok SDK**. Both embed the notice:
>
> > *Copyright 1999-2011 Havok.com Inc. (and its Licensors). All Rights Reserved.
> > See www.havok.com for details.*
>
> **Neither author's license grants any rights to the Havok code inside.** These two
> binaries are redistributed here as-is.

