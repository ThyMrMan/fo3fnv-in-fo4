# The FO4 conversion app: setup choices, mod sources, two-column replacements

Design only; status is in the [roadmap](ROADMAP.md#fo4-app). Each phase lands as
its own branch, useful on its own.

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
- **Still hard-coded:** `fo4_import/spike/facegen.py` `MO2` (the CK FaceGen
  step). `install.FALLOUT4_DIR` is now detected (`core/game_dirs.py`) with
  Steam's folder as the fallback.
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
  - **Replacements** is a placeholder until phase 6.
  - **Finished** (`finished_view.py`) shows each stage's result and time, the
    warning lines (replacement fallbacks, errors), the output folder with
    Open folder, and install notes for MO2, Vortex and manual installs.
- **Stages** (`stages.py`, no Qt) build the existing command lines from the
  settings:
  - Export: `convert.py --export-only -f <master> --data-dir <game>/Data`.
  - Scripts: into the chosen scripts folder (Setup, per game), else
    `<work>/scripts/<master>`. Pointing it at an earlier run's folder, such
    as the command line's `temp/fo4_scripts/FalloutNV.esm`, reuses those
    scripts.
  - Helper plugin and Build: into the output folder, which is the build's
    Data. The build gets `--mod-sources <settings file>`, the profile, and
    the replacement file when it exists.
  - Check: the fast reference check (`tools.validate.fo4_ref_check`, about
    1 s on the region plugin, 5 s on the whole map), with the output folder
    and mod sources as plugin folders. It runs on any OS.
  - FO4Edit's full check (`fo4_check`), optional and unticked by default
    (`stages.OPTIONAL`): it is Windows-only and waits for a click on
    FO4Edit's developer-message dialog when that shows.

  A stage that cannot run is shown disabled with the reason: FO3 has no build
  yet, a game folder without `Data`, or a Windows-only tool off Windows. The
  FO4 build calls its tools directly, and `core.subprocess_flags.windows_cmd`
  (Wine) is the route to wire them later.
- **Runner** (`runner.py`, no Qt) runs the stages in order from the repo
  folder on a QThread, streams each line to the log, and stops at the first
  failure or on Stop. With zip output, the folder is zipped beside itself
  afterwards.
- **Not yet chosen by the user:** the export folder (convert.py fixes it to
  the repo's `export/`) and a Wine prefix.
- **Not built by the app yet:** the F3NV F4SE plugin
  (`tes_runtime/fo4_condition`), Bink movies (`spike.bink`), CK FaceGen, and
  installing published face fits. The Finished screen says to install
  `F3NV.dll` separately.
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

### Convert screen

- **Stages:** each is an existing command line tool, ticked on or off: Export,
  Scripts, Helper plugin, Build, Check (`fo4_ref_check`), and FO4Edit's full
  check (`fo4_check`, unticked by default). FaceGen, LOD and BA2
  packing are added when they exist.
- **Scope:** test cell, worlds, region or whole. Also a worker count and a
  replacement profile.
- **Running:** stages run on a worker thread. The log streams into the window,
  and Build's counts and timings are shown.
- <a id="earlier-runs"></a>**What earlier runs left** (`stages.found`, added
  2026-10-24), from the app or the command line, shown beside each stage:
  - Export: the export with its date (`_HEADER.txt`).
  - Scripts: how many `.psc` files are in the scripts folder and when they
    were converted, flagged when older than the export.
  - Helper plugin and Build: the plugin in the output folder with its date.
  - The export, and scripts newer than it, count as done and start
    unticked. The status line says so. A stage is ticked or unticked only
    when its done state changes, so a stage the user ticks again stays
    ticked.
  - The mesh, texture and work caches (`output/fo4_cache/`) are shared with
    the command line whatever the output folder, so nothing needs showing.
  - Checked on the user's files: the export from 2026-10-14 and 17,577
    scripts in `temp/fo4_scripts/FalloutNV.esm` were found in 0.04 s.
    `FalloutHelpers.esl` and `FalloutNV.esp` were found with the MO2 mod
    folder as output.

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
- **Windows-only tools.** On macOS and Linux each runs through a Wine or
  Proton prefix the user points at. Without one, its stage is marked
  unavailable and the rest still runs.

  | Tool | Used by | Without it (to confirm) |
  |---|---|---|
  | FO4 Papyrus compiler (Creation Kit) | Scripts | no compiled scripts |
  | LipGen (Creation Kit) | Build, voice | lines play with no lip movement |
  | Creation Kit FaceGen | FaceGen | faces fall back to the face-fit pass only |
  | Elric (Creation Kit) | Build, collision | no FO4 collision for converted meshes |
  | `texconv.exe` (Elric folder) | face textures | no baked face textures |
  | FO4Edit 4.1.5f | Check | no FO4Edit check |

- **Native speedups:** the `.pyd` modules are built for Windows today. They
  need builds for the other OSes, or the code must fall back to pure Python.

## <a id="choices"></a>Choices: where things live

All choices live in one settings file, `fo4_app.json`. The first-run wizard
sets them and Setup edits them later.

| Setting | Options |
|---|---|
| Game installs | FNV, FO3, FO4: detected, can be changed |
| Mod sources | An ordered list of folders, any mix of kinds ([below](#mod-sources)). Empty means vanilla only |
| Output | A folder of loose files plus plugins (default), or a zip. Setting up an MO2 mod or profile comes later and is optional |
| Replacement file | Beside the app (`replacements/<source>.json`), inside the output folder, or any path |
| Export and caches | The user folder (default) or a folder the user picks; they can take tens of GB |
| Replacement profile | `vanilla-fo4`, `fnv-look`, or a modlist's ([profiles](#replacement-data)) |
| External tools | Wine or Proton prefix (macOS, Linux); NifSkope path (optional) |

`run.py` and `spike/facegen.py` read these settings instead of their
constants.

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
  - `body`: `human_male`, `human_female`, `ghoul_male`, `ghoul_female` (was
    `npcs.BODIES`). These must be Fallout4.esm NPCs. Face calibration
    (`spike/sculpt_calibration.py`) is still measured on the default humans;
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
  Replacements screen needs to assemble them from the default OMODs.
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
  - creatures and NPCs built from several parts, and weapons with their OMOD
    parts, which are just more shapes;
  - an "Open in NifSkope" button when the user has set a NifSkope path.

## <a id="finished"></a>The Finished screen

"Conversion finished" shows:
- what was built;
- warnings, such as unavailable stages or missing replacement mods;
- the output folder, with an **Open folder** button
  (`QDesktopServices.openUrl`, which works on every OS);
- short install notes for MO2, Vortex and a manual install.

A Play button and MO2 profile setup come later.

## <a id="phases"></a>Phases

| # | Phase | Main files |
|---|---|---|
| 1 | Settings and choices, game detection, mod sources (MO2 profile read-only); `run.py --mod-sources` | `core/mod_sources.py`, `fo4_import/app/settings.py`, `run.py`, `base/install.py` |
| 2 | Replacement data: categories, profile layer and origin, creature, body and defaults to JSON, DLC targets, `--profile` | `spike/replacements.py`, `spike/creatures.py`, `spike/npcs.py`, `spike/equipment.py`, `data/profiles/` |
| 3 | Record catalog and the case-insensitive file resolver | `fo4_import/app/catalog.py`, `fo4_import/app/files.py` |
| 4 | Preview renderer as a standalone viewer window | `fo4_import/app/preview/` |
| 5 | **Alpha app:** first-run wizard, Setup, Convert, Finished (loose-folder output) | `fo4_app.py`, `fo4_import/app/` |
| 6 | Replacements screen (two columns, previews) | `fo4_import/app/replacements_view.py` |
| 7 | Later, opt-in: MO2 mod and profile setup, a Play button, modlist status (each required mod installed, wrong version or missing), Wabbajack | `core/mod_sources.py`, `fo4_import/app/` |

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
