# The FO4 conversion app: setup choices, mod sources, two-column replacements

Phases 1–6 built 2026-10-24, not played ([where things stand](#where-it-stands));
phase 7 is later. The design text stays as the design record; overall status is
in the [roadmap](ROADMAP.md#fo4-app). Each phase lands as its own branch, useful
on its own.

Goal: a user converts Fallout 3 or New Vegas to Fallout 4 without typing a
command, decides where every file lives, swaps any temporary FO4 stand-in for a
record from a mod they have installed, and gets a folder they can install with
whatever mod manager they use.

## Contents

- [Where things stand](#where-it-stands)
- [Principles](#principles)
- [App shape](#app-shape)
- [Cross-platform rules](#cross-platform)
- [Choices: where things live](#choices)
- [Mod sources](#mod-sources)
- [Replacement data](#replacement-data)
- [The Replacements screen](#replacements-screen)
- [The 3D preview](#preview)
- [The Finished screen](#finished)
- [Phases](#phases)
- [Testing](#testing)

## <a id="where-it-stands"></a>Where things stand (2026-10-24)

Phases 1 to 6 are built ([phases](#phases)); each section's "As built" says
what exists. Not played in game yet.

- **Before the app** the builds were command lines run by hand
  (`script_convert.pipeline --target fallout4`, `fo4_import.helpers_plugin`,
  `fo4_import.pipeline.run`, `tools.validate.fo4_check`;
  [pipeline](fo4_pipeline.md)). They still work, and the app runs the same
  commands.
- **Replacement data:** `fo4_import/data/replacements.json` holds the
  defaults: 39 entries (weapons 15, armor 16, consumables 7, misc 1) and
  `_rules` for 14 creature skeleton folders, 4 bodies, 4 armor rules and 3
  melee types, which were code dicts before phase 2. No profile ships. The
  user's own file is written by the Replacements screen
  (`replacements/<source>.json` beside the app by default; gitignored).
- **MO2 and Fallout 4 found, not hard-coded:** `pipeline/creation_kit.MO2`
  reads `F3NV_MO2`, which the app sets from its MO2 mod source
  (`app/mo2_setup.py`); a developer checkout falls back to a fixed folder.
  `install.FALLOUT4_DIR` is detected (`core/game_dirs.py`) with Steam's
  folder as the fallback.
- **The inherited GUI** (`gui.py`, `core/gui/`, tkinter) is untouched and
  still converts to Skyrim only.
- **The whole map** builds from the command line
  ([whole map](fo4_pipeline.md#whole-map)): 1,036 placed creatures of 121
  kinds still have no FO4 base, the Replacements screen's red rows.
- **Checking:** the Check stage runs `tools/validate/fo4_ref_check.py`
  (unresolved references, headless, in seconds). FO4Edit's full check is a
  separate, optional stage: it needs a click on its developer-message dialog
  when that shows (at most every 14 days, or when a new message ships).

## <a id="principles"></a>Principles

- **The user chooses where things live.** Every location has a detected
  default and can be changed: game installs, mod folders, output, the
  replacement file, the export and caches.
- **No mod manager is required.** The app reads mods from plain folders and
  writes a folder of loose files plus plugins. MO2, Vortex or a manual install
  all work from that folder. MO2 extras (reading a profile, setting one up)
  are optional and come later.
- **Windows, macOS and Linux.** Only cross-platform libraries. Windows-only
  tools are run through Wine or Proton where possible; otherwise their stage is
  marked unavailable ([cross-platform](#cross-platform)).
- **One app for FO3 and FNV.** It is separate from the inherited Skyrim GUI.
- **The replacement rules stay as they are** ([direction](fo4_replacements.md#direction)):
  - a mod is never required to run, and a missing one falls back to the
    default;
  - the app never ships a mod's files;
  - the app is a front end over the table and holds no conversion logic of
    its own.

## <a id="app-shape"></a>App shape

- **Files:** a new launcher `fo4_app.py` and a package `fo4_import/app/`. The
  inherited `gui.py` and `core/gui/` stay untouched, because they conflict on
  every merge from `standalone`.
- **Toolkit: PySide6 (Qt 6).** It uses the LGPL and ships unmodified pip
  wheels for Windows, macOS and Linux, which is fine for an MIT tool. Why it
  replaces tkinter here:
  - the Replacements screen needs an embedded 3D view, and tkinter has no
    supported OpenGL widget (pyopengltk was last released in 2022);
  - Qt has `QOpenGLWidget`, handles HiDPI, and has filterable list models for
    the two columns.

  If Qt is ruled out, the fallback is tkinter with moderngl drawing
  off-screen into a `PhotoImage`.
- **Reuse, don't copy:** the settings load/save pattern and `run_process` from
  `core/gui/config.py` (no Tk import), `classify` from `core/gui/runner.py`,
  and the update check from `version.py`.
- **Run logs:** each Convert run writes every line it shows to one
  `logs/run-<stamp>-<plugin>.log` in the [work folder](#work-folder) (`runner.open_log`, through
  `core/run_log.py`, which keeps the last 20). The stages get
  `TESCONV_RUN_LOG`, so `convert.py` doesn't write a second log. Before 0.3 a
  stage's output lived only in the window, so a user's warnings were lost once
  it closed.
- **Imports without a display:** Qt is imported inside functions, checked by a
  startup test like `tests/test_gui_startup.py`.
- **Source game: FNV or FO3.** FO3's stages show "not available yet" until its
  build path exists. Each source has its own settings block, export, output
  folder and replacement file.
- **Screens:** Setup, Convert, Replacements, Finished. On first run a wizard
  steps through Setup's choices once.

### As built (phase 5, 2026-10-24): the alpha app

- **Start it:** `py -3.14 fo4_app.py`. The first run, with no settings file
  yet, opens the wizard (`fo4_import/app/wizard.py`). It has five pages: the
  game; the game folders, prefilled from detection and checked for
  `Data/<master>`; mods (none, an MO2 instance with its profile, or any folder
  of mods); where mods are; and where files go, including whether settings
  stay beside the app.
- **Window** (`window.py`):
  - **Setup** (`setup_view.py`) edits every setting. Each source game keeps
    its own output, replacement file and profile. Save settings writes the
    file beside the app or in the OS config folder and removes the other
    copy, so a stale one is never read.
  - **Convert** (`convert_view.py`).
  - **Replacements** (phase 6, [as built](#replacements-screen)).
  - **Finished** (`finished_view.py`) shows each stage's result and time, the
    warning lines (replacement fallbacks, errors), the output folder with
    Open folder, and install notes for MO2, Vortex and manual installs.
- **Stages** (`stages.py`, no Qt) build the existing command lines from the
  settings:
  - Export: `convert.py --export-only -f <master> --data-dir <game>/Data`.
  - Helper plugin and Build: into the output folder, which is the build's
    Data. The build gets `--mod-sources <settings file>`, the profile, and
    the replacement file when it exists.
  - Scripts: the build converts them itself (`--scripts`, see
    `fo4_import/pipeline/build_steps.py`) into the chosen scripts folder
    (Setup, per game), else `<work>/scripts/<master>`. The separate Scripts
    stage was dropped on 2026-10-31.
  - Check: the fast reference check (`tools.validate.fo4_ref_check`, about
    1 s on the region plugin, 5 s on the whole map), with the output folder
    and mod sources as plugin folders. It runs on any OS.
  - FO4Edit's full check (`fo4_check`), optional and unticked by default
    (`stages.OPTIONAL`): it is Windows-only and waits for a click on
    FO4Edit's developer-message dialog when that shows.

  A stage that cannot run is shown disabled with the reason: a game folder
  without `Data`, a missing master, or FO4Edit off Windows
  ([Windows-only tools](#windows-tools)).
- **Runner** (`runner.py`, no Qt) runs the stages in order from the repo
  folder on a QThread, streams each line to the log, and stops at the first
  failure or on Stop. With zip output, the folder is zipped beside itself
  afterwards.
- **Not yet chosen by the user:** the export folder (convert.py fixes it to
  the repo's `export/`) and a Wine prefix.
- **Since phase 7** ([extra stages](#extra-stages)): the F4SE plugin and the
  Creation Kit's FaceGen are stages. The source movies were never missing:
  every build writes them (`build_finish`, `base.bink.write_movies`;
  `spike.bink` is only the play test). Not built: installing published face
  fits.
- **Checked 2026-10-24:**
  - The app was driven off screen: Start on Convert ran Scripts, Helper
    plugin, Build and Check for the test block into a scratch output folder,
    with the MO2 Spike profile as mod source.
  - Scripts: 19,400 converted with 0 errors, in 22 s. Helper plugin: 1 s.
    Build: 168 s. Check: 138 s, with 0 errors in 13,707 records.
  - The plugin matches the command-line build: the FormID ledger is
    identical.
  - The Setup, Convert and Finished screens and the wizard pages were checked
    in screenshots. The settings file is written where chosen.
  - The export stage was not run from the app.

### <a id="convert-screen"></a>Convert screen

Top to bottom, it reads as the steps a player takes (`convert_view.py`,
`target_box.py`, `stages.next_step`/`row_state`/`game_problem`):

1. **Game.** One radio per entry in `stages.GAMES` (New Vegas; Fallout 3,
   marked experimental). A game whose folder holds no master is disabled,
   and its tooltip says why. Picking one also switches the Setup screen's
   **Convert from**, so each game keeps its own output and profile.
2. **What to convert.** A list holding the game, the DLC found in its Data
   folder, and the mod folders the user added. Each row says `built <date>`,
   `not built yet`, or `convert <master> first`. A built row names the
   release from its build stamp (`release.made_with`): `with f3nv-0.9`, or
   `a development build` (after a tag, or with only a commit recorded) for
   one built from a checkout; a stamp with neither shows the date alone. **Add a mod folder...** sits
   beside the list. An add-on's output folder and light-plugin choice show
   only when an add-on is picked.
3. **The next step in one bold sentence.** It names the missing Fallout 4 or
   game folder first, then a missing master, then "Click Convert to build"
   (how long it takes is on the estimate line), and last "is built: Convert
   rebuilds what changed, or open Finished".
4. **One large Convert button** named for the target (`Convert
   FalloutNV.esm`), then Stop, the status line ("Already done, so skipped:
   ..."), the estimate and the log.

The stages and the build's scope sit under **Show advanced options**,
folded away by default. Whole is the default scope and is listed first. A
stage that cannot run shows its reason in the gray column, where a stage
that can run shows what an earlier run left. The Classic Look stage is New
Vegas only (`GAMES[...]['classic']`).

- **Stages:** each is an existing command line tool, ticked on or off: Export,
  Helper plugin, Build (which converts the scripts), Check (`fo4_ref_check`), and FO4Edit's full
  check (`fo4_check`, unticked by default). FaceGen, LOD and BA2
  packing are added when they exist.
- **Scope:** test cell, worlds, region or whole. Also a worker count and a
  replacement profile.
- **Running:** stages run on a worker thread. The log streams into the window,
  and Build's counts and timings are shown.
- <a id="activity"></a>**Whether a quiet run is alive** (added 2026-11-24). A
  moving bar only shows the window is alive, not the build: the 0.4 run sat on
  a dead compiler for a long time while the window looked busy. So every 2 s
  a gray line under the estimate says how long the log has been quiet and what
  the build's processes are doing ("No new output for 2 min 10 s; still
  working: 6.4 cores busy across 9 processes"). Each stage's process goes into
  a Windows job of its own (`core.process_job.CpuWatch`), and the job's
  accounting counts CPU time for everything the stage starts, including
  workers that already exited. The job allows breakaway, like the pool job,
  because MO2 starts the Creation Kit that way. So the CK's own CPU time is
  not counted, and while it works the line says the build is waiting on
  another program.
- <a id="queue"></a>**The queue** (`queue_box.py`, added 2026-11-26). **Add
  <plugin> to queue**, beside Convert, saves the chosen target with its
  ticked stages and scope (`Queued`); the queue box under the buttons lists
  the waiting targets with Run queue, Remove and Clear. A target queued while
  a build runs converts after it; with nothing running, Run queue starts the
  queue. Each target runs on a copy of the settings with its game and target
  chosen (`settings_for`), so the target list can change meanwhile. Which
  stages run is decided when its turn comes (`stages.plan`), so a DLC queued
  behind its game, whose build is disabled until the game is built, builds
  once the game is done; a target with no stage left to run is skipped with a
  note in the log. A failure or Stop ends the run and keeps the rest queued.
  The log keeps every target's lines under a `===== Converting <plugin> =====`
  header, and Finished gets every target's stages, labels led by the plugin
  when there were several, and the last target's output folder.
- <a id="earlier-runs"></a>**What earlier runs left** (`stages.found`, added
  2026-10-24), from the app or the command line, shown beside each stage:
  - Export: the export with its date (`_HEADER.txt`).
  - Helper plugin and Build: the plugin in the output folder with its date.
  - The export counts as done and starts
    unticked. The status line says so. A stage is ticked or unticked only
    when its done state changes, so a stage the user ticks again stays
    ticked.
  - The mesh, texture and work caches (`output/fo4_cache/`) are shared with
    the command line whatever the output folder, so nothing needs showing.
  - Checked on the user's files: the export from 2026-10-14 and 17,577
    scripts in `temp/fo4_scripts/FalloutNV.esm` were found in 0.04 s.
    `FalloutHelpers.esl` and `FalloutNV.esp` were found with the MO2 mod
    folder as output.

### <a id="addons"></a>DLC and mods (built 2026-11-10, not run from the app yet)

The Convert screen's **What to convert** box picks the game, a DLC or pack
found in its Data folder (a plugin whose header lists the game's master), or
a mod folder the user adds (**Add a mod folder...**; a mod with several
plugins asks which). The choice is saved per source game (`addons`:
plugin, mod folder, output folder; `target`) by `fo4_import/app/addons.py`
and `target_box.py`.

- **Output.** An add-on builds into its own folder, editable in the box; by
  default the folder beside the game's output that holds its build stamp
  (`<plugin>.build.json`), so the command-line builds' folders such as
  `F3NV - Honest Hearts` are found whatever their name, else
  `settings.mod_folder_name` there: `F3NV FNV - <plugin stem>` for New
  Vegas, `F3NV FO3 - <plugin stem>` for Fallout 3, so the two games' mods
  tell apart in MO2. An earlier build's folder keeps its old name, so an
  installed mod never moves.
  Its masters' built plugins are
  read from their outputs (`--plugin-dirs`), so a master not built yet blocks
  the Build stage with its name.
- **Stages.** A mod adds **Import the mod folder** (`convert.py
  --import-mod`). Export runs `--export-only --extract-only` for the game
  and DLC, so their archives reach the export too (the game's Export stage
  did not extract before this); a mod's import already extracted its files.
  The helper plugin and the Classic Look are the game's only. Scripts go
  beside the game's scripts folder, under the plugin's name.
- **Scope** (`addons.build_scope`), from the add-on's own export when its
  Build starts (the runner takes a command or a function giving it):
  - the worldspaces it adds that a door or script reaches
    (`run.reached_worlds`) and that have grid cells, whole (Dead Money's 7,
    not its test maps);
  - the master worldspaces whose grid cells it changes: the one with the
    most cells first, as a one-cell region on one of those cells (or the
    user's region corners), the others whole. The build adds every other
    grid cell the add-on holds itself
    ([edited cells](fo4_plugin_layout.md#edited-cells)), so the add-on's
    cells are built and no others. A worldspace's persistent cell (record flag
    0x400) is not a grid cell: Honest Hearts and Better Brotherhood override
    WastelandNV's;
  - with neither, its own first interior as the start cell, new ones first
    (Gun Runners' Arsenal's vendor chest cell); a pack gets neither.
  The test block is off for an add-on. Checked on the exports: Dead Money,
  Honest Hearts, Gun Runners' Arsenal and the four packs come out as the
  command-line builds of 2026-11-09 were run.

  <a id="addon-cells"></a>**Only the changed cells (2026-11-14).** The
  region was once the box around every changed cell. Landscape Disposition
  Fix changes 503 WastelandNV cells across the map, so its box (-22 -30 21
  29) was 2,640 cells: nearly the whole game, made again and dropped as
  unchanged (233,137 references the same as the master's). Built both ways
  from the same code, the WRLD and QUST groups are byte-identical. The box
  build also made a crucified-furniture pose race, its keyword and two biped
  slot keywords on the mod's own ids, all for master content. The cell build
  instead keeps one unplaced workbench side copy: station sides follow the
  placements a build sees, so either scope makes one. Build time: 181.9 s
  against 126.8 s.

  <a id="addon-refs"></a>**Only the add-on's own references (2026-11-14).**
  Its cells still held every master reference and actor in them (93,571
  REFRs and 2,074 actors for Landscape Disposition Fix), each made with its
  base, then dropped as the same as the master's. `master_overrides` keeps a
  master record the add-on does not hold only when it names one of the
  add-on's new records, and that only happens for scope artifacts such as a
  station's side copy. So a build with masters now places only the
  references its plugin holds (`CellBuilder.placing`, `own_refs`: its own
  and its overrides). Every other reference in its cells keeps the FO4 FormID
  its master's build gave it (`master_ref`: the master's id when the master
  holds it, an actor's from its ledger), without its base being made, so
  links, enable parents, doors, navmeshes and quests still name it. The
  cell's key lights are still ranked among all its lights.
  An owner (XOWN on a reference, cell or encounter zone) that is a master's
  NPC used to resolve only because placing the master's actor made its
  base; with no master actors placed, YUP's 138 owned references lost their
  owner. `owners_from_masters` now maps each NPC named as an owner to the
  NPC its master's ledger made (`CellBuilder.owner_ids`).
  Checked against a build placing everything (NewVegasBounties, one cell):
  29 of 33 groups are byte-identical. The 18 packages differ only in their
  ForceGreet numbers ([greet once](fo4_pipeline.md#greet-once)): the old
  build also numbered the master's ForceGreets, so the add-on's own started
  at 55. The greeting line's 54 fewer conditions are those master
  ForceGreets, which the master's own greeting line already tests. One
  unused biped-slot keyword is gone. One interior lost its owner, fixed
  above.

### <a id="light"></a>Light plugins: the per-mod opt-in (built 2026-11-12, not run from the app yet)

Under the output folder, **Plugin type** has a checkbox, *Build as a light plugin*, for a DLC or mod (the game is
always full). It is saved in the add-on's entry (`light`) by `fo4_import/app/light_plugins.py`; the Build stage
passes `--light` ([the policy](research/fo4_light_plugins.md#policy)).

- **Before the first build** the box is free. **After it** the plugin's type is locked: ticking or unticking it
  for a built add-on asks first ("moves N FormIDs: saves that use this mod break, and mods built on it must be
  rebuilt"). Only a Yes stores the confirmed type (`light_confirmed`) and makes the build pass
  `--switch-plugin-type`; the build itself also refuses a switch without that flag.
- **Under the box** go the add-on's notes (`light_plugins.warnings`): once built, its own records against 4,095
  (fits; fits with little room above 3,071; does not fit); from its export, the
  [light-only problems](research/fo4_light_plugins.md#problems): new cells in an `.esm`, new worldspaces
  (untested), plain `.esp` masters.
- **Light FO4 and Creation Club plugins** need nothing new: the app counts no plugin slots, tests no `.esl`
  extension, and names their records by plugin and in-file object id (`catalog.py`, `replacements.py`).
- **Not built yet:** the light trial that counts a mod's own records before its first build (the count shows only
  after a build); a slot count against 254 when the load-order report is built.

## <a id="cross-platform"></a>Cross-platform rules

- **Paths:** `pathlib` everywhere and no backslash literals. Settings and
  caches go in each OS's user folders (`QStandardPaths`) unless the user picks
  a folder.
- **Case-insensitive lookup:** game paths are case-insensitive, and the file
  systems on Linux (and some macOS) are not. The file resolver therefore
  builds a lowercase index of every mod folder.
- **Finding games:**
  - Steam's `libraryfolders.vdf` on all three OSes, including the Proton
    prefixes on Linux;
  - GOG and the registry on Windows only;
  - every path can be set by hand.

  `install.FALLOUT4_DIR` becomes a Windows fallback only.
- **Libraries:** PySide6, moderngl (OpenGL 3.3 core; macOS supports up to 4.1
  core), Pillow, numpy and lz4 all ship wheels for all three OSes.
- <a id="windows-tools"></a>**Windows-only tools.** No stage but FO4Edit's
  check is marked unavailable off Windows (`stages.WINDOWS_TOOLS`), and the
  Creation Kit tools the build once needed are now fallbacks, each skipped
  when it is not installed. Off Windows, Build still stops at the pinned
  zlib and compiles no script (below; [blockers](../audits/fo4_redo_audit_2026-11-23.md#off-windows)).
  Untested off Windows.

  | Tool | Used by | Without it |
  |---|---|---|
  | Caprica (`external/caprica/Caprica.exe`, ours) | Build: every converted script | run directly, not under Wine (`base/caprica.py`): off Windows no script compiles |
  | FO4 Papyrus compiler (Creation Kit) | Build: the scripts Caprica fails on | those scripts stay uncompiled (`papyrus.compile_folder` returns nothing) |
  | Elric (Creation Kit) | no longer used (2026-11-24): our physics writer finishes every mesh; one it does not cover has no collision ([seam](fo4_hknp_writer.md#seam)) | — |
  | Creation Kit FaceGen | no longer used (2026-11-24): an NPC our own FaceGen fails on has no FaceGen ([own stage](fo4_facegen_plan.md#own-stage)) | — |
  | `xwma_enc.exe` (ours, `native/src/xwma`, shipped) | Build: every voice and sound file (`voice.convert` through `audio_converter.encode_xwm`); no Linux build yet, and `convert_file_to_xwm` would hand a native one Wine paths | no voice or sound files |
  | LipGenerator (Creation Kit) | Build: a voice line with no FNV `.lip`, when installed | the lip comes from the recording's loudness (`voice.loudness_lip`) |
  | `LODGenx64.exe` (bundled) | Build: object LOD, under Wine off Windows | no object LOD |
  | `texconv.exe` (Elric folder) | no longer used: our own encoder writes face and terrain LOD textures ([encoder](fo4_facegen_plan.md#own-dds-encoder)) | — |
  | FO4Edit 4.1.5f | FO4Edit's check | stage unavailable |

- **Pinned zlib:** `native/dist` holds `f3_zlib.dll` only. Elsewhere
  `base/pinned_zlib.py` raises without `libf3_zlib.so` / `.dylib`, so no
  plugin is written until those are built (`tools/generators/gen_native_c.py`).
- **Native speedups:** the `.pyd` modules are built for Windows today; the
  NIF geometry reader falls back to pure Python without its module.

## <a id="choices"></a>Choices: where things live

All choices live in one settings file, `fo4_app.json`. The first-run wizard
sets them and Setup edits them later.

| Setting | Options |
|---|---|
| Game installs | FNV, FO3, FO4: detected, can be changed |
| Mod sources | An ordered list of folders, any mix of kinds ([below](#mod-sources)). Empty means vanilla only |
| Output | A folder of loose files plus plugins (default), or a zip. Setting up an MO2 mod or profile comes later and is optional |
| Replacement file | In the work folder (`replacements/<source>.json`), inside the output folder, or any path |
| Work folder: export, caches, run logs, scripts | `F3NV Work` beside the app folder (default) or a folder the user picks; about 100 GB for New Vegas ([below](#work-folder)) |
| Replacement profile | `vanilla-fo4`, `fnv-look`, or a modlist's ([profiles](#replacement-data)) |
| External tools | Wine or Proton prefix (macOS, Linux); NifSkope path (optional) |
| How much of the PC a build uses | Low, Balanced (default) or Full ([resources](fo4_build_resources.md#profiles)) |

`run.py` reads these settings instead of its constants, and the CK and
FaceGen steps find MO2 through `F3NV_MO2` ([where things stand](#where-it-stands)).
Nothing reads the Wine setting yet: bundled exes run under the `wine` on
`PATH` (`core.subprocess_flags.windows_cmd`).

### <a id="work-folder"></a>The work folder: an app folder of code only

The app folder holds only what a release ships, so a new release can be
unzipped beside it (or over it) and the old one deleted. Everything a
conversion makes lives in the work folder (`settings.work_dir`): `export/`,
`output/` (with `output/fo4_cache`, the face bases and the mesh, work and
script caches), `logs/`, `replacements/` and `scripts/`.

- **One switch.** `asset_convert/paths.py` reads `F3NV_DATA`
  (`DATA_ENV`); `EXPORT`, `OUTPUT`, `LOGS` and `FO4_CACHE` sit under it,
  and every export, output and cache path in `convert.py`,
  `papyrus_compile.py`, `source_paths.py`, `output_layout.py` and
  `fo4_import` reads them. Unset (a developer checkout, the command line),
  it is the checkout itself, as before.
- **The app sets it** for itself at start and on Save (`workspace.use`)
  and for every stage (`mo2_setup.environment`), and finds the export
  through `settings.export_root`. In the app process, a value read at import
  is the checkout's, so in-app readers ask `paths.data_root()` when called
  (`eta.benchmark`).
- **Default: `F3NV Work` beside the app folder** (`settings.DEFAULT_WORK`),
  not the user's config folder: a New Vegas work folder is about 100 GB
  and belongs on the drive the user unzipped to, and releases unzipped
  side by side share it.
- **Older releases' data moves on first start.** Up to f3nv-0.3 the export
  and caches lived in the app folder. `workspace.adopt` renames
  `export`, `output` and `replacements` into the work folder when that has
  none yet, from this app folder (a release unzipped over the old one),
  else from the newest older release's app folder beside it (its `VERSION`
  tag; a release unzipped next to the old one). A rename is instant on one
  drive; on another drive it says to move them by hand. A checkout (no
  `VERSION` tag) and links are left alone. A saved replacement place `app`
  reads as `work`.
- **Builds an older release made convert in full**
  ([plugin layout](fo4_plugin_layout.md#moved-app-folder)); a build from a
  moved or renamed app folder of the same release still rebuilds.

## <a id="mod-sources"></a>Mod sources

A new, game-agnostic module, `core/mod_sources.py`:

- **`ModSource(folder, kind)`** has three kinds:
  - `folder_of_mods`: each subfolder is one mod (a generic mod folder,
    Vortex's staging folder, MO2's `mods`);
  - `flat`: one folder laid out like `Data` (FO4's own `Data`, or a merged
    folder);
  - `mo2_profile`: reads a profile's `modlist.txt` and keeps only the enabled
    mods, in priority order. It is read-only and optional.
- **`data_dirs(sources)`** returns the folders laid out like `Data`, in order;
  later sources win, and loose files win over archives. It feeds three things:
  - `--plugin-dirs` (`run.py` gains `--mod-sources <settings file>`);
  - the [record catalog](#replacements-screen);
  - the [preview](#preview)'s file lookup.
- **`plugins(sources)`** returns every plugin with the folder that supplies it.
- **How each kind reads** (built in phase 1):
  - `folder_of_mods` orders its subfolders by name, because Vortex staging and
    plain folders record no priority. When two mods conflict, list the one
    that should win as a later source.
  - `mo2_profile` takes the folder holding `ModOrganizer.ini`. It lists
    `gamePath\Data` first (lowest), then the profile's `+` mods from the bottom
    of `modlist.txt` up (MO2 writes the highest priority first), then
    `overwrite`. Left out: disabled `-` mods, `…_separator` entries, and `*`
    entries (DLC and Creation Club, already in the game's Data).
  - MO2's formats, checked against `src/settings.cpp` and a 2.5.2 instance:
    - path keys sit in `[Settings]` (`base_directory`, `mod_directory`,
      `profiles_directory`, `overwrite_directory`), each defaulting to
      `%BASE_DIR%/<name>`;
    - `base_directory` defaults to the folder holding the ini;
    - `selected_profile` and `gamePath` are `@ByteArray(...)` values in
      `[General]`, with backslashes doubled.
- **The settings file** is `fo4_app.json` beside the app when one is there
  (portable, as MO2 does it); otherwise it lives in `%APPDATA%\F3NV`,
  `~/Library/Application Support/F3NV` or `$XDG_CONFIG_HOME/f3nv`.
- **Game detection** (`core/game_dirs.py`) tries the registry first
  (`source_paths.find_game_path`, now with Fallout 4, New Vegas and Fallout 3
  added). Then it tries Steam's `libraryfolders.vdf` and each game's
  `appmanifest_<id>.acf`: 377160, 22380, and for Fallout 3, 22370 (GOTY)
  before 22300. `fo4_import/base/install.py` detects the same way and keeps
  Steam's default Windows folder as the fallback.
- **Later, opt-in MO2 extras:**
  - fill the source list from `ModOrganizer.ini` and its profiles;
  - write the output as an MO2 mod and enable it in a profile, refusing while
    `ModOrganizer.exe` runs, because MO2 rewrites its lists on exit.

  MO2's file formats are checked against MO2's own source before this is
  built.

## <a id="replacement-data"></a>Replacement data

- **One table** (`fo4_import/data/replacements.json`, built in phase 2).
  Entries sit under a category (weapon, armor, consumable, ammo, misc,
  creature) and are keyed by the source game's EditorID. The entry shape is
  the same as [step 1](fo4_replacements.md#how):
  `{"use": "Plugin|EditorID", "as": "item"|"stats"|"fnv", "mods": [...]}`.
- **`_rules`** say what forms the table leaves out get. They hold what used to
  be code dicts, so the app can show and override them:
  - `creature`: one entry per skeleton folder (was `creatures.STAND_INS`
    and `TEMPLATES`). A `creature` entry keyed by a CREA EditorID wins over
    its folder's rule;
  - <a id="ability-rules"></a>`ability`: one entry per FNV ability, for a creature carrying it
    among its own spells (`replacements.creature_entry`, shared by the build
    and this screen): it wins over the folder's rule, a table entry still
    wins over it. The default: `GlowingOneGlowSpell` on FO4's
    `encFeralGhoulGlowing01`, so FNV's glowing ones (the ferals, the
    glowing troopers, the Vault 34 guards, Jason Bright: 14 records owning
    their look, their template actors through them) look and act as FO4's;
  - `body`: `human_male`, `human_female`, `ghoul_male`, `ghoul_female`,
    `child_male`, `child_female` ([children](fo4_pipeline.md#child-bodies)) (was
    `npcs.BODIES`). These must be Fallout4.esm NPCs. Face calibration
    (`face/calibration.py`) is still measured on the default humans;
  - `armor`: a list of `{covers: [FNV biped slot names], use, as}`, where the
    first rule that matches wins (was `equipment.ARMOR_DEFAULTS`);
  - `melee`: `hand_to_hand`, `one_hand`, `two_hand` (was
    `equipment.MELEE_DEFAULTS`).
- **Creature modes:**
  - `stats` writes a copy of the target under FNV's name and stats, the old
    stand-ins;
  - `fnv` puts FNV's body on the target's rig. The skin and addon are read
    from the target's WNAM and the skin's MODL instead of FormIDs;
  - `item` is new: the target is used as it is, so references and lists name
    it, which is how a DLC's or mod's creature plugs in.
- **FormIDs:** they are hashed from the source's ids, so the move changes
  none. This is measured by building the same scope before and after
  ([verified](ROADMAP.md#fo4-app)).
- **Layers,** each laid over the one before, entry by entry:
  1. the defaults;
  2. a profile (`fo4_import/data/profiles/<name>.json`);
  3. the user's file, at the location they chose.

  The loader reports where each entry came from.
- **Profile header:** `_profile: {name, requires: [{plugin, nexus_id, version}]}`.
  If a plugin is missing, only that plugin's entries fall back to the layer
  below, with a warning.
- **A missing plugin,** in any layer, drops only that entry back to the layer
  below, with a warning.
- **Profiles:** `--profile` takes a name in `fo4_import/data/profiles/` or a
  JSON path. No profile ships yet.
- **Which modes a target allows:**
  - Fallout4.esm targets allow every mode.
  - A DLC's or another mod's record allows `item` only. A copy would carry
    that plugin's FormIDs, which would all need renumbering
    ([copy mode, a later step](fo4_replacements.md#later-steps-designed)).
    DLC plugins become masters before any mod's, in the game's order.
  - Creature `fnv` works only where a rig pair exists
    (`fo4_import/nif/creature.py` `PAIRS`).
- **DLC plugins** (DLCRobot, DLCCoast, DLCNukaWorld, …) become valid targets
  and masters. `replacements.extra_masters()` already appends mods' plugins.

## <a id="replacements-screen"></a>The Replacements screen

```
+--------------------------------------------------------------------------+
| [Weapons v] [search........] [ ] only unreplaced / skipped                |
+-------------------------------------+------------------------------------+
| ORIGINAL / CURRENT                  | REPLACEMENT  [Fallout 4 + DLC   v] |
|  9mm Pistol    214  10mm  (default) |  10mm Pistol   Fallout4.esm         |
|  Varmint Rifle 160  Hunting (profile)|  ...                               |
|  Gecko         256  none  (skipped) |  Mode: (o) item ( ) stats ( ) fnv   |
|                                     |                                    |
|  [  3D preview  ]  (o) source       |  [  3D preview  ]                   |
|                    ( ) stand-in     |                                    |
|  Damage 18  Ammo 9mm  Weight 2      |  Damage 18  Ammo 10mm  Weight 4     |
|                                     |       [Apply]  [Revert to default]  |
+-------------------------------------+------------------------------------+
```

- **Top bar:** a category filter (Weapons, Armor, Consumables, Ammo, Creatures,
  Bodies…), a search box, and a toggle to show only unreplaced or skipped
  forms.
- **Left column, original and current:**
  - the source game's forms in the category, each with its placement count,
    its current stand-in, and where that comes from (default, profile, user);
  - forms with no stand-in show in red: on the whole map, 1,036 placed
    creatures of 121 kinds ([whole map](fo4_pipeline.md#whole-map); 374
    in the earlier [audit](fo4_tool_audit.md));
  - a 3D preview that switches between the source model and the current
    stand-in, plus key stats.
- **Right column, replacement:**
  - a dropdown at the top picks Fallout 4 + DLC, one installed mod, or all
    installed mods (from the [mod sources](#mod-sources));
  - a list of that plugin's records in the category (EditorID, name, key
    stats);
  - a mode picker that offers only the modes the target allows;
  - a 3D preview and a stats comparison with the left;
  - Apply and Revert to default.
- **Record catalog** (`fo4_import/app/catalog.py`):
  - **What it holds,** per plugin and per type: EditorID, name, model and key
    stats.
    - Fallout4.esm's names are localized and are read through
      `fo4_import/base/strings.py`.
    - For ARMO the model comes through ARMA.
  - **How it reads:** `tes5_import/base/tes5_reader.py` `walk`, keeping the
    first of each subrecord. Weapons and armor repeat FULL inside their object
    templates ("Default", "Epic"), so the last FULL is the wrong name.
    Localized plugins (header flag 0x80) take names from their strings files,
    found loose or archived through the [file resolver](#preview). A record
    overriding a master's lists that master as its `owner`.
  - **No cache** (built in phase 3, measured 2026-10-24 on Fallout4.esm, its
    DLCs and 61 MO2 mods' plugins). Scanning Fallout4.esm takes 0.3 s, and
    all 67 plugins (16,871 entries) take 0.5 s. With the resolver's index
    (553,510 archived and 23,751 loose names), the whole load takes 1.4 s,
    too little to justify a cache between runs.
- **Saving:** Save writes the user's file at the chosen location. Reconvert
  reruns Build with `--replacements`. FormIDs are hashed, so only the swapped
  records change.

### As built (phase 6, 2026-10-24)

- **Modules:** `replacements_view.py` (the screen), `replacement_columns.py`
  (the two columns and their previews), `standins.py` (the left column's data,
  no Qt), `user_table.py` (the user's file, no Qt).
- **Left column:** the export's forms of the category, the most placed first.
  Placement counts come from REFR and ACRE (307,710 and 2,999 for FNV), read
  in 1.3 s. Each row shows what stands in now and why. `standins.current`
  asks the converter's own rules, so it can't drift from a build:
  - a table entry in any layer, shown with its layer;
  - the rule: `equipment.default_entry` for armor and melee weapons, or the
    creature's `skeleton_folder` rule;
  - the converter's choice: a gun is matched to the closest FO4 gun at build
    time, and other items are copied from FNV's record;
  - for a creature with neither, "none: skipped", in red.

  "Only forms the converter decides or skips" filters to the last two.
- **Right column:**
  - The plugin picker offers Fallout 4 + DLC, all installed plugins, or one
    plugin. The converted plugin and helper plugin are left out.
  - The mode picker offers only what the loader accepts:
    - Fallout4.esm records allow any mode;
    - other plugins' records and leveled lists allow `item` only;
    - creature `fnv` needs a rig pair for the form's skeleton folder.
- **Apply and Revert:** they write the user's replacement file at the chosen
  place and reload the table. The next Build uses the file through
  `--replacements`.
- **Match by name** (`fo4_import/app/matching.py`, added 2026-10-24) suggests
  a record per form across every category, in 0.2 s on the user's 67
  plugins. Nothing is written until the user accepts.
  - **What matches:** a record of the same category with the same name
    (lowercase, letters and digits only), or with the form's EditorID behind
    at most a port prefix. A port prefix is made of digits, underscores and
    tokens like DC, DLC04, FNV, NV, CW, so `00DCWeapKnife` and
    `00DCDLC04WeapDynamite` count but `00DCRumNukaCola` does not match
    NukaCola.
  - **Overrides are left out:** the original record is matched instead, so
    accepting adds no needless master (UFO4P's beer).
  - **The pick, in order:**
    1. name and EditorID together, then EditorID alone, then name alone
       (many items share a name);
    2. a mod's record over the base game's;
    3. the shortest prefix (vanilla `LvlFeralGhoul` over Far Harbor's
       `DLC03_LvlFeralGhoul`);
    4. the plugin that wins in the user's mod order.
  - **The Suggested column** names the record and its plugin, for example
    "Knife (ProjectMojave.esm, 1 of 3)". "1 of N" means others matched; the
    tooltip lists them.
  - **The right column follows the suggestion.** Picking a form with one
    lists its candidates, the suggestion picked and previewed beside the
    original, so it is checked without searching. A form without one lists
    the chosen plugin's records. "Browse all records", or choosing a plugin,
    lists the plugin's records for every form.
  - **Keys:** Up and Down move through the left list. Enter (on either table)
    applies the right column's pick and moves to the next form. Delete
    reverts the picked form.
  - **Accept suggestion** takes the picked form's suggestion. **Accept all
    shown** takes every suggestion in the left list after asking. Both use
    the record as it is (`item`). A suggestion equal to the current
    stand-in is never made.
  - **Measured:**
    - 1,035 suggestions from 3,920 forms, 639 of them picked from several
      matches. By category: weapons 90, armor 141, consumables 66, ammo 15,
      misc 137, creatures 586.
    - Accepting every creature suggestion wrote 586 entries, and the loader
      read them with 0 warnings.
- **Show** filters the left list:
  - All;
  - Mine (the user's file);
  - Still on a rough FO4 stand-in (the converter's defaults, rules or own
    pick);
  - Suggested, not yet accepted;
  - From the profile;
  - Skipped.
- **Previews:**
  - The left column switches between "FNV's mesh (as converted)" and the
    current stand-in. FNV's mesh is read from the output folder, so it exists
    only for forms a build put on FNV's own mesh. On the user's F3NV output
    that covers 179 of 389 armor pieces, 169 of 189 consumables, 740 of 1,711
    misc items, 34 creatures and 4 weapons.
  - A stand-in or picked record shows its model. Specifically:
    - **Guns** are assembled (`preview/assembly.py`) from the default (else
      first) combination's object mods. Each part's `C-X` connect point is
      placed on a placed part's `P-X`, with that point's rotation and
      position (`nif/gun.py` `connect_frames`, `connect_children`). Of
      Fallout4.esm's 184 damaging weapons, 83 have parts.
    - **Armor** shows its first addon's worn model.
    - **NPCs** show their skin's body.
    - **Links are followed across plugins** (`catalog.preview_models`, added
      2026-10-24 after "no model to show" turned up on records that have
      one). Each record keeps its links as catalog-wide keys ('owner
      plugin|low 24 bits'). Object mods, armor addons and races are listed
      under hidden categories so they can be found. The links followed:
      - an armor goes to its first addon with a model, else its world model;
      - an NPC goes to its template when it takes traits from it (ACBS
        template flag 0x1), else its object mods, else its skin, else its
        race's skin, else its template. A robot is assembled from its object
        mods, the same as a gun; a skin draws every addon made for the NPC's
        race (torso, hands, feet);
      - a leveled list shows its first entry that has a model;
      - a weapon uses its parts, else its own model (melee weapons with mod
        slots, such as Far Harbor's meat hook).

      Skinned parts (a robot's) keep their bind-pose place and are not moved
      by connect points.
    - **When there is still nothing, the preview says why:** no skin for the
      NPC or its race, a leveled list with no entries or none with a model,
      an addon or template not in any installed plugin, a mesh that isn't
      installed, or one that isn't a Fallout 4 NIF.
    - **Measured on the user's 67 plugins** (16,871 records; resolving them
      all takes under 0.1 s):
      - Records with nothing to show fell from about 4,300 to about 370.
        Nearly all of those have no model at all: 248 turret-mounted and
        creature-attack weapons, survival effects, mod-slot misc items, voice
        templates, and empty leveled lists.
      - About 15 point at meshes that aren't installed.
      - NPCs that preview went from about 2,900 to 6,360, and leveled lists
        from 0 to 738.
    - **Not handled:** Mechanist robots that mix parts from different robots
      (a Robobrain arm on an Assaultron) draw those parts in the wrong place,
      since the arm is skinned to another skeleton. Human NPCs show their body
      without the FaceGen head or outfit.
- **Checked 2026-10-24** against the user's MO2 mods (67 plugins):
  - The screen loads in 3.4 s.
  - A gecko spawn form shows "none: skipped".
  - Searching "gecko" finds Project Mojave's and Mojave Geckos' records.
    Applying `Geckos.esl|00DCLvlGecko` wrote the user file, and the loader
    reads it as a user entry.
  - In the real Qt window, both columns rendered: the 9mm pistol's stand-in
    (FO4's 10mm, assembled) and the laser gun.
  - **A mod's creature through a build** (the creature `item` mode from
    phase 2, first time in a build):
    - Setup: a user file pointing the `creatures\nvgecko` rule at
      `Geckos.esl|00DCLvlGecko`. The test block has no geckos, so the build
      covered the region -14 11 -13 13, which has 25 direct gecko
      placements.
    - Result: `Geckos.esl` became the fourth master, and the build reports
      "creatures (target as is): 2".
    - FNV's gecko forms take their traits from a template, so they became FO4
      template actors. Six now use the mod's leveled gecko as their template.
      The 38 placed spawns reach those six through the converted leveled
      lists.
    - FO4Edit: 0 errors in 6,216 records.
    - Appending the master moved the plugin's own FormIDs' top byte (03 to
      04), as adding a master in xEdit does.
    - Not played.

### <a id="required-mods"></a>Required mods (added 2026-10-25)

Every plugin other than Fallout4.esm that the replacement table names becomes
a master of the built plugin. If that plugin isn't installed, or one of its
own masters isn't, its entries silently fall back to the layer below. The
user's table named 38 plugins, none enabled in their MO2 `Play` profile, and
17 entries needed masters that weren't installed (`Munitions - An Ammo
Expansion.esl`, the Gauss rifle prototype Creation Club plugin). Nothing on
the screen said so.

- **The button:** "Required mods" in the top bar. It reads "Required mods (N
  to fix)" in red when any plugin can't be used. It is recounted on load and
  after every Apply, Revert or Accept.
- **The list** (`fo4_import/app/required_mods.py`, a dialog). One row per
  plugin, problems first (in red), then the most entries:
  - **Plugin.**
  - **Entries:** how many entries name the plugin, counted once per entry key
    across the default, profile and user layers, rules included. A plugin
    named only by a profile's `_profile.requires` shows 0.
  - **Status:**
    - Ready;
    - Missing masters;
    - Not enabled (the file is only in MO2 mod folders the profile doesn't
      enable);
    - Not installed (nowhere at all).

    Every status but Ready ends "its entries fall back".
  - **Where:** the mod folder that supplies the plugin. If no enabled source
    has it, each MO2 mod holding it, as `MO2 mod "X" (not enabled in profile
    Play)`.
  - **Missing masters:** the plugin's own masters that aren't loadable. Each
    one names the disabled MO2 mod that holds it, if any. For a plugin that
    is only in a disabled mod, the masters are read from that file, so the
    list shows whether enabling the mod alone is enough.

  Below the table, the loader's own warnings (`Table.warnings`, "X is not
  installed; the layer below applies") are shown as they are.
- **No second rule set:** "installed" is `replacements.presence`, the same
  check the loader uses. It is true when the plugin and every master it names
  (recursively) are found in the game's Data folder or the mod sources'
  `data_dirs`. Masters come from `replacements.file_masters`, and the layers
  from `replacements.layers`. The only new lookup is the disabled-mod index:
  each `mo2_profile` source's `mods` folder, minus the folders its profile
  enables (`mo2_folders`), scanned one level deep for plugins.
- **Tested:** `tests/test_fo4_replacements_screen.py` builds a fake MO2
  instance with four plugins, one per status, and checks the dialog off
  screen.
- **Checked 2026-10-25** (read only) against the user's saved app settings
  and MO2 `Play` profile. Of 41 named plugins (defaults included), 35 are
  ready. Five have missing masters, and all five also sit in mods `Play`
  doesn't enable:
  - `NVUMP.esp` (8 entries) needs `ccbgsfo4018-gaussrifleprototype.esl`;
  - four weapon plugins need `Munitions - An Ammo Expansion.esl`.

  `CW10mmPistol.esl` is only not enabled. In all, 16 entries fall back. The
  dialog itself has not been opened in the real window.

## <a id="preview"></a>The 3D preview

### What exists (researched 2026-10-24)

No viewer can be embedded under a permissive licence, and none needs to be:
the repo already reads every format involved. Only a renderer is new.

| Candidate | Licence | FO4 support | Route |
|---|---|---|---|
| NifSkope, fo76utils fork (2.0.dev11, 2025-12) | BSD-3 | Good: BA2, BGSM/BGEM, FO4 shaders | No embedding API; an external "Open in NifSkope" button |
| NifSkope, niftools 2.0.dev7 | BSD-3 | Partial | External only |
| MO2 NIF Preview (Exit-9B) | GPL-3 | FO4 shaders; no BGSM, no skinning | Runs only inside MO2; worth recommending to users |
| nifly / PyNifly | GPL-3 | Full | Would add a GPL DLL and duplicate our readers |
| Outfit Studio (BodySlide) | GPL-3 | Full | Not embeddable |
| three.js NIF loader | None found | — | — |
| pyvista/VTK, vispy | BSD | — | Workable, but heavy (VTK ~100 MB) and awkward for custom shading |
| **Our readers + moderngl in `QOpenGLWidget`** | MIT / LGPL (Qt) | What we write | **Chosen** |

### As built (phase 4, 2026-10-24)

- **Run it:**
  `py -3.14 -m fo4_import.app.preview <mesh> [--settings fo4_app.json] [--png out.png]`.
  The mesh is a file on disk or a Data path, looked up in `--dirs`, then the
  settings' mod sources, then Fallout 4's Data.
- **Modules:** `scene.py` (NIF to parts), `materials.py` (BGSM/BGEM or texture
  set to maps), `render.py` (moderngl, plus `render_image` off screen),
  `viewer.py` (`PreviewWidget`, a QOpenGLWidget; drag to orbit, wheel to zoom).
- **Greyscale-to-palette materials** (the 10mm and other FO4 guns) take their
  color from the palette at (diffuse green, the BGSM's `grayscale_scale`), as
  NifSkope's FO4 shader does. Without it the 10mm renders light grey.
- **FO4 NIFs only.** That covers vanilla, mods, and FNV meshes as converted in
  the output folder. FNV's raw source meshes would need the converter's
  private pyffi helpers (`convert_static._geometry`). Making those public
  changes the converter's source, which the mesh cache's code tag hashes, so
  every cached mesh would rebuild. For the left column the converted mesh is
  the better preview anyway. Raw sources can come later through
  `mesh_cache.cached_convert`.
- **Guns:** a FO4 weapon record's model is a receiver "dummy" with no
  geometry, because guns are assembled from their mods' parts. The
  Replacements screen assembles them from the default OMODs
  (`preview/assembly.py`, above).
- **Checked:** on the RTX 5070 Ti, the vanilla 10mm pistol, Dogmeat, a
  converted pre-war outfit and the converted coyote on Dogmeat's rig rendered
  off screen. The Qt window painted the outfit on an OpenGL 3.3 core context.
  macOS and Linux are untested.
- **Dependencies:** `PySide6-Essentials` (it holds QtWidgets, QtGui and
  QtOpenGLWidgets, without WebEngine and the other add-ons) and `moderngl`,
  both pinned in `requirements.txt`.

### How it works: `fo4_import/app/preview/`

- **Meshes:**
  - FO4: `fo4_import/nif/file.py` `read` and `blocks.read_tri_shape`.
    BSSubIndexTriShape is read through `read_tri_shape(Reader(raw))`, as
    `nif/creature.py` does. Arrays come from `nif/headgear.py`
    `shape_arrays`, and node transforms are composed as in `nif/outfit.py`.
  - FO3/FNV: pyffi through `nif/convert_static.py` `_geometry`.
- **Materials:** `nif/bgsm.py`, `nif/bgem.py`, and `blocks.read_texture_set`
  for meshes without a material file.
- **Files** (`fo4_import/app/files.py`, built in phase 3): `Files(dirs)` takes
  Data-like folders, winning first (`mod_sources.data_dirs()`).
  - It checks loose files first, the winning folder's kept, then every
    folder's BA2s: the winning folder's first and, within a folder, a later
    name before an earlier one, as `ba2.Archives` orders them.
  - Names are matched ignoring case, and both indexes are built on first use.
  - `mesh_path()` adds `meshes\` to a record's model.
  - FO3/FNV meshes come from the export folder, passed as one more loose
    folder; BSAs are not read.
- **Textures:** Pillow decodes BC1–BC7 with DX10 headers. `ba2.py` returns the
  top mip only, so large textures are scaled down.
- **Drawing:** moderngl in a `QOpenGLWidget`, OpenGL 3.3 core, which runs on
  macOS too.
  - One vertex buffer per shape.
  - Diffuse, normal (BC5, with Z rebuilt) and specular maps, lit with
    Blinn-Phong.
  - An orbit camera; skinned meshes show in bind pose.
  - Estimated at 400–800 lines. The look is an approximation of FO4's, not
    in-game parity ([drift](fo4_drift.md)).
- **Later:**
  - guns and robots are now assembled from their OMOD parts and an NPC's skin
    addons are drawn (above); still later: human NPCs' FaceGen heads and
    outfits, and robots mixing parts from different skeletons;
  - an "Open in NifSkope" button when the user has set a NifSkope path.

## <a id="finished"></a>The Finished screen

"Conversion finished" shows:
- what was built;
- warnings, such as unavailable stages or missing replacement mods;
- the output folder, with an **Open folder** button
  (`QDesktopServices.openUrl`, which works on every OS);
- short install notes for MO2, Vortex and a manual install.

Its buttons (phase 7, built 2026-11-10, not clicked against the real MO2
instance or game yet):

- <a id="install-status"></a>**Install status** (`status_view.py`): the
  lines of `tools/validate/fo4_install_check.py` for the app's settings
  (`machine_from`), problems in red: the game and its version, F4SE, the
  Creation Kit, MO2 and its F4SE and Creation Kit executables, each required
  mod where the game sees it (or in an MO2 mod the profile leaves off, or
  missing), New Vegas and its DLC, RAM and disk, and after a conversion each
  converted plugin in its own enabled MO2 mod with `F3NV.dll`. The
  replacement table's own mods stay on the Replacements screen's
  [Required mods](#required-mods) list.
- <a id="mo2-setup"></a>**Set up in MO2** (`mo2_setup.py`). With the
  target's output folder a mod folder of the MO2 mod source's instance, it
  enables that mod in the profile's `modlist.txt` (an absent one added at the
  top, under MO2's header) and its plugins in `plugins.txt` (ticked, or
  appended) and `loadorder.txt` (appended): the game's plugin, helper plugin
  and Classic Look when built, or an add-on's plugin, so a DLC set up after
  the game loads after it. It asks first, backs each changed list up as
  `<list>.f3nv-backup`, and refuses while Mod Organizer runs, since MO2
  rewrites its lists when it closes. An output elsewhere is still copied in
  by hand.
- **Play:** MO2's executable running `f4se_loader.exe`, for the profile
  (`ModOrganizer.exe -p <profile> run -e <title>`); without an MO2 source,
  the game folder's `f4se_loader.exe`.

### <a id="extra-stages"></a>Faces and the F4SE plugin (phase 7)

- **Install the F4SE plugin** (`app/runtime_dll.py`): copies the committed
  `tes_runtime/dist/F3NV.dll` into the game output's `F4SE/Plugins`, so the
  output is a complete MO2 mod. The game target only; the DLC and mods use
  the game's.
- **Faces** (`spike.facegen` on the built plugin, any target; 2026-11-15):
  our own FaceGen heads, the FNV face fits refined and baked in, as the
  chain makes them (about 20 minutes for the base game). Ticked by default
  and open on any OS, with or without MO2. The stages run with `F3NV_MO2`
  set to the MO2 mod source's instance, which `pipeline.creation_kit` reads
  for the profile's mod order in place of the developer's
  `C:\Modlists\fo3fnv-in-fo4`. An NPC our export fails on is listed and has
  no FaceGen; the stage still finishes (the Creation Kit fallback for those
  went on 2026-11-24). Before 2026-11-15 it was the CK's FaceGen for every
  NPC, needing MO2 and Windows, unticked as it took hours.

### <a id="rebuild"></a>Rebuild what changed (2026-11-15)

The `update` stage runs `fo4_import.pipeline.build_plan --run`, the
chain's own way to rebuild ([build plan](fo4_plugin_layout.md#build-plan)):
a plugin whose only changes are code its meshes, archives or scripts parts
ran is replayed (`part_replay`), the rest rebuilt with the command its
stamp records, masters first; a plugin's faces run again after its
rebuild. It gets `stages.rebuilt()`: the target's built plugin, the built
plugins it reads as masters, and every built plugin reading it, directly
or through another. Built plugins are the game's, each add-on's, and any
other with a finished build record in a folder beside the game's output
(the chain's and the command line's `F3NV - <mod>` folders, which the app
does not list as add-ons).

- **Ticks.** Once the target has a finished build record, Build (now "whole
  build") counts as done and starts unticked, and Rebuild what changed is
  the default; before that it is disabled ("build it once first"). Faces
  count as done once a faces run finished: the rebuild runs them again
  when the plugin changes. Ticking Build as well runs the whole build
  first, then the rebuild (the mods built on it, and stale faces).
- **On the user's setup** (read only, 2026-11-15): with the game as target,
  the set is FalloutNV.esm and the 30 mod plugins built on it, Fallout3.esm
  left out, as the chain's `others` step builds them.
- **Messages.** With nothing to rebuild it prints "nothing to rebuild: every
  plugin is up to date" and finishes; a failed plugin build prints its
  name and exit code. The Finished screen's headline names the stage that
  ended the run and its exit code (`finished_view.headline`).

### <a id="rebuild-folders"></a>A rebuild reads this work folder

A plugin's build record keeps the paths its build was given. A build made
somewhere else records that place's folders: a developer checkout keeps
`export/<plugin>` and `temp/fo4_scripts/<plugin>` relative to itself, and
another release keeps its own work folder. f3nv-0.8 replayed those paths
from its own app folder, so an Anchorage reconvert (built 2026-11-23 from
the checkout) read an export that was not there and stopped with a
`StopIteration` looking for the world `Wasteland` (2026-11-25).

- The app's Rebuild what changed passes `--export-root` and
  `--scripts-root` (its work folder's `export` and scripts folders), and
  `build_plan.rooted` moves each recorded `--export` and `--scripts` there,
  keeping the folder's name (an imported mod's through the registry). The
  faces stage's export moves the same way. When anything moved, the parts
  replay is skipped: its manifest names the old export, so the plugin is
  built whole.
- An add-on's build and rebuild need each master both built and exported
  in this work folder (`stages.missing_master`): the build reads the
  masters' records. A fresh work folder with only the DLC exported says
  "convert its master Fallout3.esm first" instead of failing.

### <a id="child-output"></a>Child processes under pythonw

The app runs under `pythonw.exe`, and its stages under the same
interpreter. A process started from it with no standard handles given gets
none: its prints and traceback go nowhere, and it exits with code 1 on its
first `sys.stdout.flush()` (reproduced 2026-11-25). That is how an
Anchorage reconvert ended in 0.7: "Rebuild what changed" started a
Fallout3.esm rebuild, the child died at once, and the log showed only the
exit code. Every child the stages start themselves goes through
`core.subprocess_flags.call_inherited`, which hands the parent's own
stdout and stderr over explicitly, so the child writes into the same log.

## <a id="phases"></a>Phases

| # | Phase | Main files |
|---|---|---|
| 1 | Settings and choices, game detection, mod sources (MO2 profile read-only); `run.py --mod-sources` | `core/mod_sources.py`, `fo4_import/app/settings.py`, `run.py`, `base/install.py` |
| 2 | Replacement data: categories, profile layer and origin, creature, body and defaults to JSON, DLC targets, `--profile` | `spike/replacements.py`, `spike/creatures.py`, `spike/npcs.py`, `spike/equipment.py`, `data/profiles/` |
| 3 | Record catalog and the case-insensitive file resolver | `fo4_import/app/catalog.py`, `fo4_import/app/files.py` |
| 4 | Preview renderer as a standalone viewer window | `fo4_import/app/preview/` |
| 5 | **Alpha app:** first-run wizard, Setup, Convert, Finished (loose-folder output) | `fo4_app.py`, `fo4_import/app/` |
| 6 | Replacements screen (two columns, previews) | `fo4_import/app/replacements_view.py` |
| 7 | MO2 mod and profile setup, a Play button, install status (each required mod installed, wrong version or missing), the F4SE plugin and faces as stages (built 2026-11-10); later: Wabbajack | `fo4_import/app/mo2_setup.py`, `status_view.py`, `runtime_dll.py` |

Phase 5 needs phases 1 and 3; phase 6 needs 2 to 5. Phases 1 to 4 do not
depend on each other.

## <a id="testing"></a>Testing

- **`mod_sources`:**
  - fixture folders: a folder of mods, a flat folder, a fake MO2 profile, and
    mixed-case paths;
  - read-only runs against `C:/Modlists/fo3fnv-in-fo4`.
- **Replacement layers:** tests for layering, origin and the missing-mod
  fallback. A test-cell FormID diff before and after phase 2 should show 0
  moved.
- **App startup:** a test that the app imports without a display.
- **Preview:** a vanilla FO4 gun, a converted FNV outfit and Dogmeat render.
- **End to end on Windows:**
  1. Swap one weapon and one creature in the app.
  2. Reconvert.
  3. `fo4_check` comes back clean.
  4. The user plays it.
- **macOS and Linux:** a CI smoke test on GitHub's hosted runners covering
  import, settings, the catalog and an off-screen render. Full builds there
  are untested.
