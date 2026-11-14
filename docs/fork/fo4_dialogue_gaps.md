# FNV dialogue left out of the FO4 build: census and fixes (2026-11-12)

**Code:** `fo4_import/spike/conditions.py`, `condition_forms.py`, `classes.py`, `npcs.py`, `say_topics.py`,
`conversation.py`; census tool `tools/validate/fo4_dialogue_census.py`.

Closes the two ROADMAP rows "Dialogue lines" and "Choices with shared answers". Their counts (about 350 lines,
236 choices) came from the 2026-11-06 build; most were fixed since. This page counts what the 2026-11-12 19:29
FalloutNV.esm build (whole map) still leaves out, by cause, and what this branch changes.

## <a id="census"></a>Census (2026-11-12 19:29 build, before this branch)

```bash
py -3.14 -m tools.validate.fo4_dialogue_census FalloutNV.esm --rows temp/dialogue_census.tsv
```

FalloutNV.esm has 23,247 INFOs. The build makes 22,116 of them; 1,131 are not built.

### Left out by a condition: 83 lines (124 placements)

| Cause | Lines | What it is | After this branch |
|---|---|---|---|
| GetIsID of an actor the build lacks | 40 | Actors FNV never places: 0 ACHR/ACRE, list or script mentions for V22Bohr, RL3Follower, VStreetCasinoGuard, SSHQEyebot, the VMS26 troopers, the North Vegas residents, vTopsBartenderRandom; DoctorBarrows only in Fallout 3 leftovers. The Forlorn Hope injured troopers and FortChildAAM are named only as templates or leveled-list entries (whether FNV's GetIsID passes for them there is not checked) | Still out: dead in FNV for the unplaced ones |
| GetDisposition (vs global GenericFriendlyDisposition) | 14 | GenericKids' hellos and goodbyes | Still out, see [disposition](#disposition) |
| GetIsRace | 8 | Lily to a child: the four FNV child races, on the Target | Built, [races](#races) |
| GetFactionRelation (no actor) | 6 | Gomorrah greetings and the Omerta gun check | Built, [empty params](#empty-params) |
| GetInCell | 3 | Lucky38Penthouse, HooverDamIntPowerPlant: cells reached by elevator or script, not in the build | Still out (build scope) |
| GetFactionRankDifference (no actor) | 2 | BoS "Hello, sir." | Built, [empty params](#empty-params); FNV reads 0 here, so it never passes in either game |
| GetMajorCrimeCount | 2 | TenpennyGuardFaction: no FNV NPC, creature or script holds it (a Fallout 3 leftover) | Still out: dead in FNV, and FO4 has no such function |
| GetQuestVariable / GetScriptVariable of no form | 3 | Authoring errors (quest 0, DoorMarker as the variable) | Still out: read 0, as in FNV |
| IsActorTalkingThroughActivator | 2 | The NCR emergency radio operator: no talker speaks as him in the build | Still out |
| GetObjectiveCompleted / Displayed | 1 | VMS41 objective 11: not authored, reads 0 in FNV | Still out: dead in FNV |
| GetIsClass | 1 | Boulder City's traveling merchants' greeting (VendorTraveler) | Built, [classes](#classes) |
| GetIsCurrentPackage | 1 | V03BryceDiePackage: a Find package, which FO4 has no procedure for | Still out (package gap) |

### Never reached the line converter: 1,048 lines

*Quest has no built line (473).* Test and debug quests (`vDialogueTestaclesDebug` 289, `VDialogueTEST` 64,
`TempMan` 3); `GenericPlayer` 29, [the player's own barks](#player-barks); `GenericIdleChatter` 15;
`VES08CampGolf` 19, `Vault108DialogueShell` 23 (gated on `Vault108GaryFaction`, which no FNV NPC holds),
`UniqueFriendlyFire` 9, `VES03DialogueWastelandHunterGS` 11 and a few single lines.

*Topic not reached (575).*
- Bark topics FO4 has no subtype for: `PLAYERLAYMINE` 44, `PLAYERTHROWGRENADE` 43, `SpeechChallengeFailure` 3
  ([barks](fo4_pipeline.md#barks)).
- Companion status barks with no state FO4 tracks: `WeaponIneffective` 20, `WeaponBroke` 17, `UsedDoctorBag` 14,
  `Regenerating` 13, `Poisoned` 12, `ArmorIneffective` 11, `KnockedBack` 2, `OnFire` 1, `Frenzy` 1
  ([companion barks](fo4_pipeline.md#companion-barks)).
- Follower command barks: `FollowersStealthing` 12, `FollowersOverburdened` 11, `FollowersAcknowledgeMyOrder` 11.
- Caravan game topics (`vCaravanQuest`, 32): the casino work's.
- `VIntroNarration` 16 (the intro slides), `DoctorMedical*` 13, radio segments and hellos about 13.
- About 290 menu answers and scene lines (Veronica's Accelerator, Bryce Anders, The King, the Weathers family,
  Mick, ...). Their menus dropped them without a count: `Conversation._answers` skipped a line whose conditions
  did not convert and recorded nothing. They are now counted as left out, with their condition
  ([answers counted](#answers-counted)); the next build's census splits them by cause.

### Choices with no line: 18 topics

| Topics | Cause | After |
|---|---|---|
| VFreeformVault22V22BohrTopic000-003 (4) | V22Bohr is never placed | Dead in FNV |
| vDialogueTheStripVStreetCasinoGuardTopic000/001/003 (3) | VStreetCasinoGuard is never placed | Dead in FNV |
| FollowersLetsGoNotYet1/2 (2) | RL3Follower is never placed | Dead in FNV |
| VES09BoulderCityTopic000/001 (2) | Answers test GetIsClass VendorTraveler | Answered, [classes](#classes) |
| Weathers family topics (3), VFSMickTopic001/006 (2) | Answers count the slave collar or the Pimp-Boy, items the build does not make | Still empty, [unmade items](#unmade-items) |
| VFSTheKingTopic035, VFSJeanBaptisteCuttingTopic027 (2) | Answers test objectives (VMS19 50, VMS29a 42) | Counted next build; VMS29a 42 is not authored, dead in FNV |

## Fixes

### <a id="empty-params"></a>An empty form parameter stays 0

FNV's condition evaluator (`TESConditionItem`, decomp `tesconditionitem.cpp:154`) passes the line's other party
when a reference parameter is empty. Fallout4.esm writes the same: 3 INFOs and 8 quests test
`GetFactionRelation` with parameter 0 (compared to 2.0). `conditions.unmapped_form` refused any form parameter
missing from the form map, 0 included; it now lets 0 through, so the test converts with its parameter empty.

### <a id="races"></a>Races: the race the build gives that race's NPCs

The build gives each NPC the race of its body (`npcs._body`: a child race the child body, HumanChildRace; a
ghoul race the ghoul body; others the human body, HumanRace). `Npcs.trait_forms` maps every FNV race to that
FO4 race, and `condition_forms` adds it to the lines' form map. All 32 GetIsRace tests in FalloutNV.esm are
Lily's (four child races, `== 1`, on the Target); each becomes `GetIsRace HumanChildRace`. Drift: an ethnic
race test would widen to every human; FNV has none.

### <a id="classes"></a>Classes a line tests

Every converted human took Fallout4.esm's Citizen. `classes.Classes` writes, once, a copy of Citizen (its PRPS
and DATA, not its localized name) for each FNV class a line tests, as `FNV_<class>`, on the FNV class's
FormID; NPCs of that class take it, and the class joins the form map, so `GetIsClass` converts as itself.
FalloutNV.esm tests one class: VendorTraveler (3 lines; 17 NPCs hold it: VES09Merchant01-04, Fem01-04,
NVMerchant* and NVProspectorMerchantPrimmDen).

### <a id="unmade-items"></a>Items the build cannot make

A line counting or checking worn an item the build does not make (no replacement: the slave collar, the
Pip-Boy, the Pimp-Boy) failed to convert. No one can hold such an item, so `condition_items` records it as
`(UNMADE, item)` and `conditions.absent` reads its test as 0, like a test of an absent quest or actor. A `== 0`
test now drops out; a `== 1` test leaves the line out as "never true", naming the function. The Weathers and
Mick lines need the items themselves (equipment substitutes), which is not dialogue work.

### <a id="answers-counted"></a>Answers counted

`SayTopics.left_out` is now the one place that counts a line left out and records its readiness entry; the menu
answers use it too.

## Left out, with reasons

- <a id="disposition"></a>**GetDisposition (14 lines).** FO4 has no disposition. No FNV script or result
  script ever calls ModDisposition (0 in SCPT, INFO and QUST), so FNV reads only its base disposition, which
  its engine computes from Charisma (GMSTs `fDispActorCharBase` -30, `fDispActorCharMult` and
  `fDispTargetCharMult` 10); the decomp does not name that function. Converting it would be a guess.
- <a id="player-barks"></a>**The player's own barks (GenericPlayer, 29 lines).** All are grunts said by the
  player: `Hit` 16, `PowerAttack` 6, `Death` 5, and two iron-sight breaths. Fallout4.esm's own
  `DialogueGenericPlayer` (000179EF) already gives the player HIT_ (7 lines), POAT and ATCK topics, so these
  would double FO4's own. They stay out.
- Bark topics without an FO4 subtype or state, follower commands, Caravan, the intro and radio: listed in the
  census above, each with its own page.

## Expected after the next build

- Lines: about 17 more built (GetFactionRelation 6, GetFactionRankDifference 2, GetIsRace 8, GetIsClass 1) plus
  the two Boulder City answers. About 66 lines stay left out by a condition, about 50 of them dead in FNV too.
- Choices: 2 more answered (Boulder City); 16 stay empty, 9 of them dead in FNV.
- The about 290 menu lines dropped without a count now show in `line left out`, so that count rises.
- FormIDs: no existing id moves. New: one CLAS (`FNV_VendorTraveler`, on the FNV class's id) and the INFOs of the
  lines now built (hashed keys no earlier build used). The preflight's `build_history` reports any EditorID that
  moved.
