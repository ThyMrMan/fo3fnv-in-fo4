# FNV's Pip-Boy tabs on Fallout 4 (SKILLS, REPUTATION, KARMA, CHALLENGES)

**Code:**
- `tes_runtime/fo4_condition/pages.cpp` (in the F3NV F4SE plugin)
- `script_convert/static_scripts/fallout4/F3NV_Pipboy.psc`, `F3NV_PipboyTab.psc`, `F3NV_KarmaPage.psc`
- `fo4_import/spike/pipboy_tabs.py`, `karma_page.py`, `reputation.py`, `character.py`

**Status:** SKILLS, REPUTATION and KARMA built and played 2026-10-23: they show, switch, and stay after leaving STAT and coming back. CHALLENGES built 2026-10-23, not played. It replaces the Pip-Boy Tabs
mod (PipboyTabs, Nexus 29568), which drew the same three tabs before.

## What Pip-Boy Tabs did for us

Pip-Boy Tabs' F4SE plugin loads its own SWF into the Pip-Boy
(`root.Menu_mc.addChild`, then `PipboyTabs_loader.content.registerTab`).
Each tab came from somewhere different:
- **Skills** (STAT): read from LevelUpMenuEx's `Data\PRKF\*.ini`
  `SkillsList`, its tab type 0.
- **Karma** (STAT): written by us to `Data\PBT\<plugin>_Karma.ini`.
- **Reputation** (DATA): written by us to `Data\PBT\<plugin>_Reputation.ini`.

## <a id="how"></a>How ours works

All three tabs go on the STAT page, after its own STATUS, SPECIAL and PERKS
tabs. The order is SKILLS, REPUTATION, KARMA, as FNV's STATS page orders
them.

From `pipboy_statspage.swf` and `pipboymenu.swf`, read with FFDec:
- **Tab names.** A page's tab names are the `_TabNames` array behind its
  public `TabNames` getter. The menu's header keeps that same array, so a
  name pushed onto it becomes a tab: the header draws it, and
  `TryToSetTab` allows it (`CanSwitchTabs` only checks the array's length).
- **Current tab.** The engine keeps the current tab number per page
  (`DataObj.CurrentTab`, set through `onNewTab`). Each vanilla tab shows
  itself only while that number is its own `TabIndex`, so all three stay
  hidden on ours.
- **Building a tab.** Every page loads into the menu's own class domain, so
  the STAT page's classes can be created by name. Each of our tabs is a new
  `SPECIALTab`. Its list (`List_mc`, a `BSScrollingList` of
  `SPECIALListEntry` rows) and description field (`Description_tf`) move
  into a clip of ours, placed where the page's SPECIAL tab sits.
  - A row shows `text`, then `value`, with "( + )" or "( - )" when its
    `modifier` isn't 0. `value` can be text.
  - The copied tab itself never joins the stage. So it never registers for
    the menu's change events, which would refill its list with the game's
    SPECIAL stats.
- **Each frame on STAT:**
  - only the clip of the current tab shows;
  - a clip that has just shown is refilled and gets keyboard focus, so the
    list's own Up/Down and mouse handling work;
  - the description field follows the highlighted row.

<a id="played"></a>**Fixed in play (2026-10-23):**
- **"skills" in lowercase.** Papyrus strings ignore case, and the first
  spelling stored wins. The plugin now uppercases each tab name.
- **Tabs missing after a page switch.** Back on STAT with one of ours
  current, none of ours showed until the tab changed. The header reads the
  page's names as the page loads, before the next frame. A listener for
  `added` on the menu now gives a STAT page its tabs as the page joins,
  before the menu's own `InvalidateData`.

## <a id="data"></a>Where the rows come from

- **Papyrus.** `F3NV_Pipboy.SetTab(name, order, rows, values, shown)` hands
  the plugin a tab:
  - `rows`: a FormList of actor values on the player (or globals);
  - `values`: the strings a row's value picks (none: the number shows);
  - `shown`: the globals that show each row (a row shows while its global
    is at least 1).

  A row's name is its actor value's name, and its description is the actor
  value's description.
- **The quests.** Each tab is a start-game quest running `F3NV_PipboyTab`.
  It hands the tab over as the quest starts and each time the Pip-Boy
  opens, because the plugin forgets tabs at each game start.
  - **SKILLS:** the `FNV_Skills` list. The numbers show, with "( + )" or
    "( - )" when buffed or hurt.
  - **REPUTATION:** each reputation's title row, shown once it has
    reputation.
  - **KARMA:** `F3NV_KarmaPage`, which extends `F3NV_PipboyTab`. It sets
    the Alignment and Title rows, then hands the tab over
    ([karma page](fo4_pipeline.md#karma-page)). Its quest keeps the Pip-Boy
    Tabs page quest's FormID.
  - **CHALLENGES** (built 2026-10-23, not yet played): a row per challenge
    counted, its progress as the number; its state global hides it until
    it shows in FNV (unlocked, and progressed unless Show Zero Progress).
    No "3/10" text: SetTab shows a number or a string from `values`, so the
    goal is in the row's description ([challenges](fo4_pipeline.md#challenges)).
- **String properties.** VMAD string and string-array properties (types 2
  and 12) were added to `script_convert.pipeline.script_entry` for this.

## <a id="legacy"></a>Old files and the mod

- **Old files.** A rebuild deletes the `Data\PBT\<plugin>_Karma.ini` and
  `_Reputation.ini` files older builds wrote (`remove_legacy_tabs`).
- **The mod.** Turn the Pip-Boy Tabs mod off in the mod list. Left on, it
  still adds its own Skills tab from LevelUpMenuEx's ini, a duplicate.

## <a id="drift"></a>Drift

- Reputation moves from the DATA page to STAT, where FNV keeps it.
- No Vault Boy pictures by the rows (FNV shows one per skill).
