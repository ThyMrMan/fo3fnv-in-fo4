# Overnight FO4 build queue, 2026-11-10: failures and build time

One unattended run of the base game and 12 FNV mods through the app's own
stage commands: build and reference check for FalloutNV.esm, the NVTUP + NVMIM
asset overlay ([asset overlays](../fork/fo4_plugin_layout.md#asset-overlays)),
then import, export, build and check for each mod. All numbers below come from
that run's step logs and each build's `stage` timing lines. Frozen; a later run
is a new file.

## Contents

- [Results](#results)
- [Failures](#failures)
- [Where the time went](#time)
- [Leads](#leads)

## <a id="results"></a>Results

The queue was stopped at 07:44 during NVMIM.esp's build, so its stamp stays
`running`. Willow's faces never ran.

| Step | Result | Build time |
|---|---|---|
| FalloutNV.esm (whole map, `WastelandNV reached`) | built, check clean | 139 min |
| NVTUP + NVMIM overlay | **failed** | 4 min |
| Better Brotherhood.esm | built, check clean; one script still fails to compile | 15 min |
| NVWillow.esp | **failed** | 8 min |
| YUP - Base Game + All DLC.esm | **failed** | 17 min |
| Placement Fixes.esm | built, check clean | 39 min |
| Sunshine On My Shoulders.esm | built, check clean | 19 min |
| AguaFria.esm | **failed** | 8 min |
| TLD_Travelers.esm | **failed** | 36 min |
| DLC Enhancements.esp | built; **check: 6 unresolved** | 32 min |
| Strip Lights Region Fix.esm | built, check clean | 14 min |
| Landscape Disposition Fix.esm | built, check clean | 8 min |
| Goodies.esp | built, check clean | 41 min |
| ExtraGoodies.esp | built; **check: 3 unresolved** | 36 min |
| NVMIM.esp | stopped mid-build | — |

Through Goodies, mod builds took 237 minutes, so 6 h 16 min with the base
game. Every import
and export step took under a minute.

## <a id="failures"></a>Failures

Four of the five crashes are one bad source file ending a whole build.
FNV skips a missing or odd mesh; our build stops.

| Step | Error | Cause |
|---|---|---|
| Overlay | `KeyError: 205`, `nif/collision.py` `_body_block` (`MOTIONS[body.motion_system]`) | An NVMIM mesh's rigid body has motion system 205, not a value Havok defines. One mesh failed the whole 13 GB overlay. |
| NVWillow.esp | `FileNotFoundError: export\NVWillow\meshes\clutter\havok_bobbleheads\bobbleheadluk_hav.nif` (a MISC model, `spike/cell.py` `mesh`) | The path is in neither Willow's exported BSA nor vanilla: a dangling path in the mod. |
| YUP | `FileNotFoundError: ...\meshes\nvdlcpre1\weapons\1handpistol\10mmpistolpreorder.nif` (`spike/guns.py` `choose`) | The pre-order pack meshes are in `export\ClassicPack.esm`. YUP's masters (FalloutNV and the five DLC) don't include it, so its export chain never reaches them. |
| AguaFria | `FileNotFoundError: ...\meshes\nvdlcpre1\armor\preordvault\valult13male.nif` (`spike/equipment.py` `_rigid`) | Same as YUP: a pre-order pack armor. |
| TLD_Travelers | `ValueError: list.index(x): x not in list`, `nif/elric.py` `graft` (`names.index(name)`) | A collision output node's name matches no node in its mesh. The log does not name the mesh. |
| DLC Enhancements check | 6 unresolved `QUST VMAD property` | Old World Blues dialogue quests (`FNV_NVDLC03DialogueKlein`, `...Mobius`, `...Dialogue0` ×2, `...Borous`) name records the build did not write. |
| ExtraGoodies check | 3 unresolved `QUST VMAD property` | Honest Hearts' `FNV_NVDLC02RadioMessage` names records the build did not write (`[046EF0C2]`, `[04A8A296]` twice): the same kind as DLC Enhancements'. |
| Better Brotherhood | all scripts compile but `FALLOUTNV_BBSelfDestructQuestScript` | "cannot compare a weapon to a int"; "GetActorBase is not a function or does not exist"; "cannot pass a void to a actorbase". |

## <a id="time"></a>Where the time went

### Mod builds remake their masters' records

A mod build does not rerun the game build, but it remakes every record of its
masters in memory, then keeps what differs. Landscape Disposition Fix holds
2,242 records (503 CELL and 1,738 REFR overrides, one WRLD). Its build still
made 1,622 NPC_, 4,514 STAT, 238 ARMO and 190 WEAP and readied 6,360 meshes.
That's why every mod costs 7–41 minutes, however small it is. The plan that
ends this is [converting one mod against a built game](../fork/fo4_mod_builds.md).

The same build reported 1,585 "master records changed by the build alone"
over 23 types (273 PACK, 264 QUST, 220 NPC_, 182 LAND, 176 REGN...). It also
reported 170 "master records dropped: would lose master entries". The mod
touches none of those types except CELL and REFR, so its plugin may carry
master records that differ only because this build made them differently
from the game build. Not checked further.

### Base game: face fits with no cache entries

| Stage | Seconds |
|---|---|
| people | 5,827 |
| collision | 653 |
| item WEAP | 495 |
| item ARMO | 166 |
| base STAT | 148 |
| worlds | 139 |
| script compile | 113 |
| gun animation data | 89 |
| assets | 81 |
| total | 8,119 |

`people` is mostly the per-NPC face fit (`spike/npcs.py` `fit_face`: sculpt
fit, tint fit, head-part choice; `FACE_WORKERS` is 6 processes of about
1.26 GB each). The work cache keys each value on the code that ran making it
([code identity](../fork/fo4_plugin_layout.md#code-identity)), so the previous
day's code changes emptied it. Earlier base builds, from that session's logs:

| Build | people | item WEAP | total |
|---|---|---|---|
| 2026-11-09 13:03 (cold) | 5,601 s | 91 s | 8,557 s |
| 2026-11-09, five later builds (warm) | 248–324 s | 46–78 s | 1,484–3,422 s |
| 2026-11-10 overnight (cold) | 5,827 s | 495 s | 8,119 s |

A user's first conversion always starts with an empty cache, so the cold row
is what a user waits for.

### Gun clips: a cache key that changes with the master set

Gun clip results (`havok/gun_clips.py`) are cached on `_inputs`, which
includes `fnv_digest`, a hash of every clip file in every export layer. Each
distinct set of masters hashes differently, so a mod whose master set differs
from every earlier build's redoes all its gun clips:

| Mod | Masters | item WEAP |
|---|---|---|
| Landscape Disposition Fix | FalloutNV | 27 s |
| Strip Lights Region Fix | FalloutNV | 135 s |
| Better Brotherhood | FalloutNV + all 5 DLC (the same set as a build the day before) | 79 s |
| Placement Fixes | FalloutNV, HH, OWB, LR | 655 s |
| Sunshine On My Shoulders | FalloutNV, DM, HH, OWB | 651 s |
| DLC Enhancements | FalloutNV, DM, HH, OWB, LR | 756 s |

### Costs every mod build pays

| Stage | Range across the 8 mod builds that finished |
|---|---|
| mesh cache check | 26–153 s (1,802–9,718 meshes) |
| script compile | 3–154 s |
| base STAT | 73–796 s (Goodies 796, Placement Fixes 373, DLC Enhancements 321) |
| people (warm) | 29–355 s |
| collision | 23–183 s |

Goodies' STAT time (796 s, against the base game's 148 s) suggests DLC statics
also had no cache entries. Not confirmed.

## <a id="leads"></a>Leads

In order of time saved on this run:

1. **Build only a mod's own records** and what they reference, reading the
   built masters for the rest ([fo4_mod_builds.md](../fork/fo4_mod_builds.md)).
   That's most of the 237 mod minutes, and it would also drop the 1,585
   master records rebuilt for nothing.
2. **Make the cold face fit cheaper**: faster fitting, or shipping the fitted
   numbers for vanilla NPCs as data. Cold against warm is about 5,500 s of the
   base game's 8,119.
3. **Key gun clips on the clip files each gun reads**, not on the whole layer
   set: about 35 minutes on this run.
4. **Skip, don't crash, on one bad source mesh**: a missing file or an
   undefined motion system. That's four of the five crashes.
5. **Pre-order pack meshes**: decide how a mod that edits vanilla pre-order
   records reaches `ClassicPack.esm`'s export without listing it as a master.
