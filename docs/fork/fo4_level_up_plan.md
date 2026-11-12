# Our own level-up menu (plan)

**Status:** planned 2026-11-12; the perk and skill images are staged by every
build (built, not shown). Status lines live only in
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

## <a id="prkf"></a>PRKF.dll's work, in Papyrus (built 2026-11-12, not used yet)

PRKF.dll keeps perk and skill points, the tagged skills and the perk list,
and opens its menus on them. None of the non-menu part needs native code,
so F3NV.dll gets nothing:
- **Points and tags** are variables of `F3NV_LevelUp` (on the
  `FNV_CharacterRules` quest), saved with the game like any script's. The
  API is PRKF's: `AddPerkPoints`, `AddSkillPoints`, `GetPerkPoints`,
  `GetSkillPoints`, `Tag`, `Untag`, `IsTagged`, and the custom events
  `PerkTaken`, `SkillTagged`, `SkillUntagged`.
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

The tag bonus stays the caller's to give, since the rules' `OnTagsFinished`
already sets it. The trait and tag menus are the menu's (order step 5).
The rules keep calling `PRKF:PRKF` until our menu replaces LevelUpMenuEx's,
and then they switch to this script, along with `F3NV_CharacterEvents`
(SetPlayerTagSkill) and converted scripts' `IsTagSkillAV`
(`commands_falloutnv.py`). Arrays a script builds hold at most 128 entries,
which `PerkList` stays under for FNV (91 perks); a DLC's perks join by the
form list merge, and their requirement rows are an open question.

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
   [images](swf_framework.md#level-up)).
2. **Opening ours instead of `LevelUpMenu`** (the framework's "replace a
   vanilla menu" mode).
3. **Perk page** with the default features above, reading `FNV_Perks` as
   LevelUpMenuEx does.
4. **Skill page** with the preview, undo and banking.
5. **Traits and tags** at character creation, with re-tagging.
6. **Options** in MCM, then the **API**, then dropping LevelUpMenuEx from
   the requirements.

**Open questions:**
- How the menu finds an image from a record: FO4's PERK has an unused
  `ICON` field and AVIF none, so our own table or that field.
- Whether Vanilla UI Plus or zUI already show highlighted requirements or
  sorting in FNV's level-up screen (their feature lists weren't found).

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
