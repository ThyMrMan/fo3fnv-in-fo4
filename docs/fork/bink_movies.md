# Source-game movies (Bink 1) on Fallout 4

Status is in the [roadmap](ROADMAP.md#parked). On Fallout 4, the build ships
the source movies and converts `PlayBink` ([plan, as built](#plan)); the
Skyrim target still drops every movie call (a note-only row in
`script_convert/command_rows.py`).

## Contents

- [Formats: both play](#formats)
- [What FO3 and FNV play](#census)
- [How Fallout 4 plays a movie](#fo4-playback)
- [Plan, as built](#plan)
- [Play test](#play-test)

## <a id="formats"></a>Formats: both play

Every FO3/FNV movie is **Bink 1** (`BIKi`). Every Fallout 4 movie is
**Bink 2** (`.bk2`, `KB2g`). Fallout 4 still reads Bink 1:

- The `bink2w64.dll` that Fallout 4 ships checks for Bink 1 headers `BIKf`,
  `BIKg`, `BIKh`, `BIKi` beside Bink 2's `KB2f`, `KB2g`.
- Skyrim SE ships a Bink 1 movie, `Data\Video\BGS_Logo.bik` (`BIKi`), and
  plays it through its own `bink2w64.dll`. That copy also accepts `BIKk` and
  `KB2f` to `KB2m`.
- Fallout 4's copy stops at `KB2g`. A current Bink 2 encoder may write a
  later revision that this DLL refuses, so re-encoding to Bink 2 is both
  harder (RAD's licensed encoder; no free one exists) and riskier than
  shipping the Bink 1 file.

The file extension does not matter: the game opens `Data\Video\<name>`
(loose files only; vanilla keeps all 14 movies loose) and Bink reads the
header.

## <a id="census"></a>What FO3 and FNV play

From the plugins' scripts and the installs' `Data\Video` folders. No movie is
packed in a BSA in either game.

**New Vegas: one real movie.** `Data\Video` holds only `FNVIntro.bik`
(1280x720, 30 fps, 4:50, 353 MB, one 48 kHz stereo track, ID 0). No DLC
plugin calls `PlayBink`.

| Call | File shipped | Effect |
|---|---|---|
| VCG00 stage 0: `PlayBink "FNVIntro.bik" 1 1 0 1` | yes | **The opening cinematic** (Benny at the cemetery, the narration) |
| VCG00 stages 7, 23: `FNVLogo1.bik`, `FNVLogo2.bik` | no | none: demo-only stages |
| `VEndingBinksSCRIPT`: `B01.bik`, `B02.bik` | no | none: commented out |
| `VEndingBinksSCRIPT`: `VB01.bik` | no | none: the call is live, but its quest `VEndingBinks` is not start-game enabled and nothing else names it (only its own `StopQuest`) |
| `Fallout_default.ini` `sIntroMovie=Fallout INTRO Vsk.bik` | no | none: Fallout 3's setting, left over |

FNV's endings are slides with narration, not movies.

**Fallout 3: 35 movies, all used.** All are 1280x720 at 29.97 fps, one track
with ID 0 (`2 weeks later.bik` has no audio), 1.1 GB in total.

| Call | Files |
|---|---|
| Engine, on New Game: `sIntroMovie` in `Fallout_default.ini` | `Fallout INTRO Vsk.bik` (4:04) |
| CG01 to CG04 stage results, between childhood stages (`0 0 1 0`: no interrupt, audio on) | `1 year later.bik`, `3 years later.bik`, `6 years later.bik`, `9 years later.bik` |
| `EndingBinksScript` (Fallout3.esm), chosen by karma and the ending | `B01.bik` to `B26.bik` |
| Broken Steel's copy of the ending script, plus its wake-up | `B01.bik` to `B29.bik`, `2 weeks later.bik` |

So the FO4 target has to play 36 movies: the 35 Fallout 3 files plus
`FNVIntro.bik`.

## <a id="fo4-playback"></a>How Fallout 4 plays a movie

- **Papyrus:** `Game.PlayBink(asFileName, abInterruptible, abMuteAudio,
  abMuteMusic, abLetterbox, abIsNewGameBink)`, latent until the movie ends.
  Vanilla calls: MQ101's stage fragments (`Intro.bk2`, `abIsNewGameBink=true`)
  and `MQ00Script` (the four `Endgame_*.bk2`). The FO3/FNV arguments map
  across: interruptible, mute audio and mute music; FNV's fourth argument
  (letterbox) is `abLetterbox`.
- **The exe** names `GameIntro_V3_B.bk2` (the logo), `MainMenuLoop.bk2` and
  the seven S.P.E.C.I.A.L. shorts itself.
- **One audio track ID.** The exe opens a movie with `BINKSNDTRACK` and
  `BinkSetSoundTrack(1, &id)` (`0x141debb50`, called from `0x141ded1b7`), so
  exactly one track plays. The ID comes from the play request. Vanilla
  `.bk2` files carry five 48 kHz stereo tracks, IDs 1 to 5 (likely the five
  voiced languages; `GameIntro_V3_B.bk2` also has ID 0). Every FO3/FNV movie
  has only ID 0, so it plays silent. English asks for ID 1
  ([play test](#play-test)); other languages are untested.
- New Game: FO3's intro is started by the engine from `sIntroMovie`. Fallout
  4's exe still names `sIntroMovie` and `sIntroSequence`, but its own story
  intro plays from MQ101's Papyrus, so the converted new-game start gets a
  `Game.PlayBink` call the same way rather than relying on an INI setting.

## <a id="plan"></a>Plan, as built

Built 2026-10-12; status in the [roadmap](ROADMAP.md#parked).

1. **Movies** (`fo4_import/base/bink.py`, `write_movies`, called from the
   build's `_finish`): every `.bik` in the source plugin's Data folder's
   `Video` (found through `source_registry`) is written to the build's
   `Data\Video` under its own name. A movie with audio goes through `retrack`
   with its one track repeated as IDs 1 to 5 (no re-encode; the video is
   untouched); a movie without audio (`2 weeks later.bik`) is copied. ID 1
   is confirmed for English; IDs 2 to 5 are a guess at the other voiced
   languages (vanilla's five tracks) and cost the audio four more times,
   about 9 MB each on `FNVIntro.bik` (37 MB, 10%). Only the masterless
   plugin writes them (Broken Steel plays its movies from Fallout 3's
   folder). A movie is rewritten only when its timestamp or track IDs differ
   from the source's.
2. **Calls** (`script_convert/commands_falloutnv.py`, `play_bink`): on
   Fallout 4, `PlayBink "<movie>" [flags]` becomes
   `Game.PlayBink("<movie>", interruptible, muteAudio, muteMusic, letterbox)`;
   omitted flags take PlayBink's defaults (0, 1, 1, 1), which are also
   Fallout 4's. A call naming a movie the build does not ship
   (`CrossRefGraph.movies`, filled by `build_xref` from the same folder) is
   dropped with a `;NE:` note, because a missing file hangs the game on a
   black screen ([play test](#play-test)). For FNV that drops `FNVLogo1.bik`,
   `FNVLogo2.bik` and `VB01.bik`. Skyrim keeps its note-only row.
3. **Not built: FO3's intro.** The engine plays it from `sIntroMovie` on New
   Game, with no script call. It needs a `Game.PlayBink` at the converted
   new-game start, and the Fallout 4 build has no Fallout 3 path yet.

## <a id="play-test"></a>Play test

`py -3.14 -m fo4_import.spike.bink --out "C:\Modlists\fo3fnv-in-fo4\mods\FNV Bink Test"`
writes the test mod:

| File | Track IDs |
|---|---|
| `Video\FNVIntro.bik` | 0 (the source file, copied) |
| `Video\FNVIntro_T1.bik` | 1 (header relabeled; same size) |
| `Video\FNVIntro_T0to5.bik` | 0 to 5 (the one track repeated; 400 MB) |
| `FNVBinkTest.esp` | quest `FNVSpike_BinkTest`, start-game enabled, script `FNVSpike_BinkTest` |

Each console function plays one file; the script logs start, end and how
long the call blocked to `Logs\Script\User\FNVBinkTest.0.log`:

```
cqf FNVSpike_BinkTest Original
cqf FNVSpike_BinkTest Track1
cqf FNVSpike_BinkTest AllTracks
cqf FNVSpike_BinkTest Missing
```

Checked offline: in both rewritten files all 8,692 frames keep their video
bytes and keyframe flags, and every track's packet equals the source's
(`tests/test_fo4_bink.py` covers the rewrite on a synthetic file).

Questions the test answers:

| Function | Answers |
|---|---|
| `Original` | Does Bink 1 play (picture)? Is track 0 heard? |
| `Track1` | Is track 1 the one English plays? |
| `AllTracks` | Sound with every candidate ID present (the fallback if neither of the above is heard) |
| `Missing` | Does a missing file return at once or hang the script? |

**Played (2026-10-12, English install):**

| Function | Result |
|---|---|
| `Original` | Picture plays, **no sound**: Fallout 4 does not play track 0 |
| `Track1` | **Picture and sound.** English plays track ID 1 |
| `AllTracks` | Not needed |
| `Missing` | **Hangs:** a black screen that cannot be skipped or backed out of; the game has to be killed |

So a Bink 1 movie plays unconverted once its audio track is ID 1, and a
`Game.PlayBink` call must never name a file the conversion did not place.
