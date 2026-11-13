# The build chain (`tools/release/fo4_chain.py`)

The whole FO4 build in one command, watched. It replaces the scratch scripts
`temp/full_chain.py`, `temp/after_chain.py` and the CK watchdog
(`ck_watch.py`) the overnight builds ran with, keeping their order and
arguments.

```bash
py -3.14 -m tools.release.fo4_chain --check     # startup checks only, seconds
py -3.14 -m tools.release.fo4_chain --notify    # run, resuming after the last finished step
py -3.14 -m tools.release.fo4_chain --fresh --kit <file.esl> --kit-mod "<MO2 mods>\F3NV - Child Race Test"
```

## <a id="why"></a>What went wrong without it (2026-11-12 and 13)

- The Steam games moved to `D:\SteamLibrary`; the source registry still
  named the old folders and the base build broke after 136 s.
- The CK hung before writing its first file (now `CK_FIRST` in
  `creation_kit.run`), and a CK that stalls mid-export is closed after
  `CK_QUIET` as if done.
- `build_plan --run` replayed a scratch build's stamp command and rebuilt
  Caravan Pack into `temp/` in a loop.
- A base rebuild inside `build_plan --run` silently reset the faces.
- Runs took far longer than usual with no one noticing until morning: base
  3,176 s against 525 to 852 s, CK faces 15,431 s against 869 to 1,170 s for
  our own FaceGen.

## <a id="steps"></a>Steps

In order, as the scratch chain ran them:

1. **base**: `fo4_import.pipeline.run` builds FalloutNV.esm whole into its
   mod folder (the folder `fo4_app.json` names for `falloutnv`), with
   `F3NV_PROFILE_STAGES=worlds,item WEAP` (`--profile-stages ''` turns it
   off).
2. **faces**: `fo4_import.spike.facegen --own-facegen`.
3. **helpers**: `FalloutHelpers.esl`.
4. **dll**: F3NV.dll into `F4SE/Plugins`.
5. **plan**, then **others**: `build_plan` over the base and every built
   plugin in the mod folders beside it (The Frontier left out), then the
   same with `--run`.
6. **faces check**: the base plugin's faces stamp names the build on disk
   ([faces-stamp](fo4_facegen_plan.md#faces-stamp)); stops with
   `FACES_NOT_FROM_BASE_BUILD` otherwise.
7. **preflight** on FalloutNV.esm (its exit code is reported, it does not
   stop the chain), then **test plugin**: with `--kit` and `--kit-mod`, the
   kit is copied into its own mod folder, left unticked.

Each step's output goes to the console and to `temp/fo4_chain/chain.log`,
between `===== <step>: ...` and `===== <step>: exit N after S s` lines.

## <a id="startup"></a>Startup checks

Before any step, in seconds, each failure a line and exit 2
(`STARTUP_CHECK`); `--check` stops after them:

- a configured path is missing: `export/sources.json`'s directories and
  homes, `%APPDATA%\F3NV\fo4_app.json` with its game installs and enabled
  mod sources, the FalloutNV.esm export and mod folder, the Fallout 4
  install, MO2 (`creation_kit.MO2`), and the tools (the CK, the Papyrus
  compiler, texconv, `ModOrganizer.exe`, the committed F3NV.dll);
- Fallout 4 (or its F4SE loader), MO2 or the CK is running;
- the mod folder's or the checkout's drive has under 40 GB free
  (`--min-free-gb`);
- a plugin outside `temp/` would read a master from a scratch copy in it
  (`build_plan.scratch_masters`, [plan-guards](fo4_plugin_layout.md#plan-guards)).

## <a id="watchdog"></a>Watchdog

Each step's process is watched every 5 s:

- **No output** for 45 min (`--no-output-minutes`): `STALL_NO_OUTPUT`.
- **No new file** for 45 min (`--no-file-minutes`) in the folders the step
  writes to, looked at every minute: `STALL_NO_NEW_FILE`. The build steps
  and the faces watch the mod folder and MO2's folder for the CK's new files
  (`creation_kit.output_dir`, overwrite by default), the build steps also
  `temp/fo4_scripts`. The plan and the preflight write nothing and are not
  watched for files.

A stalled step is ended with its children, a CK it left is closed, and the
chain exits 124. Both limits sit above the CK's own (`CK_FIRST` 30 min,
`CK_QUIET` 15 min), so the CK's handling runs first.

**Slow steps.** A step past twice its estimate prints a `SLOW:` line once
(and a notification with `--notify`). The base build's estimate is
`eta.planned` on its last finished build (the same model the build prints);
`others` sums it over the plugins the plan would build; any other step uses
its last passing run's time. After a slow base build, `eta.overran` compares
the new build's stage times with the plan and names the slowest stage of the
groups that overran most, to pass to `--profile-stages` next time.

**Notifications.** `--notify` shows a Windows toast (PowerShell's own app
id, no module needed) when the chain stops, finishes, or a step runs slow.

## <a id="resume"></a>Resume

`temp/fo4_chain/state.json` keeps each step's result (passed, failed,
stalled), its time and a key saying what it produced. A restart skips a
passed step whose key still matches:

- **base**: the base build on disk (its stamp's start and end), and only
  while `build_plan` finds it current;
- **faces**: its finished faces stamp, only while it names that base build;
- **helpers**: the checkout's commit and uncommitted changes, and the
  plugin's size and time;
- **dll**: the committed DLL's and the installed copy's size and time.

The plan, `others` (build_plan is incremental itself), the faces check, the
preflight and the kit copy always run. `--fresh` forgets the file.

## <a id="tests"></a>Tests

`tests/test_fo4_chain.py`, with fake processes, folders and clocks; no game
build, no MO2 folder written.
