# Idles and NPC animation: a second look

**Code today:** `fo4_import/spike/idles.py` (IDLE records), `idle_markers.py`
(placed markers), `packages.py` (packages), `say_topics.py` (line idles and
their helper scripts), `havok/human_clip.py` (clips),
`script_convert/command_rows_fallout4.py` (`PlayIdle`, `PickIdle`).
Design and play history: [fo4_idles.md](fo4_idles.md). Status lives in
[ROADMAP.md](ROADMAP.md#fo4-next).

Written 2026-11-19 after the user's FO3 Vault 101 play test found idles off
in general (the Overseer kept his interrogation idle after Amata left;
students sit oddly). Those two bugs have their own sessions; this is the
wider review. Every count below was measured this session from
`export/Fallout3.esm`, `export/FalloutNV.esm`, the source plugins,
`references/Fallout4.esm` and `Fallout4 - Animations.ba2`. Nothing here has
been built or played.

## <a id="summary"></a>In short

FO3 and FNV start an idle from five authored places. The converter carries
three of them into FO4 dynamic idles: a line's speaker and listener idle, a
script's `PlayIdle`, and package event idles. The last is uncommitted work
in the main checkout, dated 2026-11-16, which this review first missed
([step 2](#plan)). It drops the fourth (package idle lists) and guesses the
fifth (idle markers, matched to a vanilla marker by the clip's file name). FO4's records have all five places, with the same
layout. Its behavior graph also already does the switching and releasing
that FO3's engine did, if a held idle uses the looping event. Recent fixes
(still uncommitted in the main checkout) add Papyrus helpers on lines to
release and switch held idles. They work around the event choice and the
dropped idle lists, not the engine.

**The better approach:** copy each authored idle field into FO4's matching
field. Then choose the graph event by how long FO3/FNV holds the idle, so
FO4's own transitions end it the way FO3's engine did.

## <a id="census"></a>Where FO3 and FNV start idles

| Source | Fallout3.esm | FalloutNV.esm | What the converter does |
|---|---|---|---|
| IDLE records | 1,247 (675 human clips, 269 creature, 303 group nodes) | 1,597 (807, 403, 385; 2 other) | Converts the ones a line or script uses |
| How long a clip holds | once 715, counted loop 155, forever 74 | 957, 172, 83 | Forever: `dyn_ActivationLoop`; counted: baked into one long clip (uncommitted) |
| Line speaker idles (INFO `SNAM`) | 715 uses, 148 idles (137 human) | 333 uses, 115 idles (97 human) | Converted; seated and creature clips left out |
| Line listener idles (`LNAM`) | 61 uses, 15 idles | 1, 1 | Converted the same way |
| Package event idles (OnBegin/OnEnd/OnChange `INAM`) | 76 in 55 packages, 52 idles | 87 in 60 packages, 54 idles | Converted (`packages.with_event_idles`, uncommitted in the main checkout); the 2026-11-19 Vault 101 build has 50 |
| **Package idle lists** (`IDLF`/`IDLC`/`IDLT`/`IDLA`) | 126 packages | 242 packages | Written into FO4's PACK idle list since [step 3](#plan), standing idles only |
| Idle markers (IDLM) | 122 markers, 1,417 placed (103 markers placed) | 211, 1,424 (98) | A vanilla marker chosen by the clip's file-name prefix (`idle_markers.PLAYS`); 168 FO3 and 197 FNV placed refs get an empty marker |
| Script `PlayIdle` | 18 (outside comments) | 145 | `Actor.PlayIdle(<converted IDLE>)` |
| Script `PickIdle` | 0 | 0 | Row sends `IdleForceDefaultState` ([below](#graph)) |
| `PlayGroup` | 191 | 312 | Almost all on activators (doors, lights); not an actor idle |
| Ambient tree `GeneralIdles` | 28 nodes | 31 nodes | Built under `ActionIdle` (built, not played) |
| Tree `FurnitureIdles` | 309 nodes; 161 sitting and 40 sleeping leaves | 394; 210 and 48 | Not built (seated clips crashed in October) |
| Trees left to FO4's own graphs | `DialogueIdles` 160, `HitReactionIdles` 34, `VATSMeleeAttacks` 44 | 160, 60, 44 | Left out on purpose |

Markers list 356 human and 56 creature idles in FO3, and 626 and 70 in FNV.
Most list two or more (FO3 89 of 122).

### <a id="vault101"></a>In Vault 101 alone

- **The birth (CG00)** plays through package event idles: 24 packages
  (Player, Mom, Dad and Dr. Li, sections 0-5) with 44 OnBegin/OnChange
  idles, every one looping forever, each section's OnChange starting the
  next section's clip. All 44 are in the 2026-11-19 build.
- **Baby Steps (CG01):** `CG01DadCloseGate`'s OnBegin plays
  `LoosettnpcNTRLHandsDownTalkA`. Its own script comment explains why:
  "On begin idle required to break out of looping dialogue idle". That is
  FO3's authored release for Dad's `LooseCrouchTalkToBaby`. It is in the
  build, alongside the uncommitted `F3NV_LoopIdle` helper, which ends the
  loop on any package change. Both were added on 2026-11-16, so which one
  released Dad in play is not known.
- **The escape (CG04):** `CG04PlayerSection0`/`CG04AmataSection0` OnBegin
  (waking up) and `CG04StanleyCloseDoor` OnEnd are in the build.
- **Package idle lists, 52 packages:**
  - The G.O.A.T. students: `CG03ButchTakeTest`, `Wally`, `SusieMack`,
    `Paul`, `Freddie`, `Amata` and `ChristineKendall`. Each lists
    `LooseSitTakingTestA`/`B` (and `LooseSitCheatingOnTest` for Butch and
    Susie), seated clips that loop 20 times. These are Find packages
    (type 0).
  - `CG04GloriaMackCry` and `CrySilent` list `LooseSitTableChairSobbing`
    (10-20 loops).
  - `CG04OverseerWait` and `CG04OverseerCallForGuards` list
    `LooseHandsOnHip`.
  - Also the CG02 clapping, `CG03DadHoldPosition` (`DoctorEyeExamineA`),
    MQ01's checkpoint talkers, and one per CG00 section.

The classroom and Overseer sessions have these lists in the shared notes.

## <a id="graph"></a>What FO4's graph does with a dynamic idle

Read from the transitions of the 44 behavior files under
`Actors\Character\Behaviors` (scratch script, packfile reader). The
standing human state machine `MTRoot_SM` (`MTBehavior.hkx`):

| Event | Transition | Flags | Meaning |
|---|---|---|---|
| `dyn_Activation` | any state → `DynamicAnimation` | 0x800 | Local wildcard **without** self-transition (0x200): a one-shot idle that is playing ignores the next one-shot |
| `dyn_ActivationLoop` | any state → `DynamicLoopAnimation` | 0xA00 | Self-transition allowed: a loop can replace a loop |
| `IdleStop` | any state → `MT_State` | 0x800 | Ends either kind |

`WeaponBehavior.hkx` and `MeleeBehavior.hkx` have the same three
wildcards, but their loop has no self-transition (0x800).
`FurnitureBehavior.hkx` has the same `dyn_Activation`/`dyn_ActivationLoop`
wildcards, and `IdleStop` leaves only its loop state.
`FurnitureNoMirrorBehavior.hkx` has no loop event. `DialogueBehavior.hkx`'s
`dyn_talkGeneric` does self-transition (0xA00).

What follows from it:

- **Why the idle switch needed a helper.** A counted loop baked into one
  83.5 s `dyn_Activation` clip (Dad's Bible verse) blocks every later
  one-shot, so `LooseCrouchTalkB` never started. A clip on
  `dyn_ActivationLoop` would have been left by the graph itself: the
  one-shot goes to a different state, which the wildcard allows.
- **`IdleStop` is the release.** Vanilla's IDLE `IdleStop` (`000E9855`,
  root graph, event `IdleStop`, loose) is the record form;
  `ActionIdleStop` is what the uncommitted helpers play.
- **`PickIdle` does nothing.** Its row sends
  `PlayAnimation("IdleForceDefaultState")`, a Skyrim event that none of the
  44 FO4 human graphs declare. FO3 and FNV themselves never call it (0
  uses), but mods may. The FO4 event is `IdleStop`.
- **Loop seconds.** 3,023 of vanilla's 3,025 IDLEs write looping seconds
  0/0, `dyn_ActivationLoop` ones included. The other two are creature
  warnings (3-6 s), and none writes 255/255. We write 255/255 for "forever".
  Vanilla's forever is 0/0 on the loop event, looping until `IdleStop`.
  Whether 255/255 changes anything is untested. Whether the engine ends a
  loop by itself after N seconds is also untested on a human (the counted
  route below needs it).

## <a id="vanilla"></a>How vanilla FO4 does the same jobs

| Job | FO4's mechanism | Vanilla example |
|---|---|---|
| Gesture on a line | INFO speaker idle, `dyn_Activation`, root graph | 128 INFOs (`IdlePointing`, `MTCoughing`; counted in [fo4_idles.md](fo4_idles.md#mechanism)) |
| An idle when a package starts or ends | PACK `POBA`/`POEA`/`POCA` `INAM` | 10 uses: `IdleClapping`, `IdleFightWinner` (root graph `dyn_Activation`), Dogmeat's flavor idles |
| Hold a pose while a package runs | PACK idle list (`IDLF`/`IDLC`/`IDLT`/`IDLA`, after the conditions) | 12 packages: `DN121JakeSurrenderStayAtSelf` → `IdleHeldHostage`, the synth shutdowns, ghouls feeding (`dynamicAnimLooping`), all Travel instances |
| An NPC working at a spot | IDLM whose `IDLA` lists root-graph dynamic idles, or a FURN whose keyword picks a furniture subgraph | `NPCUseJet` (`dyn_Activation`), `NPCLockpicking*` (`dyn_ActivationLoop`), `HeldHostageIdleMarker`; smoking and clipboard markers name a flavor keyword (`QNAM`) |
| Seated flavor | The furniture subgraph's own pose and flavor clips, by keyword (`HumanRaceSubGraphData`) | `FurnitureIdleRoot` holds only 9 idles (eating, reading, barber) |

FO4's IDLM and PACK idle lists use the same subrecords as FO3's and FNV's
(xEdit's shared `wbIdleAnimation`): flags (Run In Sequence 0x01, Do Once
0x04), count, timer and the idle FormIDs. So each FO3/FNV list can be
copied field for field.

## <a id="findings"></a>Findings, most visible in the FO3 intro first

1. **Package event idles** (76 FO3, 87 FNV) were dropped by the committed
   code. The main checkout's uncommitted `packages.py` converts them, and
   the 2026-11-19 Vault 101 build has 50. That build is the one the user
   played, so the bugs reported from it happened with these idles in.
2. **Package idle lists are dropped**, starting in the exporter (126 FO3,
   242 FNV). The G.O.A.T. students, Gloria's sobbing and the Overseer's
   hands-on-hip are among them. FO4 has the field; vanilla holds poses
   with it. Exported in step 1, written in step 3 (standing idles).
3. **Held idles fight the graph's rules.** Counted loops are baked onto
   the one-shot event, which nothing can interrupt, so lines need
   `F3NV_SwitchIdle`. Forever loops have no authored release once (1) is
   dropped, so lines need `F3NV_LoopIdle`. Both are Papyrus on every
   affected line, and both work around the event choice.
4. **Idle markers are matched by file name.** `idle_markers.PLAYS` maps
   clip-name prefixes to 16 vanilla markers. A marked spot then plays
   FO4's animation, not the authored one. 168 FO3 and 197 FNV placed
   markers are empty. That is a heuristic, which the project's rules say
   to replace with the authored data. FO4's IDLM can list our converted
   IDLEs directly, as vanilla's `NPCUseJet` does.
5. **Seated idles have no home.** Being seated is measured from the clip's
   first frame (`human_clip.SEATED`, a threshold). A line's seated idles
   are left out after the October crashes, and the 161/210 sitting leaves
   of `FurnitureIdles` are not built. FO4 plays seated flavor through
   furniture subgraphs. `furniture_poses.py` already builds one for the
   crucifix: an own keyword plus a SADD race mapping it to
   `FurnitureBehavior.hkx` and a folder of FNV's enter, hold and exit
   clips.
6. **`PickIdle` sends an event FO4 lacks** (0 uses in FO3 and FNV).
7. **The exporter dropped the idle-list subrecords** of IDLM and PACK.
   `idle_markers.py` read the plugin bytes to get around it, which breaks
   the exporter's "pure dump" rule. Fixed in step 1.

## <a id="plan"></a>Plan, in the recommended order

Each step is its own change and play test. Step 1 unblocks 3 and 5.

1. **Export the idle lists (built 2026-11-19, in worktree
   `exciting-murdock-88f8f1`).**
   - `package_falloutnv.emit_idle_list` writes `IDLF.Flags`, `IDLC.Count`,
     `IDLT.Timer` and `IDLA.Idle[i]` for PACK and IDLM
     ([export](../commentary/tes4_export_falloutnv.md#idle-lists)).
   - `idle_markers.idle_lists` reads them from the export instead of the
     plugin bytes. `IDLA.Idle[]` is in the FormID key table.
   - Checked on a scratch export of both games: FO3 has 126 packages and
     122 markers with lists, FNV 242 and 198.
   - Every marker's idle list matches the old byte-reading route (122 of
     122, 211 of 211), so the markers built do not change.
   - **Needs a re-export** of every FO3/FNV export that has idle markers or
     packages, before the next import. Until then every marker reads as
     listing nothing and becomes the empty marker. Per plugin:
     `py -3.14 -m tes4_export.export <plugin> --outdir export/<plugin>
     --types IDLM PACK`.
2. **Package event idles into `POBA`/`POEA`/`POCA` `INAM` (already built,
   2026-11-16, uncommitted in the main checkout; in the 2026-11-19 Vault 101
   build).**
   - `pack_package` fills each `INAM` from `Idles.idle()`, with the same
     left-out rules.
   - Not documented or tested yet. Its note belongs in
     [fo4_idles.md](fo4_idles.md) once the play test confirms it, where the
     main checkout also has uncommitted edits.
   - *Play:* the CG00 birth sections, CG01's gate (Dad stands from the
     crouch), CG04's waking, and in FNV the opening thugs
     (`NVopeningThug01Idle`, 4 uses).
   - *Then:* check whether `F3NV_LoopIdle` is still needed. FO3's rule is
     "until another idle plays", which this and step 4 give back.
3. **Package idle lists into FO4's PACK idle list (built 2026-11-22, not
   played).** `packages.pack_idle_list` writes `IDLF`/`IDLC`/`IDLT`/`IDLA`
   right after the conditions, as vanilla does, in place of the template's
   own list. Each idle goes through `Idles.idle()`, so seated and clipless
   ones are left out; a list with none left is not written. The timer is
   copied. Of the flags, Run In Sequence (0x01) and Do Once (0x04) are
   copied, and 0x08 is always set, because all 12 vanilla lists set it.
   A guard's or follower's HoldPosition combat copy gets the same list.
   - Built lists (the export's lists in brackets): FalloutNV 136 (242),
     Fallout3 57 (126), DeadMoney 3 (5), HonestHearts 8 (10),
     LonesomeRoad 1 (3), OldWorldBlues 1 (7), NVBII 17 (21), NVBIII 17
     (21), NVWillow 12 (12), Russell 6 (6), YUP 1 (2), TLD 4 (4).
     The rest are lists on packages that are left out, or lists whose
     every idle is seated or has no human clip.
   - *Play:* Gloria crying, the Overseer waiting, MQ01's checkpoint,
     Willow's waits.
   - *The students' lists are seated clips,* so they are left out until
     step 7.
4. **Held idles on the loop event.** A counted loop keeps its baked clip
   but plays on `dyn_ActivationLoop`, with looping seconds equal to the
   clip's length. A forever loop writes 0/0, as vanilla does. Then the next
   idle of either kind replaces it through the graph's own transitions,
   and `IdleStop` ends it.
   - Drop `F3NV_SwitchIdle` and the `IsIdlePlaying` hold.
   - *Play:* Dad's Bible verse (CG01), then `LooseCrouchTalkB`.
   - *Fallback:* if the engine does not end a timed loop on a human, keep
     the clip on the loop event and end it with `IdleStop` when its line
     ends.
5. **Own idle markers.** Each FO3/FNV IDLM becomes an FO4 IDLM on its own
   FormID. Its list names the converted IDLEs; its flags, count and timer
   are copied. Drop the `PLAYS` table. A marker whose idles do not convert
   (creature ones without an own rig, seated ones) keeps today's vanilla
   stand-in until step 7. Rebuild: import.
   - *Play:* a sweeping or smoking spot in Vault 101 or Goodsprings.
6. **`PickIdle` → `IdleStop`.** Change the row to play vanilla's `IdleStop`
   idle. Tiny; scripts only. It matters only for mods today.
7. **Seated idles on furniture subgraphs.** Turn the crucifix's own
   furniture subgraph into the general route for FO3/FNV sitting idles:
   per sitting group (desk writing, table sobbing, test taking), a keyword
   and a SADD race mapping to `FurnitureBehavior.hkx` with FO3's clips as
   pose and flavor. Seated line idles and seated package idle lists then
   play inside FO4's own furniture state, not as root or furniture-graph
   dynamic idles. This is the biggest step. Coordinate with the classroom
   session, which owns the students.

**What it removes, if the play tests agree:** `F3NV_SwitchIdle`,
`F3NV_LoopIdle` (for every case a package idle covers), the `HELD`
condition, the `PLAYS` marker table, and most of the seated special cases
in `idles.py`.

## <a id="open"></a>Not verified

- The graph reading is static (transitions and flags from the files). That
  a one-shot ignores a one-shot also matches the observed Bible-verse bug,
  but nothing else here was played.
- The PACK idle list on our converted templates (Sandbox, HoldPosition,
  Sit, Travel copies) is untested. Vanilla uses it on Travel instances.
- Whether FO4 ends a timed `dyn_ActivationLoop` itself (step 4).
- `PlayIdle` counts are from the export text with comments skipped. The
  older [census](fo4_idles.md#census) counted 199 calls in the converted
  FNV scripts, which include `PlayIdle` the converter itself adds.
