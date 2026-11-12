# Our own level-up menu (plan)

**Status:** planned 2026-11-12; the perk and skill images are staged by every
build, PRKF.dll's points, tags and perk list are rebuilt in Papyrus, and our
own menu opens in place of `LevelUpMenu` with skill, perk and taken pages,
and serves as the tag and trait menus too, listing every DLC's perks and
traits (built 2026-11-12, not played).
Status lines live only in
[ROADMAP.md](ROADMAP.md). The framework side (f3ui, replacing a vanilla
menu, the image staging) is in
[swf_framework.md](swf_framework.md#level-up).

**Scope:** FNV's and FO3's level-up (skill points, perks, traits, tags) in a
menu of our own on f3ui, replacing LevelUpMenuEx, with the extras players
have bolted onto level-up menus built in. Not the perks themselves
([fo4_perks.md](fo4_perks.md)) or the rules handing out points
(`F3NV_CharacterRules`).

## <a id="today"></a>What LevelUpMenuEx does for us today

LevelUpMenuEx (Neanka; `LevelUpMenu.swf`, `PRKF.dll`, PRKF scripts and an
MCM config; unlicensed, read only, `references/LevelUpMenuEx`) is a hard
dependency:
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
| Perks every N levels | FNV 2, FO3 1 (`F3NV_CharacterRules.LevelsPerPerk`) | FNV Perk Every Level mods (59629), FNV's `iPerksPerLevel` INI tweak |
| Skill points per level, or a multiplier | 10 + Intelligence x 0.5 (FNV) or x 1 (FO3) (`character.py` `RATES`) | Skill point limiters (47036) |
| Skill cap, level cap | The game's | LevelUpMenuEx's skill cap override |
| **Choose later:** a perk-list entry that keeps the pick for later | Off | FNV mods 76593 and 45604 (a consumable reopens the pick); ours is banking |
| **Two half level-ups:** half the skill points and a perk pick, twice a level | Off | An FNV mod |
| **Random draft:** pick 1 of 3 random perks, with re-roll and remove | Off | FNV mod 77762 (needs Vanilla UI Plus there) |
| **Respec** perks, skills or both, with an optional cost (caps, an item) | Off | FO4: Perk Reset Chem, Quick Player Respec (38621), Chazz's Respec Tool (1563), Ish's Respec Mod (12383); FNV mod 71086 |
| **Delay level-up** until sleeping or resting | Off | FNV Sleep To Level Up |
| Perk sound, looping | On, as LevelUpMenuEx | LevelUpMenuEx |

Settings go in MCM, with an INI behind them so the menu works without MCM.
The rules' own values live on `F3NV_CharacterRules` today; the options
change those, not a second copy.

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
  each registered one. `Merged` joins each text, moving owners and perk
  targets by where that table's perks start; `Gather` asks each table for
  its ranks and traits held; a pick (`ListedPerk`) and the trait menu
  (`SetTraits`) go back to the table they came from. The movie sees one
  list.

Census of the exports (2026-11-12), each DLC's own listed perks (ranks) and
traits: Dead Money 7 (7), Honest Hearts 6 (6), Old World Blues 4 (5) and 6
traits (Claustrophobia, Skilled, Logan's Loophole, Hoarder, Hot Blooded,
Early Bird), Lonesome Road 13 (13), Gun Runners' Arsenal 1 (1); the four
courier packs none. With all of them: 122 perks, 16 traits, inside the
trait menu's 31 (`MASK_BITS`; a plugin past it is counted, `level-up menu
traits past its mask`).

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
6. **Options** in MCM, then the **API**, then dropping LevelUpMenuEx from
   the requirements.

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
