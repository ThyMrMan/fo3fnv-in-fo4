# FNV radio on Fallout 4 (plan, 2026-10-21)

**Code:** not built.

FNV's radio stations (Radio New Vegas, Mojave Music Radio, Black
Mountain, the casino and Tops lounges) as Fallout 4 radio: stations in the
Pip-Boy's radio list, and FNV's placed radios (the Goodsprings store's,
which Chet asks the player to fix) playing them.

## <a id="fnv"></a>How FNV does it (measured in the FalloutNV.esm export)

- **A station is a talking activator** (TACT) flagged as a radio station,
  placed once: the transmitter (`vCountryRadio` "Mojave Music Radio",
  `vCasinoUltraLuxeRadio` ...; 87 TACT in all, most of them not radios). Its
  voice type (VNAM) voices the station's spoken lines.
- **What it plays is dialogue.** The station's quest (`RadioNewVegas`,
  `vCountryRadioQuest` ...) holds radio-type lines (INFO dialog type 7) on
  the shared radio topic; the engine plays a line whose conditions pass on
  the transmitter. 505 radio lines in FNV: Radio New Vegas 216 (Mr. New
  Vegas's news, which follows quest progress, and songs), Black Mountain
  186, the lounges 6 to 33 each.
- **A song is a line naming it** (`{Song 15 Blue Moon}`) whose response
  plays a sound record: the song file (`sound/songs/radionv`, 48 songs,
  38 MB of .ogg). The line's own recording is a short stub (12 KB). The
  export drops the response sound, so it is read from FalloutNV.esm.
  A song line's result script keeps a short play history in the station
  quest's variables (`iLastSong1..3`), which its conditions read so no song
  repeats at once.
- **A placed radio is an activator** whose radio-station field (RNAM, also
  dropped by the export) names the station; activating it toggles the
  station on. `GoodspringsRadio` is broken until the player fixes it
  (`GoodspringsRadioScript`, Chet's `VFreeformGoodsprings`).

## <a id="fo4"></a>How Fallout 4 does it (Fallout4.esm)

- **A transmitter** is a placed activator (`RadioTransmitter`,
  `RadioTransmitMarker`) whose reference carries XRDO: the frequency,
  the range, and a flag (`RadioInstitutePA`, `RadioTransmitMarker17`). The
  Pip-Boy lists the transmitters in range.
- **A receiver** is an activator with the radio flag (FNAM 0x10) and RADR
  (its sound model, frequency, volume, flags): `RadioDiamondCityReceiverOff`,
  `RadioSilverShroudReceiver`.
- **What plays** is dialogue too: a station quest whose scenes speak lines
  through the transmitter (Diamond City Radio). How vanilla picks the next
  song (scene phases or a script) is to be read in step 2.

## <a id="transmitters"></a>Step 1: transmitters (built 2026-10-21, played 2026-10-21)

`spike/radio.py`. FNV flags a station TACT Radio Station (0x20000), and
Non-Pipboy (0x10000000) when only its placed radios play it; Continuous
Broadcast is 0x40000000 (xEdit wbDefinitionsFNV). Its references' XRDO
(read from FalloutNV.esm, 0.3 s) is range radius, broadcast type (Radius,
Everywhere, Worldspace and Linked Interiors, Linked Interiors, Current
Cell), static percent and a position reference. FO4's XRDO is frequency,
min and max weak distance, and Ignores Distance Checks.

FNV's Pip-Boy stations and where they stand: Radio New Vegas and Mojave
Music Radio (`Vault11a`, an interior; Everywhere), NCR Emergency Radio
(Hoover Dam, Everywhere), Camp Guardian Radio (an interior; 5,000 around an
outside position reference, 50% static), Black Mountain Radio
(WastelandNV's persistent cell; 50,000, 5% static), the Chinese Radio
Beacon (another worldspace; 3,000). The other 13 placed stations are
Non-Pipboy (casino and Tops lounges, Hanlon's broadcast, ED-E's, the
Goodsprings store's): step 3.

- **Base:** a copy of Fallout4.esm's `RadioTransmitter` (no model) named
  for the station, on FNV's FormID. Vanilla's stations share
  `RadioTransmitter` itself and take their Pip-Boy name some other way
  (likely their quest's alias, step 2); a base per station shows FNV's
  name without one.
- **Placement:** each Pip-Boy station reference in the built worldspace,
  or in an interior (the first worldspace built takes these), goes into
  the worldspace's persistent cell, persistent, at its position reference
  when it has one.
- **XRDO:** frequency a free Pip-Boy slot, one per station in FormID
  order (`FREQUENCIES`). The Pip-Boy tunes only from
  `fPipboyRadioMinFrequency` 80 to `fPipboyRadioMaxFrequency` 110 (the
  exe's defaults; Fallout4.esm sets neither), and snaps within
  `fRadioStationFuzzyRange` 0.5. The slots are 80, 80.5, 81, 84, 84.5, 85,
  90, 93, 96, 101, 108.5, 109, 109.5 and 110, each at least 1.0 from every
  transmitter in Fallout4.esm and the DLCs (82-107.3; DLCCoast 83, 94,
  103.5; DLCRobot 103; DLCworkshop03 92; DLCNukaWorld 97, 106.5). The first
  build used FormID low 24 bits / 1000 (940-1,490). Those stations never
  listed, and their scenes cycled every line in about 20 ms, around 120
  line scripts a second, until the Papyrus VM stalled (lag spikes, a 30 s
  door, no Pip-Boy, slow saves). The base carries `TES4_RadioStation`
  naming the frequency, which Papyrus cannot read from a transmitter
  (`GetRadioFrequency` is for receivers). Everywhere (or no radius) Ignores
  Distance Checks, as vanilla's global stations; a radius weak from
  where FNV's static begins (radius x (1 - static %)) out to the radius.
- Every other talking activator is still left out (counted).

## <a id="programming"></a>Step 2: programming (researched 2026-10-21)

**FNV.** A station's lines are its quest's: the quest's one quest-level
condition is GetIsID on its talking activator (`RadioNewVegas` on
`RadioNewVegasTA` 0014DF02, `vCountryRadioQuest` on `vCountryRadio`
0016B46F). Lines are radio type (dialog type 7). A program is a topic
graph entered at the shared `RadioHello` and chained by Choices:
- Radio New Vegas, 216 lines: `RadioHello` (15) choosing `RNVNewsIntro`,
  `RNVNewsStory`/`Story2`/`Story3` (118), `RNVNewsTransition`,
  `RNVNewsPost`, `RNVMusicIntroGeneric`/`Specific`, `RNVMusic` (20 songs),
  `RNVDamStory`/`Outro`. Conditions: quest variables (242), globals (44),
  GetDead (16), objectives (11), quest completed, HasPerk, stages.
- Black Mountain, 186: `RadioHello` choosing 13 `RadioBMSegment` topics
  and `RadioBMMusic`; quest variables and GetDead.
- Mojave Music Radio (15), the lounges (6-8), Camp Guardian (8), NCR
  Emergency (33): `RadioHello` only, songs and short loops.
- A song line (`{Song 15 Blue Moon}`) plays its response sound (TRDT
  Sound, a SOUN naming `sound/songs/radionv/*.ogg`); its own recording is
  a 12 KB stub. Song lines keep play history in quest variables
  (`iLastSong1..3`) their conditions read.
- Flags: most lines Random (0x02); many Run Immediately (0x08).

**FO4 (Diamond City Radio, `RadioDiamondCity` 0001FA58).** The quest's
alias `Host` (forced to the station's `RadioTransmitter` reference, flag
0x4000, display name ALDN: the Pip-Boy's name for it) is the speaker.
Scenes play everything: Radio actions (type 6) on alias Host saying a
topic, or playing a sound (HTID, an SNDR): `DiamondCityRadioMusicScene`
(repeating) says a song-intro topic (45 lines; each line's fragment sets
`CurrentSong` and the play history `LastSong01..10`, which the lines'
conditions read), then one phase per song gated on `CurrentSong` plays
the song's sound (`sound/fx/mus/radio/diamondcity/*.xwm`). Travis's lines
name him as speaker (INFO ANAM, NPC 00002F26) for the voice type.

**Design (proposed).** Per station: a quest with alias Host forced to the
transmitter (display name the station's); a speaker NPC copying the
holotape speaker with the station's voice type (as holotapes do); the
program as a repeating scene of Radio actions on Host, one phase per
topic of FNV's graph in the order the Choices give from `RadioHello`, each
phase saying its topic (FNV's conditions pick the line, the topic skipped
when none passes); a song line's recording is the song itself (the SOUN's
file, converted like the silent lines, no lip file). Open: FNV's Choices
on radio lines are not the player's; whether the engine follows the first
passing choice or picks one at random decides between that fixed order
and a script choosing the next topic.

**Built (2026-10-21, not yet played).** `Radio.program`, called as each
build quest is written:
- **Which quests.** Quest scope now also takes a quest whose own
  conditions name a placed base (a station quest's GetIsID on its
  transmitter; FNV adds a quest's conditions to every line): in the
  region the five stations' quests, `VFreeformBlackMountain` (Black
  Mountain's starts it) and the Goodsprings store's `vGSRadioQuest`
  (step 3). 69 to 76 quests; no FormID moved.
- **Host.** Alias 2000 `Host`, forced to the station's transmitter
  reference; a line's GetIsID on its station maps to the transmitter's
  base (`Radio.form_map`). It has Uses Stored Text (0x4000) and a display
  name (ALDN), a message naming the station, as `RadioDiamondCity`'s Host
  (`RadioDisplayDiamondCity` 000FF981). The first play-test built neither:
  the Pip-Boy listed no station, and the programs' lines showed as plain
  subtitles. A station's alias needs Uses Stored Text before the Pip-Boy
  lists it ([Nexus thread](https://forums.nexusmods.com/topic/4786725-phase-limit-for-radio-quest)).
- **Disabled stations.** FNV places Radio New Vegas, NCR Emergency Radio
  and Black Mountain Radio initially disabled. Scripts enable them:
  `VCG01RemoveDocCarebear` enables Radio New Vegas when the player leaves
  Doc Mitchell's. The references keep the flag, so a save made past that
  point before this build has Radio New Vegas off until
  `RNVTARef.Enable()` runs again.
- **Speakers.** A line is said by a copy of the holotape speaker on the FNV
  voice type whose recordings folder holds it (`recorded_voices`), else
  the station's own (Black Mountain's has none: Tabitha's lines are under
  `CreatureUniqueTabitha`); 38 lines recorded nowhere are left out.
- **Topics and scene (removed).** The first design was one FO4 topic per
  FNV radio topic, ordered from RadioHello along the Choices. Each station
  had one repeating scene (`FNV_<quest>Program`) with a Radio action per
  topic, and each song line's recording was its song.
- **Why it was removed.** In play-tests 3 and 4 every station's lines
  ended in under 0.1 s (97% of 14,000 lines on a new save). The scenes
  cycled about 55 lines a second and buried the Papyrus VM: a lag spike as
  Doc hands back control, a 30 s door, no Pip-Boy, slow saves. Moving the
  frequencies into the Pip-Boy band did not stop it, and the cause is not
  found. Programs are now built only on vanilla's model
  ([playlist](#playlist)); a station with spoken lines is left out,
  counted.

<a id="playlist"></a>**Playlist: a songs-only station on vanilla's model
(built 2026-10-21, played 2026-10-21: Mojave Music Radio lists in the
Pip-Boy and plays, with no lag).** A station whose radio lines all play
a song (Mojave Music Radio's 15) is built like Diamond City Radio's music
scene (`DiamondCityRadioMusicScene`):
- **Pick topic.** FNV's lines become one topic, with their conditions (no
  song in `iLastSong1..3`) and result scripts. Each keeps its own short
  recording and carries `TES4_RadioSong`, which sets the station quest's
  `TES4_RadioPlaylist.CurrentSong` to its song as it begins (attached
  as Say Once's helper is).
- **Song phases.** After the pick phase, one phase per song, gated on
  `GetVMQuestVariable ::CurrentSong_var` equal to its number. Each plays
  the song's sound record through a Radio action's sound (HTID), as
  vanilla's songs do. Each sound record copies
  `MUSRadioDiamondBillieHolidayCrazyHeCallsMe` (category, Pip-Boy
  radio output model) and plays FNV's song file, converted to .xwm under
  `Sound\FX\FNV\songs\radionv` (`Sounds.song`). FNV names
  `songs\radionv\mus_*.mp3` and ships `mus_*_mono.ogg`, found as `.ogg`,
  then `_mono.ogg` (`song_file`).
- **Running.** The scene (flags 0x104, `RadioSilverShroudQuest_Music`'s
  without begin on quest start) is started by `TES4_RadioPlaylist` as
  its quest starts. Every 5 s it is restarted if it stopped, as vanilla's
  `RadioFailsafeScript` does. A fault in a song therefore costs one pass
  per 5 s, not a spin.

<a id="heard"></a>**Messages only when heard (built 2026-10-21, not yet
played).** FNV plays a station's lines, and runs their result scripts,
only while the player listens. FO4's station scenes say every line
whether anyone is tuned in. The second play-test, on a new game in Doc
Mitchell's greeting, showed Camp Guardian's lines over and over as
top-left HUD notifications: each line's FNV script calls `ShowMessage`
(`TIF__0014ADA5` shows `NVCGHalfordRadio1`). Vanilla FO4 radio has no
subtitles. On FO4, each message a radio line (dialog type 7) shows is
guarded by `TES4_Radio.Heard(akSpeakerRef)`
(`script_convert/radio_lines.py`). Its other statements run, as FO4's
stations do, so a playlist's song history keeps up. Heard checks that the
radio is on, the player is in range, and the player is tuned to the
transmitter's frequency, which comes from the `TES4_RadioStation` script
on the transmitter base.

## <a id="steps"></a>Steps

1. **Transmitters.** Each FNV station's placed TACT becomes an FO4
   transmitter at the same place, one frequency per station, its range
   from FNV's XRDO. Played: the stations show in the Pip-Boy's radio list
   where FNV's reach.
2. **Programming.** A station quest's radio lines play on its transmitter:
   the lines through the existing dialogue converter, each song's sound
   record read from FalloutNV.esm and converted as that line's recording
   (as voice files are), the selection the way vanilla's stations pick
   theirs, keeping FNV's conditions (news that follows the quests, no song
   twice in a row). Played: Radio New Vegas and Mojave Music Radio play in
   the Pip-Boy.
3. **Placed radios.** An FNV radio activator naming a station becomes an
   FO4 receiver on that station's frequency; its script carries over, so
   the Goodsprings store radio plays once Chet's repair is done. Played:
   fix it, turn it on.

**Size:** M. Open to settle in step 1: FO4's XRDO and RADR fields (xEdit),
and the frequencies (FNV has none; one per station, clear of FO4's own).
