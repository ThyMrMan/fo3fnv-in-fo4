# Spin-off mods from F3NV.dll

A plan to release parts of the converter's runtime as Fallout 4 mods that
anyone can use, with or without the FNV conversion. Status lives in the
[roadmap](ROADMAP.md#parked). The dialogue menu has its own plan:
[dialogue menu mod](dialogue_menu_mod.md).

## <a id="why"></a>Why

F3NV.dll already does several things FO4 modders ask for: item condition per
inventory stack, readable from Papyrus; extra Pip-Boy STAT tabs; a dialogue
menu that lists any number of options. Released on their own, they help
people who will never run the converter. The converter then uses the same
releases, so there is one copy of each piece.

## <a id="today"></a>What F3NV.dll is today

One F4SE plugin (`tes_runtime/fo4_condition/`, about 3,200 lines). Each
feature is one file. All features share `condition.h`, and `plugin.cpp`
installs all of them at load.

| File | Feature | Papyrus | Installs |
|---|---|---|---|
| `plugin.cpp`, `repair.cpp`, `vendor.cpp`, `transfer.cpp` | Item condition per stack, repair from spares, vendor repair, CND line in the transfer and barter menus | `F3NV_Condition` (18 natives) | Spawn-health call redirect; transfer and barter menu listeners |
| `pipboy.cpp` | CND line, repair list and ammo list on the Pip-Boy item card | `F3NV_Condition.Pipboy*`, `F3NV_PipboyAmmo` | Pip-Boy menu listener |
| `pages.cpp` | Extra STAT tabs | `F3NV_Pipboy.SetTab` | (through the Pip-Boy listener) |
| `card.cpp` | Other mods' lines on the Pip-Boy item card, per item or per keyword ([card lines](swf_framework.md#card-lines)) | `F3NV_ItemCard.SetLine` | (drawn by our Pip-Boy movie) |
| `gfx.cpp` | Flash helpers shared by the hooked menus, and natives any movie of ours may call (`TextureExists`, for f3ui's images) | Scaleform natives `F3NV` | Nothing |
| `ammo.cpp` | Ammo choice list for the highlighted gun | `F3NV_PipboyAmmo` | (through the Pip-Boy listener) |
| `damage.cpp` | Flat Damage Threshold, per pellet | `F3NV_Damage.SetRules` | Four resistance-curve call redirects; off until `SetRules` |
| `hardcore.cpp` | Ammo weight outside Survival, HUD needs | `F3NV_HardcoreNative.Track` | One call redirect; off until its global is set |
| `sex.cpp` | Change an actor's sex through the game's own handler | `F3NV_Sex.ChangeSex` | Nothing |
| `dialogue.cpp` | Dialogue menu with any number of options | Scaleform natives `F3NV` | Three call redirects at PostLoad; stays out when `XDI.dll` is loaded |
| `plugin.cpp` | No combat sprinting | none | Turns `bCombatPathSprinting` off for every actor, always |

Hardcoded: about 35 `RelocAddr` addresses for Fallout4.exe 1.11.240, built on
raw F4SE 0.7.9 with no Address Library.

## <a id="split"></a>The split

| Release | Contains | For |
|---|---|---|
| **Framework DLL** (name to pick) | Item condition API, Pip-Boy and menu CND lines, Pip-Boy tabs API, item-card lines for other mods (`card.cpp`), `ChangeSex`, the Papyrus array library (`CRUI_Array.psc`) | Mod authors. Does nothing on its own |
| **f3ui menu library** | Our own AS3 menu toolkit: input, modal pop-ups, scroll lists, hint bar, images, translations, controller support; compiled with the open Flex SDK ([release](swf_framework.md#release)) | Mod authors who want a menu without decompiling Bethesda's files. No DLL |
| **Level-up menu** | Our level-up menu on f3ui ([plan](fo4_level_up_plan.md)): skill, perk, tag and trait pages, PRKF.dll's work in Papyrus, opened in place of `LevelUpMenu` without replacing its movie, an API for other mods ([API](fo4_level_up_plan.md#api)) | Players and perk-overhaul authors replacing LevelUpMenuEx ([below](#level-up)) |
| **Casino games and Caravan** (content mod) | The casino menus on f3ui ([plan](fo4_casino_plan.md)): slots and roulette built, blackjack and Caravan planned | Players who want the games anywhere in FO4, such as a settlement bar ([below](#casino)) |
| **Modder tools** | Stand-alone tools from the replaced CK steps ([below](#tools)) | Mod authors. No DLL |
| **Dialogue menu** | `dialogue.cpp` and its menu file, separate DLL | Players replacing XDI. No framework needed. See [its plan](dialogue_menu_mod.md) |
| **NV Weapon Condition & Repair** (content mod) | ESP + scripts that track weapons and armor, repair lists, vendors | Players. Requires the framework |
| **NV Ammo Switching** (content mod, optional) | ESP + scripts for the ammo list | Players. Requires the framework. Many alternatives exist; low priority |
| **Dynamic collision** | New DLL ([plan](dynamic_collision_mod.md)), from [the research](research/fo4_dynamic_collision.md) | Players and mod authors. No FO4 equivalent exists. No code yet |
| **Appearance comparison** | Stand-alone tool, no DLL for its viewer ([plan](appearance_compare_tool.md)): two load orders' NPCs side by side, plus a dark-face check | Players choosing between character replacers, and mod authors. No code yet |
| **F3NV.dll** | The converter's own rules: Damage Threshold, Hardcore, combat sprint, spawn condition | The FNV build only. Requires the framework and the dialogue menu |

Not released on their own:
- **Damage Threshold.** Zoltanite's mod (Nexus 109168) already does this, and ours follows its approach. Keep the credit in the code.
- **Ammo weight and combat sprint.** These are FNV rules, not general features.

### <a id="framework-rules"></a>Rules for the framework

- **Changes nothing on load.** A hook changes game behavior only after a mod
  asks for it through a Papyrus call or an INI line. Today combat sprinting
  and the spawn-health redirect apply at load. Both move to F3NV.dll.
- **Renames.** The Papyrus scripts get the framework's own prefix. F3NV
  keeps thin `F3NV_*` wrappers until the converter's scripts are regenerated.
- **Several mods at once.** `Track`, `SetTab` and the repair lists add to a
  shared table instead of replacing it, so two mods can each register their
  own items and tabs.
- **Version and API checks.** A `GetVersion()` native and an F4SE message
  other plugins can query.
- **Log** to `Documents\My Games\Fallout4\F4SE\<name>.log`, at an
  INI-selected level.

## <a id="runtime"></a>One base for both game versions

Players are split between old-gen 1.10.163 and next-gen 1.10.984 / 1.11.x.
Every DLL above needs both versions, so the port is done once:

1. Move from raw F4SE 0.7.9 to **Dear-Modding-FO4/commonlibf4**
   (GPL-3.0-or-later with the modding and linking exceptions), one DLL for
   1.10.163, 1.10.980/984 and 1.11.137–1.11.240. Chosen 2026-11-11 over
   LucaDotGit's "AV" fork: 24 contributors against one, active daily,
   our license family, and the base of Addictol and DearModdingUI
   ([comparison](research/commonlibf4_forks.md)). No VR; see
   [platforms](#platforms).
2. **Fix its version check first.** It accepts only an exact list of game
   versions and terminates the game on any other, so a game update would
   crash every DLL built on it until we rebuild. Change it to treat a
   newer version as the latest known one (what AV does), offer that
   upstream as a pull request, and carry it locally if refused
   ([why](research/commonlibf4_forks.md#verdict)).
3. Replace each `RelocAddr` with an Address Library ID. The fork names
   about half of F3NV.dll's ([coverage](research/commonlibf4_forks.md#ours))
   and the dialogue plan lists IDs for its functions. Find the rest by
   matching each function in the 1.10.163 exe, and send them upstream.
4. Build with the fork's own xmake (start from
   `Dear-Modding-FO4/commonlibf4-template`, GPL-3.0) in place of
   `build.bat`. xmake finds Visual Studio itself, so the Community
   `vcvars64` workaround ([runtime DLL build](../../tes_runtime/common/msvc.bat))
   should stop being needed.
5. Write a check for each hooked call site: when the bytes there aren't what
   we expect, log it and leave that feature off. The game should keep
   running.

## <a id="platforms"></a>Platforms: PC versions, VR, consoles

From a survey on 2026-11-11 (**V** read in source or official notes,
**S** search results only).

### How Address Library fits in

- **The problem:** every game update moves the game's functions to new
  addresses. F3NV.dll calls about 35 functions by raw address for
  1.11.240, so every update breaks it until we rebuild.
- **What it does:** Address Library (Nexus 47327, by meh321) gives each
  function a **stable ID** and ships one small database per game version
  (`Data\F4SE\Plugins\version-1-11-240-0.bin`), which the player installs.
  A DLL asks for ID 2196825 and gets that function's address in whatever
  version is running. One DLL then works on every version that has a
  database, often including future ones, without a rebuild.
- **Telling F4SE:** a DLL declares in its version data that it uses
  Address Library (`addressIndependence`) and doesn't depend on struct
  layouts (`structureIndependence`), so F4SE loads it on new game versions
  instead of refusing it (F4SE `PluginAPI.h`, V).
- **What still breaks:** a changed class layout, a function the compiler
  inlined or rewrote, and our byte patches at call sites. That's why every
  hook keeps checking the bytes it patches and turns its feature off with a
  log line when they differ.
- **ID sets:** next-gen renumbered everything, so old-gen and next-gen have
  different IDs for the same function. CommonLibF4 handles this with
  `REL::RelocationID(oldGenId, nextGenId)`.
- **Speed:** for 1.11.240 (18 Aug 2026), F4SE shipped the same day and the
  Address Library database three days later (S). Players of an
  Address Library DLL wait for that update, not for us.

### Game versions

| Version | F4SE | Address Library | CommonLibF4 forks |
|---|---|---|---|
| Old-gen 1.10.163 | 0.6.23 | `.bin`, old IDs | Dear-Modding, LucaDotGit "AV", alandtse |
| Next-gen 1.10.984 | 0.7.2 | `.bin`, next-gen IDs | Dear-Modding, LucaDotGit "AV", alandtse |
| 1.11.x (current 1.11.240) | 0.7.9 | `.bin`, next-gen IDs | Dear-Modding (up to 1.11.240), LucaDotGit "AV" |
| VR 1.2.72 | F4SEVR 0.6.21 (beta) | **CSV** (alandtse's VR Address Library: old-gen IDs mapped to VR) | alandtse; ArthurHub's VR-only CommonLibF4VR; an untested path in "AV" |

**Decision:** no fork we'd use covers all four, so **flat first, VR
later**: Dear-Modding for the three PC versions
([why](research/commonlibf4_forks.md#verdict)). When VR work starts, choose
then between a second build on alandtse's fork and adding VR to ours.

### VR

- **Possible, but its own product.** VR menus are drawn on 3D panels, the
  Pip-Boy is on the wrist or projected (FRIK), input is motion controllers,
  and our menu offsets differ. Flat UI mods mostly break there, which is why
  PipboyTabsVR and an XDI VR beta (Neanka, 2025, S) exist as separate builds.
  HUDFramework reportedly doesn't work in VR (S).
- **We can't test it:** VR isn't installed, and a headset is needed. Building
  blind would repeat the VR community's main complaint, mods that claim
  support and don't work.
- **Plan:** keep the code VR-ready (VR IDs where the library offers them, no
  flat-only assumptions in the shared base), release flat first, then offer
  a VR build as a beta for VR players to test, ideally with a VR tester or
  co-maintainer. ArthurHub's F4VRCommonFramework (VR input, VR UI widgets;
  license unchecked) is the reference for VR UI.

### Consoles

No script extender, so no DLL, no custom menus and no way for a movie to
call Papyrus. What's left is Papyrus plus replaced vanilla movies.

| | Xbox | PlayStation |
|---|---|---|
| New scripts | Yes | Not in any patch notes; assume no (V: the Aug and Oct 2026 notes add meshes, textures, sounds, video, not `.pex` or `.swf`) |
| New or replaced interface movies | Yes (FDI, HUDFramework, DEF_UI ship there, S) | Assume no |
| Size | Up to 2 GB per upload | Smaller |

What each framework could be on Xbox:

| Framework | Xbox without a DLL | Worth it? |
|---|---|---|
| HUD widgets | Yes, as HUDFramework does: Papyrus sends text through `ShowPerkVaultBoyOnHUD` and `Message.Show` number slots, a replaced `HUDMenu.swf` catches it. One way only | **Yes, the cheap way:** our widget movies already speak HUDFramework's `processMessage`, and our scripts reach HUDFramework through `CastAs`/`CallFunction`, which work on console. So our widgets run under HUDFramework on Xbox with no console framework of our own |
| Dialogue menu | A replaced `DialogueMenu.swf` can only restyle the game's four options (as FDI does). No more options, no topic links, no odds | Low. Maybe a "look only" edition once our movie exists, since ours is free of Bethesda code and can ship there |
| Pip-Boy | A replaced movie can only restyle the game's own data; no new data, no tabs fed from Papyrus | No |
| Custom menus, casino | Not possible. Message boxes, terminals and holotapes only | No (the FNV conversion can't go to console anyway) |
| Settings (MCM) | No menu; a settings holotape or terminal is the console norm | Later idea: one settings definition that shows in MCM on PC and as a holotape on console |

Rules for anything on Bethesda.net: upload only our own work; ports of
others' work need their public permission and a credit link
([community standards](https://bethesda.net/en-US/news/bethesda-softworks-community-standards), V).
Nothing written covers patched vanilla movies; they ship in practice. Our
own rule (no Bethesda files) keeps us to movies built from scratch, so a
console HUD of our own would mean a whole new HUD movie; another reason to
ride on HUDFramework there.

**Summary:** consoles get a reduced, Xbox-only experience through
HUDFramework for HUD widgets, and possibly a look-only dialogue menu.
Everything else needs F4SE and stays PC (and later VR).

## <a id="repo"></a>Where the code lives

- A new repo per release, or one repo with a folder per DLL and a shared
  `common/`. **Choose one repo**: the shared base would otherwise be copied.
  It is **Cleanroom UI** (`ThyMrMan/cleanroom-ui`, prefix `CRUI_`, private
  for now), shared with the menu framework
  ([release](swf_framework.md#release)).
- License: **GPL-3.0 with the modding exception**, for every release and
  for our code in both converter repos ([license](#license)). Credit the
  upstream tes4skyrim authors where code came from there (none of F3NV.dll
  did; the game bridge recorder would); their code stays MIT inside.
- fo4_main uses the release as a git submodule or a pinned download in
  `external/`, so the converter build stops compiling F3NV's shared parts
  itself.
- The FO4 build session owns F3NV.dll builds ([build ownership](../../CLAUDE.md)).
  The split is done on its own branch and handed over as "ready", never
  built into a game folder by the side session.

## <a id="order"></a>Order

1. **Dialogue menu**: the most wanted. XDI still gets Nexus builds, but its
   source has no license and stops in 2020, it pairs answers by position,
   and each game update waits on its authors
   ([its plan](dialogue_menu_mod.md#xdi-today)).
2. **Shared base**: CommonLibF4 (Dear-Modding), Address Library, xmake. The dialogue menu
   is the first DLL on it.
3. **Framework**: carve out the condition, Pip-Boy and tabs APIs; F3NV.dll
   then requires it.
4. **NV Weapon Condition & Repair**: the first content mod, also the
   framework's example mod.
5. **Dynamic collision**: once its open engine questions are answered.

The pieces added since (f3ui, the level-up menu, the casino, the tools and
the write-ups) are ordered in [the strategy table](#strategy) and below.
Of them, only the item-card lines need a DLL (`card.cpp`, so they ship
with the framework); f3ui, the level-up menu, the casino screens, the
tools and the write-ups don't wait on the shared DLL base.

## <a id="strategy"></a>Strategy: open, drop-in replacements

Widely used FO4 UI mods by the same small group (reg2k, very likely the
Nexus user registrator2000, and Neanka, who co-wrote XDI and made DEF_UI and
PipboyTabs) share one state: source published without a license, updates
mostly for new game versions, no new features. Nobody else can legally
maintain their cores.

| Mod | Last update | Source |
|---|---|---|
| XDI (dialogue) | Sep 2026 | GitHub, stops 2020, no license |
| HUDFramework | Mar 2017 (source uploaded Sep 2026) | `references/HUDFramework Source Code 1.0f`, no license |
| MCM | Sep 2026 | GitHub, no license |
| DEF_UI (DEF_HUD + DEF_INV, Neanka) | Real work 2016; 2024 repack "as-is, not supported" | None. Permissions forbid changing its files ([DEF_UI](#def-ui)) |
| LevelUpMenuEx (Neanka) | Not checked | `references/LevelUpMenuEx`, no license ([what it does](fo4_level_up_plan.md#today)) |

**Decision:** aim to be the open-licensed, drop-in replacement, one
framework at a time, the way Open Animation Replacer took over from Dynamic
Animation Replacer in Skyrim:
1. **Drop-in on day one:** read the old mod's config files and offer its
   Papyrus script names and functions, so mods built for it keep working.
2. **Clearly better**, not only open ([what we add](dialogue_menu_mod.md#beyond-xdi)).
3. **Not hostile:** credit the original, present ours as an alternative or
   successor.

**Order:**

| | Why this place | Effort |
|---|---|---|
| 1. XDI → our [dialogue menu](dialogue_menu_mod.md) | We need it anyway; the most to add | Large, half built |
| 2. Pip-Boy framework ([plan](swf_framework.md#pipboy)) | No incumbent to replace; builds the injection code the HUD needs | Medium |
| 3. HUDFramework → HUD on the same injection ([plan](swf_framework.md#hud)) | Ends the `HUDMenu.swf` conflict; instant messages on PC; about 25 Papyrus functions and one widget method to match | Medium once 2 exists |
| 3b. DEF_HUD layouts on the same HUD host ([plan](swf_framework.md#hud-layout)) | Move, scale, recolor and hide the game's own HUD parts without replacing `HUDMenu.swf`; reads `DEF_HUD.xml`; ends the DEF_UI + HUDFramework merge patch | Small on top of 3 |
| 4. MCM | Works, most depended on, still updated; no clear gain yet | Largest; keep using its file format |
| 5. DEF_INV-style inventory | Icons, tabs and key-ring roll-ups from sorting mods' tags; FallUI Inventory already holds this space | Large; maybe never |
| 6. LevelUpMenuEx → our [level-up menu](#level-up) | Built for the conversion already; reads LevelUpMenuEx's INI lists so its add-ons keep working | Small to medium on top of what's built |

### <a id="level-up"></a>The level-up menu

LevelUpMenuEx is a hard dependency of the conversion today, unlicensed and
in the same state as XDI and DEF_UI. Our replacement is built
([plan](fo4_level_up_plan.md), not played): skill, perk and taken pages,
and the tag and trait menus, listing every plugin's perks and traits, with
PRKF.dll's points, tags and perk list rebuilt in Papyrus. It opens in
place of the vanilla `LevelUpMenu` without shipping a `LevelUpMenu.swf`.

- **Drop-in:** read LevelUpMenuEx's INI lists (`PerksList`, `SkillsList`,
  the point settings), so P76 Perks and the You Are Exceptional and Be
  Exceptional patches work without it. Only the file format, not its code;
  still an open decision in [the plan](fo4_level_up_plan.md#api).
- **Clearly better:** the extras players bolt onto level-up menus, built in
  ([defaults](fo4_level_up_plan.md#defaults)); a Papyrus API to add perks
  and skills, open the trait and tag menus and hear when a perk is taken.
- **No DLL:** it opens from Papyrus (`F3NV_CharacterRules` closes
  `LevelUpMenu` and opens ours, [opening](fo4_level_up_plan.md#open)).
- **Needs before release:** perk and trait tables for any load order. Today
  the converter writes them from each plugin's records
  ([tables](fo4_level_up_plan.md#tables)), and the points come from
  `F3NV_CharacterRules`. Plus a play test of the built menu.

### <a id="casino"></a>Casino games and Caravan

The casino screens run on f3ui and Papyrus, with no DLL
([design](fo4_casino_plan.md#design-logic)). As a content mod, the games
could sit in any bar or settlement: slots and roulette now, blackjack and
Caravan when they're built.

- **Needs:** the rules split from FNV's records (casino, chips, comps and
  bans are per casino today), plain FO4 items for chips and cards, and a
  play test. Caravan as a card game with its own decks would stand out
  most, since FO4 has no card game.
- **Size:** medium after phase 5 of [the casino plan](fo4_casino_plan.md#phases).

## <a id="tools"></a>Modder tools from the replaced CK steps

The build now does much of what the Creation Kit, Elric, Archive2 and
LipGenerator did ([replacements](fo4_ck_replacements.md#today)). Several of
those pieces are useful to any FO4 mod author as stand-alone tools, no DLL,
on any OS. The full list, sizes and order are in
[the ideas doc](fo4_after_ck_ideas.md#picks); in short:

- [a dark-face fixer](fo4_after_ck_ideas.md#dark-face) that rebuilds only
  the NPCs whose FaceGen no longer matches the load order, without the CK;
- [AnimTextData for any mod](fo4_after_ck_ideas.md#anim-text-tool);
- [lips for voice mods](fo4_after_ck_ideas.md#lip-tool) from the audio
  alone;
- [an archive check](fo4_after_ck_ideas.md#ba2-check) for the textures
  Archive2 silently drops;
- [collision for modders](fo4_after_ck_ideas.md#collision-tool);
- [our Caprica fixes upstream](fo4_after_ck_ideas.md#caprica-upstream),
  including the temp-reuse miscompile every Caprica user has.

They share the release rules above: GPL-3.0 with the modding exception,
one repo.

## <a id="write-ups"></a>Write-ups for the community

Some findings help modders even without code. The first candidate is the
CK's face bake, read from its shader and CPU code
([shader](fo4_facegen_plan.md#ck-face-shader),
[layer list](fo4_facegen_plan.md#ck-layer-list),
[brows](fo4_facegen_plan.md#ck-brows),
[quirks](fo4_facegen_plan.md#face-d-revisit)):

- every unlisted palette option gets its default entry, so every human NPC
  gets lip color nobody chose;
- a palette's TTED is an entry index stored in a float field;
- brows are colored from the race's hair gradient, and black when the race
  has none (every child) or the hair color has no remapping index;
- layers go on at mask^(1/2.2) × value, in linear light, in reverse race
  order.

Character-preset and LooksMenu authors work against this blind today. A
public page, in our own words with no Bethesda code, costs little.

- **Size:** small. Other candidates as they come: AnimTextData's format
  ([research](research/anim_text_data.md)), Archive2's silent losses.

### <a id="def-ui"></a>DEF_UI

Read 2026-11-11 from `references/DEF_UI 1.6.0-…` (gitignored; Nexus page
included).
- **What it is:** Neanka's DEF_HUD (move, rotate, resize and recolor every
  HUD element) and DEF_INV (bigger container and barter screens, icons and
  tabs from sorting mods' name tags, key-ring roll-ups), repacked in 2024 by
  Valdacil "as-is … not monitored or necessarily supported". 1.4M unique
  downloads, 210 mods depend on it.
- **How it's built:** replaced vanilla movies, one set per screen shape
  (16:9, 16:10, 21:9, 4:3, 5:4): `HUDMenu.swf`, `PipboyMenu.swf`,
  `Pipboy_InvPage.swf`, `ContainerMenu.swf`, `BarterMenu.swf`,
  `ExamineMenu.swf`, `Workshop.swf`. Its movies date from 2016. Settings are
  edited outside the game with two Windows programs (`HUDMenuSet.exe`,
  `settings.exe`) that write XML into `Interface\DEF_CONF\`.
- **Its conflicts:** every other HUD mod, including HUDFramework, which needs
  a merged copy (shipped pre-made for HUDFramework 1.0f). It also ships its
  own copies of the game's `Translate_<lang>.txt`, which must be redone after
  each game update (1.6.0: "Updated Translate_en.txt for Next Gen update").
- **Permissions:** no changes or reuse of its files without asking; no
  source. Its icons (`iconlibs2.swf`) are its own assets and can't be used.
- **What other mods depend on is its config formats:** sorting mods (VIS,
  Better Item Sorting, and others) ship `DEF_INV_TAGS.xml` (name tag →
  icon) and `DEF_INV_TABS.xml` (tabs by filter and tag), and players keep
  `DEF_HUD.xml` layouts (per element: position, scale, rotation, colors,
  parent clip, shown parts).

**Where it fits:** not a framework, so not a target on its own. Its HUD
half is one module of our HUD host: an injected movie that applies a
`DEF_HUD.xml` layout to the game's own HUD parts, with an in-game drag
editor instead of an outside program and one layout for every screen shape.
Its inventory half competes with FallUI Inventory, which already replaced it
for most players; reading sorting mods' tag files is possible later, but
not planned.

**Rules:**
- **Formats and APIs, never code.** We've read their sources, so each
  compatibility spec is written in our own words from observed behavior and
  tested against real mods that use the original.
- **Stand-in plugins are the sensitive step.** Mods master `XDI.esm` and
  `HUDFramework.esm`, so a drop-in ships files with those names and record
  IDs. Ask the author before releasing one.
- **Author contact comes first.** If the author adds licenses, contribute to
  his mods instead (HUDFramework's unfinished F4SE fast path is a ready
  first contribution). If he declines or doesn't answer, release clean,
  credited replacements.
- **Finish the shared core first** (one DLL for every game version, the
  shared Flash library): each replacement is a promise to keep up with game
  updates, and only a shared core makes that affordable.

**Status:** the HUDFramework license question was sent to the author on
Nexus; waiting for an answer.

## <a id="license"></a>License

**Decision (2026-11-11): GPL-3.0 with the modding exception** for all our
releases and for our own code in both converter repos (`fo4_main`,
`tes4skyrim_standalone`).

- **Why:** XDI, HUDFramework and MCM are stuck because they have *no*
  license, so nobody may continue them. Any open license fixes that; GPL also
  stops anyone taking our work closed (a closed fork, or a closed rival
  converter, folding our code in), so every version built on ours stays
  open too.
- **The modding exception** (`EXCEPTIONS`, the text DCA and others ship):
  linking with the game and other proprietary game code, and with modding
  libraries under other licenses, doesn't pull that code under the GPL. Mods
  that only use our APIs (Papyrus calls, widgets, links files) are their own
  works under any license.
- **Files:** `LICENSE` (GPL-3.0 text), `EXCEPTIONS`, `NOTICE` at each repo's
  root. `NOTICE` says what each license covers: upstream tes4skyrim code
  stays MIT (its text is in `NOTICE`), third-party code under `external/`
  keeps its own, converted game data is Bethesda's and covered by none.
- **Compatible:** MIT, BSD, Apache and MPL-2.0 code can be used inside
  (Caprica, the papyrus compiler); GPL-3.0 code too (CommonLibF4, PyNifly,
  OpenMW, DCA). Code with no license still can't, whatever ours is.
- **Upstream PRs** stay MIT: we offer our own changes to upstream under its
  license.
- **Every release also gets:** Nexus open permissions (upload, modify,
  convert without asking; Bethesda.net requires public permission for ports),
  source tagged to match each Nexus version, and the line "if this project
  goes unmaintained, anyone is welcome to continue it".

## <a id="nexus"></a>Before each Nexus release

- Played on both game versions, with and without the common UI mods
  (DEF_UI, FallUI, Full Dialogue Interface).
- Played once start to finish on a gamepad, mouse and keyboard untouched
  ([controller support](swf_framework.md#controller)).
- FOMOD installer; requirements listed (F4SE, Address Library).
- README with the Papyrus API and an example script.
- Source link and license on the page.
- No Bethesda files shipped. Menu files must be our own (see the dialogue plan).
