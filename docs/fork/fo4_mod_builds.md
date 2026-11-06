# Plan: converting one mod against a game that is already built (2026-11-04)

Status: step 1 ([Part 1](#mo2-answers)) built 2026-11-04; steps 2–7 not
built ([order](#order)).

**Goal.** A user ticks an FNV mod, converts it, and the result slots into the
load order beside the already converted game, the way an FNV mod slots onto
FalloutNV.esm. Nothing else is rebuilt. Ticking a converted mod off works
like turning off any FO4 plugin. Nothing about this needs MO2, at build time
or in game.

Related plans: [Part D](fo4_plugin_layout.md#incremental) (rebuild only
the records whose inputs changed), [Part E](fo4_plugin_layout.md#which-builds)
(which plugins need a build), [Part B](fo4_plugin_layout.md#mods)
(replacement patches), and [the app](fo4_gui.md).

## Contents

- [Where things stand](#now)
- [Part 1: record MO2 answers, not MO2 files](#mo2-answers)
- [Part 2: overrides that do not stack](#stacking)
- [Part 3: the master kit](#master-kit)
- [Part 4: shared files stay with the game](#shared-files)
- [Part 5: Creation Kit steps without MO2](#ck-without-mo2)
- [Part 6: mods that need other mods](#mod-masters)
- [Order](#order)
- [Open questions](#open)

## <a id="now"></a>Where things stand

The design is mostly there already: a DLC build never rebuilds the game. It
reads the finished game build and records the questions it asked
([inputs record](fo4_plugin_layout.md#build-plan)). Dead Money's inputs
record (2026-11-04):

- the built `FalloutNV.esm`, judged only by the 43,419 game records it
  read (SHA-1 of each body) and the 44,428 FormIDs it asked about;
- the game's ledger (`FalloutNV.formids.tsv`, 6,905 lookups);
- the game's texture manifest (4,963 textures);
- 142 generated game scripts it compiled against
  (`temp/fo4_scripts/FalloutNV.esm/*.psc`);
- FNV's export of FalloutNV.esm, through the layered export index.

A game rebuild that answers those questions the same way leaves the DLC
current. Two things still rebuild every plugin:

1. **MO2's files, recorded whole** (fixed by [Part 1](#mo2-answers)). Every
   plugin's record listed `ModOrganizer.ini` and
   `profiles/<profile>/modlist.txt`, read by `core/mod_sources.py` for the
   app's mod sources, and the app settings file. MO2 rewrites the ini whenever
   it opens or closes, and ticking any mod rewrites `modlist.txt`. On
   2026-11-04, opening MO2 mid-build restarted the game build (27 min) and
   then every DLC.
2. **Converter code changes.** A change to code every build runs (dialogue,
   say) rebuilds every plugin. That is a developer's cost only, since users
   run one release. Part D is what shrinks it.

## <a id="mo2-answers"></a>Part 1: record MO2 answers, not MO2 files (built 2026-11-04)

Two readers put MO2's files in every plugin's record:
- **`core/mod_sources.py`**, which turns the app's mod sources (`--mod-sources`,
  the app settings `fo4_app.json`: here the MO2 `Play` profile) into the
  folders where replacement plugins are looked up. This reads
  `ModOrganizer.ini` and `modlist.txt` on every build. The 2026-11-04 records
  show no build read a file or listed a folder under MO2's `mods`: every
  lookup resolved in the game's Data folder. The settings file was recorded
  whole too, so changing any app setting also rebuilt every plugin.
- **`pipeline/creation_kit.py`**, for the Creation Kit's output folder and
  which enabled mod holds a file it wrote (`holding`, called by
  `rig/anim_info.py`).

What the record keeps now:
- `build_inputs.asked(kind, arg, answer, files)` logs a question and its
  answer under `asked` in `<plugin>.inputs.json`. `leave_out` drops the files
  and folders read to answer it. Both are per process, merged like the rest.
- `pipeline/mod_dirs.py`:
  - `plugin_dirs(--plugin-dirs, settings)` builds the search folders. It
    leaves out the settings file and each source's own files
    (`mod_sources.source_files`: an MO2 ini and mod list, or a folder of
    mods' listing). The folders carry the spec that made them.
  - `find(plugin, dirs)` is the lookup `replacements` uses (installed check
    and record reads). It logs `plugin found` with the plugin, the spec and
    the file found, leaving out the folders it searched.
- `creation_kit.holding` logs `mo2 holding <rel>`, and `output_dir` logs
  `mo2 output`. Both leave out MO2's ini and the profile's mod list and
  settings.
- `build_plan._asked` asks each question again (`mod_dirs.ask`,
  `creation_kit.ask`). A different answer is the reason given for the
  rebuild, e.g. `plugin found ["Guns.esp", ...]`.
- The file found is still a recorded input when the build reads it, so
  editing it rebuilds the plugin that used it.

Tested (`test_fo4_build_plan.py`): rewriting the ini, ticking an unrelated
mod or changing another app setting leaves a plugin current. The same plugin
or Creation Kit file found in a higher-priority mod makes it build.

Not covered: the Creation Kit itself loads the profile's plugins through MO2.
A run of it (FaceGen, animation data) depends on what the profile enables,
and neither the old record nor this one tracks that; its own cache keys
decide when it reruns.

## <a id="stacking"></a>Part 2: overrides that do not stack

FNV lets each plugin add to a game record. In FO4, two plugins overriding
the same record don't stack: the last one loaded wins and the other's
additions are lost. The DLC work already found and fixed several of these:

- form lists added to at run time ([lists](fo4_plugin_layout.md#dlc-lists));
- perk entries in a plugin's own perk ([perks](fo4_plugin_layout.md#dlc-perks));
- each plugin's condition rows in its own source quest
  ([condition](fo4_condition.md#sources)), and the Ammo Type hotkey the same way;
- DLC lines added to game topics as FO4 plugins add them
  ([dialogue](fo4_plugin_layout.md#dlc-dialogue)).

Single-mod conversion depends on how many such overrides are left.

**Census first.** Run `python -m tools.validate.preflight --audit dlc`
across the nine DLC builds and a few FNV mods that edit game content (quest
mods, item mods, mods that change NPCs). For each kind of game record a
converted plugin overrides, list:
- how many plugins override it;
- whether the override only adds to the game's record (needs a stacking
  mechanism) or replaces it (normal FO4 conflict, the same as in FNV).

Checks the census must answer:
- **Dialogue menus.** The game build makes each menu (DLBR, the hub scene,
  per-menu prompts). Does a mod's line in a game topic reach that menu
  without an override of the menu?
- **Leveled lists.** These are already a normal conflict in FNV, so leave
  them to the user's patch tools unless a converted plugin overrides a list
  it only adds to.
- **Start-game quests** the build merges row by row
  (`base.quest_merge`): which still merge statically instead of being
  sources like condition?

Each "adds only" kind gets a run-time mechanism like the form-list adds, or
the plugin's own record (perks, condition sources). Each "replaces" kind is
left as FO4's normal conflict rule.

## <a id="master-kit"></a>Part 3: the master kit

What a dependent build reads from the game build lives in the developer's
workspace (`temp/profile_data`, `temp/fo4_scripts`, `output/fo4_cache`). The
game conversion ships it beside its plugin, in its own output folder:
- the ledger (already written beside the plugin);
- the texture manifest;
- the generated script sources a dependent compiles against;
- a stamp with the converter release that built it.

A user's mod build points at the installed game conversion and the kit. It
doesn't need the game build's workspace. FormIDs are hashed from authored
keys, so a mod converted against one game build keeps working when the game
is reconverted with the same release. A different release says so, and the
user reconverts the mod.

To measure: whether the mod build needs FNV's whole export of FalloutNV.esm
or only the records it reads. If only those, the kit could carry a compact
index instead, and the user would not keep a full export.

## <a id="shared-files"></a>Part 4: shared files stay with the game

`FalloutHelpers.esl`, `TES4Polyfill`, `F3NV.dll` and the hotfix mod belong
to the game conversion. A converted mod's folder holds only its own plugin,
archives and loose files that differ from the game's
([master copies](fo4_plugin_layout.md#master-copies)). A second copy of a
shared script overrides the game's and breaks it, as the Skyrim fork found
with the polyfill. The build should refuse to write a shared file into a
mod's folder, not rely on the files matching.

## <a id="ck-without-mo2"></a>Part 5: Creation Kit steps without MO2

At run time nothing needs MO2: the output is plugins, archives and loose
files ([the app](fo4_gui.md)). At build time, MO2 does two jobs:

- **Runs the Creation Kit** for FaceGen export (`spike/facegen.py`) and
  animation data (`rig/anim_info.py`). The Creation Kit sees only the game's
  Data folder; MO2's virtual folder shows it our output without copying it
  there, and catches what it writes in overwrite.
- **A fixed path**, `MO2 = C:\Modlists\fo3fnv-in-fo4`, which should be the
  app's chosen location.

Without MO2, one of:
1. **Stage into Data for the run:** link the needed files into Data, run the
   Creation Kit, collect what it wrote, and remove exactly what was staged
   (by a list written before the run). This touches the game folder, which
   needs the user's consent and a cleanup that survives a crash.
2. **Skip the step**, using the fallbacks in the app's tool table: faces
   fall back to the face-fit pass. Animation data has no fallback yet; it
   would need one, or need to be written by us.

MO2 stays the default when it is present.

## <a id="mod-masters"></a>Part 6: mods that need other mods

A converted mod's masters are the FNV mod's masters, converted: the game, a
DLC, or another converted mod. Each is converted before the mods that need
it, as the build plan already orders DLC. The app shows a mod whose master
is not converted yet, and offers to convert it first. Turning a converted
master off disables its dependents, as FO4 does.

## <a id="order"></a>Order

| Step | What | Size |
|---|---|---|
| 1 | MO2 answers, not files (Part 1; built 2026-11-04, [as built](#mo2-answers)) | S |
| 2 | The census (Part 2) | S |
| 3 | Fix what the census finds that only adds | M, by its count |
| 4 | Shared-file guard (Part 4) | S |
| 5 | The master kit, and a mod build pointed at it (Part 3) | M |
| 6 | Creation Kit steps without MO2 (Part 5) | M |
| 7 | The app's "convert this mod" (with [the app](fo4_gui.md#phases)) | M |

Part D (incremental records) runs beside this: it's what makes a
developer's code change cheap. Single-mod conversion is about not rebuilding
the game at all.

## <a id="open"></a>Open questions

- How much of FNV's export does a mod build need? (Part 3.)
- For staging into Data (Part 5, option 1), is the user's consent once, or
  per run?
- A mod converted with an older release against a game converted with a
  newer one: refuse, warn, or allow when the kit's ledger still holds every
  id the mod names?
