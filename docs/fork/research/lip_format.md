# FO3/FNV and Fallout 4 lip files: one format, convertible (research, 2026-11-06)

Status: format decoded and checked on real files; converter built into the
voice stage 2026-11-06 ([built](#built)), **not yet in a game build, not
played**. Status lives in [ROADMAP.md](../ROADMAP.md).

**Why.** The FO4 build runs the Creation Kit's `LipGenerator.exe` once per
voice line (about an hour per full voice run,
[voice cache](../fo4_pipeline.md#voice-cache)), and its output is not
deterministic. FO3 and FNV already ship a `.lip` for almost every line
(FNV `Fallout - Voices1.bsa`: 52,581 `.lip` for 52,896 `.ogg`). Fallout 34's
installer lists a `lipconv.py`, which suggested converting them
([prior art](../fo4_replacements.md#fallout34)).

## <a id="container"></a>The container (both games)

From the FNV decomp: `ReadAnimationFromStream` (`@fnv 0x004d5350`), the
zero-run reader `FUN_004d5880` (`0x004d5880`) and `ReadBufFromMemory`
(`0x004d5570`), in `references/fnv_decomp/src/fallout_shared/lipsynchanim.cpp`
and `src/staging/blk_004c0000_od.cpp`.

| Offset | Field |
|---|---|
| 0 | u32 version = 1 |
| 4 | u32 size: body length **+ 16** (every file of both games; the reader allocates `size + 16` and never needs it exact) |
| 8 | u32 flags: bit 0 = body compressed. FNV/FO3 write 1; FO4 writes 13 (bits 2 and 3 not decoded) |
| 12 | body, compressed when bit 0 is set |

**Compression:** a non-zero byte is itself; a `00` byte is followed by a u16
count of zero bytes (one run per `00`, at most 0xFFFF).

## <a id="body"></a>The body

| | FO3 / FNV (flags 1) | Fallout 4 (flags 13) |
|---|---|---|
| Header | u32 frames, i32 start offset (negative = lead-in frames) | u32 frames, i32 start offset, u32 targets = 43 |
| Per frame | 16 mouth shapes + 17 modifiers, f32 | 43 targets + 17 modifiers, f32 |
| Rate | 30 fps (`ApplyToAnimationData` steps 1/30 s) | same layout; frame counts match FNV's for the same line |

- **Mouth shapes 0–15, both games:** Aah, BigAah, BMP, ChJSh, DST, Eee, Eh,
  FV, I, K, N, Oh, OohQ, R, Th, W.
- **Modifiers 0–16, both games** (names in `Fallout4.exe` in this order):
  BlinkLeft, BlinkRight, BrowDownLeft, BrowDownRight, BrowInLeft,
  BrowInRight, BrowUpLeft, BrowUpRight, LookDown, LookLeft, LookRight,
  LookUp, SquintLeft, SquintRight, HeadPitch, HeadRoll, HeadYaw. FNV scales
  14–16 by three game settings on load.

**Checked:** the layout leaves 0 bytes over in 1,500 sampled FNV lips, 1,500
FO3 lips (`Fallout - Voices.bsa`) and every flags-13 lip sampled from the
five Fallout 4 voice archives.

## <a id="targets"></a>Fallout 4's 43 targets

- **Tracks 0–15 are FNV's 16 mouth shapes in FNV's order.** Paired over 106
  Doc Mitchell lines (11,485 frames: FNV's own lip against the
  LipGenerator lip our build wrote for the same recording, matched through
  `FalloutNV.formids.tsv`), FNV track *i* correlates best with FO4 track *i*
  for every *i* (0.37–0.67), with no other track above 0.10.
- **LipGenerator writes only tracks 0–15** and the same 11 modifiers FNV
  uses (803 built lips sampled). Tracks 16–42 stay zero. Vanilla Fallout 4
  lines do use tracks 16–42.
- `Fallout4.exe` also holds male and female phoneme tables (IY, IH, … SIL,
  SHORTSIL, FLAP: 43 each). They are not the order of the lip tracks.
- Other formats in vanilla: `TOM3` lips (about 2% of base-game lines, a
  24-byte header then frames × 53 f32, uncompressed), flags 9 and 8, and
  16-target lips in DLCRobot. Not needed: our build writes flags 13.

## <a id="conversion"></a>Conversion

FNV/FO3 lip → FO4 lip: same frames and offset, the 16 mouth shapes into
tracks 0–15, 27 zero tracks, the 17 modifiers, flags 13, size = body + 16.

- **Encoder checked:** decoding 602 of our built LipGenerator lips and
  re-encoding them gives 602 byte-identical files.
- **Speed:** 2.1 ms a line in plain single-process Python (3,000 lines in
  6.2 s), about 110 s for all of `Voices1.bsa`, against about an hour of
  LipGenerator.
- **Gain beyond speed:** Bethesda's own timing, blinks, brows and head moves
  for each line, the same every build, and no Creation Kit needed for voice.

## <a id="built"></a>As built (2026-11-06)

**Code:** `fo4_import/base/lip.py` (the conversion), `fo4_import/spike/voice.py`
(`own_lip`, `relip`, `relip_once`), `asset_convert/sources/bsa_extract.py`
(lips extracted).

- **Exports keep `.lip` files.** BSA extraction and mod ingest used to drop
  them; now both keep them, so a voice mod's `.lip` replaces the vanilla one
  together with its `.ogg`. An archive extracted before this gets only its
  `.lip` files added on the next extraction (a `lips` count in the
  manifest marks it done). Added 2026-11-06: FNV 52,581, Dead Money 2,558,
  Honest Hearts 2,263, Old World Blues 2,177, Lonesome Road 1,123, FO3
  44,961 (`Voices` and `MenuVoices`), Anchorage 2,139. The inherited Skyrim
  voice step ignores them (its file pattern takes audio only).
- **Voice stage.** A line whose recording has a `.lip` beside it gets that
  lip converted and packed with the xWMAEncode audio; LipGenerator only runs
  for lines without one. The failed-job record keys on the lip's hash too,
  so lines LipGenerator failed on are tried again.
- **Existing builds.** `relip_once` gives every built `.fuz` its own lip once
  per staging root (`VoiceLips/<plugin>.txt` holds the scheme), keeping the
  audio; files brought back from the voice cache are relipped as they
  return. Conversion is 0.4 ms a line warm; the first pass over a whole-map
  build (about 158,000 files) is mostly disk reads, minutes once.
- **Checked:** `tests/test_fo4_lip.py`; six Doc Mitchell lines through the
  real stage (ffmpeg, xWMAEncode): each `.fuz` holds the line's own lip and
  `RIFF…XWMA` audio, and a LipGenerator lip is replaced once, not again.

**Open:**
- **In game:** the timing is FNV's, for FNV's recording. Our `.xwm` must
  start where the `.ogg` starts; check one line plays in sync.
- **Lines with no `.lip`:** 315 lines in `Voices1.bsa` have none; they keep
  LipGenerator.
- FO4 flag bits 2 and 3 are copied from LipGenerator and not decoded.
