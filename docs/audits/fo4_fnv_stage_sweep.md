# FNV stage sweep on Fallout 4, 2026-11-18

The first full run of the layer 1 stage sweep
([plan](../fork/fo4_test_layers_plan.md#l1)) over the whole-map FalloutNV.esm
build, on the test laptop, from the checkpoint `f3nvtest_vcg01_vit_o_matic_male`.

**Run.** 350 cases (349 quests and the report). The first run stopped at
`VNelson`, where a load the game never took after `vNellisMoveToPearl`
(that quest moves the player and asks for an autosave) left 25 cases and
VNelson unrun. Those 26 then passed in a second run. The sweep now queues a
dropped load again and can relaunch after a failure
([S3, S5](../fork/fo4_test_layers_plan.md#s3)). Most cases take 7 to 17 s.

**Checks.** 85 checks failed, in 18 quests. Sorted by cause:

| Kind | Checks | Verdict |
|---|---|---|
| A stage the sweep waited 30 s for a quest script's timer to set | 51 | Mostly the sweep's own limit: the timer sets that stage only from one earlier stage (VCG01: 98 → 100 → 102 → 105) or while a menu is open, and the straight `setstage` order never meets that. VCG00 alone has 28. |
| `setstage` run, the stage still not done after 10 s | 10 | VCG00 5 to 15 (9), VMQ03b 200; quests the checkpoint has already finished; not looked at further |
| A stage a line's result script should set, run outside its talk | 2 | `vDialogueEDE` 20, `VDialogueVegasNorth` 80; not looked at |
| Papyrus errors in converted scripts | 22 | Below |

**The Papyrus errors** (failed checks in brackets where more than one):

| Error | Where | Verdict |
|---|---|---|
| `Actor Value "Confidence" cannot be modified in scripts` | `F3NV_CowerPackage` (VMS16b) | **Bug, fixed**: FO4 refuses `ModValue` on Confidence; vanilla only calls `SetValue`. No converted cower ever cowered ([packages](../fork/fo4_pipeline.md#packages)) |
| `does not contain valid inventory objects or keywords` | `TES4Polyfill.RemoveAllTypedItems` (Arcade's armor) | **Bug, fixed**: an empty item-type list is now skipped |
| `Cannot call play() on a None object` | `FadeToCreditsTimerScript` | **Bug, fixed**: the SOUN names a `.wav` that ships only as an `.ogg` (10 FNV sounds, 1 FO3) ([sound properties](../fork/fo4_pipeline.md#sound-properties)) |
| `Cannot play a None idle on an actor` (4) | Victor's Securitron idles in VCG00, Mr. House's screen | Known gap: creature idles on a rig that is not our own are left out ([idles](../fork/fo4_idles.md)) |
| `cannot enable an object with an enable state parent` (2) | `vHDNCRTrooperPowerStati` (`vHDPlantNCRRef04`) | Faithful: the GECK says Enable on an enable child "will have no effect". FO4 only logs it |
| `unknown quest objective` (10) | `VMS43a`'s stage fragments | Faithful: the source quest authors no objectives at all, yet its stages set 10 to 30 |
| `Cannot remove None from a container`, a call on None | VCG00 stage 0 | The Pip-Boy glove has no FO4 item; the sweep runs the opening out of order |
| `does not have any inventory` | VCG00 stage 100 (McMurphy unequips the shovel) | Sweep context: the actor is not loaded |
| `Remove()`/`Add()` on None after `VMS16.Stop()`, `Stop()` on None at stage 110 | `QF_VMS16` | **Open.** Both properties are filled in the built VMAD (`TES4ScriptPackages` 02C4E50A, `VMS16` 02104EAE). Other fragments that use properties after stopping their quest, including VMS16's own `GSVictorRef`, did not fail |

**Update (the same day, layer 2):** the route sweep reproduced this and
showed the cause. A console `setstage` on a quest whose fragment has
already finished and stopped it starts the quest again and runs the
fragment again, and in the restarted quest the properties read None. The
sweep's `setstage` order did that here. The route sweep's fallback now
sets a stage only when it isn't done
([layer 2](../fork/fo4_test_layers_plan.md#l2-built)). Whether a converted
`SetStage` can restart a finished quest in play is not yet checked.

**The VMS16 lead.** The FO3 sweep shows the same thing in `QF_CG02` stage 100:
its first call, `CG02.Stop()`, hits None, and 138 more calls on None follow.
In both quests the quest property names the quest itself, and the quest has
already been stopped by its own fragment once in the sweep. The sweep's
`setstage` then starts it again. The theory, not yet checked: once a stopped
quest is restarted, its fragment script's object properties read None. It
would also hit converted scripts that `SetStage` a stopped quest, because
`TES4SetStage` starts it first.

## FO3 sweep, the same night

136 cases over the region build (Vault 101 and the 3×3 cells around -4, -4),
from `f3nvtest_cg02_bb_gun_female`. The first run crashed the game in
`CG00`'s birth stages (a race change on a CG02 save, sweep context), and the
case-level relaunch carried the rest: 134 of 136 passed. 221 checks failed:
- 38 timer stages and 4 result-script stages;
- 2 stages that `setstage` didn't set;
- 177 Papyrus errors. Nearly all are calls on None in main quests whose
  references lie outside the region (MQ01, MQ02, MQ11 and others), which is
  expected of a region build.

The ones that aren't None:
- **Bug, fixed:** "armor cannot be equipped by the passed in actor's race"
  in CG02 stage 100. The adult suit was equipped before `AgeRace` made the
  player an adult ([age before equipping](../fork/fo4_fo3_child_player.md#age-then-equip)).
  CG03 stage 5 and CG04 stage 2 show the same error only because the sweep
  loads a child save.
- "Attempted to add invalid perk" in MS03 stages 215, 225 and 250, and
  "unknown quest objective" in MS11Fin and CG03Test: not looked at.

**Fixed in this pass:** 2 converter bugs (sounds, CG02's age order) and 2
shared scripts (cowering, the item-type move). All were found
only because the sweep reads every converted script's Papyrus errors.
