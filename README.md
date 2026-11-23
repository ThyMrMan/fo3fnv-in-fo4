# fo3fnv-in-fo4

**Play Fallout: New Vegas inside Fallout 4.** This tool converts your own
copy of New Vegas, its DLC and many of its mods into Fallout 4 plugins: the
whole Mojave, its quests, dialogue and voices, NPCs and creatures, guns,
perks, skills, reputation, karma, Hardcore mode and radio.

> [!WARNING]
> **Alpha.** New Vegas is playable from Doc Mitchell's house onward, and
> nearly every system is built, but much of it has never been played start
> to finish. Expect bugs. Expect some updates to need a new game. Back up
> your saves.

> [!IMPORTANT]
> **No game files are included.** This project ships only code. It reads
> the games you own and converts them on your PC. **Don't share the
> converted files.**

---

## What you get

| Plugin | What it is |
|---|---|
| `FalloutNV.esm` | New Vegas: the Mojave and every interior, its NPCs, quests, dialogue and scripts |
| `FalloutHelpers.esl` | Shared records the converted plugins use |
| `DeadMoney.esm`, `HonestHearts.esm`, `OldWorldBlues.esm`, `LonesomeRoad.esm`, `GunRunnersArsenal.esm` | The DLC you own |
| `CaravanPack.esm`, `ClassicPack.esm`, `MercenaryPack.esm`, `TribalPack.esm` | The add-on packs you own |
| `FalloutNV - Classic Look.esl` | Optional: New Vegas's flatter lighting and color ([below](#classic-look)) |
| `F3NV.dll` | The project's F4SE plugin: the New Vegas rules Fallout 4 can't do by itself (Damage Threshold, item condition, the Pip-Boy's SKILLS, REPUTATION, KARMA and CHALLENGES tabs, Hardcore's ammo weight and HUD, the dialogue menu) |

**In the game:**
- **The world:** the Mojave's land, buildings and interiors, distant land
  and objects, New Vegas's weather and the Pip-Boy world map.
- **People and creatures:** NPCs with their own faces and outfits; geckos,
  cazadores, nightstalkers, securitrons and the rest on their own skeletons
  and animations; New Vegas's spawns.
- **Dialogue and quests:** New Vegas's voices with lip sync, in a dialogue
  menu with the full line text; every quest script converted.
- **Your character:** SPECIAL, the 13 skills, 200+ perks and traits, New
  Vegas's level-up, tag skill and trait menus (options in MCM), reputation,
  karma, challenges, Hardcore mode, chem addiction.
- **Combat:** New Vegas's guns, ammo types and the ammo hotkey, weapon mods,
  item condition and repair, critical hits, Damage Threshold, sneak attacks,
  grenades and mines, and V.A.T.S. tuned toward New Vegas's.
- **Also:** the radio stations, terminals, lockpicking and hacking by skill,
  the casino games and Caravan, and New Vegas's intro movie.

**Mods:** about 20 New Vegas mods convert on top of the game, for example
YUP, NVMIM, Willow, JSawyer Ultimate, the New Vegas Bounties series, Russell,
The Living Desert and Better Brotherhood.

**Fallout 3** is experimental: it converts from the command line, not the
app yet, and only its opening (Vault 101) has been tested in game. Keep it
in its own Mod Organizer profile: with New Vegas loaded too, both openings
start at once.

Known problems are listed in the
[roadmap](docs/fork/ROADMAP.md#known-bugs); where play
differs from New Vegas is in [fo4_drift.md](docs/fork/fo4_drift.md).

---

## <a id="install"></a>Install

### What you need

| | |
|---|---|
| **Windows 10 or 11** | The conversion runs Windows-only tools. |
| **Fallout 4** | The current Steam version, **1.11.240**. |
| **Fallout 4 Creation Kit** | Free on [Steam](https://store.steampowered.com/app/1946160/). The conversion uses its tools; you don't need to open it. |
| **Fallout: New Vegas** | Steam or GOG, with any DLC you want converted. |
| **[Mod Organizer 2](https://github.com/ModOrganizer2/modorganizer)** | Set up for Fallout 4. The steps below assume it. |
| **[F4SE](https://f4se.silverlock.org/)** | For 1.11.240, installed into your Fallout 4 folder. |
| **Three mods in MO2** | [Address Library for F4SE Plugins](https://www.nexusmods.com/fallout4/mods/47327), [Mod Configuration Menu](https://www.nexusmods.com/fallout4/mods/21497), [Black Landscape Fix](https://www.nexusmods.com/fallout4/mods/108574) (the F4SE version; without it, some bare ground turns black). |
| **A strong PC** | 32 GB of RAM and about 100 GB of free disk space. |

**Turn off Extended Dialogue Interface** if you have it: `F3NV.dll` brings
its own dialogue menu, which switches itself off while XDI is loaded.

### 1. Download

1. Open the [Releases page](https://github.com/ThyMrMan/fo3fnv-in-fo4/releases)
   and download **Source code (zip)** from the newest release.
2. Unzip it to a folder you can write to, outside `Program Files`, for
   example `C:\Games\fo3fnv-in-fo4`.

### 2. Start the app

Double-click **`Convert to Fallout 4.cmd`** in that folder.

- The first time, it installs Python 3.14 (if you don't have it) and the
  packages the converter needs. This takes a few minutes.
- It offers to download `xWMAEncode.exe` from Microsoft (part of the DirectX
  SDK, about 600 MB, deleted afterward). Say yes: voice lines need it.
- It checks your PC against the list above, then opens the app. Anything
  missing is listed with what to do; the window stays open until you press a
  key.

### 3. First-run setup

The app asks four things. Each one can be changed later on the **Setup**
screen.
1. **Which game:** Fallout: New Vegas.
2. **Game folders:** your New Vegas and Fallout 4 folders (usually found for
   you).
3. **Mods:** pick **A Mod Organizer 2 instance**, then its folder and
   profile.
4. **Where files go:** choose an output folder **inside your MO2
   instance's `mods` folder**, for example
   `...\mods\F3NV - Fallout New Vegas`. That lets the app enable everything
   in MO2 for you. Pick a work folder on a drive with plenty of free space.

### 4. Convert New Vegas

On the **Convert** screen:
1. Under **What to convert**, pick **FalloutNV.esm**.
2. Under **What the build covers**, pick **Whole**.
3. Leave the default stages ticked (Export, Helper plugin, Build, Faces,
   Install the F4SE plugin, Check references).
4. Click **Start**.

The first conversion takes several hours: it converts every mesh, texture,
sound and face once. Later rebuilds reuse that work and take minutes. Keep
the app open until the **Finished** screen appears.

### 5. Add it to Mod Organizer

Close MO2, then click **Set up in MO2** on the Finished screen. It enables
the converted mod and its plugins in your profile in the right order, after
backing up your lists. Click **Install status** to check that everything is
in place.

If your output folder isn't inside MO2's `mods` folder, copy it there as a
new mod, enable it, and tick `FalloutNV.esm` and `FalloutHelpers.esl` in the
plugin list, after Fallout 4's own plugins.

### 6. Play

Start Fallout 4 through F4SE: **Play** on the Finished screen, or MO2's F4SE
entry. Choose **New**. Fallout 4's intro and character creation come first;
then the game moves you to Doc Mitchell's house in Goodsprings, plays New
Vegas's intro, and you make your character as in New Vegas.

If the opening doesn't start, open the console (`~`) and type
`setstage FNV_NewGame 10`.

## <a id="convert"></a>The DLC and mods

Convert New Vegas first; the DLC and mods build on it. Each goes into its
own mod folder.

- **A DLC or add-on pack:** pick it under **What to convert** (the app lists
  the ones in your New Vegas `Data` folder), keep **Whole**, and click
  **Start**. It goes into its own folder beside the game's, such as
  `F3NV - Dead Money`.
- **A mod:** click **Add a mod folder...** and choose the folder holding the
  mod's plugin (for example a mod you unpacked, or one from your New Vegas
  mod manager). The app imports it, then converts it the same way.

After each one, click **Set up in MO2** again. The DLC and mods load after
`FalloutNV.esm`.

## Updating

1. Download the new release and unzip it over your old folder (or into a
   new one; your settings come along if you kept them beside the app).
2. Start the app, pick **FalloutNV.esm**, make sure **Rebuild what changed**
   is ticked, and click **Start**. It rebuilds only what the update touched, then the DLC
   and mods built on it.
3. **Install status** names any plugin still built by an older release.

The release notes say whether an update needs a new game. Your saves keep
working across rebuilds unless they say otherwise.

## <a id="classic-look"></a>Classic Look

`FalloutNV - Classic Look.esl` is optional (tick **Classic Look plugin** on
the Convert screen). It changes only lighting and color, so you can turn it
on or off at any time, mid-game, without a new save.

| | Off (default) | On |
|---|---|---|
| **Shadows** | The main lights in each room cast shadows, so interiors have depth, as in Fallout 4. | No light casts a shadow, as in New Vegas: rooms look flatter. |
| **Color** | New Vegas's colors through Fallout 4's camera curve: richer contrast, deeper darks. | New Vegas's own softer, washed-out contrast, at the same brightness. |

Everything else is the same either way: where lights are, their color and
reach, the weather, glowing signs and neon.

## Problems and reports

- **Install status** (Finished screen) checks every requirement and says
  what to do about each problem.
- Known bugs are listed in the
  [roadmap](docs/fork/ROADMAP.md#known-bugs).
- Please report what you find in
  [the issues](https://github.com/ThyMrMan/fo3fnv-in-fo4/issues). Name the
  release (shown in the app's title bar) and attach the conversion's
  warnings or your Papyrus log.

---

## Where this came from

This project began as a fork of
[bryantmh/tes4skyrim](https://github.com/bryantmh/tes4skyrim) (TES
Auto-Convert), by way of
[ThyMrMan/tes4skyrim](https://github.com/ThyMrMan/tes4skyrim), which
converts Morrowind and Oblivion to Skyrim. The Fallouts moved to Fallout 4
because it already has guns, V.A.T.S., crippled limbs, radiation, terminals,
the Pip-Boy and radio. The inherited Skyrim converter is still in this
repository (`TES Auto-Convert.cmd` opens it); use ThyMrMan/tes4skyrim for
it.

## For developers

The pipeline, every system's design and its measurements are in
[docs/fork/](docs/fork/). Start with:
- [fo4_pipeline.md](docs/fork/fo4_pipeline.md): how the build works;
- [ROADMAP.md](docs/fork/ROADMAP.md): status;
- [fo4_gui.md](docs/fork/fo4_gui.md): the app;
- [fo4_plan_release.md](docs/fork/fo4_plan_release.md#release-identity):
  releases (`f3nv-<major>.<minor>` tags).

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

