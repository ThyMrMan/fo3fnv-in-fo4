# Plan sketch: the build without the Creation Kit (2026-11-11)

Status: 1 [built](#ba2), 2 [built](#caprica) and 7 [built](#lips)
(2026-11-11, not built in game); the rest ideas. Status lives in
[ROADMAP.md](ROADMAP.md). Built on the [open-tools survey](research/fo4_open_landscape.md#tools)
and the build's own docs; costs quoted are the docs' measurements.

**Why.** The FO4 build still runs Bethesda's and Microsoft's Windows-only
tools as stages: the Creation Kit (FaceGen, AnimTextData), Elric, Archive2,
LipGenerator, xWMAEncode and FO4's Papyrus compiler
(`fo4_import/app/stages.py`, `WINDOWS_TOOLS`). Each one blocks the
[cross-platform app](fo4_gui.md), and several cost time, determinism or
reliability on Windows too.

## <a id="today"></a>Where each step stands

| Step | Tool today | Already ours |
|---|---|---|
| Navmesh | none | Converted from FNV ([navmesh](fo4_pipeline.md#exterior-navmesh)) |
| Terrain and object LOD | none | Written from FNV's tiles and LOD meshes ([terrain](fo4_pipeline.md#terrain-lod), [objects](fo4_pipeline.md#object-lod)) |
| Lip files | LipGenerator for lines with no FNV `.lip` | FNV's lips converted ([lips](research/lip_format.md#built)) |
| Papyrus | FO4's compiler for scripts Caprica can't take | Caprica first ([Caprica](fo4_pipeline.md#caprica)) |
| AnimTextData | CK `-GenerateAnimInfo` through MO2 | Third-person gun entries ([writer](research/anim_text_data.md#writer)) |
| FaceGen | CK `-ExportFaceGenData` through MO2; we bake FNV's shape into its head (`face/bake.py`) | Plan to write the heads ourselves ([facegen plan](fo4_facegen_plan.md#direct)) |
| Collision and ragdolls | Elric | Our pre-Elric blocks; the graft (`nif/elric.py`) |
| BA2 packing | Archive2 (`base/ba2_pack.py`) | Staging and options |
| Voice audio | xWMAEncode inside each `.fuz` | The `.fuz` itself |
| Precombines and previs | none yet (CK planned, [before](fo4_pipeline.md#before)) | Not built |

## <a id="options"></a>What we could build, by payoff for the work

| # | Replace | Size | What it gains |
|---|---|---|---|
| 1 | **Archive2 → our own BA2 writer** (GNRL and DX10 chunks) | Small. Open references: `Ryan-rsm-McKenzie/bsa` (MIT), `northaxosky` `btdx` (Apache-2.0) | No CK Tools install for packing; runs on any OS; packing in our process pool |
| 2 | **FO4's compiler → Caprica only** | Small to medium: fix Caprica's own failures upstream (MIT), the [error table](fo4_pipeline.md#caprica-errors) lists them | Scripts build on any OS; no 25–30 min fallback path on a first build |
| 3 | **CK AnimTextData → our writer for everything** | Medium: format decoded ([AnimTextData](research/anim_text_data.md)), name hash known, gun entries written | Removes a CK run (233 s when it ran every build), the MO2 round trip and the CK editing deployed files in place ([why](fo4_own_rig.md#anim-info)) |
| 4 | **CK FaceGen → our own heads and tint textures** | Large; already [planned](fo4_facegen_plan.md#direct) | FNV's full face shape (sliders reach 70–91%); no CK stage (0.43 s per NPC plus MO2); mod builds stop needing the CK for new NPCs. A community first: no open FO4 FaceGen baker exists |
| 5 | **Elric → our own hknp collision writer** | Large. Starting points: `Kalmarv/havok-formats` (GPL-3.0, builds hknp compressed meshes, reads hk_2014 packfiles), BGS's class layouts (MIT), our NIF writer | Byte-reproducible output (Elric writes uninitialized bytes: 162 of 946 files differed); parallel (Elric deadlocks above one instance); no crash cases (the TLD_Travelers `graft` failure); 23–183 s off each mod build; a fixed ragdoll order for own rigs ([random today](fo4_own_rig.md)). A community first: nobody writes FO4 collision openly |
| 6 | **xWMAEncode → something open** | Spike first: does the game play another codec inside `.fuz`? Else vet `595554963github/Xwma-Codec` (GPL-3.0, no README) | Voice builds on any OS |
| 7 | **LipGenerator → nothing** | Small: only lines with no FNV `.lip` (Voices1: 315 of 52,896) need it; make those from the audio's loudness, or leave them silent | The last LipGenerator run gone; deterministic lips (LipGenerator gave 1,758 and 1,746 bytes for one line) |
| 8 | **Precombines and previs, our own** | Very large. Precombining is mesh merging plus records; previs is a visibility bake. Nothing open exists | Frame rate in dense areas without the CK, and per-mod rebuilds. Do the CK route first; revisit once it works |

## <a id="gains"></a>What the whole set buys

- **The app on Linux and the Steam Deck.** Today four app stages are
  Windows-only. Items 1–7 make every stage but precombines portable.
- **No Creation Kit install for users.** Users would need only the game and
  their mod manager, not the CK, CKPE and Tools.
- **Mod-manager neutral for real.** The CK steps run through MO2
  (`pipeline/creation_kit.py`) so the CK sees the profile's plugins;
  [the app's design](fo4_gui.md) promises any mod manager.
- **Faster, repeatable builds.** No serial CK or Elric runs, everything in
  the process pool, the same bytes every build (FaceGen and lips included),
  so caches hold and mod builds stay small ([build speed](fo4_build_speed.md)).
- **Tools other modders don't have.** An open FaceGen baker and an open FO4
  collision writer would each be firsts
  ([survey](research/fo4_open_landscape.md#tools)), and both fit
  [the spin-off strategy](spin_offs.md#strategy).

## <a id="ba2"></a>1. The texture BA2 is ours (built 2026-11-11, not built in game)

`base/ba2_textures.write_textures` replaced Archive2 in
`ba2_pack.pack_textures`, beside our general writer (`ba2_write`). Layout
read off Archive2's own archives: version 8 `DX10`, one chunk per texture,
24-byte record (both name hashes, `dds`, size, mip count, DXGI format, cube
flag, tile mode 8) and 24-byte chunk (offset, zlib size, size, first and
last mip, `0xBAADF00D`), the DDS bodies zlib level 6 back to back, then the
names. Textures unchanged since the last pack are copied out of the old
archive still compressed.

**Checked against Archive2 (2026-11-11):**
- AutumnLeaves: all 174 textures Archive2 packed have the same record and
  the same compressed bytes (0.4 s).
- FalloutNV.esm: 13,181 of 13,189 shared textures identical (99 s for
  1.6 GB). The 8 others are object-LOD textures whose lower mips changed
  after the deployed archive was packed: same top mip, both zlib 6.
- Formats in every staging folder (census): DXT1, DXT3, DXT5, ATI2/BC5U,
  32-bit BGRA, cube maps, and 24-bit BGR.

**Archive2 dropped textures without a word.** 24-bit BGR has no DXGI
format, and Archive2 left every such texture out and still exited 0:
AutumnLeaves' ending slide `alendslides/alintro1.dds`, 10 + 2 textures in
Weapons of the New Millenia, and the Classic Look's 54 LUTs. Our writer
stores 24-bit as opaque B8G8R8A8 (`expand_bgr`), and a format it cannot
name stops the pack with the file's path.

**The Classic Look's LUTs stay loose.** `build_finish` kept only
`Effects\LUTs\FNV` out of the archive, so `Effects\LUTs\FNVClassic` was
staged and then dropped by Archive2. Both folders now stay loose like
vanilla's LUTs, and `ba2_pack._unstage` moves LUTs an older build staged
back into the Data folder.

## <a id="caprica"></a>2. Caprica only: every script, with our Caprica build (2026-11-11, not built in game)

**Done.** We now bundle our own Caprica build ([what changed](fo4_pipeline.md#caprica-ours)):
relational operators on strings, and a fix for Caprica's temp reuse, which
had silently miscompiled 59 FalloutNV scripts (Victor's game start among
them). `List` lost its `= None` defaults and `nvse_falloutnv._array_call`
passes all 20 (`LIST_SLOTS`). FalloutNV.esm's 17,507 scripts: 17,490
compile in Caprica, and the 16 own errors fail in FO4's compiler too, so
none is left for FO4's compiler. FO4's compiler stays the fallback for
mods' scripts; `caprica.SAME_ERRORS` needs no change, since Caprica now
gives its operator message only where FO4's compiler fails too.

What follows is the measurement that led here.

A probe compiled every script of a converted folder with Caprica the way
the build does (`caprica.compile_files`) and listed what it left to FO4's
compiler:

| Folder | Scripts | Caprica | Own errors | Left to FO4's compiler |
|---|---|---|---|---|
| FalloutNV.esm | 17,507 | 17,490 | 16 | 1: `F3NV_Array` |
| AguaFria.esm (masters imported) | 45 | 42 | 3 | 0 |

`F3NV_Array` (`script_convert/static_scripts/fallout4/`) has two things
Caprica refuses:
1. `List`'s 20 `Var a = None` defaults ([known](fo4_pipeline.md#caprica-errors)).
   Dropping them and having `nvse_falloutnv._array_call` pass all 20 compiles
   in both (tried, then reverted: alone it gains nothing).
2. `KeyBefore`'s `(akA as String) < (akB as String)`, the StringMap key order
   xNVSE iterates in. FO4's compiler compiles `<` on strings; Caprica allows
   it only on Int and Float, and on `Var` neither compiler does. FO4 Papyrus
   has no string or array-sort function to order strings another way, and
   F4SE adds none.

Ways past 2, none built:
- **Patch Caprica** (MIT) to allow the relational operators on strings for
  `-g fallout4`, as FO4's compiler does, and offer it upstream. The bundled
  `external/caprica` release would become our build until upstream ships it.
- **Papyrus assembly**: Caprica assembles a hand-written `.pas` (tried: a
  `COMPARELT` on two strings assembles), so the comparison could live in a
  tiny `F3NV_StringOrder.pas`. Needs the static-script copy
  (`context_setup`, shared with the Skyrim converter), the build's staging
  and the compile driver to carry `.pas` files.
- **A native in F3NV.dll**: makes the array script need the DLL.

Also found: `caprica.SAME_ERRORS` counts Caprica's operator message as an
error FO4's compiler gives too. That holds for numbers misused on forms but
not for strings, so a converted script ordering strings would be recorded as
failing instead of falling back. None of the 32 built `compile_state.json`
files records that message today.

## <a id="lips"></a>7. Lips from loudness when LipGenerator can't (built 2026-11-11, not built in game)

A line with no `.lip` of its own still goes to LipGenerator when it is
installed. When it is missing or fails, `voice._convert_one` used to leave
a bare `.xwm` (sound, no mouth). It now packs the `.fuz` with a lip made
from the recording's loudness (`voice.loudness_lip`, `lip.from_loudness`):
ffmpeg decodes it mono at 16 kHz, each 1/30 s frame's RMS over the line's
95th percentile opens Aah to at most 0.8, frames under 15% stay shut, three
frames averaged; every other target and modifier is zero. Failed-job keys
carry `LIP_FALLBACK`, so lines an older build left lipless are tried once
more. Not looked at in game: how a loudness lip reads next to LipGenerator's.

## <a id="order"></a>Suggested order

1, 2 and 7 first: small, and each removes a whole tool. Then 3, which
removes one CK run. 4 is already planned for quality reasons. 5 is the
largest and most valuable; start with a spike that round-trips one of our
Elric-made NIFs' physics through `havok-formats`. 6 needs its spike. 8 waits
for the CK route.
