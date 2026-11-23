# fo3fnv-in-fo4

**Play Fallout: New Vegas and Fallout 3 inside Fallout 4.** This tool
converts your own copy of either game, its DLC and its mods into Fallout 4
plugins: the whole map, its quests, dialogue and voices, NPCs and creatures,
guns, perks, skills, karma and radio, plus New Vegas's reputation and
Hardcore mode.

> [!WARNING]
> **Alpha.** New Vegas is playable from Doc Mitchell's house onward, and
> nearly every system is built, but much of it has never been played start
> to finish. **Fallout 3 is experimental:** only its opening in Vault 101
> has been tested ([below](#fallout-3)). Expect bugs. Expect some updates to
> need a new game. Back up your saves.

> [!NOTE]
> **⚠ AI-Led Development Notice.** This project was developed entirely with
> AI tooling, primarily Claude Opus, with in-game testing and guidance
> provided. It is open source under the GPL-3.0 license
> ([below](#credits--license)).

> [!IMPORTANT]
> **No game files are included.** This project ships only code. It reads
> the games you own and converts them on your PC. **Don't share the
> converted files.**

---

## What you get

| Plugin | What it is |
|---|---|
| `FalloutNV.esm` or `Fallout3.esm` | The game: its whole map and every interior, its NPCs, quests, dialogue and scripts |
| `FalloutHelpers.esl` | Shared records the converted plugins use |
| New Vegas: `DeadMoney.esm`, `HonestHearts.esm`, `OldWorldBlues.esm`, `LonesomeRoad.esm`, `GunRunnersArsenal.esm`, and the packs `CaravanPack.esm`, `ClassicPack.esm`, `MercenaryPack.esm`, `TribalPack.esm` | The DLC and add-on packs you own |
| Fallout 3: `Anchorage.esm`, `ThePitt.esm`, `BrokenSteel.esm`, `PointLookout.esm`, `Zeta.esm` | The DLC you own |
| `FalloutNV - Classic Look.esl` | Optional, New Vegas only: its flatter lighting and color ([below](#classic-look)) |
| `F3NV.dll` | The project's F4SE plugin: the rules of the old games that Fallout 4 can't do by itself (Damage Threshold, item condition, the Pip-Boy's SKILLS, REPUTATION, KARMA and CHALLENGES tabs, Hardcore's ammo weight and HUD, the dialogue menu) |

**In the game:**
- **The world:** the land, buildings and interiors, distant land and
  objects, the game's own weather and the Pip-Boy world map.
- **People and creatures:** NPCs with their own faces and outfits; geckos,
  cazadores, yao guai, super mutants, robots and the rest on their own
  skeletons and animations; the game's own spawns.
- **Dialogue and quests:** the original voices with lip sync, in a dialogue
  menu with the full line text; every quest script converted.
- **Your character:** SPECIAL, the skills, the perks and traits, the
  original level-up and tag skill menus (options in MCM), karma and chem
  addiction. New Vegas adds its traits, reputation, challenges and Hardcore
  mode.
- **Combat:** the original guns, ammo types and the ammo hotkey, item
  condition and repair, critical hits, sneak attacks, grenades and mines,
  and V.A.T.S. tuned toward the old games'. New Vegas adds its weapon mods
  and Damage Threshold.
- **Also:** the radio stations, terminals, and lockpicking and hacking by
  skill. New Vegas adds its casino games, Caravan and its intro movie.

**Mods:** about 20 New Vegas mods convert on top of the game, for example
YUP, NVMIM, Willow, JSawyer Ultimate, the New Vegas Bounties series, Russell,
The Living Desert and Better Brotherhood. Fallout 3 mods go through the
same steps, but none has been tested yet.

Known problems are listed in the
[roadmap](docs/fork/ROADMAP.md#known-bugs); where play
differs from the original games is in [fo4_drift.md](docs/fork/fo4_drift.md).

---

## <a id="install"></a>Install

### What you need

| | |
|---|---|
| **Windows 10 or 11** | The tested setup. Linux and macOS may work, since the conversion no longer runs the Creation Kit for its main work, but nobody has tried them yet ([below](#other-systems)). |
| **Fallout 4** | The current Steam version, **1.11.240**. |
| **Fallout 4 Creation Kit** | Free on [Steam](https://store.steampowered.com/app/1946160/). Install it, but you don't need to open it. Converted scripts compile against the Fallout 4 script sources it installs (`Data\Scripts\Source\Base\Base.zip`). The app also falls back on it for the few faces our own FaceGen can't make. |
| **Fallout: New Vegas or Fallout 3** | Steam or GOG, with any DLC you want converted. For Fallout 3, the Game of the Year edition has all five DLC. |
| **[Mod Organizer 2](https://github.com/ModOrganizer2/modorganizer)** | Set up for Fallout 4. The steps below assume it. |
| **[F4SE](https://f4se.silverlock.org/)** | For 1.11.240, installed into your Fallout 4 folder, its `Data` folder included (converted scripts compile against its script sources). |
| **Three mods in MO2** | [Address Library for F4SE Plugins](https://www.nexusmods.com/fallout4/mods/47327), [Mod Configuration Menu](https://www.nexusmods.com/fallout4/mods/21497), [Black Landscape Fix](https://www.nexusmods.com/fallout4/mods/108574) (the F4SE version; without it, some bare ground turns black). |
| **A strong PC** | 32 GB of RAM and about 100 GB of free disk space. |

> [!CAUTION]
> **Uninstall or disable Extended Dialogue Interface (XDI)** before you play.
> The conversion's dialogue runs entirely through its own menu framework,
> Cleanroom UI (`CleanroomDialogue.dll` and `CleanroomUI.dll`, installed with
> the converted game): every conversation, its full line text, the skill and
> speech checks, and the quest stages and scripts that dialogue starts. While
> XDI is loaded it takes over the dialogue menu and Cleanroom UI's menu
> switches itself off, so most conversations, and the quests that depend on
> them, break. **Install status** flags XDI if it finds it.

<a id="other-systems"></a>**On Linux or macOS** (untested): install Python 3.14,
then run `python3.14 -m pip install -r requirements.txt` and
`python3.14 fo4_app.py` in the downloaded folder instead of the `.cmd`
launcher. Install the Creation Kit through Steam anyway, for its script
sources. The few faces our own FaceGen can't make fall back to running it,
and it runs only on Windows. Please [report](#problems) how it goes.

### 1. Download

1. Open the [Releases page](https://github.com/ThyMrMan/fo3fnv-in-fo4/releases)
   and download **`fo3fnv-in-fo4-<release>.zip`** from the newest release's
   assets (about 12 MB), not **Source code (zip)**: that one is the
   developers' whole repository, and it can't build the menus without
   extra tools.
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
1. **Which game:** Fallout: New Vegas or Fallout 3 (experimental). You can
   switch at any time on the Convert screen.
2. **Game folders:** your Fallout 4 folder and the folder of each game you
   own (usually found for you).
3. **Mods:** pick **A Mod Organizer 2 instance**, then its folder and
   profile.
4. **Where files go:** choose an output folder **inside your MO2
   instance's `mods` folder**, for example
   `...\mods\F3NV - Fallout New Vegas`. That lets the app enable everything
   in MO2 for you. Pick a work folder on a drive with plenty of free space.
   Each game keeps its own output folder.

### 4. Convert the game

On the **Convert** screen:
1. Under **1. Game**, pick the game, for example **Fallout: New Vegas**.
2. Under **2. What to convert**, pick the game itself, for example
   **FalloutNV.esm: the game**. Each row says whether it is built yet.
3. Click the **Convert** button. It names what it will build, for example
   **Convert FalloutNV.esm**.

The bold line above the button always says what to do next. Leave **Show
advanced options** folded: the stages and the scope (**Whole**) are already
set.

The first conversion takes several hours: it converts every mesh, texture,
sound and face once. Later rebuilds reuse that work and take minutes. Keep
the app open until the **Finished** screen appears.

### 5. Add it to Mod Organizer

Close MO2, then click **Set up in MO2** on the Finished screen. It enables
the converted mod and its plugins in your profile in the right order, after
backing up your lists. Click **Install status** to check that everything is
in place.

If your output folder isn't inside MO2's `mods` folder, copy it there as a
new mod, enable it, and tick the game's plugin (`FalloutNV.esm` or
`Fallout3.esm`) and `FalloutHelpers.esl` in the plugin list, after
Fallout 4's own plugins.

### 6. Play

Start Fallout 4 through F4SE: **Play** on the Finished screen, or MO2's F4SE
entry. Choose **New**. For New Vegas, Fallout 4's intro and character
creation come first; then the game moves you to Doc Mitchell's house in
Goodsprings, plays New Vegas's intro, and you make your character as in New
Vegas. Fallout 3 starts in Vault 101 ([below](#fallout-3)).

If the opening doesn't start, open the console (`~`) and type
`setstage FNV_NewGame 10`. The quest has this name for both games.

## <a id="convert"></a>The DLC and mods

Convert the game first; its DLC and mods build on it. Each goes into its
own mod folder.

- **A DLC or add-on pack:** pick it under **2. What to convert** (the app
  lists the ones in your game's `Data` folder) and click **Convert** (the
  button carries its name). It goes into its own folder beside the game's, such as
  `F3NV - Dead Money`.
- **A mod:** click **Add a mod folder...** beside the list and choose the
  folder holding the mod's plugin (for example a mod you unpacked, or one
  from your old mod manager). It joins the list, picked; click
  **Convert**. The app imports it, then converts it the same way. Pick the
  game the mod was made for under **1. Game** first.

After each one, click **Set up in MO2** again. The DLC and mods load after
the game's plugin.

## <a id="fallout-3"></a>Fallout 3

Fallout 3 converts the same way as New Vegas, with a few differences. It is
experimental: so far only its opening in Vault 101 has been built and
played, by our automated test runs. The rest of the Capital Wasteland and
the DLC convert the same way but are untested.

**Set it up apart from New Vegas.** Both games' plugins carry the
new-game quest, so with both loaded, both openings start at once.
- In MO2, make a second Fallout 4 profile for it, for example "Fallout 3".
- On the **Setup** screen, with **Convert from** set to Fallout 3, choose
  its own output folder inside MO2's `mods` folder, for example
  `...\mods\F3NV - Fallout 3`.
- Under **Mods to pick replacements from**, set your MO2 row's **MO2
  profile** to the Fallout 3 one while you work on Fallout 3, and back to your New Vegas
  profile afterward. **Set up in MO2** and **Play** use that profile.

**Convert it.** On the Convert screen, pick **Fallout 3** under **1. Game**,
then **Fallout3.esm: the game**, and click **Convert Fallout3.esm**. Its
DLC (Operation: Anchorage, The Pitt, Broken Steel, Point Lookout and
Mothership Zeta) then show in the list as `convert Fallout3.esm first`
until it is built, and each converts into its own folder, such as
`F3NV - BrokenSteel`. Then click **Set up in MO2** on the Finished screen.

**What to expect in game:**
- Fallout 4's own intro movie plays first; Fallout 3's isn't converted yet.
- You are born in Vault 101 and play the opening as in Fallout 3: birth,
  Baby Steps, the 10th birthday, the G.O.A.T. and the escape. The race and
  SPECIAL menus open where Fallout 3 opens them.
- The child years play on the adult body, and the child jumpsuit doesn't
  show on it yet.
- A level you gain inside the vault arrives at once; Fallout 3 held it until
  you left.
- New Vegas's systems stay off: no reputation, challenges, Hardcore mode,
  casino or Classic Look plugin.
- Past the vault door is unplayed. Please [report](#problems) what you find.

## Updating

1. Download the new release and unzip it over your old folder (or into a
   new one; your settings come along if you kept them beside the app).
2. Start the app, pick the game and its plugin (for example
   **FalloutNV.esm**) and click **Convert**. It rebuilds only what the
   update touched, then the DLC and mods built on it.
3. **Install status** names any plugin still built by an older release.

The release notes say whether an update needs a new game. Your saves keep
working across rebuilds unless they say otherwise.

## <a id="classic-look"></a>Classic Look

New Vegas only. `FalloutNV - Classic Look.esl` is optional (tick **Classic Look plugin** under
the Convert screen's advanced options). It changes only lighting and color, so you can turn it
on or off at any time, mid-game, without a new save.

| | Off (default) | On |
|---|---|---|
| **Shadows** | The main lights in each room cast shadows, so interiors have depth, as in Fallout 4. | No light casts a shadow, as in New Vegas: rooms look flatter. |
| **Color** | New Vegas's colors through Fallout 4's camera curve: richer contrast, deeper darks. | New Vegas's own softer, washed-out contrast, at the same brightness. |

Everything else is the same either way: where lights are, their color and
reach, the weather, glowing signs and neon.

## <a id="problems"></a>Problems and reports

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

[CLAUDE.md](CLAUDE.md) holds the working rules. The command-line build of
New Vegas's whole map is below; Fallout 3's opening build is in
[fo4_fo3_plan.md](docs/fork/fo4_fo3_plan.md#build).

```bash
py -3.14 -m fo4_import.pipeline.run --export export/FalloutNV.esm --out <Data>/FalloutNV.esm --data <Data> --scripts temp/fo4_scripts/FalloutNV.esm --world WastelandNV reached --whole --no-test-cell GSDocMitchellHouse
```

Tests: `py -3.14 -m pytest tests/test_fo4_*.py`.

---

## Credits & License

Thanks first to the people who kept Fallout 3 and New Vegas moddable for
fifteen years: the authors of xEdit, NVSE and xNVSE, JIP LN NVSE, FOSE and
F4SE, and the writers of the GECK and Fallout wikis, whose work this project
leans on every day. And thanks to the Morroblivion, Skyblivion and Skywind
communities, where this all started. You are an inspiration.

This project's own code is released under the **GNU GPL-3.0** ([LICENSE](LICENSE))
with a modding exception ([EXCEPTIONS](EXCEPTIONS)). The code it started from,
[tes4skyrim](https://github.com/bryantmh/tes4skyrim) by bryantmh and contributors,
stays under the **MIT License**; [NOTICE](NOTICE) says which is which. Converted
game files come from your own copies of Bethesda's games; none of these licenses
cover them.

### What the Fallout 4 conversion uses

| Contributor / Component | Used for | License / Terms |
|--------------------------|----------|-----------------|
| [xEdit and all contributors](https://github.com/TES5Edit/TES5Edit) | Record layouts for all three games; the condition functions and actor value names, read from `wbDefinitionsFNV.pas`, `wbDefinitionsFO3.pas` and `wbDefinitionsFO4.pas` in `external/xedit/`; `LODGenx64.exe` (distant objects) in `external/lodgen/`; FO4Edit's optional full check | MPL-2.0 / GPL-2.0 (xEdit dual license); the definitions are unmodified, MPL-2.0 text in `external/xedit/LICENSE.txt`; LODGen redistributed |
| [F4SE](https://f4se.silverlock.org/) team | `F3NV.dll` is an F4SE plugin built against F4SE 0.7.9's source | F4SE's own terms; F4SE itself is not redistributed (you install it) |
| [ThyMrMan — Cleanroom UI](https://github.com/ThyMrMan/cleanroom-ui) | The dialogue menu and menu framework: `CleanroomDialogue.dll` and `CleanroomUI.dll`, and its plugin, movies, translations, MCM page and scripts (built from the pinned commit, prebuilt in the release download) | **GPL-3.0** with the modding exception; redistributed |
| [7-Zip](https://www.7-zip.org/) (Igor Pavlov) | `external/7zip/`: the launcher takes `xWMAEncode.exe` out of Microsoft's SDK installer; reading mod archives | **GNU LGPL** with BSD-3-clause and unRAR parts; redistributed, license text in `external/7zip/License.txt` |
| [zlib](https://zlib.net/) (Jean-loup Gailly, Mark Adler) | `native/dist/f3_zlib.dll`: one pinned zlib, so the same build gives the same bytes on every PC | **zlib License**; redistributed, license text in `native/src/f3_zlib/zlib/LICENSE` |
| [Orvid — Caprica](https://github.com/Orvid/Caprica) | Fallout 4 Papyrus compiler (v0.3.0), `external/caprica/Caprica.exe` | **MIT** (© 2015 Orvid King); redistributed, license text in `external/caprica/LICENSE` |
| [Bad Dog — PyNifly](https://github.com/BadDogSkyrim/PyNifly) | Havok packfile reader and animation codec, vendored in `external/pynifly_hkx/`: creature and gun animation conversion | **GPL-3.0** (vendored from PyNifly 27.4.0; local changes marked `# TESConversion:`); see the GPL note below |
| [FFmpeg](https://ffmpeg.org/) | `external/ffmpeg/ffmpeg.exe`, decoding the games' MP3 and WAV voice and sound files | **LGPL v2.1 or later**; redistributed, license text in `external/ffmpeg/COPYING.LGPLv2.1`. See the LGPL note below |
| [Microsoft DirectX SDK (June 2010)](https://www.microsoft.com/en-us/download/details.aspx?id=6812) | `xWMAEncode.exe`, compressing voice lines | Microsoft; **not redistributed**: the launcher fetches it from Microsoft |
| [Apache Flex SDK](https://flex.apache.org/) | Compiling our own menus' ActionScript into Flash movies | **Apache-2.0**; a build tool, not shipped (the release download carries the movies it built). Adobe's `playerglobal.swc` is never shipped or committed |
| [Dear-Modding-FO4 — CommonLibF4](https://github.com/Dear-Modding-FO4/commonlibf4) | `F3NVTest.dll`, the automated test runs' control channel | **GPL-3.0**; test-only, never shipped |
| Bethesda — Fallout 4 Creation Kit | The Fallout 4 script sources converted scripts compile against, unpacked from your install; the fallback for faces our own FaceGen can't make | Bethesda's terms; installed by you from Steam, not redistributed |
| xNVSE, JIP LN NVSE and FOSE sources; the GECK, Fallout and Fallout 4 Creation Kit wikis; [NifSkope](https://github.com/niftools/nifskope); Neanka's LevelUpMenuEx and HUDFramework | What the old games' functions, records and meshes really do, and how Fallout 4's menus are built | Reference only, not redistributed |

### Inherited from the Skyrim converter

The Morrowind and Oblivion to Skyrim converter this project grew from is still
in the repository (`TES Auto-Convert.cmd`; use
[ThyMrMan/tes4skyrim](https://github.com/ThyMrMan/tes4skyrim) for it). The
Fallout 4 conversion doesn't use these, but they ship with the source:

| Contributor / Component | Used for (by the Skyrim converter) | License / Terms |
|--------------------------|----------|-----------------|
| [xEdit](https://github.com/TES5Edit/TES5Edit) | `BSArch.exe` (BSA packing) in `external/bsarch/` | MPL-2.0 / GPL-2.0; redistributed |
| Zilav's Oblivion → Skyrim xEdit conversion scripts | The original inspiration and the information needed to get started | Reference only, not redistributed |
| [Ormin — NIFConverter](https://github.com/Ormin/skyblivion-NIFConverter) and [ScriptConverter](https://github.com/Ormin/skyblivion-ScriptConverter) | Mesh and OBScript → Papyrus conversion reference | Reference only, not redistributed |
| [russo-2025 — papyrus-compiler](https://github.com/russo-2025/papyrus-compiler) | Skyrim Papyrus compiler, `external/papyrus-compiler/papyrus.exe` | **MIT** (© 2025 russo-2025); redistributed, license text in `external/papyrus-compiler/LICENSE` |
| [OpenMW](https://openmw.org/) | The Morrowind dialogue engine and MWScript interpreter, vendored into `external/openmw/` and linked into `MorrowindRuntime.dll` | **GPL-3.0**; see the GPL note below. License text in `external/openmw/LICENSE` |
| [figment — hkxcmd](https://github.com/figment/hkxcmd) | Havok packfile XML ↔ binary, `external/hkxcmd/hkxcmd.exe` | **BSD-3-Clause** for its own sources (text in `external/hkxcmd/LICENSE.TXT`). **Statically links Havok**; see the Havok note below |
| [Monitor221hz — HKX2-Enhanced-Library](https://github.com/Monitor221hz/HKX2-Enhanced-Library) | Skyrim SE 64-bit Havok packfile ↔ XML, `external/hkxconv/hkxconv.exe`. Forked from [ret2end](https://github.com/ret2end/HKX2Library), in turn from [katalash](https://github.com/katalash/DSMapStudio) / [krenyy](https://gitlab.com/HKX2/HKX2Library); bundles `BinaryReaderEx` from [JKAnderson — SoulsFormats](https://github.com/JKAnderson/SoulsFormats) | **No stated license** anywhere in that chain; a community project, publicly distributed and freely forked, redistributed here on that basis. Details in `external/hkxconv/README.md` |
| [LvxMagick — DovahNifWorkbench](https://www.nexusmods.com/skyrimspecialedition/mods/183399) | Mopp Bridge, `external/mopp_bridge/dovah_hkp_mesh_mopp_bridge.exe` | No stated license (Nexus only, no public source). **Statically links Havok**; see the Havok note below |
| Oblivion banner font ([dafont](https://www.dafont.com/oblivion.font)) | The Skyrim converter's banner | *Free for personal use only*, based on Bethesda's trademarked logo. **Not** bundled; the banner ships as pre-rendered vector outlines |

> **Note on GPL-3.0:** `external/pynifly_hkx/` (animation conversion for both
> converters) and `external/openmw/` (linked into the Skyrim converter's
> `MorrowindRuntime.dll`) are GPL-3.0, as is this project's own code. If you
> redistribute a build that includes either, the GPL's terms apply to that
> distribution. `TESRuntime.dll` carries a line-for-line port of OpenMW's alchemy
> apparatus formula (`tes_runtime/tes/alchemy.cpp`), so it is GPL-3.0 as well.

> **Note on LGPL (FFmpeg):** `external/ffmpeg/ffmpeg.exe` is built from **unmodified**
> FFmpeg 7.1.2 sources under LGPL v2.1, with no GPL components (`--enable-gpl` and
> `--enable-version3` are both off). Because it is statically linked, LGPL §6 requires
> that recipients be able to relink it against a modified FFmpeg — satisfied by
> `tools/generators/build_ffmpeg.py`, which pins the exact upstream tarball and records every
> configure flag used to produce the shipped binary.

> ### ⚠️ Note on Havok
>
> Two binaries the Skyrim converter bundles, `hkxcmd.exe` and
> `dovah_hkp_mesh_mopp_bridge.exe`, statically link the **proprietary Havok SDK**.
> Both embed the notice:
>
> > *Copyright 1999-2011 Havok.com Inc. (and its Licensors). All Rights Reserved.
> > See www.havok.com for details.*
>
> **Neither author's license grants any rights to the Havok code inside.** These two
> binaries are redistributed here as-is. The Fallout 4 conversion uses neither: it
> writes Fallout 4's Havok physics with its own code.
