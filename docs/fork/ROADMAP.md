# Fork roadmap

The one place status lives. Plan files in this folder hold design only; when a
piece is built, played or dropped, the change is made here and nowhere else.

**Focus:** standalone play of each converted world, stability, performance.
Staying equivalent to upstream is not a goal; staying mergeable with it is, so
the fork's docs live in `docs/fork/` and upstream's plans stay in
`docs/plans/`, unedited.

| File | Holds |
|---|---|
| [character.md](character.md) | Attributes, skills, leveling, perks, standings and the stats menu, for all four games |
| [standalone_play.md](standalone_play.md) | Setup, MO2 integration, per-world profiles, launcher, world picker |
| [performance.md](performance.md) | Rules for new systems, Papyrus runtime cost, FO3/FNV occlusion |
| [kill_cams.md](kill_cams.md) | Kill cams and killmoves on converted weapons, per game |
| [bink_movies.md](bink_movies.md) | Source-game Bink 1 movies (parked) |
| [research/](research/) | Findings and notes that are not plans: [character findings](research/character_findings.md), [graphics options](research/graphics_options.md), [Fallout 4 as the target](research/fo4_target.md) |
| [done/](done/) | Plans that are built, kept as their design record: [preflight audits](done/preflight_audits.md) |
| [fo4_spikes.md](fo4_spikes.md) | **This repo's current work:** the spikes that decide whether FO3/FNV on Fallout 4 is buildable |

## <a id="fo4"></a>Fallout 4 spikes

| Piece | Status |
|---|---|
| [Step 0: groundwork](fo4_spikes.md#step-0) | **Built 2026-10-05:** FO4 writer + tests, `Fallout4.esm` dump, script sources, compiler checked. Not yet loaded in FO4Edit or the CK |
| [Spike 1: dialogue](fo4_spikes.md#spike-1) | **1a text-only played 2026-10-05:** greeting opens the menu with all of Doc's options; added topics, Say Once variants, skill checks, sub-menu returns and Goodbye confirmed ([design](fo4_spikes.md#spike-1-design)). **1b played 2026-10-05, passed** ([1b](fo4_spikes.md#spike-1b)): three speakers share one forced-alias scene, each seeing only their own options; `[Leave]` replaces Tab, walking away ends the talk, Random piles vary. The gate is passed: 1b needs no hand work. **Voice played 2026-10-05** ([voice](fo4_spikes.md#spike-1-voice)): Doc's FNV lines as `.fuz` with CK-generated lips. Only the player opens a talk (`GetPlayerActivated`, played). Open: the player's "Hi" |
| [Spike 3: one script](fo4_spikes.md#spike-3) | **Measured 2026-10-05** ([results](fo4_spikes.md#spike-3-measured)): of 199 sampled converted FNV scripts, 81 compile unchanged with FO4's compiler, 54 fail only through our helper scripts, 64 on their own code (update loop, actor values, `SendModEvent` lead). 20 of 554 command rows change; VMAD changes are small. **Target switch built** ([target](fo4_spikes.md#spike-3-target)): Doc Mitchell's script emits as FO4 Papyrus and compiles with FO4's compiler; Skyrim output unchanged. **Corpus gate built** ([gate](fo4_spikes.md#spike-3-gate)): all FNV scripts converted for FO4; **98.5% compile** (17,425 of 17,698) after `RewardXP` → native `RewardPlayerXP` and the character menus → a custom event. **All 16 FO4 helpers compile** ([helpers](fo4_spikes.md#spike-3-helpers)): 3 left out as unneeded, the converter's FO4 rules applied to the shared source, 8 function overrides with a drift guard. **99.9% compile** (17,672 of 17,695) after `OnTrigger`, `SetRestrained`, fast travel, sleep and menu events and the singles ([singles](fo4_spikes.md#spike-3-singles)); a duplicate-name guard and per-game prefixes ([names](fo4_spikes.md#spike-3-names)). The doctors' stage scripts compile since a quest stage's bare call acts on the player ([VDoctors](fo4_spikes.md#spike-3-vdoctors)); **17,676 after the singles** ([singles](fo4_spikes.md#spike-3-else-text)): text after `else` is dropped as FO3/FNV's compiler drops it (18 lines in 13 scripts), a no-value call's `set` stores the empty value. Left: 19, all in scripts nothing attaches. **FO4 VMAD built** ([vmad](fo4_spikes.md#spike-3-vmad)): matches vanilla byte for byte (520 of 521 INFOs, all sampled quests). **End to end played 2026-10-05** ([end to end](fo4_spikes.md#spike-3-end-to-end)): Doc's converted script on his stand-in binds; `setav FNV_Variable01 1` turns the player's controls off and back on. FO4 has no `Variable01`–`10`, so the plugin carries its own. The 8-second wait measured at 8.06 s ([timing](fo4_spikes.md#spike-3-timing)). **Dialogue fragments played 2026-10-05** ([fragments](fo4_spikes.md#spike-3-fragments)): 29 lines carry their converted FNV scripts; paid treatment, stimpaks, water and barter work. The stand-ins' own FO4 greetings and scenes still compete with ours (stand-in only). **Shared helper plugin played 2026-10-05** ([helper plugin](fo4_spikes.md#spike-3-helper-plugin)): `TES4Helpers.esl` holds Variable01-10, the FO3/FNV skills, the helper quests and `TES4ControlsDisabled`; `AV()` reads it and FO3/FNV skills keep their names on FO4; corpus still 17,672 of 17,695. **VDoctors played 2026-10-05** ([VDoctors](fo4_spikes.md#spike-3-vdoctors)): the doctors quest with its converted stage script, treatment heals and the radiation line clears rads (stages 10 and 30 done). The compile gate now compiles only changed scripts and their users |
| [Spike 2: one interior cell](fo4_spikes.md#spike-2) | Waits on spike 1 |

## <a id="phases"></a>Phases

1. **Stable ground.** Play everything written but not yet played (below), run
   the preflight audits after every build, and land the two safest Papyrus
   cost fixes.
2. **The stats sheet.** Character pieces T and G1 (data, then a sheet that
   writes nothing), then checks S1 to S3, then F.
3. **Setup without hand work.** Standalone play pieces B, C and D, then H.
4. **Systems with gameplay weight.** Item condition (H), level-up and chargen
   in the sheet (G2), and skill effects built with their systems (J).

## <a id="character"></a>Character systems

Carried over from the character plan's own status notes of 2026-09-28.

| Piece | State |
|---|---|
| A: character data | Built for Oblivion and Fallout; Morrowind not started |
| I: runtime leveling gate | Built; played with Oblivion |
| D: skill-use leveling | Built; played with Oblivion 2026-09-27 |
| E: Fallout XP leveling | Built; played in New Vegas 2026-09-27 |
| E: perks and traits, level-up perk and trait menus | Written, **not played** |
| E: reputation and karma for scripts and conditions | Written, **not played** |
| E: karma and infamy from kills and thefts | Written, **not played** |
| E: Fallout 3 rules plugin | Builds (2026-09-28), **not played** |
| E: Fallout 3 speech challenges | Written, **not played** |
| G: Fallout chargen as message boxes (S.P.E.C.I.A.L., tag skills) | Written |
| B, C: shared stat store and NPC stat natives | Not started |
| T: skill table columns | Not started |
| G1: read-only stats sheet | Not started |
| F: own-store skills, active skill | Not started; waits on S1 to S3 |
| G2, H, J | Not started |

## <a id="stability"></a>Stability

- **Play-test backlog:** every "not played" row above.
- **Preflight audits:** built (`python -m tools.validate.preflight`, `--audit
  logs` after a play-test). Open gaps:
  - audit 1 doesn't check stage-item conditions or Say Once lines;
  - audit 2 doesn't evaluate condition-filled aliases, and marks required
    ones for review;
  - audit 4 uses the quest audit's dialogue models rather than the two
    emulators;
  - audit 6 doesn't check that quest actors have a package bringing them to
    their scenes.
- **[Kill cams and killmoves](kill_cams.md):** not started. Killmoves misfire
  on converted weapons (FO3/FNV's baton plays a sword killmove). Options
  recorded; first step is the census of the vanilla killmove conditions.

## <a id="performance"></a>Performance

| Item | State |
|---|---|
| [Papyrus cost](performance.md#papyrus) 2: GameMode loops | Not started; first, safest |
| Papyrus cost 1: quest poll interval | Not started; after the Creation Kit check |
| Papyrus cost 3: dialogue state in actor values | Not started |
| Papyrus cost 4: patrol arrival checks | Not started; lowest |
| [FO3/FNV occlusion](performance.md#occlusion) | Not started; cost in play unmeasured |

## <a id="standalone-play"></a>Standalone play

| Item | State |
|---|---|
| Pieces A to H | Not started. MO2 profiles `FNV`, `FO3` and `Oblivion` exist, made by hand |
| World picker on the main menu | Candidate; needs DLL work |
| Upstream PR #65 | Open, with the plan's earlier copy; the fork's copy has moved on |

## <a id="parked"></a>Parked

| Item | Why |
|---|---|
| [Bink movies](bink_movies.md) | Nothing plays; low value against the rest |
| OBSE command coverage | Until the standalone Oblivion work is done; probe in `probes\obse_coverage` |
| Nehrim | Deprioritized for the four main games |
| [Graphics and OpenMW research](research/graphics_options.md) | Notes to revisit when the project is more mature |

## <a id="upstream"></a>Upstream plans, not followed

These stay in `docs/plans/` as upstream wrote them.

| Plan | Why not |
|---|---|
| [character_sheet.md](../plans/character_sheet.md) | Conflicts with [character.md](character.md#sources) on leveling, layout and governing stats; its menu plumbing, stat store and Statistics tab are reused |
| [horse_rideability.md](../plans/horse_rideability.md) | Outside the focus |
| [in_app_update.md](../plans/in_app_update.md) | Outside the focus |
| [morrowind_object_scripts.md](../plans/morrowind_object_scripts.md) | Built and confirmed upstream; nothing left to follow |
| [navmesh_lattice.md](../plans/navmesh_lattice.md) | Upstream's experiment, opt-in |
| [vanilla_creature_swap.md](../plans/vanilla_creature_swap.md), [vanilla_item_swap.md](../plans/vanilla_item_swap.md) | Optional add-ons, outside the focus |

## <a id="elsewhere"></a>Notes kept elsewhere

- The Claude Doc "Oblivion Profile Research" predates this folder. Anything in
  it that is still true belongs here; after that, treat it as frozen.
- Agent memory is per machine and is never the only copy of a finding.
