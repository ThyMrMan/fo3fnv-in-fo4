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

### <a id="vulpes-clean-start"></a>Vulpes from a clean start

The scene comes from the export (`VNiptonSceneControlScript`,
`VNiptonSceneVulpesTrigger01Script`) and the 2026-11-10 built plugin.
YUP ships its own copy of the control script; the logic below is the
same.
- **What drives it:**
  - VNipton starts with the game, so no quest needs starting.
  - Code box `VNiptonCodeBox`: a timer runs while its cell is loaded.
  - The player enters one of four "Start the Show" trigger volumes around
    the town (base 16B090), which sets the code box's `bVulpesTrigger`
    to 1.
  - When the player is within 2,500 of `VNiptonVulpesMeet01` and
    `FNV_vStoryEventVulpesDead` is 0, the code box enables Vulpes. He is
    an initially-disabled actor *outside* the Town Hall door, not inside
    it.
  - About 7 seconds later, after he and his six guards get their travel
    packages, `iVulpesAppears` becomes 2.
  - When the player is within 600 of `VNiptonVulpesSceneMarker`, he gets
    `vNiptonVulpesDialogueForce` and `bVulpesTalks` becomes 1.
- **The force-greet package's conditions** (FO4 GetVMScriptVariable on the
  code box ref): player distance < 2000, `bVulpesTalks` == 1,
  `iVulpesLeaves` < 1.

**Ids.** In the table, xx is FalloutNV.esm's load index in the game,
which depends on the load order. In xEdit the same ids read 03xxxxxx. To
find xx in game, run `help "Vulpes Inculta" 4`: his NPC_ id is xxEF0853.
- FNV refs keep their FNV object id.
- Actors are renumbered by key (`ACHR 0013BF5B STH` in
  FalloutNV.formids.tsv).

| What | In game | Persistent | Where (x, y, z) |
|---|---|---|---|
| Code box (`VNiptonCodeBox`, FNV 0016B097) | xx16B097 | yes | −33280, −95123, 7906 (≈1100 above the ground) |
| Scene marker (FNV 0016B095) | xx16B095 | yes | −33155, −91760, 6785 |
| `VNiptonVulpesMeet01` (FNV 0013BF67) | xx13BF67 | yes | −33157, −91979, 6822 |
| Vulpes, placed (FNV 0013BF5B) | xx893C9C, initially disabled | yes | −33136, −91052, 6945 |
| Vulpes NPC_ (FNV 001300E2) | xxEF0853 | | |
| Triggers: west road, south, east, small | xx171B8D, xx16B0AC, xx171B8C, xx171B8E | no | −34709,−92014; −33170,−93610; −31655,−91719; −32519,−92888 |
| Quest; global | `FNV_VNipton`; `FNV_vStoryEventVulpesDead` | | |

The Nipton exterior cells have no EditorID, and the triggers are not
persistent, so console `moveto` can't reach them from another cell. The
code box can be reached: it is persistent, about 1,500 south of the south
trigger, and outside every trigger.

**Recipe (no save needed):**
1. From the main menu: `coc qasmoke`, then `tgm`. You arrive 1,100 units
   above the ground and fall.
2. `help "Vulpes Inculta" 4` gives xx.
3. `player.moveto xx16B097`.
4. Check the starting state:
   - `GetQuestRunning FNV_VNipton` should be 1.
   - `prid xx16B097`, then `sv`: `bVulpesTrigger`, `iVulpesAppears`,
     `bVulpesTalks` and `iVulpesLeaves` should all be 0.
   - `xx893C9C.GetDisabled` should be 1.
5. Walk north up the road into town, which crosses the south trigger after
   about 1,500. Run `sv` on the code box again: `bVulpesTrigger` should be
   1, and `iVulpesAppears` 1, then 2. Vulpes walks out of the Town Hall.
6. Keep walking north to the front of the Town Hall, within 600 of the
   scene marker. `bVulpesTalks` becomes 1, and Vulpes walks up and starts
   talking. His GREETINGS line opens the Topic list (hub 03D4727A /
   03447EEE), and that is our menu.

**If a step stalls, force it, in this order:**
- `set FNV_vStoryEventVulpesDead to 0`
- `xx16B097.SetPV bVulpesTrigger 1` (the trigger did not register), then
  stand within 2,500 of xx13BF67 so the code box enables him;
- `player.moveto xx16B095` (puts you at the marker);
- last resort, when he stays disabled: `xx893C9C.Enable`, then
  `xx16B097.SetPV iVulpesAppears 2`. That skips his walk-out and his
  guards. Then walk within 600 of the marker, so the code box adds the
  package itself.
- Never set `bVulpesTalks` by hand: the code box adds the package only
  while it is 0.

A save made at step 3 replays the test. `iVulpesLeaves` turns to 1 when
the force-greet package ends; after that, the package's conditions fail
and he leaves.

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
    topic's first passing INFO, chosen by the engine's picker (0x698DB0)
    once, then the same INFO each time that action asks again
    ([retries](#answer-retries)).
  - Options below 5 go to the vanilla functions unchanged.

**Menu movie.** `fo4_import/dialogue_menu/movie.py` reads
`Interface/DialogueMenu.swf` from the user's `Fallout4 - Interface.ba2`.
FFDec compiles our own `as3/DialogueMenu.as` over the game's class
(`fo4_import/base/ffdec.py`, shared with the casino movie). The result is
cached under `temp/` and written only to an output folder.
- The list is a 640-wide box in FNV's style: an outline, the selected row
  outlined, and up/down marks joined by a line in the box's left column
  when it scrolls (HUD color, outline, marks and the wheel lock confirmed
  in game 2026-11-10). Its bottom is 36 above the safe area's
  bottom; it shows 5 rows, and a long prompt wraps. Said options are
  dimmer.
- **Colors follow the player's HUD color (V):** DialogueMenu's
  `registerObjects` (callback 0, 0x1043D19) makes each registered holder a
  BSGFxShaderFXTarget and calls 0x1043EF0 with type 0, which goes to
  0x1B04500 with HUD color type 2 (GameplayHUDColor, stored at +0xA8). That
  sets a color multiplier over the holder, so the list, which lives in the
  Question holder, draws its text, outlines and marks in white and shows
  them in the HUD color (confirmed in game with a pink HUD color). Nothing
  is hard-coded to a color.
- **No translucent fills in a HUD-colored holder (V, measured).** In the
  pink-HUD screenshot (HUD 255,128,255) every drawn pixel is opaque: the
  0.5 scroll line reads 131,62,131 over both a 24,14,12 and an 86,40,20
  floor, the 0.3 mark 81,38,81, the 0.08 row fill 21,10,21, and the 0.2
  black backdrop 0,0,0. Alpha only darkens the color; only undrawn pixels
  show the scene. So the movie draws no backdrop. Its backdrop is the
  game's own shaded background, which vanilla menus turn on with
  `EnableShadedBackground(target, 1, 1.0)` (0x1B04350; type 1 is
  MenuNoColorBackground, as at 0x107C30B and 0xA492E4): one quad over the
  target's bounds (0x1B04AB0), drawn by the UI shader. F3NV.dll's
  `ShadeList(on)` turns it on for the Question holder (menu +0xF8, checked
  against the shader target vtable 0x27236D0) and off by clearing flag bit
  0 at +0x8C. To keep that holder's bounds equal to the box, the movie
  moves it to the box's middle and empties the hidden buttons' text.
  Confirmed see-through in game (played 2026-11-11). A menu that first shows none of ours asks again each frame for
  30 frames before leaving the game's buttons.
- **Escaped prompts.** The build writes `&`, `<` and `>` in player lines as
  `&amp;`, `&lt;` and `&gt;`, because XDI shows option text as HTML
  ([xdi-html](fo4_pipeline.md#xdi-html)). This menu and vanilla's
  BSButtonHint show plain text (`GlobalFunc.SetText(tf, text, false, true)`),
  so the movie decodes the three entities wherever text comes in
  (`GetDialogueOptions` and `SetButtonText`) before upper-casing it.
  `&lt;Keep holdout weapons&gt;` showed as `&LT;KEEP HOLDOUT WEAPONS&GT;`
  (played 2026-11-11).
- **Keys:**
  - arrows, W/S, the mouse wheel, or the gamepad's Quickkey up/down move;
    F3NV.dll keeps the wheel from the camera while a choice waits. The
    wheel reaches the camera through the camera states' "should handle"
    tests (V): FirstPersonState (0x10213E0) takes ZoomOut,
    ThirdPersonState (0x102DFC0) both; F3NV.dll refuses ZoomIn/ZoomOut
    there. CameraZoomHandler (0x10784D0), blocked first, was not the path
    (played 2026-11-10);
  - Enter, E (Activate), 1–9, a click, or gamepad A pick;
  - Tab, Esc or Cancel leave the talk.
- With no DLL, or no linked options, it lists the game's own four buttons.

### <a id="links-file"></a>The links file

The DLL reads `Data\F4SE\Plugins\F3NV_Menus\*.txt` the first time a menu
opens. Each build writes `<plugin stem>.txt` there beside its plugin
(`fo4_import/dialogue_menu/__init__.py`). Lines are tab-separated, `#` starts
a comment, object ids are hex:

- **Four columns, a link:** option plugin, option INFO, answer plugin,
  answer DIAL. Kept only when the option is an INFO and the answer a DIAL.
- **Five columns, a skill check:** answer plugin, answer INFO, actor value
  plugin, AVIF, number needed (decimal).
- **Seven columns** (the hub rebuild's): a link with its option's check.
  Still read.

The log line is
`dialogue menu: <file>: N links, M resolved, K skill checks`. A file named
`F3NV_MenuHub.txt` (the XDI-era hub) is still read and logged `DEPRECATED`;
builds and `fo4_deploy` delete it and `F3NV_MenuHub.esp`.

### <a id="skill-checks"></a>Skill checks (confirmed in game, 2026-11-11)

FNV shows a check against the player's current value: `[Speech 25]  text`
on a pass, `[Sneak 14/50]  text` on a fail (FalloutNV.exe's strings `[%s`,
`%s %d/%d`, `%s]  %s`: two spaces after the bracket). The plugin keeps the
build's baked `[Name N] text` as the no-DLL fallback.

- **Build** (`fo4_import/spike/skill_tags.py` `tag_check`): a prompt's
  check is the first condition among the lines sharing that prompt that is
  `GetActorValue` on the player (run on target, or on reference PLAYER) of
  a skill or SPECIAL, not a global. Every answer line with that prompt
  carries the tag and a five-column check row, so the failing line (the one
  that plays when the check fails) shows the failed tag. Measured on the
  hub rebuild (FNV + YUP): 4,481 of 4,496 tagged options matched; 15
  `[Endurance 9]` prompts test Endurance > 6 (an authored mismatch).
- **DLL**: the option shows the prompt of the answer line `Pick` chose
  (FNV shows the first passing line's), else the option's own. `Tagged`
  rewrites its tag from `player->actorValueOwner.GetValue(av)`, using that
  line's check row, else the option's, and flags a failed row.
- **Color** (V): DialogueMenu colors each registered holder through
  0x1043EF0(menu, target, type, dim). Type 0 is the HUD color; 1/4/5,
  2/6 and 3/7 are the speech-challenge tints `iDialogueSC_Easy/Med/Hard_Tint*`
  (jump table at 0x1043FB8). The game re-tints the four holders on every
  SetButtonText (0x1043539), so the movie moves failed rows into a layer in
  the Negative holder (menu +0xE8), laid over the list, and calls
  F3NV.dll's `TintFailed` on each draw. That native applies type 3 (Hard,
  red) through the same function.

### <a id="answer-retries"></a>Answer retries, and Willow's slow answers (2026-11-11)

Report: NVWillow's Willow pauses for a long time after an option is
picked; FalloutNV.esm's NPCs answer at once.

- **The engine asks the NPC slot again until the NPC can speak (V,
  disassembly).** After the NPC slot (0x415A21) returns a line, the Player
  Dialogue run function returns without saying it, and asks again next
  frame, while any of these hold: the NPC's byte +0x10A is 1 (0x2C6E60,
  called at 0x415AC5; CommonLibF4 names it the reference's model state, 1
  while its 3D loads, I), the NPC has no process (+0x300), or the line has
  no topic. The engine's own function gives the same INFO on every ask.
  Ours answered once and gave nothing after, and a null line makes the
  action end without the NPC's line (0x415A2C to slot 19, 0x415000). It
  now gives the picked line to that action on every ask, and logs
  `+N ms: asked again (n) for <INFO>; NPC 3D loading 0|1` on the first
  ask and every hundredth.
- **The trace runs past the answer.** The `+N ms` wait lines carry on
  until the action ends, with the NPC's 3D loading bit: `NPC line said,
  NPC talking 1` is when the answer starts. The menu's own lines (`menu
  shown`, `menu ready`) carry the time since the pick.
- **Willow's records and files match FalloutNV.esm's (V, measured
  2026-11-11 on the deployed build).** Four of her answer INFOs (03769CE1,
  0377F791, 03965644, 034C1ACB) against four of Doc Mitchell's
  (02AFAB95, 02E94E76, 02651DC2, 02B5C088): the same INFO layout (ENAM,
  TRDA, TSCE + ALFA + Phase0), the same answer DIAL fields, and the same
  next-step scene (FNAM 0x1064, one Player Dialogue action). Her .fuz
  files are present (775 of 785 answer lines and all 267 follow-up lines;
  the 10 missing are `...`-type lines), stored uncompressed like the
  game's, in the same xWMA format (mono 44.1 kHz, 6000 B/s). Her source
  recordings have no leading silence. Her lips are copied frame for frame
  from her .lip files and run 0.23 s past the audio at the median against
  Doc Mitchell's 0.50 s. Multi-response lines are rarer in her mod (9%)
  than in FalloutNV.esm (18%). Speaker idles are on 4.5% of her INFOs.
- **What is hers alone is script load.** Her F3NV.log answers come 0 to
  15 ms after the pick, like everyone's, so the time goes after the
  answer is chosen. About 58 of her scripts fail to compile, so many of
  her quest scripts fail to link or bind. Her freeform quest, her own
  script and her sunglasses item then log a None error with a stack on
  each timer tick: about 6,000 stack lines of the 45,000 Papyrus log
  lines in a 33-minute run. Whether that holds her line back is not measured: the new trace
  says where the time goes.

### <a id="prompt-macros"></a>The player's name in prompts (2026-11-11)

Report: Willow's "My name's &PCName;" showed the macro as written.

- **FNV's rule (V, FalloutNV.exe 0x7070C0, `interface.cpp:5166` in the
  decomp).** `&name;` is, in order: a control's label, a global's value
  (by EditorID), `PCName` (the player's name), `PCRace`, `PCSex`,
  `PCSexPronoun`, `PCSexPossessive` (game settings), then a game setting.
  Names match in any case.
- **Census (FO3, FNV, DLC and mod exports).** `&PCName;` 242 times, in
  five casings: about 190 in note text, 22 in dialogue prompts (INFO
  prompts, DIAL FULL; Willow's included), one NPC_ FULL. `&PCSex;` 10 and
  `&PCRace;` 9, all in notes. The control macros (`&sUActnJump;`, …) are
  in MESG text and the build already writes them as FO4 tags
  (`spike/controls.py`).
- **Prompts: written out by F3NV.dll.** FO4's own replacement
  (`<Alias=Player>`, 39 uses in Fallout4.esm's string tables, in books,
  terminals and messages) needs a quest alias and runs only in the game's
  text menus. Our menu reads prompts raw (0x69E740), and no vanilla
  prompt carries a token, so the DLL writes `&PCName;` and `&PCRace;` out
  when it lists an option (`Expanded`): the player base's name and the
  player's race name. `&amp;PCName;`, from plugins built for XDI, reads
  the same.
- **Not done: notes and messages.** Their 200-odd uses still show the
  macro. FO4's way is `<Alias=Player>` in a book read through a quest's
  book alias with Uses Stored Text, or a message with an owner quest.
  That needs a quest and alias for every note.

### <a id="said-gray"></a>Said options (2026-11-11)

Report: Johnson Nash's "I lost a package I was supposed to deliver." was
dim before it was picked.

- One option stands for an FNV topic, and it shows the prompt of the
  topic's answer line that plays now. Nash's topic (option 089D5980) has
  "I'm a courier with the Mojave Express." first, then "I lost a package
  …". The menu dimmed by the option INFO's said byte, which picking the
  first line set, so the next line came up dim (F3NV.log).
- FNV keeps said on its INFO, which here is the answer line. The menu
  now dims by the said byte of the line that plays (the engine sets it
  when the NPC says it).

### <a id="backdrop-rows"></a>The backdrop under fewer rows (2026-11-11)

Report: Willow's one-option menu had the shaded backdrop running far
below the box. The backdrop is the game's shaded background, sized from
the Question holder's bounds. Flash counts hidden children in a
container's bounds, and the rows beyond the menu's count were only hidden,
keeping the text and place of the last longer menu. Unused rows now leave
the holder (`draw`).

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
- `tools.dialog.menu_rebuild` (the hub plugin rebuilt from XDI-built
  menus) is gone: the build makes menus in this model itself
  ([converter](#converter)).

### <a id="vulpes"></a>Vulpes Inculta's Topic list (GREETINGS hub)

- **The hub:** P0 03D4727A, N 03447EEE. FalloutNV.esm has 2,656 player
  and 2,656 NPC lines there. YUP overrides or adds 35 of each.
- **Both "I'll do as you ask" options** (03330928, 0331C0EE) pair with
  the End Scene answer ("Then I bid you 'Vale'", 035AA687 / 03AEAEEE,
  flags 0x44) in the game build and with YUP over it. Offline, the pairing
  is not broken. Why the conversation does not end in game is not known.
  The DLL trace names the answer the engine actually plays.
- **The rebuild** of FalloutNV.esm + YUP gives F3NV_MenuHub.esp (27 MB):
  - 11,518 scenes with menus, 11,765 menus, 54,466 options and 65,529
    answer copies under 13 quests; 8 options have no answer, 53 sit in two
    menus and keep their first;
  - `fo4_ref_check` found 0 unresolved references among 518,234 in
    120,008 records. Another 513 go into masters it was not given (XDI and
    the DLCs).
- **Vulpes's talk (V, data):** his force greet plays the silent Greeting
  line (033AA035), whose script opens the GREETING scene. His line there
  ("I was just finishing up making an example of this town…", 03ECC85F)
  starts Scene6624, two speech lines; the second (03E8601C) starts the hub.
  His other GREETING lines ("How interesting! You're the Profligate
  courier…") start Scene6620 instead, a menu of its own (player topic
  0358C4EA) that only GREETING lines start. The hub-only rebuild left it
  unlinked, so the 22:51 play showed the game's single button there; the
  all-menus rebuild lists his options there (23:17 play). F3NV.dll logs a
  menu with none of ours once:
  `none of ours in scene … with NPC …: lines, linked, pass, answered`.
  - Both Vulpes options link to an answer topic whose only line shares
    the End Scene answer.
- **Not yet built:**
  - The engine's `IsPlayerTalking` fix;
  - speech challenges (the text and odds are not added to the prompt);
  - text replacement in prompts.

### <a id="setup"></a>Trying it in game

1. Turn off XDI (the install check reports it as a CONFLICT). Builds made
   since the [converter switch](#converter) no longer master XDI.esm.
2. For the demo, install `output/fo4_dialogue_menu/` as a mod placed above
   F3NV and enable F3NV_MenuTest.esp. A converted game needs nothing more:
   its build ships the DLL, the movie and its links.
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

### <a id="converter-built"></a>As built (2026-11-11)

**Code:** `fo4_import/spike/conversation.py`, `fo4_import/dialogue_menu/__init__.py`,
`tes_runtime/fo4_condition/dialogue.cpp`.

- **A menu** (FNV Choices, or the Topic list) is one Player Dialogue
  action: one player topic holding an option per FNV topic, then `[Leave]`
  on the Topic list (and on a Choices menu that can never end), beside an
  empty NPC topic. No pads, no gate conditions, no XDI keyword; plugins no
  longer master XDI.esm. A menu ends its scene; the answer starts what
  follows.
- **An option** shows its topic's first line's prompt (tagged with its skill
  check), on the topic's AddTopic gate only. F3NV.dll lists it while one
  line of its answer topic passes, and shows that line's prompt.
- **An answer topic** is built once per FNV topic for the whole build
  (`Hub.answers`): every line of the topic in Hub order, each with its own
  prompt and conditions, starting what its FNV line leads to with the
  speaker forced into the Speaker alias (ALFA; 65 vanilla cross-quest TSCE
  lines carry ALFA 0). `[Leave]` links to one silent End Scene answer.
- **Shared steps live in one quest.** Every step any quest reaches (not a
  chat's or a `TES4Talk_` talk's own) is built once, in the generated
  start-game Greetings quest (`Hub.home`), so a quest that stops cannot
  take a shared scene with it, and no menu is built twice. This replaces
  the five copies of [no-dll](#no-dll). The Greetings quest is written after
  every cell quest.
- **The links file** lists each option → answer topic and each tagged answer
  line's check ([links-file](#links-file)); the masterless build also
  installs the menu movie when FFDec and the game's Interface archive are
  there.
- **Keys** (authored data only): answer DIAL `DIAL answer <FNV topic>`,
  answer INFO `INFO <line> <part> at answer`, menu topics
  `DIAL <step> options|answers`, option `INFO option <step> <FNV topic>`,
  where `<step>` names the FNV Choices topics (or `menu hub`). A DLC that
  derives the same key reuses its master's record in place.
- **Folded in:** tool-audit F2 (holotape copies keyed by their note), F3
  (no split options any more), F5 (Say Once stages numbered in FormID order
  before use); see [fo4_tool_audit.md](fo4_tool_audit.md#formids).
- **Audit:** `preflight/menus.py` checks the links file against the
  plugin's menus (every option linked; every link from a menu option to an
  answer topic with a line, the plugin's or a master's; every check on an
  INFO and an AVIF). It replaces checks 1–3, `xdi_menus` and
  `dlc_overrides.unpaired_menus`.
- **Save break:** every menu and scene dialogue id moves once (approved).
  Quest Say topics, barks, greetings, holotapes and radio keep theirs.
- **Measured** (V, 2026-11-11): the GSDocMitchellHouse test-cell build
  (every quest's dialogue), before → after: DIAL 6,576 → 2,008, INFO
  4,139 → 3,090, SCEN 1,493 → 513, dialogue 3.6 → 1.9 MB, plugin 9.6 →
  7.8 MB, `quests` stage 5.8 → 5.0 s; 560 options linked, 24 skill-check
  rows, the links audit clean. Against the deployed ledger, 3,278 of the
  build's 11,638 keys are new (all menu, answer and shared-step records,
  and 773 line copies); 8,360 keep their ids.

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
Fixed by the switch: every shared step is built once, in `Hub.home`
([as built](#converter-built)).
