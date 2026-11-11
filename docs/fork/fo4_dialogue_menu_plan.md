# Our own dialogue menu (replacing XDI): test-build plan

Designed 2026-11-10, not built. Why: XDI pairs options and answers by
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
  `BranchTrampoline` (192 bytes, fully budgeted: raise it), patches vtable
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
