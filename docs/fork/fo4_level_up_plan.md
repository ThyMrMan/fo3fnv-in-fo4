# Our own level-up menu (plan)

**Status:** planned 2026-11-12; the perk and skill images are staged by every
build, PRKF.dll's points, tags and perk list are rebuilt in Papyrus, and our
own menu opens in place of `LevelUpMenu` with skill, perk and taken pages,
and serves as the tag and trait menus too, listing every DLC's perks and
traits, with the balance options and a hotkey in MCM and an API for other
mods; LevelUpMenuEx is no longer required (built 2026-11-12, not played).
Status lines live only in
[ROADMAP.md](ROADMAP.md). The framework side (f3ui, replacing a vanilla
menu, the image staging) is in
[swf_framework.md](swf_framework.md#level-up).

**Scope:** FNV's and FO3's level-up (skill points, perks, traits, tags) in a
menu of our own on f3ui, replacing LevelUpMenuEx, with the extras players
have bolted onto level-up menus built in. Not the perks themselves
([fo4_perks.md](fo4_perks.md)) or the rules handing out points
(`F3NV_CharacterRules`).

## <a id="today"></a>What LevelUpMenuEx did for us

LevelUpMenuEx (Neanka; `LevelUpMenu.swf`, `PRKF.dll`, PRKF scripts and an
MCM config; unlicensed, read only, `references/LevelUpMenuEx`) was a hard
dependency until 2026-11-12 ([dropped](#dropped)):
- it lists `FNV_Perks` (its INI's `PerksList`; 91 FNV perks by level then
  name) and `FNV_Traits`, reading each perk's ranks, level and next rank
  ([fo4_perks.md](fo4_perks.md#hasperk));
- its skill page spends the skill points `F3NV_CharacterRules` hands out;
  perk points come every `LevelsPerPerk` levels from the same rules (the
  INI's own `PPPerLevel` stays 0);
- its trait and tag-skill menus (`OpenTraitsMenu`, `OpenTagSkillsMenu`,
  with re-tagging) run character creation.

What it lets a player set (its MCM): the perk sound and whether it loops,
showing or hiding ineligible perks, and a hotkey that opens the menu without
the Pip-Boy. Its INI (for mod authors): the perk and skill lists, perk and
skill points per level, a skill cap override, and turning off vanilla
perks. Its Papyrus: add or read perk and skill points, the trait and tag
menus, and events as skills are tagged. Nine translation files.

## <a id="defaults"></a>Built in and on by default

Only what makes the menu easier to use; nothing here changes balance.

| Feature | Seen in |
|---|---|
| **Search** by name, requirement or perk type | Baka Level Up Menu (FO4 48730) |
| **Filters** (available, ineligible, all) and **sorting** (level, name, category) | LevelUpMenuEx has only the ineligible toggle |
| **Requirements met and unmet**, each with the player's value: "Science 50 (you have 45)", "Level 8" | Partly in LevelUpMenuEx |
| **Skill preview** while spending: the new value, the tag bonus, and the perks those points would unlock | None found |
| **Undo and reset** of points spent before confirming | None found; FNV has no undo |
| **Perks taken**, with their ranks, on their own tab | Neither game's level-up screen |
| **Banking:** leave with points unspent and spend them later | FNV Delay Level Up (87427) |
| **Hotkey** to reopen the menu (banked points, or to browse) | LevelUpMenuEx |
| **Controller support, HUD or FallUI color, translations** | Our framework ([controller](swf_framework.md#controller), [translations](swf_framework.md#translations)) |

## <a id="options"></a>Options, defaulting to the source game's values

Each changes balance, so each defaults to what FO3 or FNV does, and keys on
the character's starting world
([both profiles](#profiles)).

| Option | Default | Seen in |
|---|---|---|
| Perks every N levels (**built**) | FNV 2, FO3 1 (`F3NV_CharacterRules.LevelsPerPerk`) | FNV Perk Every Level mods (59629), FNV's `iPerksPerLevel` INI tweak |
| Skill points per level and per Intelligence (**built**) | 10 + Intelligence x 0.5 (FNV) or x 1 (FO3) (`character.py` `RATES`) | Skill point limiters (47036) |
| Skill cap (**built**), level cap | The game's | LevelUpMenuEx's skill cap override |
| **Choose later:** a perk-list entry that keeps the pick for later | Off | FNV mods 76593 and 45604 (a consumable reopens the pick); ours is banking |
| **Two half level-ups:** half the skill points and a perk pick, twice a level | Off | An FNV mod |
| **Random draft:** pick 1 of 3 random perks, with re-roll and remove | Off | FNV mod 77762 (needs Vanilla UI Plus there) |
| **Respec** perks, skills or both, with an optional cost (caps, an item) | Off | FO4: Perk Reset Chem, Quick Player Respec (38621), Chazz's Respec Tool (1563), Ish's Respec Mod (12383); FNV mod 71086 |
| **Delay level-up** until sleeping or resting | Off | FNV Sleep To Level Up |
| Perk sound, looping | On, as LevelUpMenuEx | LevelUpMenuEx |

**Built 2026-11-12 (not played):** an MCM page per game plugin
(`fo4_import/level_up/options.py`, templates in `level_up/mcm/`), installed by
the game build as `MCM/Config/F3NV_<plugin>/` (loose; `F3NV: Fallout New
Vegas`, `F3NV: Fallout 3`):
- **LEVEL-UP:** levels per perk (1 to 5), skill points per level (0 to 30),
  skill points per Intelligence (0 to 3, by 0.5), skill cap (50 to 250, by
  5). The rates apply from the next level-up (`TopUp` reads them each time).
- **LEVEL-UP MENU:** show every perk at first (LevelUpMenuEx's ineligible
  filter; `ShowAllPerks`, the movie's starting `showAll`), and a hotkey
  that opens the menu (`keybinds.json`, `CallFunction` of the rules'
  `OpenLevelUp`): the [defaults](#defaults)' hotkey.

**No second copy, and no INI of ours.** MCM's `PropertyValue` sources
read and write the rules quest's own properties (`F3NV_CharacterRules`'
rates, `F3NV_LevelUp`'s `SkillCap`, `ShowAllPerks`), which the save keeps.
Our scripts call nothing of MCM's, so they compile and run without it.
Without MCM every option stays the game's value the build wrote; the plan's
"INI behind it" would need F3NV.dll to read one (Papyrus can't read a mod
INI), so it is left out until a player needs the options without MCM
(console: `setpqv`). Each game plugin's rules quest has its own values, so
the options key on the character's starting world as the rules do
([profiles](#profiles)). `MCM.swf` and `mcm.dll` know these source types
and `scriptName` (read 2026-11-12); whether `CallFunction` honors
`scriptName` on a quest with three scripts is the play check's.

**Not yet:** the level cap (FO4 has none to set; FNV's is
`iMaxCharacterLevel`), the perk sound (our menu plays none yet), and the
off-by-default features above (choose later, half level-ups, random
draft, respec, delay until sleep).

## <a id="prkf"></a>PRKF.dll's work, in Papyrus (built 2026-11-12, used by our menu)

PRKF.dll keeps perk and skill points, the tagged skills and the perk list,
and opens its menus on them. None of the non-menu part needs native code,
so F3NV.dll gets nothing:
- **Points and tags** are variables of `F3NV_LevelUp` (on the
  `FNV_CharacterRules` quest), saved with the game like any script's. The
  API is PRKF's: `AddPerkPoints`, `AddSkillPoints`, `GetPerkPoints`,
  `GetSkillPoints`, `Tag`, `Untag`, `IsTagged`, and the custom event
  `PerkTaken`. The tags themselves live on `F3NV_CharacterEvents`
  ([tags](#tags)); `Tag`, `Untag` and `IsTagged` pass through to it.
- **The perk list** is `FNV_Perks` through F4SE's Perk natives:
  `NextRank` and `Rank` walk a perk's rank chain (`GetNextPerk`,
  `GetNumRanks`). `Eligible` is the level (`GetLevel`) plus the engine's own
  test of the converted conditions (`IsEligible`, which skips the level).
  `PerkList(0|1|2)` returns all of them, the eligible ones or the
  ineligible ones. `TakePerk` adds the next rank for a perk point, and
  `RaiseSkill` spends skill points up to `SkillCap`.
- **Requirement rows** show the reasons ("Science 70 (you have 45)").
  `fo4_import/spike/level_up.py` turns each playable perk's source
  conditions into a row in parallel arrays (`Requirement*`), because the
  build can't write struct properties. A row is an actor value, sex,
  another perk or the level, with the comparison, the value and the OR
  flag. `RequirementRows`, `PlayerValue` and `RequirementMet` read them.
  Census: FNV 105 rows (97 skill or SPECIAL, 6 sex, 1 perk, 1 level), FO3
  66, nothing left out (`level-up requirement not shown`). A row shows
  the base value; whether the perk can be taken is still `IsEligible`'s
  call.
  - **Fixed 2026-11-12:** a sex row compared the player's sex with the
    condition's value (1), so every "is male" perk (Lady Killer,
    Confirmed Bachelor, Action Boy) failed for a man. A sex row now tests
    the player's sex `==` or `!=` the sex the condition names
    (`GetIsSex(Male) == 1` is "sex == 0").

Since our menu took over level-ups ([open](#open)), the rules give each
level's points to this script, and no PRKF menu is opened any more
([tags](#tags)). Arrays a script builds hold at most 128 entries,
which `PerkList` stays under for FNV with its DLCs (122 perks); a DLC's
perks join `FNV_Perks` at run time ([lists](fo4_plugin_layout.md#dlc-lists)),
and the menu reads each plugin's own table ([tables](#tables)).

## <a id="open"></a>Opening ours in place of `LevelUpMenu` (built 2026-11-12, not played)

No DLL, and no `LevelUpMenu.swf` of ours. `F3NV_CharacterRules` already
watched `LevelUpMenu`; now, whenever it opens, `OpenLevelUp`:
1. closes `LevelUpMenu` and the Pip-Boy (FNV's level-up screen is not
   part of its Pip-Boy, and no source gives FO4's menu depths, so ours is
   not put over an open Pip-Boy);
2. gives the levels gained since the last time their points (`TopUp`,
   now into `F3NV_LevelUp`, no longer topping up PRKF's);
3. once, moves the points and tags LevelUpMenuEx kept on an older save to
   ours (`MovePrkf`, [tags](#tags),
   [end-user state](../../CLAUDE.md#end-user-state));
4. waits until no menu is open (`WaitOutOfMenus`), then opens ours
   (`ShowOurs`, shared with the tag and trait menus).

So it catches every way into `LevelUpMenu`: the Pip-Boy's button,
LevelUpMenuEx's hotkey, a script. The cost is a moment of the vanilla (or
LevelUpMenuEx's) screen before ours, and the Pip-Boy closing. If that
flash is ugly in play, the next step is F3NV.dll swapping the menu table's
`LevelUpMenu` constructor (`UI::menuTable`, F4SE `GameMenus.h`), which
needs no flash and no Pip-Boy close; F4SE's own custom menu can't be
registered under a vanilla name (`RegisterCustomMenu` refuses a
registered name).

The perk stage handling (`WatchStages`, `RunPerkStages`,
[intense training](fo4_pipeline.md#intense-training)) runs round our menu
in every mode.

## <a id="menu"></a>The menu (built 2026-11-12, not played)

`fo4_import/level_up/` (`F3NV_LevelUp.as`, `f3nv/levelup/Character.as`)
on f3ui, built by `mxmlc`, installed by the masterless build as
`Interface/F3NV_LevelUp.swf`, registered by `F3NV_LevelUp.psc` with the
casino's menu flags. Three pages (Prev/Next):
- **SKILLS:** each skill and its value. Accept or Right sets a point, Left
  takes one back, within the points, the base and `SkillCap`; Y resets;
  X spends them. The list shows "45 > 50" while set, and the right side
  names the perks those points would open. Back with points set asks
  whether to spend them.
- **PERKS:** the perks with a rank left that can be taken now; X shows all
  of them, the others dimmed. The right side shows the image, ranks held,
  the requirements (level first, OR groups on one line, each unmet one
  with "(you have N)") and the description. Accept asks, then takes it;
  Papyrus's `TakePerk` (the engine's `IsEligible`) has the last word.
- **TAKEN:** the perks held, with their ranks.

Points not spent stay for later (banking). The HUD color, hints with key
names or button glyphs, and translated words (`$F3NV_LU_*`) come from the
library.

**What the menu shows comes from the build, not the engine.** F4SE's Form
and Perk natives aren't flagged no-wait, so each call from Papyrus costs
its stack a frame; asking for 91 perks' names, descriptions, images,
levels and ranks would take seconds. The build writes them as properties
(`level_up.py`): the skills' on `F3NV_LevelUp` (`skill_table`), the perks'
and traits' on each plugin's `F3NV_LevelUpTable` ([tables](#tables),
`table_properties`): `SEP`-joined strings
(`PerkNames`, `PerkDescriptions`, `PerkImages`, `SkillNames`, ...), the
levels and rank counts, every rank in order (`RankForms`), and per
requirement row its perk's place in the list (`RequirementOwners`), where
the tested value is (`RequirementTargets`: SPECIAL then skills, or a
listed perk) and a label. Census (stand-in FormIDs, 2026-11-12): FNV 91
perks, 111 ranks, 105 rows, every row placed, descriptions 12 KB; FO3 61,
91 and 66. At open, `Gather` asks only for the ranks held (`HasPerk` along
`RankForms`) and the 20 base values, split over 8 stacks
(`CallFunctionNoWait`) so their frames overlap; the menu works out
eligibility from the rows. The log line `F3NV_LevelUp: sent in Ns` measures
it.

**Not yet:** search and sorting, options and the API (step 6).

## <a id="tables"></a>Every plugin's perks and traits (built 2026-11-12, not played)

A DLC adds perks and traits, and two plugins overriding one record don't
stack ([dlc-lists](fo4_plugin_layout.md#dlc-lists)), so no DLC overrides
the game's tables. As with condition's rows
([sources](fo4_condition.md#sources)), each plugin's are its own:
- `F3NV_LevelUpTable` holds one plugin's own listed perks and traits
  (`table_properties`, `builder.ids.is_own`: a DLC's, not its masters'):
  names, descriptions, images, levels, rank chains, the traits' forms, and
  its perks' requirement rows. A row's owner and a perk row's target index
  this table's perks; a requirement on a perk of another plugin is a target
  of -1, and the menu is told whether the player has it
  (`UnlistedHeld`).
- The game's table is a script of the rules quest itself, beside
  `F3NV_LevelUp`. A DLC writes `FNV_LevelUpTable_<plugin>`, a start-game
  quest that adds itself to `FNV_LevelUpTables` (an empty game form list;
  `FormList.AddForm` is kept by the save and stacks) as it starts. A DLC
  without perks or traits writes none.
- When the menu opens, `F3NV_LevelUp.Collect` takes its own quest's table
  first (an older save's rules quest never ran the table's start), then
  each registered one. `Merged` joins each table's text whole; the movie
  moves owners and perk targets by where that table's perks start
  ([open delay](#open-delay)). `Gather` asks each table for its ranks and
  traits held; a pick (`ListedPerk`) and the trait menu (`SetTraits`) go
  back to the table they came from. The movie sees one list.

Census of the exports (2026-11-12), each DLC's own listed perks (ranks) and
traits: Dead Money 7 (7), Honest Hearts 6 (6), Old World Blues 4 (5) and 6
traits (Claustrophobia, Skilled, Logan's Loophole, Hoarder, Hot Blooded,
Early Bird), Lonesome Road 13 (13), Gun Runners' Arsenal 1 (1); the four
courier packs none. With all of them: 122 perks, 16 traits, inside the
trait menu's 31 (`MASK_BITS`; a plugin past it is counted, `level-up menu
traits past its mask`).

## <a id="open-delay"></a>The open delay (built 2026-11-12, not played)

Played 2026-11-12: every open logged `sent in 2.2s` (the menu's data,
gathered after it opened), on top of the wait for the Pip-Boy to close and
0.5 s more. Papyrus runs only a small slice of script work each frame, and
each native call on the player costs its stack a frame. The open spent its
time on:
- **Text the build already knew.** The table joined its perk levels and
  ranks (91 each) and six columns of its 105 requirement rows, about 800
  joins of growing strings, and moved owners and targets one by one.
- **`UnlistedHeld`**, one `HasPerk` per row testing a perk the table
  doesn't list, after `Gather` instead of beside it.
- **The tag and trait menus** gathered every perk and row they never show
  (fixed first: each mode gathers only what it shows).

Now:
- **The build writes the texts whole.** `PerkLevels`, `PerkRanksText` and
  every `Requirement*` column are SEP texts (`level_up.properties`,
  `perk_table`); `PerkRanks` stays an array for the ranks held. `Text`
  returns properties only, so an open joins one text per table.
- **The movie moves the indexes.** `Built` hands over each table's perk
  and row counts (args 33 and 34, the added perks as a last group), and
  `Character.groupStarts` moves each row's owner and perk target by where
  its table's perks start.
- **Only the unlisted rows are asked about.** The build lists them
  (`UnlistedRows`, `UnlistedPerks`); `ScanUnlisted` runs as one more stack
  beside `Gather`'s, and hands over the indexes of the rows that pass
  (with an added perk's game test), not a 0 or 1 per row.
- **Gathered while the Pip-Boy closes.** `ShowOurs` calls `Prepare`
  first, which registers the menu and builds its data; the menu opens once
  no menu is open, without the 0.5 s settle a message box needs
  (`WaitOutOfMenus(False)`), and `Send` hands the prepared data over.

**Play check:** the Papyrus log's `gathered in` line per open, and the
time from the level-up button to a filled menu.

## <a id="tags"></a>Tag skills and traits (built 2026-11-12, not played)

The same movie and script, opened in another mode
(`F3NV_LevelUp.Open(mode, count, bonus)`; `LevelUpMode`, `TagsMode`,
`TraitsMode`), each with one page and no Back:
- **TAG SKILLS** (`kind == "tags"` from a converted `SetTagSkills count`,
  `count` skills in all: FNV's 3 at Doc Mitchell's, one more for Tag!).
  Accept tags or untags; a skill tagged before stays (locked); the list
  shows the value with the tag bonus. X confirms once exactly `count` are
  tagged ("Tag N more" otherwise), and `OnMenuTags` gets a bit per skill.
- **TRAITS** (`kind == "traits"`, up to `TraitCount`, 2): Accept chooses or
  drops a trait from `FNV_Traits`, with its image and description; X
  confirms, and `OnMenuTraits` adds the chosen and removes the dropped
  ones. The trait names, descriptions and images are build tables
  (`TraitNames`, ...; `level_up.py` `texts`), as the perks' are.

The picks come back as an Int bitmask, so a menu holds at most 31 entries
(`MASK_BITS`); the build counts any past that (`level-up menu entries past
its mask`, 0 today: FNV has 13 skills and 10 traits, FO3 has no traits).

**The tags live on `F3NV_CharacterEvents`**, which converted scripts
already call: `IsPlayerTagSkill` is `IsTagged`, `SetPlayerTagSkill` is
`SuggestTag` (`commands_falloutnv.py`). A suggested tag (the Vault 21 psych
test's picks) counts as tagged and shows up ticked in the tag menu, where
the player may still untag it. **The bonus** (`TagBonus`, 15) is the rules':
`TagsChosen` gives it to each tagged skill not yet in `Bonused` and takes
it back from one untagged, then clears the suggestions; `SetSkillBases`
adds it back when SPECIAL is set again. So a skill keeps one bonus however
often the menu runs.

`MovePrkf` runs once, on a save made with LevelUpMenuEx: it moves PRKF's
banked points and tagged skills to ours, each tag marked as bonused (its
tag menu gave it). It is the only code still calling PRKF; without
LevelUpMenuEx its calls give nothing.

## <a id="images"></a>Images from the records

Each perk's image is its FNV `ICON`, staged by `level_up_icons.py` and
written into the converted PERK's own `ICON` (FO4's "Image" field, which
vanilla never fills; F4SE's `GetIconPath` reads it, since `BGSPerk` has a
`TESIcon`), and into the menu's `PerkImages` table. Skills have no such
field in FO4 (`ActorValueInfo` has none), so their images are only in
`SkillImages`, from the FNV AVIF's `ICON`.

## <a id="api"></a>For other mods

As with [item-card lines](swf_framework.md#card-lines), a small API:
- **Papyrus:** add perks or skills to the menu; open the trait and tag
  menus (with re-tagging, for FNV's Tag! perk); add points; events as a perk
  is taken, a skill tagged and a level-up finished.
- **LevelUpMenuEx's INI list format** (`PerksList`, `SkillsList` and the
  point settings), read so existing add-ons (P76 Perks, You Are Exceptional
  and Be Exceptional patches) work without LevelUpMenuEx. Only the file
  format, not its code. **Open decision**, as with PipboyTabs' INIs.

**Built 2026-11-12 (not played),** all on `F3NV_LevelUp`:
- **Reaching it:** `F3NV_LevelUp.Get()` (global), so a mod needs no master
  but `FalloutHelpers.esl`, which every converted plugin masters. It reads
  Cleanroom UI's shared holder when `CleanroomUI.esl` is loaded
  ([plugin](#plugin)), else `F3NV_CharacterEvents.LevelUp` (helper quest
  `0x901`, [holder](#holder)), which the level-up
  sets as the rules quest starts (`OnInit`) and each time our menu registers
  (`Register`, `Announce`); on a save from before, `Get()` is None until
  the menu first opens. With two games loaded, the one whose rules ran last.
- **Points:** `AddPerkPoints`, `AddSkillPoints`, `GetPerkPoints`,
  `GetSkillPoints`, `RaiseSkill`, `TakePerk`, `CanTake`, `Rank`,
  `NextRank`, `PerkList` (from [prkf](#prkf)).
- **Menus:** `OpenLevelUpMenu()` (as the Pip-Boy's button: points topped
  up, then ours), `OpenTagMenu(aiTags)` (tags in all; tags held stay
  locked, so Tag! is `OpenTagMenu(held + 1)`), `OpenTraitMenu(aiTraits = 0)`
  (0: the game's `TraitCount`). Each goes through the holder's openers,
  which `F3NV_CharacterEvents` hands to the rules' (`OpenLevelUp`,
  `OpenTags`, `OpenTraits`); they wait until no menu is open.
- **Tags:** `Tag`, `Untag`, `IsTagged` (`F3NV_CharacterEvents` holds them).
- **Events:** `PerkTaken` (the rank), `SkillRaised` (skill, points spent,
  new base), `TagsChosen`, `MenuClosed` (mode, perk and skill points left:
  a level-up finished when the mode is 0), `SkillTagged` and
  `SkillUntagged` (the host's, for tags set through it or our menu);
  `F3NV_CharacterEvents`' own `SkillTagged` and `SkillUntagged` for every
  tag.

## <a id="holder"></a>The level-up holder (Cleanroom UI's, built 2026-11-12, not played)

`F3NV_LevelUp` and `F3NV_LevelUpHolder` are Cleanroom UI's
(`ThyMrMan/cleanroom-ui`, its `docs/level_up_plan.md#holder`), copied here
until the converter takes that repo as a submodule. The host names no
converter script: it asks its holder (its `Events` property) for the tags,
for where `Get()` finds it, and for what opening each menu does.

**`F3NV_CharacterEvents` is our holder** (`extends F3NV_LevelUpHolder`):
- Its `IsTagged`, `IsSuggested`, `Tag`, `Untag` and `SuggestTag` have the
  holder's signatures, so they replace the holder's own as they were; the
  tags stay in its saved `Tagged` and `Suggested`.
- `Running()` and `Hold()` use its `LevelUp` property, as `Get()` did
  before, so older saves keep the running level-up.
- `OpenLevelUp`, `OpenTags` and `OpenTraits` call the rules' openers of
  the same names (`Rules()`: `LevelUp as F3NV_CharacterRules`), which top
  up points, give the tag bonus and move LevelUpMenuEx's state.

`F3NV_LevelUpHolder.psc` ships with the masterless build like every
static script; without it `F3NV_CharacterEvents` would not bind. On a save
from before, `F3NV_CharacterEvents` gains its parent's variables; **check
in game** that an older save keeps its tags.

## <a id="plugin"></a>`CleanroomUI.esl` (not shipped yet)

`Get()` first reads Cleanroom UI's shared holder (`CleanroomUI.esl`
`0x800`), which every level-up host announces itself to, and falls back to
ours above. The converter doesn't ship `CleanroomUI.esl` yet, so today
`Get()` takes the fallback; `Game.IsPluginInstalled` keeps the missing
plugin out of the log.
- **Perks of other mods:** `AddPerk(akFirstRank)` and `RemovePerk`, kept by
  the save. An added perk no plugin's table lists comes after them, read
  from the perk itself as the menu opens (`DescribeAdded`: `GetName`,
  `GetDescription`, `GetIconPath`, `GetLevel`, `GetNumRanks`, each a frame
  per perk). Its requirements are one row of kind 4, the game's own test
  of its next rank (`IsEligible`), shown as "Its own requirements"
  (`$F3NV_LU_OWN_TEST`); taking it is `TakePerk` as for any other.

**Not yet:** skills of other mods (the menu's skills are FNV_Skills, and a
skill's tag rides a 31-bit mask), and LevelUpMenuEx's INI format (the open
decision above). A tab in an added perk's name or description would split
its entry: Papyrus has no string search to strip it.

## <a id="dropped"></a>LevelUpMenuEx dropped (2026-11-12, not played)

Nothing of ours needs LevelUpMenuEx any more:
- **No INI.** The game build no longer writes `Data/PRKF/<plugin>.ini`
  (its perk and skill lists, `disableVanillaPerks`, the skill cap). An
  older build's copy is deleted by the next one (`character.drop_prkf_ini`,
  counted as `LevelUpMenuEx INI deleted`); the deployed copy goes with the
  deploy's `--delete-stale` ([end-user state](../../CLAUDE.md#end-user-state)).
  The perk chart it turned off never opens: `LevelUpMenu` opening opens
  ours ([open](#open)).
- **No compile dependency.** `header_dirs()` (and Caprica's
  `HEADER_FOLDERS`) is F4SE then Base; `references/LevelUpMenuEx` is
  reading material only. The one call left, `MovePrkf`, reaches
  `PRKF:PRKF` by name (`Prkf`, `Utility.CallGlobalFunction`), so it
  compiles without LevelUpMenuEx's sources.
- **The move from an older save.** `MovePrkf` runs only while PRKF.dll is
  loaded (`F4SE.GetPluginVersion("PRKF")`): it moves the banked perk and
  skill points and the tagged skills once, the first time our menu opens.
  Without PRKF.dll it waits, so a player who removed LevelUpMenuEx before
  updating can put it back for one load. The README says to keep it until
  the menu has opened once.
- **Not a requirement anywhere:** the install check
  (`fo4_install_check.REQUIRED_MODS`), the README's mod list and the app's
  finish text no longer name it. Installed alongside, it does no harm: its
  `LevelUpMenu.swf` is what opens, and ours replaces it.

## <a id="profiles"></a>Both profiles

- Every setting keys on the character's starting world, as the character
  rules do ([decisions](character.md#decisions),
  [profiles](character.md#profiles)): an FO3 character gets a perk every
  level and no traits; an FNV character gets traits and a perk every two
  levels.
- [No base-game override](character.md#no-base-overrides): our menu opens in place of the vanilla
  `LevelUpMenu`; we never ship a `LevelUpMenu.swf`.

## <a id="order"></a>Order

1. **Spike:** one staged perk image mounted and shown in a menu of ours
   (DXT3/DXT5 through `MountImage` are untested;
   [images](swf_framework.md#level-up)). **Built 2026-11-12, not played.**
   - **PRKF.dll's state in Papyrus** ([prkf](#prkf)): built 2026-11-12.
2. **Opening ours instead of `LevelUpMenu`** ([open](#open)): built
   2026-11-12 in Papyrus, not played.
3. **Perk page** with the default features above, reading `FNV_Perks` as
   LevelUpMenuEx does ([menu](#menu)): built 2026-11-12 with filters,
   requirements and a taken page, and every DLC's perks and traits
   ([tables](#tables)); search and sorting left.
4. **Skill page** with the preview, undo and banking ([menu](#menu)):
   built 2026-11-12.
5. **Traits and tags** at character creation, with re-tagging
   ([tags](#tags)): built 2026-11-12, not played.
6. **Options** in MCM ([options](#options)): the balance values, the
   show-all filter and the hotkey built 2026-11-12, not played; the level
   cap, perk sound and the off-by-default features left. Then the **API**
   ([api](#api)): `Get`, the menu openers, `AddPerk` and the events built
   2026-11-12, not played; other mods' skills and the INI format left. Then
   dropping LevelUpMenuEx from the requirements ([dropped](#dropped)):
   done 2026-11-12, not played.

**Open questions:**
- Whether the moment of `LevelUpMenu` before ours is acceptable in play,
  or F3NV.dll should swap the menu's constructor ([open](#open)).
- Whether Vanilla UI Plus or zUI already show highlighted requirements or
  sorting in FNV's level-up screen (their feature lists weren't found).
- Settled 2026-11-12: a perk's image is in its own `ICON` and the menu's
  table, a skill's only in the table ([images](#images)).

## <a id="sources"></a>Sources (searched 2026-11-12)

- [LevelUpMenuEx (28222)](https://www.nexusmods.com/fallout4/mods/28222),
  [Baka Level Up Menu (48730)](https://nexusmods.com/fallout4/mods/48730),
  [P76 Perks (107588)](https://www.nexusmods.com/fallout4/mods/107588),
  [Traits and More Perks (8802)](https://www.nexusmods.com/fallout4/mods/8802/?tab=description)
- Respec: [Chazz's Respec Tool (1563)](https://www.nexusmods.com/fallout4/mods/1563?tab=description),
  [Quick Player Respec (38621)](https://nexusmods.com/fallout4/mods/38621?tab=posts),
  [Ish's Respec Mod (12383)](https://www.nexusmods.com/fallout4/mods/12383?tab=docs),
  [Perk Reset Chem](https://wccftech.com/fallout-4-mod-players-reset-refund-perks/)
- FNV: [Delay Level Up and banking (87427)](https://nexusmods.com/newvegas/mods/87427),
  [Choose Later (76593)](https://nexusmods.com/newvegas/mods/76593),
  [level-up tweaks (45604)](https://www.nexusmods.com/newvegas/mods/45604),
  [perk every level (59629)](https://nexusmods.com/newvegas/mods/59629),
  [skill point limiter (47036)](https://www.nexusmods.com/newvegas/mods/47036),
  [random perk pick (77762)](https://nexusmods.com/newvegas/mods/77762),
  [full respec (71086)](https://www.nexusmods.com/newvegas/mods/71086),
  [skill points formula](https://fallout.fandom.com/wiki/Fallout:_New_Vegas_skills)
