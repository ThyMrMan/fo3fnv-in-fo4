# Dialogue menu as a standalone mod (XDI replacement)

A plan to turn the converter's dialogue menu
([test-build plan](fo4_dialogue_menu_plan.md)) into a Nexus mod that can
take XDI's place in any Fallout 4 load order. Part of the
[spin-off plan](spin_offs.md). Status lives in the [roadmap](ROADMAP.md).
**V** = read in source or code, **S** = from search results only.

## <a id="goal"></a>Goal

A player removes XDI, installs ours, and:
- vanilla dialogue shows as a full-text list, as with XDI;
- every mod built for XDI (Fallout: London, Brothers in Arms and others)
  still lists all its options;
- mods built for our menu get more: any number of options, answers linked
  by topic instead of by position, icons, skill-check tags.

It ships no Bethesda file, runs on old-gen and next-gen, and can be
configured and themed without editing Flash.

## <a id="xdi-today"></a>XDI today

- **Maintained on Nexus, closed elsewhere.** GitHub `reg2k/xdi` (no license,
  last pushed 2020, V) stops at 1.3.x. Nexus has 1.3.6 for 1.10.163, 1.4.3
  (Dec 2025) for 1.11.191 and a build for 1.11.221 (Jun 2026) (S). Who
  maintains these, and whether 1.11.240 is covered, is unknown.
- **Why ours is still worth it:** no license, so nobody can fix or port it;
  options and answers are paired by position, which breaks when a mod
  shifts a menu ([robustness research](research/fo4_dialogue_robustness.md));
  every game update waits on one person's rebuild; it ships its own
  `DialogueMenu.swf`, so it fights FDI and other UI mods.
- **Its rules (V, from the GitHub source; read for understanding, never
  copied):**
  - Active only when the player's current scene has keyword `XDI.esm:000800`,
    or a keyword another plugin names in `Data\XDI\*.ini`
    (`[XDI] Plugin= ActivationKeyword= ResultGlobal=`).
  - Every non-empty player INFO in the action's four topics becomes its own
    option. NPC answers pair by index: from the option's index up to the
    next non-empty player INFO. With no NPC INFO it looks one phase ahead
    for an NPC Response action.
  - Extras: a "scene link" on an INFO (jump to scene and phase), Say Once,
    text replacement, unvoiced player lines skipped.
  - Papyrus script `XDI`: `GetVersionCode`, `GetSceneLink`, `SetSceneLink`,
    `ResetSaid`.
  - Per option, Flash gets: prompt, response, enabled, said, challenge
    level and result, linked to self, ends scene, barter, inventory.
  - Settings (MCM): wrap text, dim spoken, icons, question icon, option
    numbers, 1–9 hotkeys, subtitle position, brackets, shaded background,
    debug.
- **Who requires it (S):** Fallout: London (ships its own copy), CSEP's
  Brothers in Arms, Point Lookout, Conquer the Institute and others. Sim
  Settlements 2 works with it but doesn't require it.

## <a id="have"></a>What we have

The menu is played in parts: HUD color, scrolling, the shaded backdrop and
skill-check tags were checked in game on 2026-11-10/11
([as built](fo4_dialogue_menu_plan.md#as-built)). It works like this:

- **Links files** `Data\F4SE\Plugins\F3NV_Menus\*.txt`, tab-separated:
  option INFO → answer topic, plus optional skill checks
  (`dialogue.cpp` `ReadLinks`). An INFO in a links file is "ours". The
  answer is the answer topic's first passing line, chosen by the game's own
  picker (`0x698DB0`).
- **Anything else** (vanilla, other mods) falls back to the game's four
  button texts drawn as a list, plus `[Leave]`.
- **Steps aside** when `XDI.dll` is loaded. It reads nothing of XDI's, so a
  mod built for XDI shows only vanilla's four options.
- **The movie** is our own (since 2026-11-11): only our AS3, built like the
  casino's ([own movie](fo4_dialogue_menu_plan.md#own-movie)). It can be
  shipped.
- **No settings:** 5 rows, 640 wide, font 18, keys fixed in the AS3.
- Raw 1.11.240 addresses, inside F3NV.dll.

Not built yet: speech challenges (text and odds), text replacement in
prompts, the engine's `IsPlayerTalking` fix
([open items](fo4_dialogue_menu_plan.md#as-built)).

## <a id="swf"></a>Front 1: our own movie, nothing of Bethesda's

### What the engine needs from the movie

Reading our `DialogueMenu.as` against the vanilla contract it mirrors:

| Direction | Calls |
|---|---|
| Engine → movie | `SetButtonText(i, text)` (button 3 arrives last), `ShowButtonHelp`, `HideButtonHelp`, `EnableMenu`, `DisableMenu`, `PlaySpeechChallengeAnim`, `ProcessUserEvent(name, down)`, `onSetSafeRect` |
| Movie → engine (`BGSCodeObj`) | `registerObjects(Positive, Negative, Neutral, Question, SpeechChallengeAnim)`, `onButtonRelease(i)`, `OnSpeechChallengeAnimComplete()` |
| F4SE → movie | `onF4SEObjCreated(f4se)`, giving `f4se.plugins.<ours>` |

`registerObjects` matters most: the engine turns those five clips into
shader targets and tints them with the HUD color, and our DLL's backdrop
and red tint act on the same targets. None of this needs Bethesda's art.
The five clips can be empty Sprites our code builds and draws into.

### What we take from vanilla today, and its replacement

| Vanilla piece | Replacement |
|---|---|
| `Shared.AS3.IMenu`, `GlobalFunc` (safe rect) | Our own small base class. Safe-rect math is a few lines |
| `FadeHolder_mc` and the four holders, timeline labels | Sprites built in code; show and hide tweens in code |
| `BSButtonHint` bar | Our own hint bar. No open-source clean one exists; it reads the platform from `uiPlatform` and draws key names or the `$Controller_Buttons` font glyphs |
| `SpeechChallengeAnim_mc` | Our own short animation in code that calls `OnSpeechChallengeAnimComplete` |
| Fonts | `$MAIN_Font` and `$MAIN_Font_Bold` by name with `embedFonts`. The casino movie proves this works with no imported library. The game maps the names through `FontConfig.txt`, so every language's fonts apply |

### Toolchain

- **Apache Flex SDK `mxmlc`** on Java, targeting Flash Player 11.2 / SWF 15
  with only `playerglobal.swc`, no Flex framework. Open repos build FO4
  menus this way headless: `DCCStudios/F4-BetterWeaponScrapping` (MIT) and
  `ReidenXerx/fo4-silhouette` (GPL-3). We build the SWF once at release and
  ship it, so players need no Java.
- Or keep our FFDec route: `casino/movie.py` writes a deterministic
  skeleton and FFDec compiles our AS3 over it. Its output is ours alone, so
  it ships too. **Pick mxmlc** for the mod: it's the standard compiler,
  reports errors properly, and needs no skeleton. Its output carries a build
  date, stripped after the build; the full comparison is in the
  [Flash framework plan](swf_framework.md#toolchain), which this menu is
  built on.

### The spike that decides it

The casino's movie is an F4SE custom menu and lost the HUD tint
([casino notes](fo4_casino_plan.md)). Untested: a from-scratch movie
loaded **as** `DialogueMenu`, where the engine itself calls
`registerObjects` and tints. Test that first: a minimal movie with five
empty holders and a text list, installed as a loose
`Interface\DialogueMenu.swf`, run with the current DLL. If the tint
applies, everything else is ordinary AS3 work. If not, the DLL tints the
holders itself (it already reaches them for `ShadeList` and `TintFailed`).

### Why this helps the converter too

- No install step reads `Fallout 4 - Interface.ba2`, and no Java or FFDec on
  the player's machine. The converter's own install gets simpler.
- A built movie can be versioned and tested like code; the pre-push rule
  against `.swf` files only has to allow our own build output.
- The casino menus can move to the same build later.

## <a id="fo4-dialogue"></a>Front 2: FO4 dialogue, not just FNV dialogue

Today the menu knows two kinds of menu: ours (links files) and everything
else (four buttons). The mod needs four sources of options, picked per
menu in this order:

| Mode | When | Options | Answers |
|---|---|---|---|
| **Linked** (ours) | The option INFO is in a links file or carries our keyword | Every linked INFO that passes | The answer topic's first passing line (the game's picker) |
| **XDI** | The scene has `XDI.esm:000800` or a keyword from `Data\XDI\*.ini` | Every non-empty player INFO in the four topics | XDI's index ranges, then one phase ahead |
| **Vanilla, expanded** | Optional (setting): any other scene | As XDI mode | As XDI mode |
| **Vanilla** | Any other scene | The game's four, full text | The game's own |

What has to change in the DLL:

- **XDI mode.** Implement the pairing rules above from their description,
  never from XDI's code. Read `Data\XDI\*.ini` in the same format so
  existing mod setups work.
- **`XDI.esm` stand-in.** Mods that require XDI list `XDI.esm` as a
  master, so it must exist. Ship a stand-in with the same two records
  (keyword `000800`, global `000801`) and nothing else, plus a Papyrus
  script `XDI` with the same four functions on our natives. **Decision
  needed:** ask XDI's authors first. Taking a mod's file name is a courtesy
  question, not just a technical one.
- **Per-option data**, as XDI gives it, filled from engine state for every
  mode: said (INFO byte `+0x43`, already read), speech challenge level and
  result, loops back to the same menu, ends the scene, barter
  (`VendorInfoScript`), inventory (`OpenInventoryInfoScript`). These drive
  the icons.
- **Speech challenges.** Vanilla's challenge colors and odds, and FNV-style
  `[Skill v/N]` tags for linked menus. The FNV tag stays a linked-mode
  feature.
- **Scene links** (`Get/SetSceneLink`): kept per INFO in the co-save.
- **Leaving.** `[Leave]`, Tab and Esc stop the player's scene. In a quest
  scene with no exit that can break the quest. Only offer Leave where the
  vanilla menu would let the player walk away, or behind a setting.
- **Answer correctness.** Linked mode already uses the game's picker, so
  Random, conditions and Say Once behave as vanilla. XDI mode must keep
  XDI's index pairing exactly, or XDI mods lose lines.
- **Converter side.** The FNV build keeps writing links files. Rename the
  folder to the mod's own (`Data\F4SE\Plugins\<Mod>\Links\`) and keep
  reading `F3NV_Menus\` as `DEPRECATED`
  ([end-user state](../../CLAUDE.md#end-user-state)).

## <a id="config"></a>Front 3: settings, themes, icons and an API

### Settings: one INI, MCM-ready

`MCM\Config\<Mod>\settings.ini` holds the defaults and `MCM\Settings\<Mod>.ini`
the user's changes, the layout MCM and XDI use, so players get an in-game
settings page without us writing one. Per-feature switches:

| Group | Settings |
|---|---|
| Modes | XDI mode, vanilla expanded, linked mode |
| List | rows shown, width, font size, position (anchor and offset), wrap, brackets, option numbers, 1–9 hotkeys, dim said, shaded background and its opacity |
| Icons | on/off, per-icon on/off, icon size |
| Leave | show `[Leave]`, which keys leave, where allowed |
| Keys | up, down, choose, leave (key codes) |
| Speech | challenge colors, odds shown, FNV skill tags |
| Debug | log level, Flash log |

The DLL reads the INI and passes it to the movie in one call, so the movie
never reads files itself.

### Themes and icons

- **Icons** are loose DDS files in `Interface\<Mod>\Icons\`, loaded with
  F4SE's `MountImage` (the casino movie already loads DDS this way). Users
  replace or add icons without touching the SWF.
- **Built-in icons:** question / loops back, ends conversation, barter,
  inventory, speech challenge (by level), quest-related, said.
- **Which icon an option gets**, in order: an icon an author set (API or
  links file), then a rule in `Data\F4SE\Plugins\<Mod>\Icons\*.ini`
  (keyword on the INFO or its topic, or its quest → icon), then the
  built-in flags.
- **Theme file** (colors on top of the HUD color, fonts by `FontConfig.txt`
  name, row spacing) so UI packs like FallUI can ship a matching look.
  Strings (`[Leave]`, tags) come from `Interface\Translations\<Mod>_<lang>.txt`;
  the whole approach, fallback, fonts and checks are in the
  [Flash framework plan](swf_framework.md#translations).

### For mod authors

- **Links files** become a documented format with a version header and
  optional columns: option, answer topic, skill check, icon, sort order.
- **Papyrus** script `<Mod>` (prefix to pick): `GetVersion`, `SetOptionIcon(TopicInfo, String)`,
  `SetOptionText`, `HideOption`, `LinkAnswer(TopicInfo, Topic)` at
  runtime, `ResetSaid`, scene links, `IsActive`.
- **Events:** an F4SE custom event (Papyrus) when a menu opens and when an
  option is picked, so other mods can react without hooking.
- **Example plugin** with one scene using linked options, and one using
  XDI-style authoring.

## <a id="beyond-xdi"></a>What we offer beyond XDI

Matching XDI only gets players to switch at no loss. The reason to switch
is what FO4 dialogue modding still lacks next to Skyrim SE. From a survey
of both games' dialogue mods (2026-11-11, mostly search results, so **S**):

| Gap in FO4 | Skyrim SE has | What we bring | How close we are |
|---|---|---|---|
| **Add dialogue to any NPC** without editing their scenes | Topic-based dialogue: any mod adds a topic to any NPC | A **topic list** ("ask about…") in any conversation, filled by any mod's topics with their own conditions. FO4's scene-only dialogue has no equivalent | Built for the FNV conversion: options link to topics, the game's picker answers |
| **Data-driven overrides**: add, hide, rename or replace options and NPC lines from files, no plugin edits | Dynamic Dialogue Replacer (YAML, conditions, priorities) | Our links files grown into rule files: inject, hide, rename, re-answer, with conditions and priority | Links files exist; conditions and overrides are new work |
| **Mods adding options to the same menu break each other** | n/a (topics don't collide) | Answers linked by topic, so two mods' options sit side by side. XDI pairs by position | Built |
| **Speech checks are opaque** | Dialogue tags mods | `[Charisma 6/8]` tags, success odds for vanilla challenges, failed checks colored | Tags built for FNV skills; odds need the challenge formula read from the exe |
| **No dialogue history** | Dialogue History (po3): searchable log, ambient lines too | A log of every line heard, with speaker and quest, behind a hotkey | Our hooks already see every option and answer; ambient lines need the hook our Skyrim flight recorder uses (`dialogue_capture.cpp`), ported |
| **No "already heard" or quest markers** | Smart Talk (2025), vanilla used-topic graying | Markers for said, new, leads somewhere new, quest-related; exposed so themes can style them | Said is read; the rest is new |
| **No skip or pacing control** | Instantly Skip Dialogue, Smart Talk | Instant or hold-to-skip, auto-advance for unvoiced lines | New |
| **Blank options** need per-mod patches | n/a | When an option has no text, show its paraphrase or the answer's text | Partly built: we already fall back to the answer line |
| **"XDI is not running" after updates** | Address Library culture | One DLL for every runtime, plus a status line saying why a feature is off (call site changed, conflict found) | The call-site check exists; the message is new |
| **Authors can't see why an option is missing** | Console tools, no in-menu one | A **debug inspector**: every candidate line for this menu, which condition failed, which rule hid it | New, but it's the preflight audits' idea moved into the game |
| **Thin author API**: XDI's is one scene keyword | Papyrus Extender, SKSE events | Events (menu opened, option shown, option picked, line spoken), functions to add or change options at runtime | New |
| **AI dialogue sits outside the menu** | Mantella, CHIM, SkyrimNet (menu integration planned, not built) | An **option provider** interface: another DLL or script adds options to the live menu. An AI mod can offer "Say something…" and hand back to vanilla topics | New; the provider interface is the same one the topic list needs |

### Where this leads

The pitch is a **dialogue framework** for Fallout 4, with the menu as its
face: topics any mod can add to any NPC, rules files instead of plugin
edits, open scoring of speech checks, a history, and tools that show
authors what happened. XDI compatibility is how players get in without
losing their mods. It is not the reason to install it.

### Left out

- **Camera.** Several FO4 mods handle the dialogue camera, and Sim
  Settlements 2 needs the vanilla one. Stay compatible; add nothing.
- **Companion affinity preview** ("Piper will like that"). FO4 fires
  affinity from scripts on the chosen line. Reading those reliably needs
  research first; park it.

## <a id="runtime"></a>Game versions

- Use **Dear-Modding-FO4/commonlibf4** (GPL-3.0 with the modding
  exception): one DLL for old-gen 1.10.163, next-gen 1.10.980/984 and the
  1.11.x line. `F4SEMenuFramework` and the FO4 OAR port already ship one
  DLL across those on it. Chosen 2026-11-11 over LucaDotGit's "AV" fork,
  with a local fix so an unknown newer game version doesn't terminate the
  game ([comparison](research/commonlibf4_forks.md);
  [plan](spin_offs.md#runtime)). Not `libxse/commonlibf4` (one runtime per
  build) or `alandtse/CommonLibF4` (stops at 1.10.984, but has VR:
  [platforms](spin_offs.md#platforms)).
- Turn the 19 dialogue addresses into Address Library IDs (7 are already
  known, in [the engine table](fo4_dialogue_menu_plan.md#engine)), then
  match each function in the 1.10.163 exe.
- Keep the existing check: when a call site doesn't hold the vanilla call,
  log it and leave dialogue to the game.

## <a id="parity"></a>Parity checklist

| XDI feature | Ours today | Needed for release |
|---|---|---|
| Unlimited options | Linked menus only | All modes |
| Full-text vanilla options | Yes (list of four) | Yes |
| XDI-authored mods | No | XDI mode + `XDI.esm` stand-in |
| `Data\XDI\*.ini` activation | No | Yes |
| Papyrus `XDI` script | No | Same four functions |
| Icons (question, door, barter, inventory) | No | Yes, replaceable DDS |
| Option numbers, 1–9 keys | Keys only | Both, switchable |
| Gamepad (D-pad, A, B, correct glyphs) | Wired, never played with a pad | Played start to finish on a pad ([controller support](swf_framework.md#controller)) |
| Dim said | Yes | Switchable |
| Shaded background | Yes | Switchable, opacity |
| Subtitle position | No | Yes |
| Speech challenge display | No (FNV tags only) | Vanilla colors and odds |
| Scene links | No | Yes |
| Text replacement | No | Yes |
| MCM settings | No | Yes |
| Old-gen and next-gen | 1.11.240 only | Both |
| Ships no Bethesda file | No | Yes |

## <a id="phases"></a>Phases

1. **Movie spike:** the five-holder movie as `DialogueMenu.swf`; does the
   engine tint it? (Front 1.) **Done:** played 2026-11-11, the engine tints
   it ([spike 3](swf_framework.md#spikes)).
2. **Own movie:** the list, hint bar, speech animation and safe rect, built
   by `mxmlc`, replacing the FFDec patch in the FNV build too. **Partly
   done:** the list and safe rect on our own movie (played 2026-11-12), on
   `mxmlc` and `f3ui` (built, not played). Not built: the hint bar (waits for
   the library's `HintBar`) and a speech animation.
3. **Shared base and its own DLL:** CommonLibF4 (Dear-Modding), Address Library, xmake;
   `dialogue.cpp` moves out of F3NV.dll ([spin-off plan](spin_offs.md#runtime)).
4. **Modes:** XDI mode, vanilla expanded, per-option flags, Leave rules.
   Test against one XDI-requiring mod and Sim Settlements 2.
5. **Settings, icons, theme, translations, the Papyrus API and events.**
6. **The framework features** ([beyond XDI](#beyond-xdi)), in this order:
   topic list and option providers (one interface), rules files, speech
   odds, debug inspector, history, markers, skip and pacing.
7. **Compatibility pass:** FallUI, DEF_UI, Ultra Wide Interface, dialogue
   camera mods, FDI (refuse to load beside it, with a message).
8. **Release:** FOMOD, example plugin, author docs, GPL-3.0 with the
   modding exception ([license](spin_offs.md#license)), Nexus page.
   A first release can stop after phase 5 plus the topic list, if XDI
   parity and one clear new feature are enough to launch on.

## <a id="decisions"></a>Open decisions

- Shipping an `XDI.esm` stand-in, and asking XDI's authors first.
- The mod's name and Papyrus prefix.
- Whether "vanilla expanded" (XDI pairing on every scene) is on by default.
  XDI only does it on keyworded scenes.
