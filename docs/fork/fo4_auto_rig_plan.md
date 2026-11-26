# Creatures with no rule: an automatic route

**Code:** `fo4_import/spike/creature_routes.py`, `fo4_import/rig/derive.py`,
`fo4_import/spike/creature_attacks.py` (`clip_groups`)

Status: BUILT (routes 1–5); not yet played in game. The skip path in
`Npcs.placed` is still a count, not an error ([below](#skips)).

A creature folder used to convert only if someone wrote a rule for it, either in
`fo4_import/data/replacements.json` (`_rules.creature`) or in
`fo4_import/data/creature_rigs.json` (own rig). Fallout3.esm and FalloutNV.esm
have rules for every folder they place. The Fallout 3 DLC don't, and a mod with
a new creature never will. Any creature with no rule was skipped, and so was
every reference that placed it. The conversion now picks a route itself.

## <a id="why"></a>Why: The Pitt's failed check

f3nv-0.12's Pitt build finished, but its reference check failed. The Pitt's
trogs had no rule, so the build skipped 80 placed trogs and 52 marker creatures
(`marker_creature.nif` records that take a trog template through `TPLT`). One of
those markers, `DLC01FF007TrogRef`, is named by 3 packages
(`DLC01FF007SlaveCorpseCheck*`: PLDT and a condition) and 4 dialogue
conditions. `Npcs.placed` gives an ACHR id only to an actor whose base converts,
so those 10 references got an id for a record that was never written.

The hand rule sends `dlcpitt\creatures\streettrog` to a Fallout 4 feral ghoul,
as `stats` (FO4's look, the trog's stats). It stays: a hand rule wins.

## <a id="census"></a>Folders with no rule (f3nv-0.12 logs, 2026-11-26)

Counts are the placed references skipped, from each build's
`ACRE skipped (no FO4 base)` lines. The clip and bone counts come from the
exported meshes in `F3NV Work\export\<plugin>\meshes`.

| Folder | Plugin | Placed | Clips | Bones | Route taken |
|---|---|---|---|---|---|
| `dlcpitt\creatures\streettrog` | ThePitt.esm | 80 (+52 markers) | 35 | 54 | hand rule (ghoul) |
| `dlcanch\creatures\chimera` | Anchorage.esm | 8 | 17 | 12 | derived rig (a tank: hull pelvis, radar head, track feet) |
| `dlcanch\creatures\spidermine` | Anchorage.esm | 17 | 8 | 13 | derived rig |
| `dlc04\creatures\hillfolk1` | PointLookout.esm | 9 (+60 through the `DLC04LvlSwampFolk*` lists) | 47 | 58 | derived rig (biped) |
| `dlc04\creatures\hillfolk2and3\anims` | PointLookout.esm | 6 | 71 | 61 | derived rig (biped, guns) |
| `dlc03\creatures\smbonecrusher` | BrokenSteel.esm | 3 | 118 | 57 | same skeleton as the super mutant |
| `creatures\failedfevsubject` | Fallout3.esm | 2 | 0 | none | still stand-in (a speaker body) |

## <a id="order"></a>The route, in order

For each creature folder with placed or listed members, `Routes.of` takes the
first route that works:

1. **A hand rule**, if there is one. Hand rules override everything below.
2. **The same skeleton as a ruled folder.** When the set of `NiNode` names in a
   folder's `skeleton.nif` equals a ruled folder's, it takes that rule (and, for
   `fnv`/`stats`/`item` rules, that folder's body pair). Node names are authored
   data, so this is not a guess. A partial match (the swamp folk's 51 of 58) is
   not enough. Each `skeleton.nif` is looked up file by file across the export
   layers: Broken Steel's export holds a `creatures\smspinebreaker` folder with a
   few `.kf` files and no skeleton, so a folder-level lookup misses Fallout 3's.
3. **An own rig derived from the files** ([below](#derive)), on the mole rat's
   template.
4. **A stand-in by creature type** (`DATA` creature type): a super mutant (4),
   a feral ghoul (5), a protectron (6); any other type takes the mole rat.
   The plan said "by body plan"; the creature type is the authored indicator,
   so it replaced the bone-tree guess.
5. **A still stand-in** for a model with no `skeleton.nif` (the FEV subject):
   FO4's protectron speaker with the creature's NIF, as talking machines are.

A model-templated record (`TPLT` with Use Model) takes its template's route.
Every creature that reaches step 2 or later is logged as
`creature route (<how>): <folder>`, so it can be reviewed and promoted to a hand
rule.

## <a id="groups"></a>Which animation group a .kf plays

The group is the **name of the NiControllerSequence inside the .kf**, not the
file name. `FalloutNV.exe`'s animation-group setup compares each sequence's name
against the group table (`TESAnimGroup`, `_stricmp(apSequence->GetName(), …)`;
`references/fnv_decomp/src/fallout_shared/tesanimgroup.cpp`). The file name
gives only the hand-type, movement and power-armor prefixes (`0x5f38d0`,
`KF_PREFIX`). A variant suffix (`_2`) follows the first `_` and is cut off
(assumed from the data; the decomp's handling was not traced).

Confirmed in the exported files:

| File | Sequence |
|---|---|
| swamp folk `locomotion\forwardwalk.kf` | `Forward` |
| chimera `mtfastforward.kf` (top level) | `FastForward` |
| `2hmpowerattack.kf` | `AttackRightPower` |
| brahmin `mtforward.kf` | `FastForward` |

`clip_groups(root)` reads every `.kf` under a folder (hurt variants left out)
from its string table; the 10 older 20.0.0.4 files in
`characters\_male\idleanims` have none and are decoded instead.

Switching attacks and run speeds from file names to sequence names changed 6 of
77 FNV/FO3 folders' attack groups (the mirelurk king and `hillfolk1` gain power
attacks; Mister Gutsy, the sentry turret and the alien lose groups they never
used) and 2 folders' run clips: the brahmin's `mtforward.kf` is a FastForward
sequence, so its run speed is now the average of two clips; the nightstalker's
misspelled `mtfastfoward.kf` is now found but has no effect (it has an own rig).

## <a id="derive"></a>Deriving a rig entry

`rig/derive.py: derived(folder, root, parts, people)` builds the same `Rig` a
`creature_rigs.json` entry makes ([the rig table](fo4_own_rig.md#table)):

| Part | Source |
|---|---|
| `clips` | `clip_groups`: Idle ← idle; turns; WalkForward ← forward; RunForward ← fastforward, else forward; WalkBackward ← backward; CombatIdle ← aim, else idle. Among several clips for one group: no prefix or `h2h` first, then no variant, then the shallowest. No forward group: immobile. |
| `attacks` | the attack groups present, power groups as power attacks |
| `parts` | the creature's BPTD (already read from the source plugin by `rig/records.fnv_parts`; no export change was needed) mapped onto the body plan |
| `pose_bones` | three distinct ragdoll bodies: pelvis, chest, head |
| `guns` | when the creature carries a gun and its skeleton has a `ProjectileNode`: the ranged clip on `RightHand` |

The body plan reads `skeleton.nif`'s bone tree and its ragdoll bodies. The head is
BPTD's Head1 node, else the last body down the centerline. The trunk is the
head's ancestors. Legs are the side chains, sided by world X and sorted front to
back by their reach along the pelvis-to-head line, multi-body chains first (an
antenna is a one-body chain).

Checked against the hand entries (`tests/test_fo4_own_rig.py`, FalloutNV.esm):
clips and attacks are identical for all 12 FNV rigs except the securitron's
hand-picked gun and Talk clips and the queen ant's second gun; pose bones match
for 10 of 12 (the giant rat and spore plant differ only in the chest).

A derived rig fails with a reason (`no skeleton`, `fewer than three ragdoll
bodies`, `no Idle clip`), and the folder drops to step 4. Derived rigs are made
once per build and kept in memory.

**Unverified:** a derived ranged rig puts its gun on `RightHand`; the hand
entries use `MiddleHand` for spitters. Whether the FO4 gun copy's equip slot
agrees has not been checked in game.

## <a id="saves"></a>FormIDs and saves

A placed actor that starts converting gets its ACHR id from its own source
FormID (`ACHR_KEY`), as every built actor does; no written record moves. The ids
that references to it carried while it was skipped pointed at nothing, so
nothing saved can hold them. New bases, races and armor are keyed on authored
data (the folder, EditorIDs). `tests/test_formid_determinism.py` passes.

## <a id="skips"></a>Skips

`Npcs.placed` still counts `ACRE skipped (no FO4 base)` rather than failing the
build. With the five routes every placed creature in Fallout 3 and its DLC has
a route; the count stays as the check that this holds for a new plugin.
