# Script hotfixes between builds

**Code:** `tools/release/fo4_hotfix.py`, `tools/release/fo4_deploy.py` (manifest, install, clearing).

A whole-map build and its DLC take about an hour (66 min on 2026-11-04: the base game 29, the DLC and packs 37).
A play test finds a bug in about 20 minutes, so most of the cycle was the build. Most fixes found in play are
Papyrus: the talk opening, the script packages, reputation, quest scripts. Those can reach the game without one.

## <a id="how-it-works"></a>How it works

```bash
py -3.14 -m tools.release.fo4_hotfix                      # the base game
py -3.14 -m tools.release.fo4_hotfix --plugin temp/profile_data_dm/DeadMoney.esm
py -3.14 -m tools.release.fo4_hotfix --dry-run            # list what would ship
```

1. The plugin's build stamp names its export, data, script and master folders.
2. The FNV scripts are converted as the build converts them (`build_steps.convert_scripts`), helpers and their
   Fallout 4 overrides included.
3. Each converted script is compared with its copy in the script stage, the sources the plugin's last build
   compiled (`script.stage_dir`). A script that differs ships. So does a helper the stage lacks (a new
   `F3NV_` script a changed one uses). A converted FNV script the build never compiled does not: no record runs it.
4. They compile in a scratch folder. The new sources come first on the import path, then FO4's and F4SE's
   headers, the masters' converted scripts, then the stage for everything unchanged.
5. The `.pex` files go to `Scripts\` in the `F3NV - Hotfix` MO2 mod, replacing that plugin's earlier hotfix.
   `F3NV_Hotfix.json` there lists each plugin's files and when they shipped.

Each hotfix compares against the last full build, so it carries every script change since that build, not
only the newest.

A hotfix takes the machine's build lock, so it waits for a running build instead of converting into the same
folder. It refuses while Fallout 4 runs.

<a id="per-game"></a>**One hotfix mod per source game (2026-11-17).** `F3NV - Hotfix` is New Vegas's (its DLC builds
share it), `F3NV - Fallout 3 Hotfix` is Fallout 3's (`fo4_deploy.HOTFIX_MODS`, picked by `fo4_deploy.hotfix_mod`
from the build stamp's `--export`). Both games ship scripts of the same names (`TES4Polyfill`, the `F3NV_`
helpers), so one shared mod put one game's copy into the other's profile, and clearing one game's hotfix deleted
files the other had listed. Each game's MO2 profile enables its own: the "Fallout 3" profile has
`F3NV - Fallout 3 Hotfix` where `F3NV - Hotfix` was, and `F3NV - Hotfix` off.

**One-time setup (by hand in MO2):** enable the game's hotfix mod and place it last, below every `F3NV - ` mod. Loose
files already win over BA2 archives, where the builds pack their scripts since 2026-11-11
([main archive](fo4_pipeline.md#main-archive)); being last makes it win over any loose script a mod still has.

## What it cannot carry

- **Records.** A fix that adds or changes a record (a package input, an alias, a new property's value) needs a
  build. A script whose new property the plugin does not fill yet sees None. Scripts that check their
  properties keep the old behavior until the build lands.
- <a id="needs-a-build"></a>**Refused: a property a record would fill (2026-11-17).** A changed script that adds
  an object property with no default, or changes such a property's type, would see None until a build fills it
  from the records: a quest fragment's every value empty looks like a converter bug and sends a test run chasing
  it. So `fo4_hotfix` refuses with exit 2 and names each such property ("needs a full build"). Value properties
  (`Int`, `Float`, `Bool`, `String`, `Var` and their arrays: the converted scripts' variables) and properties with
  a `=` default are never filled by a record, so they ship.
- **A changed function signature.** Unchanged callers keep the compiled call they had. Papyrus binds by name at
  run time, so a call with the wrong arguments fails until the build recompiles them.
- **Saves.** Scripts only: no FormID is involved, so a save made with a hotfix carries over to the build.

## <a id="clearing"></a>Clearing

A loose hotfix script would keep winning over the build that contains its fix, and over every later fix to the
same script. So `fo4_deploy` clears a plugin's hotfix files once it deploys a build of that plugin that
**began after the hotfix shipped**. A build begun before it lacks the fix, so the hotfix stays. Clearing reads
the build stamp's `started` time and the manifest's `shipped` time.
