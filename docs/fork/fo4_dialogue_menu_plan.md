# Our own dialogue menu (replacing XDI): test-build plan

Designed 2026-11-10; the test build is made ([as built](#as-built)) and not
yet played. Why: XDI pairs options and answers by
position, which forces a copy of every answer per menu, pads, and gates,
and breaks whenever a mod shifts a menu
([robustness research](research/fo4_dialogue_robustness.md)). XDI's
GitHub source (`reg2k/xdi`, 2019, game 1.10.75) and `Neanka/DialogueMenu`
carry no license, and the build in use is an unofficial 1.11.240 port, so
we write our own in F3NV.dll, reading theirs for understanding only (as
with the FNV decompilation: read and cite, never copy).
**V** = verified (disassembly, measurement, code), **I** = inferred.

## <a id="engine"></a>What the engine already does (1.11.240)

Found by matching the port's own signature strings, each unique in
`Fallout4.exe.unpacked.exe`, then reading the functions.

| What | RVA | Address Library ID | |
|---|---|---|---|
| Option → INFO (player and NPC slot), `GetInfoForDialogueOption(action, scene, actor, option)` | 0x416600 | 2196825 | V |
| Its two call sites (player, NPC) | 0x41568A, 0x415A21 in fn 0x415280 | 2196817 | V |
| `GetNPCResponseInfo(action, scene)` and its call site | 0x414180; 0x413DA8 in fn 0x413A20 | 2196806; 2196800 | V |
| `SelectDialogueOption_Internal(player, option)` (4 = none) | 0xD76130 | 2233190 | V |
| INFO picker (topic, speaker, target) | 0x698DB0 | 2208361 | V |
| `IsPlayerTalking` call | 0xC7C07A | in 2229971 | V |
| g_menuTopicManager | 0x30E6E50 | 4796064 | V |

- **Vanilla picks the NPC answer as FNV does (V).** The picker walks the
  topic's INFOs in order and returns the first that passes (quest running,
  conditions, said check); Random-flagged INFOs up to Random End are a
  random pick among the passing. The player INFO that was spoken plays no
  part. Only XDI's positional ranges make position matter.
- **State (V):** the action's chosen option at +0xE0, the player's chosen
  response at +0xD3C; slots 0–3 are the four vanilla options. XDI stores
  option + 5 for its own entries; the engine keeps whatever
  `SelectDialogueOption_Internal` is given.
- **Action layout (V by use):** Player Dialogue: player topics +0x20[4],
  subtypes +0x40[4], NPC topics +0x98[4], subtypes +0xB8[4]; NPC Response:
  topics +0x20[4], subtypes +0x40[4].

## <a id="have"></a>What we have

- **F3NV.dll** (`tes_runtime/fo4_condition`, ~2.5k lines, built by
  `build.bat` with `cl` against F4SE 0.7.9 headers and libs, raw 1.11.240
  RVAs, no Address Library). It already registers Papyrus natives, uses a
  `BranchTrampoline` (256 bytes since the dialogue hooks), patches vtable
  slots, and drives menus at runtime through `GFxValue::Invoke` and
  `GFxFunctionHandler` (pipboy.cpp). No dialogue code, and F4SE 0.7.9 has no
  TESTopic / TESTopicInfo / BGSScene layouts: those are new work.
- **Toolchain gap:** `tes_runtime/common/msvc.bat` names VS Build Tools,
  which is not installed; run Community's `vcvars64.bat` first.
- **SWF building:** `fo4_import/casino/movie.py` compiles our own AS3 into a
  skeleton SWF with FFDec (`-importScript`), deterministic and cached. No
  step yet patches a vanilla SWF; the pre-push hook refuses any committed
  `.swf`.
- **The build marks menus** with XDI.esm's keyword (`records.py:73`
  `XDI_KEYWORD = 0x800`; `cell.py:114` masters `XDI.esm`).

## <a id="design"></a>Design

- **An option names an FNV topic; its answer is that topic's first
  passing line,** built once per FNV line, not per menu. The answer's own
  next step (its Choices menu, the Topic list, the end, or its Follow Ups
  scene) is the line's, so nothing per-menu stays on it.
- **Hooks:** five-byte call redirects at the three call sites; anything
  below 5 passes to the vanilla functions. Our versions return the option's
  player INFO, and for the NPC slot and response the first passing INFO of
  the option's answer topic (call the picker at 0x698DB0).
- **The option → topic link:** a property on the script options already
  carry (CHOICE_VMAD), or a sidecar map read at load. TPIC ("Previous
  Topic") fits the type but its engine meaning is unknown; check before use.
- **Menu file:** at install, extract `Interface/DialogueMenu.swf` from the
  user's `Fallout4 - Interface.ba2`, import our own AS3 list class with
  FFDec, write `<output>/Interface/DialogueMenu.swf`. Never commit it.
- **Coexistence:** refuse to install the hooks, and log it, when
  `XDI.dll` is loaded or a call site no longer points at the vanilla
  function. Other mods with a loose `DialogueMenu.swf` clash the same way.

## <a id="test-build"></a>The test build

1. **Toolchain:** Community `vcvars64`, then `build.bat`; the unchanged DLL
   must rebuild.
2. **Structures:** TESTopic, TESTopicInfo, BGSScene action fields from the
   exe (the offsets above), with the picker's signature.
3. **DLL `dialogue.cpp`:** the three hooks, the option table for one menu,
   a trace of options shown and picked to `F3NV.log`.
4. **SWF:** the install-time patch: a list of N options that scrolls,
   select calls our DLL, Tab leaves.
5. **One hand-built menu:** a scene with six options naming six answer
   topics, in a scratch plugin; keep XDI.esm as a keyword master so the
   main build is untouched. A test MO2 profile with XDI.dll and its BA2 off.
6. **Measure and play:** options shown, answers right, say once, Random,
   camera, voice, leave.

Only after that plays: the converter switch (below), with its FormID drift
measured and approved.

## <a id="as-built"></a>The test build as built

**Engine pieces it uses (1.11.240 RVAs; V = read in the disassembly at
each call):**

| What | RVA / offset | |
|---|---|---|
| INFO passes its conditions `(info, bool*, speaker, target)` | 0x69F490 | V |
| INFO prompt text `(info) → const char*` | 0x69E740 | V |
| Mark INFO said `(info)` | 0x69F8D0 | V |
| Quest alias → handle `(quest, UInt32*, alias)`; handle → ref | 0x671FA0; 0x21E550 | V |
| Player Dialogue vtable; its run function, slot 21 | 0x2488978; 0x415280 | V |
| Player says the picked option: `48 8B C8` at 0x4158D2 → `EB 1E 90` skips it | 0x4158D2 | V |
| Camera turns to the player: the 1 at 0x83266C; 2 keeps it on the NPC | 0x83266C | V |
| Scene → quest | scene +0xA8 | V |
| Action: alias +0x08, topics +0x20[4], chosen option +0xE0 (4: none) | | V |
| Player's chosen response, read by `GetNPCResponseInfo` | player +0xD3C | V |
| Topic: INFO array +0x50, order table +0x58 (u16 links, 0xFFFF ends) | | V |
| Topic: INFO count +0x60 | | I |
| INFO: said byte +0x43, flags +0x44 | | V |

**F3NV.dll (`dialogue.cpp`).**
- On PostLoad it hooks the three call sites with five-byte calls, and
  takes vtable slot 21 to know which Player Dialogue action is running. It
  refuses, and logs why, when `XDI.dll` is loaded or any site no longer
  calls the vanilla function. `TRAMPOLINE_SIZE` is now 256.
- It registers a Scaleform plugin object, `f4se.plugins.F3NV`, with three
  natives:
  - `GetDialogueOptions()` returns `[{text, said}]` for the waiting action;
  - `SelectDialogueOption(i)` picks one, as option i + 5;
  - `Log(text)` writes a line to F3NV.log.
- **Which options are listed:** every INFO in the action's four player
  topics that has a link, passes its own conditions, and whose answer
  topic has a line that passes now.
- **When an option is picked:**
  - The player slot returns the option's INFO and marks it said. The
    player does not speak it, and the camera stays on the NPC, as in FNV.
  - The NPC slot, or a following NPC Response action, returns the answer
    topic's first passing INFO, chosen by the engine's picker (0x698DB0),
    once.
  - Options below 5 go to the vanilla functions unchanged.

**Menu movie.** `fo4_import/dialogue_menu/movie.py` reads
`Interface/DialogueMenu.swf` from the user's `Fallout4 - Interface.ba2`.
FFDec compiles our own `as3/DialogueMenu.as` over the game's class
(`fo4_import/base/ffdec.py`, shared with the casino movie). The result is
cached under `temp/` and written only to an output folder.
- The list shows 7 rows and scrolls. Said options are grey.
- **Keys:**
  - W/S, the mouse wheel, or the gamepad's Quickkey up/down move;
  - Enter, E, 1–9, a click, or gamepad A pick;
  - Tab goes to the engine and leaves.
- With no DLL, or no linked options, it lists the game's own four buttons.

### <a id="links-file"></a>The links file

The DLL reads `Data\F4SE\Plugins\F3NV_Menus\*.txt` the first time a menu
opens. Each line has four tab-separated columns: the option's plugin, the
option INFO's object id (hex), the answer's plugin, and the answer DIAL's
object id. `#` starts a comment. A link is kept only when its option is an
INFO and its answer a DIAL. The log line is
`dialogue menu: <file>: N links, M resolved`.

### <a id="test-mod"></a>Test mods

- **`python -m fo4_import.dialogue_menu.test_mod`** writes
  `output/fo4_dialogue_menu/`: F3NV_MenuTest.esp (only Fallout4.esm as
  master), its links, the menu movie and the DLL.
- The global `F3NVMenuTest` at 1 makes any NPC greet with an 8-option menu:
  - first-passing (an alternate line at 2);
  - Random ×3;
  - Say Once option;
  - Say Once answer;
  - Goodbye (End Scene);
  - a long prompt;
  - an option listed only at 2;
  - one never listed, because no line of its answer passes.

  Every answer that does not end the scene starts the menu again.
- **`python -m tools.dialog.menu_rebuild`** rebuilds one built XDI menu in
  this model:
  - one answer topic per option, under the menu's quest;
  - a copy of each paired answer that keeps its own conditions, flags,
    scripts and next step, and shares the response and voice (DNAM).

  The pairing is XDI's own (`xdi_menus.pair_lines`).

### <a id="vulpes"></a>Vulpes Inculta's Topic list (GREETINGS hub)

- **The hub:** P0 03D4727A, N 03447EEE. FalloutNV.esm has 2,656 player
  and 2,656 NPC lines there. YUP overrides or adds 35 of each.
- **Both "I'll do as you ask" options** (03330928, 0331C0EE) pair with
  the End Scene answer ("Then I bid you 'Vale'", 035AA687 / 03AEAEEE,
  flags 0x44) in the game build and with YUP over it. Offline, the pairing
  is not broken. Why the conversation does not end in game is not known.
  The DLL trace names the answer the engine actually plays.
- **The rebuild** of FalloutNV.esm + YUP gives F3NV_MenuHub.esp:
  - 1,994 options and 2,687 answer copies;
  - `fo4_ref_check` found 0 unresolved references among 23,421. Another
    61 go into DLC masters it was not given.
  - Both Vulpes options link to an answer topic whose only line shares
    the End Scene answer.
- **Not yet built:**
  - The engine's `IsPlayerTalking` fix;
  - speech challenges (the text and odds are not added to the prompt);
  - text replacement in prompts.

### <a id="setup"></a>Trying it in game

1. Make a test MO2 profile. Turn off the mod holding `XDI.dll` and
   `XDI - Main.ba2`, but keep XDI.esm, because the build's plugins have it
   as a master.
2. Install `output/fo4_dialogue_menu/` as a mod placed above F3NV, so its
   F3NV.dll and `Interface/DialogueMenu.swf` win. Enable
   F3NV_MenuTest.esp. F3NV_MenuHub.esp is optional: it needs YUP and goes
   after it.
3. In game, type `set F3NVMenuTest to 1` (or 2) in the console, then talk
   to any NPC.
4. **What to check in F3NV.log:**
   - `dialogue menu: hooked, player line skip ready`;
   - one `option i: …` line per listed option;
   - `picked …` when an option is chosen;
   - `NPC slot answers …` or `NPC Response answers …` with the answer
     INFO, never 00000000;
   - the menu's own `key …` / `event …` lines, the first time each one
     is seen.

## <a id="converter"></a>The converter switch, and what it saves

Measured on the 2026-11-10 FalloutNV.esm (V): 158,223 INFO (77 MB),
69,923 DIAL, 16,879 SCEN; 96 MB of the 315 MB plugin is dialogue. Menus:
11,375 scenes; 65,012 answers (10,797 distinct line parts, 6.0 copies
each), 53,672 options, 10,947 pads, ~400k gate conditions on options and
pads. Voice: 160,068 files (6.0 GB of the 8.4 GB Main BA2) for 52,549
distinct (line part, voice type, response).

Estimate with our menu (I): ~4.3k menu scenes, ~16–19k options, 0 pads,
~8–10k answer topics, 10,797 answers; total INFO ~45–58k; dialogue bytes
~63 MB → ~9 MB for menus; voice ~1.8 GB. The `quests` stage (30–150 s)
should be 2–3× faster, plus less to write, voice and pack.

Code: `conversation.py` loses the option gates and pads (`_option`,
`_prompt`, `_slot`, `_shared`, `_either`, `_earlier` and their helpers);
answers are built once per FNV topic; `say_topics.prompt_places` goes.
Audits: `menus.py` checks 1–3 and `dlc_overrides.unpaired_menus` are
replaced by a menu → topic map check. Keys, from authored data only:
answer INFO `INFO <line> <part>`, answer DIAL `DIAL answer <topic>`, menu
by the line owning the Choices list, option `<menu> <topic>`, so a mod's
edit overrides the master's in place. Every dialogue id moves once: a
planned save break.

## <a id="no-dll"></a>A saving that needs no DLL

**The game's menus are built five times (V).** 1,816 of the 4,327
distinct menus are rebuilt in full in GREETINGS and in four other quests
(VFreeformBlackMountain 000E61A4, VDialogueRaul 000E61A5,
VFreeformMcCarran 000E7363, VFreeformFreeside 0010E195), each with its own
`menu hub` scene and ~10.5k answers: 41,980 of the 65,012 answers. Likely
cause (I): each quest's `Conversations` keeps its own placed list, so a
talk that leads back to the Topic list rebuilds the whole conversation in
that quest. Fixing it under XDI cuts about two thirds of the answer
copies (and their voice files), but moves those ids: also a save break.
