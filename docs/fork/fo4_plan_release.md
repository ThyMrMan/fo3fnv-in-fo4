# Plan: one release path for testers

Status: phase 1 built ([install check](#install-check)); the rest designed,
not built. Overall status is in the
[roadmap](ROADMAP.md#fo4-app); sizes come from the
[issue plan](fo4_issue_plan.md#medium).

## <a id="goal"></a>Goal

A tester downloads one release, follows one install route, and gets the
base game, the DLC and the packs converted, installed and launched from the
app. An update then rebuilds only what changed, or ships scripts alone when
that is enough. Every distribution row below is a piece of that one path.

| Row | Size | Doc |
|---|---|---|
| Clean-machine install | M | [install](../../README.md#install) |
| Conversion app phase 7: MO2 setup, Play, the DLL, movies, FaceGen, DLC | L | [phases](fo4_gui.md#phases) |
| Replacement profiles | M | [direction](fo4_replacements.md#direction) |
| Wabbajack modlist | XL | [direction](fo4_replacements.md#direction) |
| Mod builds | M | [mod builds](fo4_mod_builds.md) |
| Build only what changed | Built | [which builds](fo4_plugin_layout.md#which-builds) |
| Meshes and materials in the Main BA2 (load time) | Play | [below](#load-time), [main archive](fo4_pipeline.md#main-archive) |

## <a id="exists"></a>What exists

**The app** (`fo4_app.py`, `fo4_import/app/`):
- `stages.GAMES` knows one plugin per source game (`FalloutNV.esm`). There
  is no DLC or pack stage; the README gives the DLC command lines by hand.
- `stages.command` and `stages.build_arguments` build the export, helper
  plugin, build and check command lines. `stages.package` zips the output.
- `finished_view.INSTALL_NOTES` tells the user to install `F3NV.dll`
  separately. There is no Play button and no update check.
- `core/mod_sources.py` reads an MO2 instance (`mo2_layout`,
  `mo2_folders`, `enabled_mods`) for mod sources, read-only.
- The [required mods](fo4_gui.md#required-mods) dialog
  (`app/required_mods.py`) uses `replacements.presence`, the loader's own
  installed check.

**What the build already ships** (read in code, not checked on a clean
machine):
- **The DLL.** `spike/condition.py` copies `tes_runtime/dist/F3NV.dll` into
  `<data>/F4SE/Plugins/` on the base build (not on a DLC build, where
  `builder.built` is set). The README's step 2 and the Finished notes
  predate this.
- **The movie.** `spike/build_finish.py` calls `base/bink.write_movies`,
  which writes FNV's `Video` folder into the build's Data
  ([as built](bink_movies.md#plan)).
- **Gun animation data** without the Creation Kit:
  `build_finish._gun_anim_text` ([writer](research/anim_text_data.md#writer)).

**What still needs the Creation Kit through MO2:**
- `pipeline/creation_kit.py` fixes `MO2 = C:\Modlists\fo3fnv-in-fo4` and
  runs `ModOrganizer.exe run -e "Creation Kit"` (`creation_kit.run`). The
  app's MO2 choice does not reach it.
- `rig/anim_info.generate` runs it on every build whose races name a graph
  (`build_finish`, own-rig creatures). The CK sees MO2's Data, so it reads
  the *deployed* mod, not the build folder
  ([anim info](fo4_own_rig.md#anim-info)).
- `spike/facegen.run_ck` runs `-ExportFaceGenData` the same way. It is a
  separate command after the build; neither the app nor the README runs it.
- Face fits can be published and installed (`spike/face_fits.py` export,
  verify, install), but none has been published
  ([face fits](fo4_pipeline.md#published-face-fits)).

**Deploy, hotfix and the build plan:**
- `tools/release/fo4_deploy.py`: `refusal` (missing folders, a running or
  failed stamp, the game running), `plan` (copy by size and time, list
  stale files), `listed_only` for a DLC's own file list, and
  `clear_built_hotfixes`. `MOD` and `HOTFIX_MOD` are fixed paths under
  `C:\Modlists\fo3fnv-in-fo4`.
- `tools/release/fo4_hotfix.py`: `build_options` reads the stamp's
  command, `changed_sources` compares with the last build's script stage,
  `compile_changed` compiles, `install_hotfix` ships into
  `F3NV - Hotfix` ([how it works](fo4_hotfix.md#how-it-works),
  [clearing](fo4_hotfix.md#clearing)).
- `fo4_import/pipeline/build_plan.py`: `plan` orders plugins by masters and
  calls `check` on each (`current`, `build`, `after`); `run` builds until
  none needs it, through `rebuild`, which reruns the recorded command;
  `verify` rebuilds a current plugin and compares bytes. MO2 answers are
  asked again through `mod_dirs.ask` and `creation_kit.ask`
  ([build plan](fo4_plugin_layout.md#build-plan),
  [MO2 answers](fo4_mod_builds.md#mo2-answers)).
- `pipeline/build_steps.write_stamp` records the git commit. `_git`
  returns '' when git fails, so a build from a ZIP download carries no
  release identity ([stamp](fo4_pipeline.md#build-stamp)).

**Releases and profiles:**
- `.github/workflows/tag-on-push.yml` tags master and writes notes with
  `tools/release/release_notes.py`, keyed on `version.STEP_KEYS`, the
  inherited Skyrim GUI's steps. `portable-package.yml` calls
  `tools/release/build_portable.py`, which is not in this repo.
- `spike/replacements.py` reads profiles from `PROFILES`
  (`fo4_import/data/profiles/`) through `layers`; that folder does not
  exist, so no profile ships.

## <a id="framework"></a>The framework: one release path

One route, written down once and automated by the app. Four parts:

1. **What a tester downloads:** a tagged release of the repo (code only;
   no Bethesda data). The tag is the release identity, written into a file
   the build reads when git is absent. Optional release assets, like the
   navmesh cache: published face fits.
2. **The one supported install:** Windows, Steam Fallout 4 1.11.240, the
   Creation Kit, and one MO2 instance anywhere on disk holding the required
   mods. Each plugin builds into its own MO2 mod (`F3NV - Fallout New
   Vegas`, `F3NV - <DLC>`), the layout the developer already uses. Vortex
   and a manual install stay "should work" from the output folder, not
   supported.
3. **What the app automates:** the MO2 location comes from the app's
   settings everywhere (the CK step, deploy, hotfix). Convert covers the
   base game and every DLC and pack found, in master order, through the
   build plan: the first run builds everything, later runs only what needs
   it. FaceGen runs after each build. Play launches F4SE through MO2.
4. **How updates ship:** a release that changes only scripts is applied
   with `fo4_hotfix` on the tester's own build (scripts convert locally, so
   nothing Bethesda's ships). A release that changes records runs
   `build_plan --run`. Release notes say which kind each release is.

**Why this covers the rows.** The clean-machine run tests part 2 and
decides what part 3 must handle. Phase 7 is part 3. Profiles and the
Wabbajack modlist are inputs to part 2 (a modlist is the required mods
plus a profile, installed into the same MO2 instance). Mod builds are one
more plugin in the same build plan and the same per-plugin mod folders.
Build-only-what-changed is the engine of part 4.

**Engine and tool mechanisms used:** MO2's `run -e <executable>` (already
used by `creation_kit.run`), Fallout 4's loose files and plugins, and the
existing Python tools. Nothing here needs new runtime code.

### <a id="dll-decisions"></a>DLL decisions

- **None needed.** One candidate was considered: `F3NV.dll` warning in game
  when its release differs from the plugin's. The alternative, chosen: the
  build stamp carries the release, and the app refuses a deploy or hotfix
  across releases. No approval is asked for.

## <a id="phases"></a>Phases

| # | Phase | Size | Delivers | Checked by | Needs |
|---|---|---|---|---|---|
| 1 | Install check (**built**, [below](#install-check)) | S | A read-only command that reports each README requirement on this machine: Fallout 4 version, the CK, F4SE, the MO2 instance and its "Creation Kit" executable, the required mods enabled in the profile (`replacements.presence`), free disk | A test on a fake MO2 instance (one missing per requirement); all ready on the dev machine | The play test |
| 2 | Clean-machine run | M | The user follows the README on a clean Windows account with phase 1's check; every failed or unclear step listed here | The run's notes; the build reaches Doc Mitchell's house in game | 1, the user |
| 3 | MO2 from settings | M | `creation_kit.MO2`, `fo4_deploy.MOD` and `HOTFIX_MOD` come from the app's `mo2_profile` source through one function; the hard-coded path stays only as the fallback | Tests with a fake instance at another path; `build_plan` gives the same verdicts before and after | 2 |
| 4 | Release identity | S | The tag in a file the stamp reads when git is absent; the app shows it; deploy and hotfix refuse a build from another release | Unit tests on the stamp and `refusal` | 2 |
| 5 | App phase 7 | L | DLC and pack stages found from the exports, built in master order through `build_plan`; each plugin into its own MO2 mod; the FaceGen stage (`spike.facegen`); a Play button; Finished notes and README rewritten for the route | The app driven off screen as in phase 5 of the [app](fo4_gui.md#phases): test block plus one pack, FormID ledger identical to the command line; in game, the DLC loads from its own mod | 3, 4 |
| 6 | Updates in the app | M | "Update" runs `build_plan --run`, or `fo4_hotfix` for a scripts-only release; `build_plan --verify` passed on every plugin first | `test_fo4_build_plan.py`, `test_fo4_hotfix.py`; in game, a hotfixed script on a tester's build | 5 |
| 7 | Replacement profiles | S | `vanilla-fo4` in `fo4_import/data/profiles/`; the app's profile picker lists the folder | Loader reads it with 0 warnings; a test-cell build moves 0 FormIDs | 5 |
| 8 | Mod builds steps 2 to 7 | M each | The [order](fo4_mod_builds.md#order): census, add-only fixes, shared-file guard, the master kit, CK steps without MO2, "convert this mod" | `preflight --audit dlc` counts; a mod build against the kit only | 5, 6 |
| 9 | Wabbajack modlist | L | An MO2 instance with the required mods and a profile, compiled for Wabbajack; the app converts into it | A second clean-machine run, from the modlist to Doc Mitchell's house | 2, 5, 7 |

**First to choose in phase 5: build into the MO2 mod, or into a staging
folder and deploy.** The CK step reads the deployed mod
(`anim_info.generate`), so on a clean machine a staging build runs the CK
before the plugin is in MO2. Building straight into the mod folder avoids
that. Deploying keeps `fo4_deploy.refusal`'s guard against a half-written
mod. Phase 2 shows which one fails; the plan leans toward building straight
into the mod folder for testers, with deploy left as the developer's tool.

### <a id="install-check"></a>Phase 1 as built: the install check

```bash
py -3.14 -m tools.validate.fo4_install_check [--settings F] [--mo2 DIR] [--profile NAME] [--work DIR]
```

`tools/validate/fo4_install_check.py` reads the app's settings
(`fo4_import/app/settings.py`: game folders, the first `mo2_profile` mod
source, the work folder) and falls back to `creation_kit.MO2`. It writes
nothing and prints one line per check, `OK` or the problem with what to
do; exit code 1 when any check needs attention.

| Check | Read from | Problem words |
|---|---|---|
| Fallout 4, its version, the CK, F4SE | `game_dirs` via settings; `Fallout4.exe`'s file version (`core.setup_check.exe_version`); `CreationKit.exe`, `f4se_loader.exe`, `f4se_1_11_240.dll` in the game folder | MISSING, WRONG VERSION |
| New Vegas and its DLC | `FalloutNV.esm` and the nine DLC/pack masters in its `Data` | MISSING (DLC are listed, never a failure) |
| MO2 | `ModOrganizer.ini`, the profile's `modlist.txt`, `gamePath`, the executables titled "Creation Kit" and the one running `f4se_loader.exe` (its title is the Play entry) | MISSING, WRONG |
| The README mods | each mod's file in an enabled folder (`mod_sources.data_dirs`): `version-1-11-240-0.bin`, `PRKF.dll`, `mcm.dll`, `BlackLandscapeFixRD.dll` under `F4SE/Plugins`; else in a mod the profile leaves off | MISSING, NOT ENABLED |
| RAM, free disk | installed RAM (32 GB); free space on the work folder's drive (100 GB) | LOW |
| After a conversion | every plugin with a `<plugin>.build.json` beside it where the game sees it: alone in its own MO2 mod, in no other, not in the game's Data or overwrite, stamp `finished`, ticked in `plugins.txt`; `F3NV.dll` in some `F4SE/Plugins` | WRONG PLACE, UNFINISHED, NOT ENABLED, MISSING; NOT YET (passes) before any conversion |

Not checked: the required mods are enabled through
`replacements.presence` only for the replacement table's plugins (the
[required mods](fo4_gui.md#required-mods) dialog); this check covers the
README's fixed list. XDI (`XDI.dll`) where the game sees it is a CONFLICT: F3NV.dll's menu replaces it.

Checked by `tests/test_fo4_install_check.py` (15 tests: a fake game, New
Vegas and MO2 instance all OK, then each requirement removed, disabled or
misplaced). On the dev machine (2026-11-08) all 28 checks are OK: 1.11.240,
9 of 9 DLC, every README mod enabled, ten converted plugins each in its own
`F3NV - <name>` mod, `F3NV.dll` in the base game's mod. The MO2 F4SE
executable is titled `F4SE` there, which answers the open question below
for this instance; phase 5 should read it the same way.

## <a id="load-time"></a>Load time: meshes in the Main BA2

Built 2026-11-09, not played. The last launch took about 3.5 minutes to
the main menu with 63,500 loose files in the mod folder. The build now
packs `Meshes` and `Materials` (46,886 files, 2.29 GB) into
`<plugin> - Main.ba2` with the sounds, uncompressed, as vanilla's DLC do;
each DLC build packs its own. The deploy ships the archive instead of the
loose files and deletes the mod folder's loose copies on every run, since
a loose file wins over the archive. About 16,650 loose files remain:
16,179 scripts (kept loose for hotfixes), 363 textures, 47 music files,
the video and a few dozen others. Details and measurements:
[main archive](fo4_pipeline.md#main-archive).

How to measure it: launch through MO2's F4SE entry with a stopwatch from
the click to the main menu's first frame, twice (the second launch has a
warm disk cache), and compare with the 3.5 minutes. Before launching, check
the mod folder has no `Meshes` or `Materials` folder left and that
`FalloutNV - Main.ba2` is about 8.4 GB. Then load a save at Goodsprings:
a red error marker or a missing mesh means the archive does not hold that
file.

## <a id="play-test"></a>What the play test should tell us first

- **`F3NV.dll` from the build's own copy.** The Pip-Boy's SKILLS tab shows
  and condition works with the DLL the build placed in
  `F4SE/Plugins/`. If not, phase 5 needs a DLL step.
- **The intro movie** plays from the build's `Video` folder. If not, the
  movie step stays on phase 5's list.
- **Faces after a build without a fresh `spike.facegen` run.** If they are
  wrong or dark, FaceGen is required in the route, not optional.
- **The DLC from their own mod folders:** Dead Money's vending machines and
  a GRA gun. A failure here changes phase 5's per-plugin layout.
- **A hotfix during the test,** if one ships: the fixed script wins over
  the build's. If not, part 4's scripts-only route is off until fixed.
- **A save from before an update** loads after a records rebuild. The
  answer sets what release notes promise.

## <a id="open"></a>Open questions

- Is `tes_runtime/dist/F3NV.dll` in the repo, so a ZIP download has it?
  `.gitignore` does not exclude it; not checked against git.
- Does the CK step need CK Platform Extended? `creation_kit.CK_CRASHES`
  reads its crash folder; not checked whether the CK runs without it.
- The MO2 executable name for Play (an F4SE entry) is not fixed anywhere
  yet; MO2 names it at install. Phase 1 reads it from the instance (the
  executable whose binary is `f4se_loader.exe`); `F4SE` on the dev machine.
- Should face fits ship as a release asset, as the navmesh cache does
  ([cache](../../CLAUDE.md#shared-navmesh-cache))? The cold `people` stage
  took 4,239 to 4,365 s ([measured](fo4_plugin_layout.md#which-builds)).
- Can a Wabbajack modlist leave the converted files to the app, since they
  can never be in it? Not checked against Wabbajack's own docs.
- Release notes: adapt `release_notes.py` to FO4's kinds (scripts only,
  records) or write the kind by hand per tag?
- macOS and Linux stay out of the tester route until the build's Windows
  tools run there ([cross-platform](fo4_gui.md#cross-platform)).
