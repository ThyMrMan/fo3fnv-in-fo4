# Dialogue robustness: why it breaks, and what would harden it

Research, 2026-11-10, after YUP broke Vulpes Inculta's menu
([dlc-prompts](../fo4_plugin_layout.md#dlc-prompts)). Three read-only
surveys: the history of FO4 dialogue failures, how FNV mods edit master
dialogue (census of every mod export), and how sturdy the menu design is.
**V** = verified in code, data or a fetched source; **I** = inferred.

## <a id="pairing"></a>How a menu pairs options and answers

- **Pairing by position is XDI's rule, not the engine's (V).** `reg2k/xdi`
  `src/DialogueEx.cpp` `BuildDialogueMap`: each player-topic slot (PTOP,
  NTOP, NETO, QTOP) pairs only with its own NPC topic. Option *i* owns the
  NPC INFOs from *i* up to the next player INFO with text; a pad (no
  responses, no shared INFO) is skipped as an option but keeps its slot.
  `GetNPCInfo` takes the first passing answer in that range, skipping a said
  Say Once one. It runs while the list is built, before the pick, so an
  answer condition that tests "which option was picked" cannot work.
- **Vanilla FO4 is not positional (I).** Of `Fallout4.esm`'s 1,669
  multi-INFO player topics in Player Dialogue actions, 1,072 have fewer NPC
  INFOs than player INFOs (ArturoGreetScene: male and female player lines,
  one answer). Vanilla's own rule is not disassembled.
- **Order inside a topic is record order (V).** FO4 INFO has a `PNAM`
  (xEdit `wbDefinitionsFO4.pas:9726`), but none of vanilla's 78,087 INFOs
  sets it.
- **Open (not verified):** where the engine puts a later plugin's *new*
  INFOs in a master's topic. Every claim that two mods' additions compose
  depends on it.

So a plugin is safe to the menu only when its edit keeps, per pair of
topics, player INFOs (options plus pads) equal to answers, slot for slot.
Unsafe edits: a new option beside a master option it replaces (the YUP
bug), deleting a master INFO, adding an answer to an existing option, and
an unbalanced block before the end of the list.

## <a id="history"></a>Failure classes so far

22 FO4 dialogue failures since 2026-10-12 (fo4_pipeline.md,
fo4_plan_dialogue_reach.md, commits). Grouped:

| Class | Cases | Guard today |
|---|---|---|
| A. Option shown when no answer passes (gate looser than answers) | Doc's option on Chet, Nash's stall, Torini, Cliff, Jason Bright, Vulpes "lessons" | Good: `menus` checks 2–3, `xdi_menus` |
| B. Position pairing and record structure | Shared Infos dropped, YUP's shifted answers | `menus` check 1 (own records only), `unpaired-menus` (new) |
| C. Engine state the converter's records change | barter over the talk, Say Once marker stages, greeting scene left running, talked-to flag, force greet picked again | Weakest: one audit rule (TSCE), single unit tests or none |
| D. Lines lost when a condition can't convert | Benny's Tops greeting | `condition_diff`, `dialogue_loss` counts, no baseline |
| E. Reach and wiring | intercoms, force-greet topics, Choices | `fo4_dialogue`, `dialogue_loss` counts |
| F. A line more actors can say than in FNV | ED-E's beeps, holotape played 2,125 greetings | Partly; the audit counted the copies as built |
| G. Mod and DLC merging, FormID keys | VDoctors ids moved, DLC rewrote 37,510 INFOs, `[Leave]` on mod menus, YUP's prompts | Piecemeal `dlc` checks; the same root (a key from computed data) recurs |
| H. Text and voice | padded silent lines, HTML in prompts | Unit tests |

Classes C, F and G keep recurring and have no general check.

## <a id="mods"></a>How mods edit master dialogue

Census of master INFO overrides (YUP 5,822, Goodies 308, ExtraGoodies 26,
Better Brotherhood 57, DLC Enhancements 72; NVWillow adds 333 new INFOs).
Kinds, worst first:

1. **Choices menus rebuilt under new keys (V).** A menu is keyed by
   `repr(('menu', choices))` and the quest reaching it first. YUP changes
   choices on 300 lines, so 655 DIAL and 100 SCEN keys are menus the game
   never had; 110 DIAL and 22 SCEN are game menus copied under another
   quest. The game build itself makes each menu once per reaching quest
   (Jimmy's 0015697A option has copies under 000E61A4, 000E61A5, 000E7363,
   0010E195 and GREETINGS).
2. **Part of an option's group changed (V counts).** The option is rebuilt
   from the changed lines only: YUP 298 groups, Goodies 15. Fixed for the
   slots by `_slot`; the option's conditions still come from the changed
   subset only.
3. **Changed lines the build never reaches (I).** A line in a topic offered
   only through Choices is rebuilt only if a mod line leads there: YUP
   1,196, Goodies 55. The edit is silently lost.
4. **Say Once on a changed line (I).** The plugin's lines mark its own Say
   Once quest while the game's copies read the game's: YUP 865 lines.
5. **Split shape changed (V counts):** a result script added or removed on
   a multi-response line moves its part keys (YUP 36).
6. **Deleted (YUP 16) or moved (Goodies 3) master INFOs (I):** the game's
   copies keep playing.
7. **Topic-only edits (I):** a topic name (YUP 226) or top-level flag
   change is applied only if a line of it also changed.
8. **Safe (V):** response text, conditions, result scripts and flags on
   reached lines override the game's ids in place. New INFOs a DLC adds to
   a game topic go at the end and balance (Honest Hearts 5, Lonesome Road 4,
   NVWillow 3 menus).

## <a id="hardening"></a>What would harden it

Ranked by value per cost.

1. **Check every menu on the load-order view (preflight).** Audits read a
   plugin's own records, so a mod's damage to the game's menus is invisible
   to `menus` check 1. Merge the plugin over its masters and run checks 1–3
   on the result; `unpaired-menus` becomes a special case.
2. **Refuse to write an unbalanced menu (converter).** Emit an option, its
   pads and its answers as one unit and assert, per Player Dialogue action
   after merging with the masters, player INFOs == answers; fail the build.
3. **Key every record by authored data only.** The recurring class G: keys
   built from text (prompts), from the reaching quest, or from choice lists
   as a mod edits them. Rule: a mod's record for a master line or menu takes
   the master's key (as `_slot` now does for options); check it in the
   `dlc` audit as "no mod key whose FNV line or step already has a master
   key" (generalizes `copied-lines`).
4. **One build per menu, not per reaching quest.** Kills the copies and the
   new-quest keys of kind 1. Large FormID drift in the game build: needs a
   save break decision.
5. **Rebuild a whole menu step from master plus mod lines** when a mod
   touches any of its lines, so options, pads and conditions come out
   complete at the master ids, and `drop_unchanged` prunes the rest. Fixes
   kinds 2, 3 and 7. Deleted and moved lines: override every master copy
   with a never-true condition (kind 6). Say Once: use the master's marker
   (kind 4).
6. **Engine-state audit (class C).** List every record or script the
   converter adds that changes persistent state (stages, talked-to, package
   picks, running scenes, Say Once) and check each has its FNV-side reset.
7. **Speaker-set differential (class F):** each built line's speakers must
   be a subset of FNV's.
8. **Baselines for dialogue audit counts,** failing on an increase, as
   `build_diff` does for FormIDs.
9. **Replay check:** diff the menus the `fo4_trace` log records in play
   against what the audit predicts, so a runtime-state bug shows after one
   play test.

Rejected: answer conditions keyed to the picked option (XDI evaluates
answers before the pick); using the spare NTOP/NETO/QTOP slots per mod
(four slots, and two mods would fight over the scene); a runtime pairing
hook (it would hook the functions XDI already hooks, and a DLL is the last
resort). A one-option-per-answer-scene design (each option's silent router
line starts its own answer scene) would remove position pairing entirely,
at the cost of a scene per option and a full FormID break.

Our own menu in F3NV.dll, replacing XDI, is planned in
[fo4_dialogue_menu_plan.md](../fo4_dialogue_menu_plan.md).
