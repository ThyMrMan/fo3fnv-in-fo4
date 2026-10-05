# FO4 spikes: deciding whether FO3/FNV on Fallout 4 is buildable

Design only; status is in [ROADMAP.md](ROADMAP.md). The findings behind this
plan are in [research/fo4_target.md](research/fo4_target.md).

## Contents

- [Order and why](#order)
- [Step 0: groundwork](#step-0)
- [Spike 1: dialogue](#spike-1)
- [Spike 3: one script](#spike-3)
- [Spike 2: one interior cell](#spike-2)
- [Decision point](#decision)
- [Test setup](#test-setup)

## <a id="order"></a>Order and why

Spikes come before more exe reading. The [AI rules](research/fo4_target.md#ai-rules)
read so far settled the one question exe work could decide: FO4's AI
decisions are Skyrim's. The questions that could still sink the project are
on the content side, ordered by how decisive each is:

1. **Dialogue (spike 1).** Can FO3/FNV dialogue be generated for FO4 at all?
   This is go/no-go.
2. **Scripts (spike 3).** How big is the script back end? Runs in parallel
   with spike 1 and needs none of your play time.
3. **Assets (spike 2).** What does the mesh/material/collision/FaceGen back end
   really cost? Only worth paying for once spike 1 passes.

Exe reading resumes where a spike needs it. Spike 1 plays a force greet, which
settles R10 by observation.

## <a id="step-0"></a>Step 0: groundwork

| Piece | What |
|---|---|
| FO4 plugin writer | `fo4_import/base/writer.py`: `FO4PluginWriter` (form version 131, FO4 header with HEDR 1.0, INTV and INCC, FO4 top-level group order), plus `pack_quest()` / `pack_topic()` for FO4's nesting. Dialogue has no top-level group: each QUST is followed by a quest-children group (type 10) holding DLBR, then DIAL with its INFO group (type 7), then SCEN, in vanilla's order. Tests: `tests/test_fo4_writer.py` |
| Vanilla dump | `references/Fallout4.esm/`: all 138 record types, 558 MB, from `tools/esm/tes5_esm_reader.py --generic`. The `--generic` switch skips the tool's Skyrim field layouts and condition names, so FO4 fields show as raw FormID/uint/float/hex rather than mislabelled Skyrim fields. FO4-specific decoders get added as spikes need them |
| Script sources | `references/fo4_scripts/Base` (Base, the six DLC and Creation Club zips, 10,258 files, with `Institute_Papyrus_Flags.flg`) and `references/fo4_scripts/F4SE` (29 files). Import order: F4SE first, then Base |
| Compiler | Fallout 4's own `Papyrus Compiler\PapyrusCompiler.exe`. A smoke script with a struct, a timer and F4SE's `Form.GetEditorID` compiles. The vendored `external/papyrus-compiler/papyrus.exe` is Skyrim-only: it stops at the first `Struct` |

Known gap: `tes5_import.base.tes5_reader.walk(raw, b'DIAL')` (a *filtered*
walk) prunes group type 10 as Skyrim cell children, so it misses every FO4
topic. Unfiltered walks, and the dump tool, see them. An FO4 reader needs its
own child-group table.

## <a id="spike-1"></a>Spike 1: dialogue (go/no-go)

Generated from the FNV export by code, not built by hand in the CK.

- **1a. Doc Mitchell's opening conversation**, as XDI-enabled scenes:
  - the topic list, with more than four options;
  - SPECIAL and skill checks;
  - a silent player;
  - the force greet, played, to settle R10;
  - his voice lines as `.fuz` with lip data.

  The speaker is a vanilla FO4 NPC base in a test cell, so no converted
  meshes or FaceGen are involved.
- **1b. One generic topic many NPCs share**, placed on three vanilla NPCs.
  This tests how FO3/FNV's "any NPC whose conditions pass can say it" maps onto
  FO4's alias-based scenes.
- **Gate:** if 1b can't be generated without hand work, stop and rethink
  before any asset work.

## <a id="spike-3"></a>Spike 3: one script

Convert one FNV terminal or object script, emit FO4 Papyrus, and compile it
with FO4's compiler. Hydra (in the MO2 instance) logs broken script linkage
in game. Answers: the size of the FO4 command-row table and of VMAD for FO4.

## <a id="spike-2"></a>Spike 2: one interior cell

Doc Mitchell's house:

- statics, lights and doors;
- meshes through a minimal FO4 mesh writer plus BGSM/BGEM materials;
- textures re-encoded;
- FaceGen for Doc from the CK;
- no precombines.

fnv-to-fo4's format facts serve as a checklist
([research](research/fo4_target.md#fnv-to-fo4)), with NifSkope 2.0.dev11's
`nif.xml` as the layout reference.

## <a id="decision"></a>Decision point

After spikes 1–3: the architecture plan (the `fo4_import` package, the asset
writers, the script back end, the runtime), or a stop.

## <a id="test-setup"></a>Test setup

MO2 instance `C:\Modlists\fo3fnv-in-fo4`. Spikes run in a minimal `Spike`
profile, one change per test:

- the game and DLC;
- F4SE, the Address Library and MCM;
- XDI and LevelUpMenuEx;
- Addictol (crash logger, with its engine fixes off if its INI allows);
- Hydra.

UFO4P and the engine-fix mods stay in the `Default`/`Play` profile, because
they edit vanilla records and engine code a spike may be measuring. Generated
plugins never master UFO4P. Vanilla censuses read the game's own
`Fallout4.esm` (the dump above), not MO2's merged view.
