# What to redo now that newer machinery exists (audit, 2026-11-23)

Early Fallout 4 work was built as fast spikes. Since then the repo gained its
own FaceGen, a Creation-Kit-free face calibration, its own DDS encoder, our
Caprica build, `hknp_write` collision, a runtime DLL (F3NV.dll) and own-rig
creatures. This audit checks which older decisions those change, ranked by
payoff for the work. Read and measured only: no code changed. Docs found
wrong were fixed in the same pass ([below](#docs-fixed)).

**Sources.** Every build stamp under `D:/Modlists/fo3fnv-in-fo4/mods/*/F3NV_Build.mohidden`
(37 stamps, the newest base-game build 2026-11-21, DLC and mods to
2026-11-23), the build and faces logs in `temp/` and `temp/queue/`, the
pre-Elric inputs the build keeps (`output/fo4_cache/pre_elric`, named in
each plugin's `.replay.json`), `temp/fo4_scripts/FalloutNV.esm` (the
converted scripts of the 2026-11-21 build), and the code at `ed19ce1c`.
Scratch scripts are one-offs, not kept.

## <a id="ranking"></a>Ranking

| # | Item | Done then | Exists now | Measured evidence | Payoff | Size |
|---|---|---|---|---|---|---|
| 1 | [Script calls with a Fallout 4 native](#natives) | Rows inherited from the Skyrim converter write a `;NE:` note (`command_rows.py:431` "SetCombatStyle → no-op (managed by CK/race)") | Vanilla Fallout 4 declares `Actor.SetCombatStyle` (`Base/Actor.psc:626`), `Cell.SetPublic`, `Actor.SetCriticalStage`, `Weapon.Fire`, `ClearDestruction`, `Game.ShowAllMapMarkers`; the [decision table](../fork/fo4_plan_script_functions.md#decision-table) routes them (route 1) | 659 markers left in FalloutNV.esm's scripts (was 1,276); **177** are route-1 natives, phase 2 of the plan, still unbuilt | Combat styles for 40 scripts (Lily, spore carriers), cell public flags, traps that fire, crit stages | S |
| 2 | [Drop Elric](#elric) | Elric finishes every mesh our writer doesn't cover | `hknp_write` covers convex, round, mesh, list, constraint and phantom bodies | FalloutNV.esm: **0** of 6,188 meshes with collision go to Elric. NVWillow: 2 of 2,066, and Elric failed both. 6 Elric cache entries used since 2026-11-15, all at mod-build times | One CK tool and one Windows exe fewer for collision | S |
| 3 | [Drop the CK FaceGen fallback](#faces) | The CK through MO2 makes FaceGen for NPCs ours fails on | Our FaceGen is the app's default (`stages.py:250` passes `--own-facegen`), encoder our own since 2026-11-23 | 286 logged face runs: 1 had failures (Dead Money dev run, 2026-11-21, 5 NPCs), and there the CK fallback failed too | Removes the last CK run in a build (`creation_kit.run`) | S |
| 4 | [Caprica leaves whole folders to FO4's compiler](#caprica) | Caprica first, FO4's compiler for the rest | Our Caprica build compiles the base game (13,643 of 13,644 FO3 scripts; 5,011 of 5,011 in the queue build) | Latest builds: Zeta 295 of 879 left to FO4's compiler, NewVegasBountiesII 82 of 974, then FO4's compiled all but 7 and 1. Alone, Caprica names each failing Zeta script correctly | Off Windows those scripts stay uncompiled; on Windows, minutes per mod build | S to diagnose |
| 5 | [Off-Windows blockers](#off-windows) | Built Windows-first | The CK steps became fallbacks; a Wine wrapper (`core.subprocess_flags.windows_cmd`) exists for bundled exes | `pinned_zlib` ships only `f3_zlib.dll` and raises without the library: every plugin write stops. Caprica and FO4's compiler run without the Wine wrapper | Linux and macOS, which README calls "may work" | S (zlib) to M (scripts) |
| 6 | [Weather clouds](#clouds) | FO4's cloud layers recolored, because FNV's textures seamed on FO4's dome (played 2026-10-23) | Our DDS encoder (2026-11-23) and texture BA2 writer (2026-11-11) can write reprojected cloud textures | 14 weathers, 1 without FNV clouds (FalloutNV.esm stamp) | FNV's own skies | M |
| 7 | [`spike/` code shape](#spike) | Everything grew in `fo4_import/spike/` | `face/`, `base/`, `pipeline/`, `nif/`, `havok/`, `rig/` | 158 modules, 24,567 code lines; 154 used by the build, 4 test-plugin generators. 3 copies of `base/strings.LOCALIZED` | Fewer drift bugs from copied rules | S (copies), L (moves) |
| 8 | [Third-person gun animations](#guns) | ROADMAP: "Third-person animations are Fallout 4's" | FNV's own third-person clips, built 2026-11-13 (`b84d2b73`, `havok/gun_third.py`) | Doc-only: ROADMAP was stale | Correct status | Done (doc) |
| 9 | [Armors on stand-ins](#armors) | ROADMAP: "21 of 98 armors use stand-ins" | Outfit fitting (`nif/outfit.py`), headgear | FalloutNV.esm stamp: 15 of 323 ARMO keep FO4's worn models (13 other slots, 2 no FNV worn model); 24 more keep only FO4's ground model | Correct status | Done (doc) |
| 10 | [Previs](#previs) | "needs the Creation Kit" | Nothing since | Previs is an Umbra tome only the CK writes ([research](../fork/research/fo4_precombines_previs.md#ck)); no precombine or previs code in `fo4_import` | None yet | — |

## <a id="natives"></a>1. Script calls with a Fallout 4 native

**Census.** `python -m tools.audit.script_marker_census
temp/fo4_scripts/FalloutNV.esm export/FalloutNV.esm`: **659 markers in 386
scripts, 89 functions** (80 on a condition line). The
[2026-10-31 census](../fork/script_markers.md#census) had 2,156, and the
ROADMAP's 1,276 was the count after its first fixes. The
[plan's](../fork/fo4_plan_script_functions.md#exists) rerun had 806; since
then IgnoreCrime (185) and GetIgnoreCrime (3) were built.

**Route 1 still unbuilt.** Every route-1 row of the
[decision table](../fork/fo4_plan_script_functions.md#decision-table) is
still in the census: SetCombatStyle 54, setCS 4, SetRumble 10,
SetCellPublicFlag 10, SetPublic 2, PlayMusic 9, GetFurnitureMarkerID 8,
TriggerScreenSplatter 8, UseWeapon 8, SetCriticalStage 6, EnterTrigger 5,
FireWeapon 5, GetContainer 5, SetSecExp 5, SystemSave 5, ForceSave 2,
GetPCMiscStat 4, IsInList 4, AttachAshPile 3, GetContainerInventoryCount 3,
GetCurrentAIPackage 3, PlayBink 3, ClearDestruction 2, SetItemValue 2,
ShowBarberMenu 2, CreateDetectionEvent, ExitGame, GetXPForNextLevel,
IsSpellTarget, ShowAllMapMarkers 1 each: **177 markers**.

- The shared rows were written for Skyrim, which lacks several of these
  natives, and the Fallout 4 target inherits the note
  (`command_rows.py:422` SetActorFullName, `:428` SetCellPublicFlag, `:431`
  SetCombatStyle, `:451` SetPublic). A Fallout 4 row in
  `command_rows_fallout4.py` overrides each, as IgnoreCrime's does.
- `SetSecExp` is SetSecuritronExpression's short name; only the long name
  has a handler (`commands_falloutnv.py:605`), so 5 lines in
  `vFreeformTheStreet02` miss the face screen built for the long one.
- **SetActorFullName (17) needs no DLL.** The plan lists it as a DLL
  candidate, but F4SE, which the build already requires, declares
  `Form.SetName` (`F4SE/Form.psc:32`). It renames the base, as FNV's
  command does.
- `isps3`, `iswin32` and `isgoredisabled` already emit `0` with a note
  (`constants_falloutnv.py:172-184`); they count as markers but are
  converted.

## <a id="elric"></a>2. Drop Elric

**How measured.** Each build keeps every pre-Elric NIF it finished
(`elric_cache.keep_input`), listed in `<plugin>.replay.json` under
`pre_elric`. Running `hknp_write.finish` over each, as
`elric_cache.process` does first, and reading the blocks of each one it
declines:

| Build | Meshes finished | Ours | Declined, no Havok at all | To Elric |
|---|---:|---:|---:|---:|
| FalloutNV.esm (2026-11-21) | 7,784 | 6,188 | 1,596 | **0** |
| NVWillow.esp (2026-11-23) | 2,066 | 1,723 | 341 | **2** |

A mesh without Havok blocks never reaches Elric (`elric.finish` skips it,
`havok_start` is None). NVWillow's two: `cakeplate.nif` (a flat convex
shape; our writer raises `ValueError: cannot convert float NaN to
integer`) and `reloadingbench_tool_02a.nif` (a triangle mesh on a moving
body). Its stamp records `meshes without collision (Elric failed) 2`, so
Elric failed both. Every other stamp records 0 failures.

The Elric cache (`output/fo4_cache/elric`, 13,834 entries) has 6 entries
used since 2026-11-15, all at mod-build times on 2026-11-22 and 23: at most
four mod meshes still take Elric's cached output.

**What would go.** The Elric run in `elric_cache.process`, `elric.process`
and the Elric tag; the cache module's finish, graft and replay plumbing
stays (it is the build's mesh cache too). Not measured: `rig/assets.py:197`
falls back to Elric for an own-rig skeleton `hknp_ragdoll` declines; check
the 12 own-rig races before removing it. The two NVWillow shapes would be
left without collision, as Elric leaves them today.

## <a id="faces"></a>3. Drop the CK FaceGen fallback

- **App:** the Faces stage passes `--own-facegen` (`app/stages.py:250`);
  the CK runs only for NPCs our FaceGen fails on (`spike/facegen.py`
  `fallback`).
- **Measured:** 286 `own FaceGen written` lines across `temp/**/*.log`.
  One run had failures: `temp/facetest/dm_run2.log` (2026-11-21), 5
  Dead Money NPCs, and its CK fallback left all 5 without FaceGen
  (`CK fallback failed ... 5 of 5 NPCs have no FaceGeom NIF`). No other log
  names a fallback.
- **What would go:** `facegen.fallback`, the CK export branch (`heads` with
  `own` false, `--collected`), and with them the last build caller of
  `creation_kit.run` (`facegen.py:198`). The module's MO2 profile reading
  stays: our own FaceGen reads the profile's mod order through it
  (`face/own_facegen.py:203`, `spike/facegen_skin.py:99`). A face that fails
  would be reported and left without FaceGen, which is what the fallback
  gave the only time it ran.

## <a id="caprica"></a>4. Caprica leaves whole folders to FO4's compiler

From the latest logs (`temp/queue/`):

| Build | Caprica compiled | Left to FO4's compiler | FO4's compiler's result |
|---|---|---:|---|
| Zeta.esm (`build_Zeta.esm.log`) | 584 of 879, 14 runs | 295 | 872 of 879 compile |
| NewVegasBountiesII.esp (`rebuild_addons.log`) | 892 of 974, 12 runs | 82 | 973 of 974 compile |
| Anchorage.esm | 538 of 540 | 1 | — |
| Fallout3.esm, BrokenSteel, PointLookout, ThePitt | all | 0 | — |

`caprica._drain` stops a folder when a run names no script of it, and
`compile_files` deals the scripts into up to 12 folders, so each such stop
hands a whole folder (879 / 12 = 73 for Zeta, 974 / 12 = 81 for Bounties
II) to FO4's compiler. Run alone, Caprica names the failing Zeta scripts
(`FALLOUT3_DLC05SpaceBridge01MasTri_7703`: `Unexpected character ':'`;
`FALLOUT3_DLC05CryoFreezeRoomSCRIPT`: `Unable to resolve type
'TES4Polyfill'`), and `caprica._errors` parses both. Why a run inside the
folder named none is **not found**; a timeout or a crash on another script
are the candidates. Off Windows there is no FO4 compiler, so those scripts
would stay uncompiled.

## <a id="off-windows"></a>5. What blocks Linux and macOS today

Read from the code; nothing was run off Windows.

| Blocker | Where | Effect | Fix |
|---|---|---|---|
| **Pinned zlib ships for Windows only** | `base/pinned_zlib.py` loads `native/dist/f3_zlib.dll` (`libf3_zlib.so` / `.dylib` elsewhere, not committed) and raises `RuntimeError` without it; `base/record_compression.py` and `base/ba2_textures.py` call it | The plugin write and the texture BA2 stop: no build finishes | Build and commit the `.so` and `.dylib` (`tools/generators/gen_f3_zlib.py`); S |
| **Script compile** | `base/caprica.py:122` runs `Caprica.exe` directly, not through `windows_cmd`; imports joined with `;`. FO4's compiler (`base/papyrus.py`) is a Windows exe too | No `.pex` for any converted script | Run Caprica through `windows_cmd` and Wine paths, or build Caprica for Linux and macOS (its CMake/vcpkg recipe, `external/caprica/f3nv.patch`); M |
| **Voice and sound audio** | `asset_convert/audio/audio_converter.convert_file_to_xwm` needs `xWMAEncode.exe` (no fallback); runs through `windows_cmd` (Wine) | Without Wine and the exe, no voice or sound files. The launcher that downloads xWMAEncode is the Windows `.cmd` | [CK replacements item 6](../fork/fo4_ck_replacements.md#options) (not started) |
| **Object LOD** | `LODGenx64.exe` through `windows_cmd` (`asset_convert/lod/lod_gen.py:1008`) | Under Wine only | — |
| **Script headers** | `base/papyrus.unpack_headers` reads the CK's `Data/Scripts/Source/*/*.zip` | The CK must be installed (Steam runs it under Proton) | README already says so |
| **Wine setting unused** | `app/settings.py:41` keeps `tools.wine`; nothing reads it | `windows_cmd` takes `wine` from `PATH` only | Read it, or drop it |
| FO4Edit's check | `stages.WINDOWS_TOOLS` | Stage greyed out | Optional stage |
| Native speedups | `native/dist/*.cp314-win_amd64.pyd` | `nif_geom_native.native()` falls back to Python; navgrow is the Skyrim navmesh path | Slower only |

## <a id="clouds"></a>6. Weather clouds

`spike/weather_clouds.py` keeps FO4's cloud layers and colors them as FNV's
first drawn layer, because FNV's cloud textures "do not fit FO4's sky dome
(played 2026-10-23: hard seams)". The blocker was the dome's mapping, not
tooling. What changed: textures can now be written and packed without
texconv or Archive2 (our encoder, `base/dds_encode.py`; texture BA2,
`base/ba2_textures.py`). A reprojection of FNV's four layers onto FO4's
dome UVs is new work; the payoff is FNV's own skies over the 14 converted
weathers. Not measured: FO4's dome UV layout.

## <a id="spike"></a>7. `spike/` code shape

- **158 modules, 24,567 code lines** in `fo4_import/spike/`. Imported by the
  build: 154. With no importer: `bink`, `look_race_test`, `neck_test`,
  `step_map`, each a `python -m` test-plugin generator. 41 are imported from
  outside `spike/`. Largest: `cell.py` 1,162 code lines, at the 1,200 limit.
- **Copied rules.** An AST hash of every function body over 40 nodes in
  `fo4_import` found one exact copy (`nif/bgsm.py:47` and `nif/blocks.py:41`,
  `take`). Same-named constants with equal values: `LOCALIZED = (FULL,
  DESC)` in `base/strings.py:22` and copied in `spike/ammo_mods.py:70`,
  `spike/equipment.py:108`, `spike/guns.py:66`, while
  `spike/child_race_test.py:40` lists five tags (adds `TTGP`, `MPPN`,
  `FMRN`): the copies can drift from the rule. Also
  `'Fallout4 - Animations.ba2'` in 3 files, `FNV_SKELETON` in 2,
  `SHAPES` in 3 `face/` files.
- No rule found duplicated between `spike/facegen*.py` and `face/`: the
  spike modules are the stage's command line and its work-cache wrappers.
- **Payoff.** Folding the copies is small and stops drift. Moving the 154
  modules out of `spike/` renames imports in 154 files and tests for no
  behavior change; not worth it on its own.

## <a id="guns"></a>8. Third-person gun animations

`havok/gun_third.py` writes FNV's `characters\_male` weapon clips onto
FO4's human skeleton (commit `b84d2b73`, 2026-11-13; [step
1](../fork/fo4_gun_animation.md#third-person-clips) "built"). The
FalloutNV.esm stamp counts 82 `guns on FNV clips`. Open: a third-person
keyword for the 14 guns without an entry ([ranking](../fork/fo4_gun_animation.md#measured)).
Own-rig work (`rig/`) is for creatures and does not change guns.

## <a id="armors"></a>9. Armors on stand-ins

From the FalloutNV.esm stamp: `ARMO 323`; `ARMO on the template's models
(other slots) 13`, `(no FNV worn model) 2`; `ARMO on the template's world
model (FNV has none) 24`. The "other slots" are armors that are neither
headgear nor upper body (`spike/equipment._on_template`). Which items
those 13 are was not listed.

## <a id="previs"></a>10. Previs

Unchanged. Previs data is an Umbra tome only the CK writes
([research](../fork/research/fo4_precombines_previs.md#ck)); `fo4_import`
has no precombine or previs code. Our own precombines remain the
[research route](../fork/research/fo4_precombines_previs.md#own-precombines).

## <a id="docs-fixed"></a>Docs fixed in this pass

- [ROADMAP](../fork/ROADMAP.md): the script converter's count (1,276 → 659),
  guns (third-person clips built), outfits (15 of 323), building without the
  CK (measured fallbacks), planned item 7.
- [fo4_gui.md](../fork/fo4_gui.md): the facegen MO2 path is no longer
  hard-coded (`creation_kit.MO2` reads `F3NV_MO2`, set by
  `app/mo2_setup.py:57`); the Windows tools table gains xWMAEncode, LODGen
  and the pinned zlib, and LipGenerator is still called when installed.
- [fo4_ck_replacements.md](../fork/fo4_ck_replacements.md#today): FaceGen
  and collision rows.
- [script_markers.md](../fork/script_markers.md#ranking): rows 15, 17, 18
  and 19 (IgnoreCrime, the casino and Caravan menus and the radio calls are
  built; SetCombatStyle has a native).
- [fo4_plan_script_functions.md](../fork/fo4_plan_script_functions.md#phases):
  phase 8's row had fallen out of the phases table; SetActorFullName has
  F4SE's `Form.SetName`.
- [README](../../README.md#other-systems): what is known to block Linux and
  macOS.
