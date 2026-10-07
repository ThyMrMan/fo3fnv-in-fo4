# Fallout 4 as the target for FO3 and FNV

Started 2026-10-05. The question: should FO3 and FNV convert to Fallout 4
instead of Skyrim SE, so the Fallout systems the fork rebuilds by hand in
Skyrim come from FO4's engine instead? Under that split, Morrowind and
Oblivion would stay on Skyrim. This note holds findings only. The decision and
any plan come later, and status goes in [ROADMAP.md](../ROADMAP.md).

## Contents

- [Summary](#summary)
- [What is installed](#installed)
- [What FO4 gives natively](#native)
  - [Asset overlap](#asset-overlap)
- [What FO4 still lacks](#gaps)
- [What the move throws away](#lost)
- [Existing FO4 mods for the gaps](#mods)
- [AI rules in Fallout4.exe](#ai-rules)
- [How the pipeline would split](#pipeline)
- [Target formats](#formats)
- [fnv-to-fo4](#fnv-to-fo4)
- [Decisions for the user](#decisions)
- [Proposed spikes](#spikes)

## <a id="summary"></a>Summary

- **Why move.** FO4 does natively what the fork has built or planned in
  Skyrim. That covers guns, VATS, crippled limbs, radiation, terminals,
  holotapes, the Pip-Boy, power armor, crafting, companions and combat styles.
  FO4 also ships vanilla versions of most FO3/FNV creatures: deathclaw,
  radroach, mirelurk, super mutant, ghoul, brahmin and the robots.
- **What it costs: a second back end.** The pipeline has no idea of a target.
  Every converter packs TES5 subrecords by hand. About 1,135 Skyrim.esm FormID
  literals sit in 67 files.
- **What carries over:**
  - export text, the script front end (lexer, parser, AST), the record
    framing, FormID hashing, the condition-remap generator, authored navmesh
    and textures;
  - plus knowledge of the source data, which is the larger part of the past
    work.
- **What is rewritten or dropped:**
  - Rewritten: NIF output, collision, Havok, dialogue layout, LOD and every
    runtime DLL.
  - Dropped: SKSE does not port to F4SE.
- **Biggest risk: dialogue, now narrower.** FO3 and FNV list their topics.
  Vanilla FO4 offers a voiced player exactly four choices, built from scenes.
  The Extended Dialogue Interface (XDI, [mods](#mods)) lifts that limit in
  the engine:
  - any number of options, each with its own conditions;
  - full text shown;
  - a silent player, with no pause and the camera kept on the NPC;
  - Say Once.

  F4NV, Capital Wasteland and Cascadia all build on it. What's left is a
  mapping question: how FO3/FNV topics, which any NPC can say when the
  conditions match, become FO4 scenes. Spike 1 settles that.
- **Second risk, now read: the package engine is Skyrim's.** The census
  says 58 of 115 bugs came from imitating FO3 engine rules in Skyrim's AI
  ([census](fallout_rule_census.md)). `Fallout4.exe` decides package choice,
  `EvaluatePackage`, the dialogue pause, IgnoreCrime and the failsafe warp the
  way Skyrim does, function for function ([AI rules](#ai-rules)). So the
  phase A record work carries over as design, and the phase B runtime is
  still needed, rewritten for F4SE. Two things improve: radio is native, and
  a force greet probably lasts through the conversation.
- **Missing systems have FO4 mods, but most can't be used as code.** Karma
  can be a soft dependency through its API. Reputation is closed to new
  factions. The skills framework (LevelUpMenuEx) is maintained for 1.11.240.
  Weapon condition has to be built here ([existing mods](#mods)).

## <a id="installed"></a>What is installed

Paths are relative to `C:\Program Files (x86)\Steam\steamapps\common\Fallout 4`.

| Item | Version, notes |
|---|---|
| `Fallout4.exe` | 1.11.240.0, newer than the 2024 next-gen update (1.10.980). `Fallout4.exe.unpacked.exe` sits next to it |
| `CreationKit.exe` | 1.11.240.0. `Tools\LipGen\CreationKit32.exe` handles lip generation |
| F4SE | 0.7.9. Full source is in `src\f4se-0.7.9.tar.gz`; `PluginAPI.h` is the plugin interface |
| Address Library for F4SE | **Not installed.** A native plugin on 1.11 needs the 1.11-format `Data\F4SE\Plugins\version-*.bin` |
| DLC | All six, plus the HD texture pack and nine Creation Club `.esl` files |
| Tools | Archive2 1.1.0.5, Elric (`Tools\Elric\Elrich.exe`), LipGen + LIPFuzer, xWMAEncode, MaterialEditor, the 3ds Max NIF exporter, Papyrus compiler 2.8.0.4 |
| Script sources | Zipped: `Data\Scripts\Source\Base\Base.zip` (7,874 entries, with `Institute_Papyrus_Flags.flg`) plus a DLC zip each. The F4SE `.psc` files sit loose in `Data\Scripts\Source\`, outside the CK's import paths |
| References | In `references\` (gitignored). Held here: the FO4 CK wiki, FO4Edit 4.1.5f, LevelUpMenuEx. Junctions to the shared Fallout references in `tes4skyrim_main\references` ([CLAUDE.md](../../../CLAUDE.md)). xEdit's `wbDefinitionsFO4.pas` is in `references\xEdit\Core`; NifSkope 2.0.dev11, with its FO4 `nif.xml`, is in `references\NifSkope` |

The runtime is very new (August 2026). Mods and CommonLibF4 lag behind new
runtimes, so a downgrade may be needed later, as Skyrim was taken back to
1.6.1170. That decision can wait until a native plugin is
actually needed.

## <a id="native"></a>What FO4 gives natively

| FO3/FNV system | Today in Skyrim | In FO4 |
|---|---|---|
| Guns: firing, magazines, reload, iron sights, ammo | FalloutRuntime about 2.4k C++ plus about 1.9k of Havok graph patching | Native. Weapon mods become OMODs |
| VATS, kill cams | Not started | Native. Crits use a charge meter instead of FNV's chance roll; matching FNV needs a perk entry point or Papyrus |
| Limb damage, severing | Severing built but has never worked | Native conditions and dismemberment |
| Radiation | None; 22 Fallout actor values read as inert | Native `Rads`, rad resistances and hazards. FO4 rads cut max HP; FNV's sickness tiers need MGEF + Papyrus |
| Terminals, holotapes | Paged message boxes, notes as books | Native TERM and NOTE. Menu result scripts become VMAD terminal fragments |
| Pip-Boy, HUD, radio | None; radio is phase B8, Large | Native. The UI is Scaleform; FNV's XML menus don't port |
| Condition functions | About 237 functions dropped | Most exist: VATS, limb, rads |
| SPECIAL | Written, not played (rules plugin) | Native actor values |
| Perks, XP | Written / played | Native ranked chart and `Experience`. FNV's "a perk every 2 levels" pacing needs Papyrus or a menu |
| Companions | Package choice only | Native affinity, command wheel, follower state |
| Hardcore needs | None | Survival mode's `HC_ManagerScript` covers hunger, thirst, sleep and sickness and could be adapted |
| Crafting | None (RCPE) | COBJ + CMPO; RCPE maps onto COBJ |
| Power armor | Worn armor | Frame + fusion cores, or plain ARMO behind a perk gate (see [decisions](#decisions)) |
| Combat styles | Exported empty | Skyrim-lineage CSTY records |
| Creatures | Converted skeletons and behaviors | Vanilla equivalents can be reused instead of converted |

### <a id="native-records"></a>More native features, mostly record mapping

Most of these are field translations in `fo4_import`, not runtime work.
"Checked" means read in `wbDefinitionsFO4.pas` or the vanilla dump
(2026-10-05); the rest is general knowledge, still to confirm.

**Use outright:**

| FO3/FNV | FO4 | Checked |
|---|---|---|
| Lock difficulty 0–100 | REFR `XLOC` levels on the same scale: Novice 1/25, Advanced 50, Expert 75, Master 100, plus Requires Key, Requires Terminal, Barred, Chained. The lockpick minigame is FO3's | Levels ✔ |
| Terminal hacking difficulty | The same tiers on the placed terminal, with the FO3/FNV word-guess minigame | Tiers ✔; that hacking reads the terminal ref's `XLOC` is likely, not confirmed |
| FO3 skill books (+skill) | BOOK `DNAM` flag Advance Actor Value, pointing at our skill AVIFs | ✔ |
| FNV skill magazines (timed buff) | BOOK `DNAM` Add Spell (or Add Perk); a timed spell gives the buff | ✔ |
| Chems, addiction, withdrawal | ALCH Addiction + Addiction Chance; vanilla `AddictionOdds*` effects | ✔ |
| Hardcore food, water, sleep (FNV) | Survival keywords: `HC_EffectType_Hunger/Thirst/Sleep/Disease`, `HC_SustenanceType_*`, `HC_IngestedRads`, disease-risk keywords. Tag FNV consumables and let the Survival manager run them | Keywords ✔; that the manager accepts tagged FNV items needs a test |
| Rads in food, water, weather | Rads on consumables, radioactive water, radiation storms | — |
| Workbench, reloading bench, campfire | FURN `WBDT` bench types (Weapons, Armor, Alchemy for chemistry and cooking, Power Armor, Robot) + COBJ keyed to bench keywords (`WorkbenchChemlab`, `WorkbenchCooking`); FNV recipe categories map onto them | ✔ |
| Weapon mods (FNV's 3 slots) | OMOD + attach points, a superset | ✔ (above) |
| Grenades, mines, thrown weapons | Native weapon types and the grenade hotkey | — |
| Damage types (energy, fire, poison…) | DMGT records | ✔ |
| Leveled lists, "use all", encounter zones | Same record lineage (LVLI/LVLN Use All) | ✔ |
| FO3 bobbleheads | `BobbleheadKeyword` + pickup perk | Keyword ✔ |
| Quest objectives and markers | QUST objectives with alias targets, Pip-Boy log, compass | — |
| Vendors, caps, barter | Vendor factions, merchant chests, caps | — |
| Projectiles, explosions, impacts, body parts | Same lineage | — |
| Weapon and creature animations | FO4's gun animation sets by weapon type; map FNV animation types onto them rather than convert | — |

**Use with adjustment:**

- **Damage Threshold vs Damage Resistance**: FNV subtracts flat DT; FO4
  uses a DR curve with physical, energy and radiation values. No exact
  match: convert DT to DR by formula, or adjust damage through perk entry
  points. A balance decision, not a port.
- **Speech and skill checks**: FO4's speech challenge is Charisma-based and
  random; FNV's are deterministic conditions, which we already convert. Keep
  ours; borrow FO4's challenge coloring at most.
- **Criticals**: see VATS above.
- **Implants, traits**: plain perks; the menu is LevelUpMenuEx.

### <a id="asset-overlap"></a>Asset overlap: FO4 models in place of converted ones

Measured 2026-10-05: FNV's distinct display names (export) against
Fallout4.esm's editor IDs (base game only; the dump's display names are
string ids). Matched by hand, so the counts are approximate.

| Category | FNV | Direct FO4 counterpart | Near (same role, other look) | Notes |
|---|---|---|---|---|
| Weapons | 203 names, about 150 real player weapons | ~43 (~30%): 10mm, .44, laser and plasma pistol/rifle, Gatling laser, minigun, Fat Man, missile launcher, flamer, Gauss rifle, alien blaster, hunting rifle, SMG, power fist, Ripper, Shishkebab, super sledge, sledgehammer, machete, switchblade, bat, lead pipe, pool cue, tire iron, rolling pin, boxing gloves, knuckles, nail board, cane, fire-hydrant bat, frag/plasma/pulse grenades and mines, bottlecap mine | ~6–8: combat/riot shotgun, double-barrel for the caravan/single/sawed-off, combat or assault rifle for the service rifle/assault carbine, lever-action (Far Harbor) | FNV-only: 9mm, 12.7mm, .357, varmint, cowboy repeater, trail carbine, brush gun, anti-materiel, sniper rifle, grenade launchers, Laser RCW, rechargers, Plasma Defender, Multiplas, Tesla cannon, most uniques |
| Creatures | ~33 families | ~19: radscorpion, bloatfly, brahmin, deathclaw, dogs, feral and glowing ghouls, mirelurk and king, mole rat, radroach, eyebot, Mr. Handy/Gutsy, protectron, robobrain (Automatron), sentry bot, turrets, super mutant, behemoth, yao guai, alien; Nightkin as super mutants | — | Missing: gecko, cazador, nightstalker, ants, mantis, giant rat, bighorner, coyote, Securitron, spore carrier, centaur, floater, trog |
| Consumables | 188 | ~65, ~80 with the "Irradiated" variants that share a model: the chems, Stimpak, RadAway, Rad-X, Stealth Boy, blood packs, Nuka-Cola and Quantum, the pre-war foods, liquors, most creature meats | — | Missing: FNV's desert plants and its own creatures' meat |
| Armor, clothing | 356 | ~30–40 (~10%): combat, leather and metal armor and helmets, T-45d and T-51b, vault jumpsuits, radiation suit (hazmat), gas mask, glasses, tuxedo and hat, baseball cap, hard hat, Pip-Boy | ~30: pre-war outfits, lab coats, hats, merc and wastelander outfits | None for faction gear (NCR, Legion, Khans, Boomers, Powder Gang, Kings, Remnants). FO4 armor is pieces worn over clothing, FNV's whole suits, so a swap changes the item's structure |
| Architecture, landscape | — | Low: FO4's ruin and vault kits suit FO3's DC more than the Mojave | — | Adobe, desert rock and the Strip are FNV's own |
| Textures alone | — | None: FO4 textures belong to FO4 meshes and BGSM materials | — | — |

**Plan: a substitution table**, FNV form → the FO4 vanilla asset it uses,
with FNV's stats kept and FO4's model (and, for guns, animations) taken.
FO4 assets are referenced by path, never redistributed.

- **Weapons first**: an FO4 gun mesh brings its first- and third-person
  animations, reloads and OMOD attach points, the hardest assets to convert;
  FNV's three mod slots map onto that gun's OMODs.
- **Creatures and power armor next**: skeletons and behaviors come free.
- **Consumables and clutter**: a cheap win but optional; converting them is
  easy anyway.
- **Not** landscape, architecture, faction gear, faces or uniques.
- It shrinks the conversion, it does not remove it: about 60% of the weapons
  and most of the world are FNV-only.
- FO4's 10mm or laser rifle does not look like FNV's: make it a per-category
  choice (FO4 look or FNV look), not fixed.

## <a id="gaps"></a>What FO4 still lacks

These need emulation on FO4 too. Unlike Skyrim, FO4 lets a plugin define its
own actor values, and F4SE adds about 248 Papyrus functions (58 of them on
`InstanceData`).

| System | How |
|---|---|
| 13 skills | Plugin AVIFs. WEAP DNAM has an actor-value "skill" field for damage scaling. Checks become conditions on the AVIFs. The menu can come from LevelUpMenuEx ([mods](#mods)) |
| Karma, fame/infamy, reputation | Globals or AVIFs plus Papyrus and a UI. FO4 has no REPU or CHAL records. Karma can go through KARMA's API; reputation is ours to build ([mods](#mods)) |
| Weapon and armor condition | No item health in FO4. Needs F4SE `InstanceData` plus extra data, or a native plugin. This is character piece H, which isn't started anyway. Ours to build ([mods](#mods)) |
| Ammo effects (AMEF) | No ammo effects; approximate with OMODs or legendary effects |
| Topic-list dialogue | XDI ([mods](#mods)) gives any number of options and a silent player. What remains is mapping FO3/FNV topics onto scenes (spike 1) |
| FNV extras | Caravan, casino and challenges, the same as on Skyrim today |

## <a id="mods"></a>Existing FO4 mods for the gaps

Read from the Nexus pages on 2026-10-05; nothing was downloaded. Every one of
them forbids re-uploading, so none can ship inside the converter's output.
The choice is between a dependency the player installs, as Fallout: London,
F4NV and Cascadia do with LevelUpMenuEx, or our own build.

| System | Mod | State | Permissions | Use |
|---|---|---|---|---|
| Karma | [KARMA](https://www.nexusmods.com/fallout4/mods/80425) (bp42s) | 3.4.0, updated 2026-08-30; ESL-flagged ESM, no vanilla edits; soft requirement PipboyTabs | Modify with credit. Assets free with credit, except the SWF icons and the sounds (their makers' permission). No re-upload, no conversion to other games | **Soft dependency.** Its `KARM:API` script is built for other mods to call. Converted FO3/FNV scripts would raise karma through it. Its FO4-specific events (bounty hunters, vanilla quest karma) would need switching off in its MCM. If it's missing, a fallback global keeps the value |
| Reputation | [REPUTATION](https://www.nexusmods.com/fallout4/mods/79394) (bp42s) | 2.1.1, updated 2026-09-24; needs Random Encounter Framework | Modify with credit, but **no new factions by patch**: factions sit at fixed indexes, and the author adds them on request only | **Closed for this use.** NCR, Legion, the Strip families and FO3's town standings are all new factions. Build our own fame/infamy store, using its features (hit squads, gift givers, prices) as a design reference |
| Skills, tag skills, traits | [Be Exceptional](https://www.nexusmods.com/fallout4/mods/28222) (Rcollpc) | 0.97d, unsupported since 2018 | Modify with credit; assets need permission | **Reference only.** Its approach is the one to follow: 16 skills as actor values, points on level-up, skills tuned by globals and form lists, SPECIAL feeding skills |
| Level-up menu | [LevelUpMenuEx](https://www.nexusmods.com/fallout4/mods/28822) (Neanka) | F4SE plugin, kept current: updated for 1.11.240 on 2026-09-06, every runtime since 1.10 | None stated | **Dependency.** It adds perks, skills, traits and tag-skill menus, including FNV's skill-point formula. This is the menu the character plan's pieces G1/G2 would otherwise build |
| Dialogue | [Extended Dialogue Interface](https://www.nexusmods.com/fallout4/mods/27216) (reg2k, Neanka) | Updated for 1.11.240 on 2026-09-01; about 1.3M users, used by 124 mods. F4SE plugin + `DialogueMenu.swf`; source on GitHub ([reg2k/xdi](https://github.com/reg2k/xdi), C++; [Neanka/DialogueMenu](https://github.com/Neanka/DialogueMenu), AS3), but with no license and nothing pushed since 2020 | Free to use. Link to the Nexus page, but **total conversions that need a new game may bundle it**, stating the version | **Dependency, and bundling is allowed.** Details below the table |
| Script and setup framework | [Hydra](https://www.nexusmods.com/fallout4/mods/104159) (SoleVaultBoy) | 1.0.2, released 2026-04-26, updated 2026-05-03; about 46k users; F4SE plugin, needs the Address Library; old-gen, next-gen and Anniversary | Nexus: no re-upload, changes need permission; source under GPL-3.0 with modding exceptions | **Development tool now; decide when the runtime is built.** Details below the table |
| Weapon and armor condition | [Armor and Weapon Condition](https://www.nexusmods.com/fallout4/mods/96830) (MarkReal) | 2.0.2, 2025-11; about 1.9k users; needs NV Ammo Crafting and Papyrus Common Library | Changes and asset use need permission | **Build our own.** Its notes confirm the method: FO4 WEAP has no health field, so the mod drives condition from keyword multipliers in Papyrus. We have FNV's per-weapon health and damage scaling in the export, and can carry them exactly |
| Challenges | [CHALLENGES – F4NV](https://www.nexusmods.com/fallout4/mods/76347) (bp42s) | 3.0.5, 2025-07; about 193k users; nearly every FNV challenge and most challenge perks, rewards as XP and perks, a Pip-Boy DATA tab; the author says the engine does most of the condition checks. Hard requirements: PipboyTabs, Baka Framework, Garden of Eden | No re-upload, no conversion. Author notes: "all of the scripts and records are fair game", except re-uploading an edited standalone version with different challenges; the `.swf` art needs its artists' permission | **Reference, not a dependency** (three extra F4SE plugins). Build our own from FNV's CHAL records in the export, borrowing its design and, with credit, its scripts and records |
| Pip-Boy pages | [PipboyTabs](https://www.nexusmods.com/fallout4/mods/29568) (Neanka) | Updated for 1.11.240 on 2026-09-06; F4SE plugin; custom Pip-Boy pages tracking any actor value or global. LevelUpMenuEx fills a skills tab in it automatically; KARMA lists it as a soft requirement | None stated | **Candidate dependency, behind our API with a fallback**: one UI for skills, karma, fame/infamy and challenges. Same single maintainer as LevelUpMenuEx |
| Papyrus extras | [Baka Framework](https://www.nexusmods.com/fallout4/mods/43627) (shad0wshayd3) | 5.0.0, 2026-09-22; small: editor IDs at runtime, `StringUtil`, Pip-Boy light and radiation events, a crafting Story Manager fix | Upload, modify and convert with credit; source GPLv3 | **Only if a piece is needed**; mostly overlaps Hydra. Liberal enough to bundle |
| Papyrus extras | [Garden of Eden PSE](https://www.nexusmods.com/fallout4/mods/74160) (LarannKiar) | 23.6, 2026-09-06; 1,150+ native functions | No re-upload; modifying needs permission; no conversion (legacy ≤19.7 is MIT) | **Avoid**: overlaps Hydra (about 2,800 functions) with the most restrictive terms of the set |

F4NV, the "Fallout 4: New Vegas" project CHALLENGES is part of, brings FNV
into FO4 by hand. Its challenge, karma and reputation choices are tested
answers to the same problems, worth checking before designing ours.

**How XDI works** (its modders' guide, Nexus article 552):

- A scene opts in by carrying the XDI keyword. A plugin can name its own
  keyword (1.2.0).
- Player options are written into the usual four response categories. The
  category no longer matters, and each category may hold any number of
  options.
- Every player line and NPC response keeps its conditions.
- A player line can have several NPC responses (a skill check's pass and
  fail). They pair by position, padded with empty options.
- Each response can link to its own scene phase or scene.
- Option cues: a question icon for lines that don't advance the
  conversation, a door icon for lines that end it.
- Vanilla FO4 dialogue is left alone.

For the converter, that means:

- FNV's `INFO` flags map almost directly: Say Once, Goodbye (the door icon),
  and info-only lines (the question icon).
- A topic list becomes one XDI player-dialogue action per phase.
- What still needs designing:
  - FO3/FNV topics belong to quests and can be spoken by any NPC whose
    conditions pass, while FO4 scenes are built around quest aliases;
  - Add Topic and the greeting that opens a talk;
  - looping back to the topic list after an answer.

**What Hydra offers** (its Nexus page, read 2026-10-05):

| Feature | Use to us |
|---|---|
| Editor IDs kept at runtime | Now: console and scripts can find plugin forms by name during play-tests |
| Papyrus linkage logging | Now: catches scripts and structs with broken links (spike 3) |
| Requirements Runner: a JSON file declares game version, F4SE version, plugins and DLLs; a mismatch warns on the main menu | Setup: names a missing or wrong-version dependency (XDI, LevelUpMenuEx) instead of failing silently |
| About 2,800 Papyrus functions: hash maps and sets, strings and regex, files and JSON, 64-bit numbers, form and engine accessors | Later: much of what converted FO3/FNV scripts and NVSE/JIP commands need, which vanilla Papyrus lacks |
| Script Object Runner: binds a script to a form at load, no dummy quest | Later: a home for the karma, reputation and item-condition logic |
| Menus and Misc Stats runners: load custom SWF menus; add Pip-Boy stats | Later: our own menus; Karma, Fame/Infamy and FNV's statistics on the stats page |
| Translations runner | Later: FO3/FNV text in other languages without editing STRINGS files |
| Engine patches: preload scripts; speed up native calls (experimental, off by default) | Neither needed. 1.0.2 already pulled part of the speed-up for changing script behavior |

**Against requiring it now:** it is one author's project, two weeks old at
1.0.2, and the speed-up patch has already changed behavior once. It keeps its
place in the `Spike` profile for logging, and disabling it is the first step
when a test result looks odd. Decided when the runtime is built (policy:
behind our API, with a fallback).

### <a id="dependency-policy"></a>Dependency or our own build

Proposed 2026-10-05, not yet decided. The split runs on what a mod's value
is:

- **Content mods** (Karma, Reputation, Weapon Condition) are mostly Papyrus
  and records. Their value is the design, and reading them gets that, so
  depending on them costs more than it saves.
- **Engine and UI frameworks** (XDI, LevelUpMenuEx) do their hard work in
  F4SE hooks and Scaleform movies. A design reference doesn't replace that.

**What a required dependency costs:**

1. **Setup without hand work** ([standalone play](../standalone_play.md)).
   Nexus files can't be fetched automatically for most users, and these
   authors forbid re-uploading. Each dependency is a manual download outside
   the converter, and the portable package can't be self-contained. XDI is
   the exception: total conversions may bundle it.
2. **The runtime gate.** An F4SE plugin is built for one exe version. After a
   game patch, players wait for the author. If the author stops, the
   converted games are pinned to an old runtime or need a rushed
   replacement. LevelUpMenuEx and XDI's menu both come from one person
   (Neanka).
3. **Control over behavior and bugs.**
   - We can't fix their code: LevelUpMenuEx states no permissions, and XDI's
     source has no license.
   - Our rules have to fit their extension points: FO3's perk every level
     against FNV's every two, different skill sets, and rules keyed on the
     character's starting world.
   - A fault inside their DLL is a black box to our disassembly and flight
     recorder.
4. **Saves.** Saves hold their forms and state. Uninstalling one, or a
   version that changes its data, can break a save, and the FormID-stability
   rules can't cover forms we don't own.
5. **Conflicts and support.** XDI replaces `DialogueMenu.swf` and
   LevelUpMenuEx the level-up menu, so other mods touching either conflict.
   Every report starts with "ours or theirs?".

**What building our own costs:**

- An F4SE plugin needs the 1.11 Address Library (not installed) and new
  addresses after each patch.
- Menus mean Scaleform/AS3 authoring, with no FO4 UI tooling here yet.
- We take on the per-patch update work the author does today.

F4SE itself is already accepted as a dependency, as SKSE and the Address
Library are for Skyrim. The question is how many more to add.

**The middle path: a dependency we can swap out.**

- Converted scripts call our own small API script, and only that script
  talks to the outside mod.
- When the mod is missing, the API falls back to something simple, such as
  the message-box level-up the Skyrim rules plugin uses.
- Replacing or dropping the dependency then touches one script, and the game
  still runs without it.

| Mod | Proposed | Why |
|---|---|---|
| XDI | Required, bundled | Engine-level; bundling allowed; nothing replaces it |
| LevelUpMenuEx | Behind our API, with a fallback | Engine + UI work, but a single maintainer. Pacing can differ per character; the skill and perk lists can't ([read](#levelupmenuex)) |
| KARMA | Our own, borrowing its design | Papyrus-only, cheap to reproduce; its API would add a manual install for little gain |
| REPUTATION | Our own | Closed to new factions |
| Armor and Weapon Condition | Our own | Restrictive permissions; FNV's own per-weapon health is better data |
| Hydra | Development tool; decide when the runtime is built | Large Papyrus library and setup checks, but brand new with one maintainer ([above](#mods)) |
| CHALLENGES | Our own, from FNV's CHAL records, borrowing its design | Three extra F4SE plugins as hard requirements; its author allows reusing its scripts and records |
| PipboyTabs | Behind our API, with a fallback | One Pip-Boy UI for skills, karma, fame/infamy and challenges; LevelUpMenuEx already feeds it |
| Baka Framework | Only if one of its pieces is needed | Small and liberally licensed, but mostly covered by Hydra |
| Garden of Eden PSE | No | Overlaps Hydra; restrictive terms |

### <a id="levelupmenuex"></a>LevelUpMenuEx, read

Read 2026-10-05 from the copy in
`references\LevelUpMenuEx` (`PRKF.dll`, built
2026-09-06, the 1.11.240 release), from its Papyrus source
`Scripts\Source\User\PRKF\PRKF.psc`, its INI and MCM files, and the DLL's
strings and INI loader. It finds the game's functions by signature scan, not
the Address Library.

**What it does:**

| Piece | How |
|---|---|
| Config | Every `Data\PRKF\*.ini` is read once at load: `disableVanillaPerks`, `overrideMaxSkillsValue` (last file wins), `PerksList` and `SkillsList` (each names a FormList), `PPPerLevel` and `SPPerLevel` (summed across files) |
| Perks | Entries of each `PerksList` FormList, checked to be PERKs and **copied into a fixed array at load**. The menu groups them by SPECIAL or "Non SPECIAL" and shows level and condition requirements. An "ineligible" filter shows or hides perks that fail their conditions (MCM default: show) |
| Skills | Entries of each `SkillsList` FormList, checked to be AVIFs and copied the same way. Spending skill points raises the actor value's base, up to `overrideMaxSkillsValue` |
| Points | Its own perk-point (PP) and skill-point (SP) counters, saved in the F4SE co-save. On each level-up it adds the INI's per-level amounts. It also hooks the game's own perk-point grant |
| Papyrus | `AddPP`, `AddSP`, `GetPP`, `GetSP`, `UpdateMenu`, `OpenMenu` |
| Traits | `OpenTraitsMenuFL(list, count, allowCloseWithoutSpending)`: pick N perks from a FormList, optionally none, as FNV's traits are |
| Tag skills | `OpenTagSkillsMenu(count, bonus, allowRetag)`, plus `AddTagSkillAV`, `RemoveTagSkillAV`, `IsTagSkillAV`. A tag adds the bonus to the skill's base value. Events `PRKF::TagSkills::Tagged`, `UnTagged` and `Finish` |
| Other | It replaces `Interface\LevelUpMenu.swf`. It takes a messaging interface for other F4SE plugins (`PRKFAddDataMessage`) |

**FO3 against FNV:**

- **Pacing works per character.** Set `PPPerLevel` and `SPPerLevel` to 0 and
  have our level-up script call `AddSP` with the character's world's
  formula: FO3's 10 + INT, or FNV's 10 + INT/2. FO3's perk every level and
  FNV's every two need `AddPP`. Not checked: whether `AddPP` takes a
  negative number, or whether the game's own point should be withheld in
  some other way.
- **Chargen works for both.** Tag three skills with a +15 bonus: call
  `OpenTagSkillsMenu(3, 15, false)` for both games. FNV traits: call
  `OpenTraitsMenuFL(traits, 2, true)`. For FO3, skip the traits call.
- **The lists can't differ per character.** They are fixed when the game
  loads, so a profile holding both FO3 and FNV shows the union of skills.
  FO3 has Small Guns and Big Guns; FNV has Guns and Survival. The other
  eleven are shared, so the union is 15.
  - Perks can still be gated on the character's world, through a perk
    condition on the starting-world global. They then fall under the
    "ineligible" filter, but are hidden only if the player turns
    "show ineligible" off.
  - Skills have no such filter.
- **Per-world FO4 profiles avoid the problem.** Each profile ships its own
  INI and lists through MO2. The all-Fallout profile has to accept the union,
  or share actor values (FO3's Small Guns as FNV's Guns, for example).
- **Not provided:** skill effects (damage, prices, lock and terminal levels,
  healing). Those stay ours, as perk entry points and conditions on the skill
  actor values, the way Be Exceptional does them.

**Checks before relying on it:**

1. Negative `AddPP`, or another way to skip a level's perk point.
2. Whether the menu can hide a skill.
3. That "hide ineligible" hides perks gated on the starting-world global.

None of these needs the converter. A small test plugin with
LevelUpMenuEx loaded would answer all three.

LevelUpMenuEx shipping a 1.11.240 build within a month of that runtime also
eases the downgrade question in [What is installed](#installed).

## <a id="ai-rules"></a>AI rules in Fallout4.exe

Spike 4, read 2026-10-05 from `Fallout4.exe.unpacked.exe` (1.11.240, image
base `0x140000000`, RTTI intact). Addresses are RVAs. The rules and their FO3
and Skyrim readings are in [engine rules](fallout_engine_rules.md) and
[Skyrim hooks](skyrim_hooks.md). Functions were matched to Skyrim 1.6.1170's
by their shape and callers: the AI state clear is instruction for instruction
the same.

| Rule | FO4 | Same as |
|---|---|---|
| R1 package choice | Chooser `0xc57a20` asks, in order: the alias packages (Actor slot 91 `0xc69440` → extra `0x88`, `ExtraAliasInstanceArray`, the same type number as Skyrim), the base form's list, the template/default list (`0x654f80` → `0x65dbd0`), the AI default (`0xcf1770`), then a combat override (`0x653b50`) | **Skyrim.** Quest-gated packages on aliases still outrank the actor's own list (census R1-1), and the default list still replaces "keep the current package" |
| R1 keep the winner | `0xcf4810`, called twice by the low-process update `0xcf6620`: winner from `0xc57a20`, `cmp` with the AI's current package `[ai+0x20]`, return when equal. FO4 adds an override branch before the compare (actor `+0x2d0` bit 26, a distance test, `0xc6b8d0`) | All three |
| R2 Once Per Day | `ExtraRunOncePacks` present | Skyrim (not read further) |
| R3 periodic check | `fEvaluatePackageTimer` 15.0 | Skyrim's value (code not read) |
| R3 `EvaluatePackage` | Native `0x10f8b00` → `Actor::EvaluatePackage` `0xc695d0(actor, 0, abResetAI)`. FO4's Papyrus adds `abResetAI` (default false). The deferred call sets actor `+0x2d0` bit 16, plus bit 17 for a reset, and moves the AI's last-processed hour back one. The per-actor update `0xc63bc0` (at `0xc6427c`) then runs the immediate call. **Without a reset** it still calls `0xd39880`, the AI state clear (Skyrim's `0x713ce0`, 22 callers to Skyrim's 21), then a forced update (`0xcefe60`). Same guards as Skyrim: actor state 0, 3 or 7 (mask `0x89`) | **Skyrim.** An unchanged package restarts: the students-stand-up bug (census R3-5) carries over. The reset flag only adds a deeper reset |
| R5 world pause | `DialogueMenu`'s constructor ORs `0x18800` into the menu flags (`+0x58`, F4SE `GameMenus.h`): allow saving, custom rendering, assign cursor. Not `kFlag_PausesGame` | **Skyrim**: no pause; FO4 talks happen in the world |
| R8 IgnoreCrime | Command table entry `0x2eed690`, handler `0x5d71b0` is `mov al, 1; ret` | **Skyrim**: a stub |
| R10 force greet end | `BGSProcedureForceGreet` (vtable `0x2510b00`), update slot 12 `0x72c970` → `0x719660`. Unlike Skyrim's greet step, a player greeting creates a conversation object (`proc+0x30`). The procedure is marked done (`0x757bc0`, Skyrim's `0x48f0c0` byte for byte) only when `0x718100` → `0x7183e0` reports it finished. That happens when either actor is gone, or when a timer runs out while the speaker has no dialogue extra (Actor slot 92 `0xc5c370`, extra `0x92`) | **Probably FO3**: the greet seems to last until the talk ends, not until the menu opens. **Not confirmed**; needs a play-test or a read of extra `0x92`'s writer |
| R13 player packages | `Game.SetPlayerAIDriven` present | Skyrim |
| R14 failsafe warp | `MovementPlannerAgentWarp` RTTI and the `FailSafe Warp` string (used at `0xdd5f05`); `bUseMovementBlockedPackage:General` defaults to 0 | **Skyrim**: actors still warp past a locked door (census R14-1) |
| Radio | `BGSSceneActionRadio`, `ExtraRadioData`, `ExtraRadioReceiver`, `ExtraRadioRepeater`, `PipboyRadioData`, `ForceRadioStationUpdate`, `fRadioStationFuzzyRange` | **Native**: FO3/FNV stations become FO4 radio activators and scenes, not runtime work (phase B8, Large, today) |

**What it means:**

- Moving to FO4 removes the radio work and maybe the force-greet fix (B2).
- The rest still needs a runtime, as F4SE code reading FO4's exe:
  - the R1 chooser redirect;
  - R3 not restarting an unchanged package;
  - the R8 crime drop;
  - the R14 warp refusal.

  That's phase B, with every Address Library ID found again for FO4.
- <a id="no-pause"></a>**R5 is kept as FO4 has it (decided 2026-10-05):** talks
  stay unpaused, with no DLL to freeze the world. What FNV's pause guarded is
  handled with records where it matters:
  - leaving: FNV's Tab becomes a `[Leave]` option (XDI's menu takes every key
    press, so Tab never reaches the game), and walking away ends the scene
    ([1b](../fo4_spikes.md#spike-1b));
  - combat breaking into a talk: FO4's normal behavior, accepted;
  - game time and script timers running during a talk: checked per script
    in spike 3, fixed with conditions or an "in dialogue" test where content
    counts time across a conversation.
- The phase A record work keeps its design, because the engine rules it
  works around are the same:
  - package order;
  - hold in place;
  - shared-topic line order;
  - Once Per Day;
  - IgnoreCrime.
- **Not read:**
  - the line picker and greeting chooser (R9; FO4's `DIAL`/`INFO` follow
    Skyrim's layout, so it's likely the same);
  - the Must Complete test in `0xcf6620`;
  - the periodic check's code;
  - what `abResetAI` resets beyond the AI state.

## <a id="lost"></a>What the move throws away

- **Code that doesn't port:**
  - FalloutRuntime (guns), the Havok gun-graph patches, the Fallout half of
    the conversation director and the phase A/B package coercions;
  - plus about 10k lines of `*_falloutnv.py`, which target TES5 layouts.

  The phase A rules and census stay valid as knowledge. FO4 breaks the same
  rules Skyrim does ([AI rules](#ai-rules)), so the code that enforces them
  would be rewritten for F4SE, not dropped.
- **Cross-world play for Fallout.** An all-worlds profile could no longer hold
  Oblivion and FNV together. FO3 and FNV could still share one FO4 all-worlds
  profile. This changes the standing rule that every plan supports both
  profiles ([decisions](#decisions)).
- **Upstream mergeability for Fallout.** Upstream targets Skyrim only, so its
  Fallout fixes would stop landing in the FO4 path. The four open upstream PRs
  for FNV (#69 to #71) stay useful upstream either way.

## <a id="pipeline"></a>How the pipeline would split

Stages run `tes4_export` → `tes5_import` → `asset_convert` → `script_convert`.

| Layer | Fate under an FO4 target |
|---|---|
| `tes4_export` (export text) | Shared unchanged. It is the only neutral layer |
| `tes5_import/base/writer.py` record framing, `derive_formid` | Shared; FO4 uses form version 131, HEDR 1.0 |
| Record converters (`tes5_import` about 64k lines) | A new sibling package, `fo4_import`, reading the same text. Many FO3/FNV records sit closer to FO4 than to TES5: TERM, NOTE, AMMO, PERK, LGTM, IMGS, IMAD, ECZN |
| Conditions | Regenerate `ctda_fnv_remap.py` against `wbDefinitionsFO4.pas` (generator: `tools/generators/gen_ctda_fnv_remap.py`) |
| Navmesh | FO3/FNV navmesh is authored and only repacked, so FO4 needs just a new NVNM serializer |
| NIF, materials | New writer: 20.2.0.7 / BSVER 130, BSTriShape, BSSkin, plus BGSM/BGEM per shape. pyffi can't write FO4 |
| Collision, Havok | Rewrite: hknp physics, Havok 2014. Elric can finish collision. `external/pynifly_hkx/anim_fo4.py` already reads and writes FO4 animations |
| Textures | Re-encode normal maps to BC5. FO4's `_s` is BC5 (R specular, G gloss); FNV keeps specular in the normal-map alpha |
| Archives | `BSArch -fo4` / `-fo4dds`, or Archive2 |
| Scripts | Keep the front end. Needs:<ul><li>a new emitter and row table</li><li>actor values passed as forms</li><li>VMAD for FO4</li><li>the FO4 compiler with Base.zip headers</li></ul>Compiler: FO4's own `PapyrusCompiler.exe`; the vendored `papyrus.exe` is Skyrim-only (fails on `Struct`), checked 2026-10-05 |
| FaceGen | Precomputed per NPC: run CK `-ExportFaceGenData` after the plugin is written |
| Precombines, previs | CK `-GeneratePreCombined`, `-GeneratePreVisData`, `-CompressPSG`, `-BuildCDX`. The first build can skip them and take the performance hit |
| LOD | New BTR/BTO output; FNV's prebuilt LOD can be renamed (see fnv-to-fo4) |
| Voice, lip | `.fuz` again, built with FO4's LipGen + LIPFuzer |

## <a id="formats"></a>Target formats

- **Plugin:**
  - Form version 131; HEDR 1.0 (DLC 0.95); flags ESM 0x1, localized 0x80,
    ESL 0x200. TES4 needs INCC.
  - Records FNV has that FO4 drops: ALOC, AMEF, CCRD, CDCK, CHAL, CHIP, CMNY,
    CREA, CSNO, DEHY, HAIR, HUNG, IMOD, LSCT, LVLC, MSET, PWAT, RADS, RCCT,
    RCPE, REPU, SLPD.
  - Mappings: CREA → NPC_ + RACE; LVLC → LVLN; HAIR/EYES → HDPT; IMOD → OMOD
    with attach points (weapon meshes must split into parts); RCPE → COBJ.
- **NPC_:** morph-key face data plus required FaceGen
  (`Meshes\Actors\Character\FaceGenData\FaceGeom\<plugin>\<FormID>.nif`).
- **Dialogue:** scenes with a Player Dialogue action, plus DLBR/DLVW. Quest,
  info and scene logic lives in Papyrus fragments.
- **Packages:** Skyrim-style procedure trees.
- **Papyrus:**
  - New in the language: structs, namespaces, `Var`, CustomEvent, remote
    events, Const.
  - Events: `OnUpdate` is replaced by timers; OnHit needs registration.
  - Compiled `.pex` is not compatible with Skyrim's.

## <a id="fnv-to-fo4"></a>fnv-to-fo4

[terry-haire/fnv-to-fo4](https://github.com/terry-haire/fnv-to-fo4) was
reviewed through the GitHub API, without cloning.

- **License and activity:** GPL-3, 64 stars, last push 2024-06-20, dormant.
  Issue #7 (converter hangs) is open.
- **Where the logic lives:** in two submodules.
  - A NifSkope fork (`src/spells/convert/convert.cpp`, 5.1k lines;
    BSD-style, with the additions unlicensed). It converts strips and shapes
    to BSTriShape, writes one JSON BGSM/BGEM per shape and maps Havok
    materials and layers.
  - An xEdit fork (`xEdit/Convert/*.pas`, MPL-2.0). It copies elements
    path → path, driven by CSVs (`Build/ElementConversions/`).
- **Pipeline:** BSA extract → NifSkope convert → Elric (with a loop that
  retries up to 100 times, deleting the mesh that crashed it) → Archive2 → an
  xEdit convert.
- **What it covers:**
  - Covered: meshes, worldspace, cells, landscape, placed objects, and FNV's
    prebuilt LOD renamed to BTR/BTO.
  - Not covered: actors, quests, scripts, dialogue, navmesh (deleted),
    equippable weapons/armor, texture conversion (specular dropped),
    precombines.
- **Bugs:**
  - Emittance colours are written R, B, G.
  - Specular colour is overwritten with white.
  - Landscape layers outside index -1..2 are deleted.
- **Worth taking as facts (clean-room, not code):**
  - the FO/FNV → FO4 Havok material and layer maps (`convert.cpp`
    lines 438-660);
  - the strip winding rule;
  - the shader-flag → BGSM key table (`c_material.cpp`);
  - the "alpha-blended lighting shape → effect shader unless it's a decal"
    rule;
  - LOD file naming and recentring (`lod.cpp`);
  - `__RecordConversions.csv` as a gap checklist.
- **Verdict:** reference only. The fork's own export text and record
  knowledge already go well beyond it.

## <a id="decisions"></a>Decisions for the user

1. **Profiles.** Accept that Oblivion/Morrowind and Fallout can no longer share
   one all-worlds profile, and that FO3 + FNV share an FO4 one instead.
2. **Where the work lives.** Decided 2026-10-05: a separate repo,
   [fo3fnv-in-fo4](https://github.com/ThyMrMan/fo3fnv-in-fo4) (private for
   now). It is a new repo, not a GitHub fork, carrying `standalone`'s history
   so upstream and `standalone` still merge in. FO4 code goes beside the
   inherited Skyrim code; nothing is deleted while merges continue.
3. **Freeze the Skyrim Fallout path?** What happens to Fallout work in Skyrim
   (FalloutRuntime, phase B, character rules for Fallout) while the FO4 spikes
   run. Upstream fixes already in flight (#69 to #71) are unaffected.
4. **Dependencies.** Accept or change the proposed split in
   [Dependency or our own build](#dependency-policy).
5. **Fidelity defaults.** Defaults to pick: power armor (FO4 frame vs worn),
   crits (charge vs chance), FNV's perk pacing, a voiced-player wheel vs a
   silent list UI. Decided 2026-10-07: drift toward FO4's mechanism is
   accepted and recorded ([fo4_drift.md](../fo4_drift.md)); topic dialogue
   is XDI's silent list.
6. **Character system.** Decided 2026-10-07: FNV's (and FO3's) own
   character system on LevelUpMenuEx (`PRKF`, installed with F4SE
   1.11.240), not FO4's perk chart. FNV's 13 skills stay plugin actor
   values, so the 956 FNV and 94 FO3 dialogue skill checks keep their
   meaning. LevelUpMenuEx reads `Data\PRKF\*.ini`: `SkillsList` and
   `PerksList` (form lists), `PPPerLevel`/`SPPerLevel` (whole numbers),
   `disableVanillaPerks`; its Papyrus (`PRKF:PRKF`) has `AddSP`/`AddPP`,
   `OpenTagSkillsMenu(3, 15, …)` and `OpenTraitsMenuFL(list, 2, …)`.
   FNV's 10 + Intelligence ÷ 2 skill points and a perk every 2 levels come
   from a level-up script adding the difference. Drift: skills show in
   LevelUpMenuEx's menu, not a Pip-Boy page; the Pip-Boy keeps FO4's
   SPECIAL and perk pages.
7. **Garden of Eden.** Decided 2026-10-07: a dependency (F4SE plugin,
   about 1,160 Papyrus natives; headers copied into
   `references\GardenOfEden` for compiling). First use: FO3/FNV
   `SexChange` as the console's `sexchange` (`ExecuteConsoleCommandSilent`),
   which FO4 Papyrus cannot do. Taken where it removes a recorded drift or
   a polling loop, not by default: `RegisterForOnPerkPointIncrease` (a
   real level-up hook for the character rules), the native events
   (`OnActorValueChanged`, container changes, object loads, cell attach,
   hits) in place of 0.1 s GameMode polls, VATS critical charge and count
   for FNV's crit chance, current-topic and dialogue pause/stop for
   scripted lines, per-item instance data for later item conditions.

## <a id="spikes"></a>Proposed spikes

Each spike is small, can be thrown away, and answers one question before
anything is committed:

1. **Dialogue.**
   - Build Doc Mitchell's opening conversation (FNV) by hand, from the
     export text, as XDI-enabled FO4 scenes: topic list, more than four
     choices, SPECIAL/skill checks, silent player.
   - Then build one generic topic that many NPCs share, to see how
     quest-owned, condition-picked topics fit alias-based scenes.
   - Answers: whether the topic → scene mapping can be generated without
     hand work, and what it does with Add Topic, greetings and the
     return to the topic list.
2. **One interior cell end to end.**
   - Doc Mitchell's house: records via a minimal `fo4_import` (CELL, REFR,
     STAT, LIGH, DOOR, NPC_), meshes through a minimal BSTriShape + BGSM
     writer (or Elric), textures re-encoded, FaceGen from the CK.
   - Answers: the real cost of the asset back end.
3. **One script.**
   - Compile a converted FNV object script (a terminal's, for instance)
     against FO4 headers.
   - Answers: whether the vendored compiler works, and how big the row-table
     change is.
4. **Exe reads.** Done 2026-10-05 ([AI rules](#ai-rules)): FO4's AI is
   Skyrim's for R1, R3, R5, R8 and R14. Radio is native. A force greet
   probably lasts through the talk.
