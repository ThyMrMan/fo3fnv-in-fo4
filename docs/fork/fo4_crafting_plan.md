# New Vegas crafting benches in Fallout 4

A plan for the question "how could we replace the crafting benches with
the FNV versions?". It records what the build does today, a census of
FNV's and FO4's crafting, three routes and a recommendation. Status lives
in the [roadmap](ROADMAP.md). **V** = read in data, code or a decompiled
movie, **P** = played, **S** = from the wiki or other text only.

## <a id="today"></a>What we build today (V)

`fo4_import/spike/crafting.py` (wired in `spike/cell.py`: `Crafting(...)`,
`station`, `base_of`, and `_gameplay` → `crafting.build()`):

- **Stations.** An FNV activator whose script runs `ShowRecipeMenu` on a
  category in `STATIONS` becomes a copy of a vanilla workbench FURN with
  FNV's name, model and bounds. Campfires copy `WorkbenchCookingFire`; the
  workbench and the reloading bench copy `WorkbenchChemistryA`. The copy's
  workbench keyword is swapped for the category's own keyword
  (`FNV_<category>`), so each bench lists only its own recipes and vanilla's
  are untouched. The activator's script is dropped.
- **Recipes.** Each RCPE of a station category becomes a COBJ on FNV's
  FormID: ingredients as components, the bench keyword, the sub-category as
  a recipe filter keyword (the menu tab, FNV's name), and conditions on the
  player: the skill as `GetValue <skill AV> >= level`, `GetHasNote` as
  holding the note's book, `HasPerk` as the converted perk. A recipe with
  any other condition is skipped and counted.
- **Several outputs.** A COBJ makes one item, so such a recipe makes a
  token, and a start-game quest's player alias (`F3NV_RecipeOutputs`) swaps
  it for a Use-All leveled list as it arrives.
- **Where the player stands.** FO4 walks the player to the furniture's
  marker. Three play rounds (2026-11-07 to 11-09) moved it, and each open
  side is now its own record (`FNV_<EditorID>_<Side>`); fixed, not built
  ([station entry](fo4_pipeline.md#station-entry)). FNV never had this:
  `ShowRecipeMenu` opens the menu where the player stands.
- **Weapon mods** are FO4 object mods at FO4's weapons workbench, built
  2026-10-22 and merged (`fo4-weapon-mods` is in `fo4-2026-10-31`)
  ([weapon mods](fo4_pipeline.md#weapon-mods)).

So a player at an FNV bench in the Mojave sees FNV's model and name; on
use the player is walked to a marker and FO4's crafting menu
(`ExamineMenu` in cooking mode) opens with FNV's recipes under FNV's
sub-category tabs, components counted, `$COOK` as the build button.
Neither the skill requirement nor a quantity choice is shown (see
[FO4's menu](#fo4-menu)).

Gaps in today's build (V, from the census below):

| Gap | Recipes or placements | Why |
|---|---|---|
| Dead Money's vending machines | 49 recipes, 22 placed machines | `NVDLC01VendingMachineRecipes` isn't in `STATIONS`; the machine's script also shows a first-use message, which a dropped script loses |
| Conditions other than skill, note, perk | Lonesome Road 14 with `GetItemCount`, 2 `GetDeadCount`; Honest Hearts 4 `GetStage`, 3 `GetMapMarkerVisible`; Dead Money 3 `GetInCell`, 1 each `GetEquipped`, `GetItemCount`, `GetQuestVariable` | `_condition` converts only `HasPerk` and `GetHasNote` |
| `ShowRecipeMenu` from dialogue | Veronica and ED-E as mobile workbenches (1 FNV INFO), Lonesome Road's 4 INFOs | the [script functions plan](fo4_plan_script_functions.md) gives it a hidden placed workbench; not built |
| DLC builds | every DLC recipe | `export_records` layers the masters, so a DLC build also walks FalloutNV.esm's 105 recipes; whether it rewrites them as overrides is unchecked (the level-up tables solved the same thing with `builder.ids.is_own`) |

## <a id="census"></a>Census

### <a id="fnv"></a>FNV and its DLC (V)

Scratch census of `export/<plugin>/RCPE.txt`, `RCCT.txt`, `SCPT.txt`,
`INFO.txt` and `REFR.txt` (script kept outside the repo; counts below).

| Plugin | RCPE | By category | Skill on the recipe |
|---|---|---|---|
| FalloutNV.esm | 105 | Reloading Bench 37, Campfire 36, Workbench 32 | Repair 39, Science 31, Survival 30, Explosives 3, Medicine 1, none 1 |
| DeadMoney.esm | 77 | Vending Machine 49, Reloading Bench 11, Workbench 6, Campfire 5, none 6 (`RecipeNVDLC01Extra01`-`06`, never listed) | none 57, Repair 15, Survival 4, Explosives 1 |
| HonestHearts.esm | 32 | Campfire 17, Workbench 11, Reloading Bench 4 | Survival 16, Repair 12, none 2, Science 1, Melee 1 |
| OldWorldBlues.esm | 29 | Campfire 15, Workbench 14 | Survival 16, then one recipe for each of the other 12 skills, 1 more Science |
| LonesomeRoad.esm | 30 | Workbench 21, Reloading Bench 5, Campfire 4 | Repair 16, Science 6, Survival 4, Unarmed 2, Guns 1, Explosives 1 |
| GunRunnersArsenal.esm | 18 | Workbench 12, Reloading Bench 6 | Explosives 8, Repair 6, Science 4 |

- **Categories (RCCT):** 10 in FalloutNV.esm: 3 station categories and 7
  sub-categories (Ammo 44, Food 22, Breakdown 14, Aid 11, Chems 7,
  Weapons 4, Misc 3 in the base game). Dead Money adds 1 station category.
- **Skill levels:** 68 distinct (skill, level) pairs over all 291 recipes.
- **Outputs:** in FalloutNV.esm 14 recipes make several items (all 14
  breakdowns), 35 make more than one of an item. The DLC add 3 multi-output
  recipes.
- **Conditions:** FalloutNV.esm 25 recipes, `HasPerk` 17 (Hand Loader,
  Junk Rounds, Vigilant Recycler...), `GetHasNote` 9. DLC conditions as in
  the [gaps](#today). No recipe tests Hardcore: Hardcore changes no bench
  or recipe, only what the made items do ([Hardcore](fo4_hardcore.md)).
- **Stations:** every one is an activator whose script calls
  `ShowRecipeMenu <category>`. FalloutNV.esm: `WorkBench` (41 placed),
  `ReloadingBench` (39), `CampfireCrafting01`-`04` (118) and
  `VCG03CampfireCrafting03` (1). The DLC reuse these (Dead Money 7,
  Honest Hearts 17, Old World Blues 12, Lonesome Road 24 placed) and add:
  Dead Money's Art Deco vending machine (`NVDLC01VendingArtDeco`, 21, and
  its `OFF` variant, 1), Honest Hearts' campfires (28) and hot plate,
  Old World Blues' hot plate in the Sink (`NVDLC03HotPlate`, 6, using
  FNV's campfire script). The Sink has no crafting records of its own: its
  workbench and reloading bench are FNV's, and its Biological Research
  Station, Book Chute and Toaster are talking activators, not recipe menus
  (S, wiki). Gun Runners' Arsenal adds recipes only. Dialogue opens the
  menu in 5 INFOs (Veronica and ED-E as mobile workbenches, S).
- **Weapon mods (IMOD):** FalloutNV.esm 50, Dead Money 5, Honest Hearts 6,
  Old World Blues 4, Lonesome Road 6, Gun Runners' Arsenal 41. FNV fits
  them from the Pip-Boy's item menu, never at a bench, and they can't be
  taken off (S, wiki).

**FNV's menu** (V: `export/FalloutNV.esm/misc/menus/recipe_menu.xml`;
`references/fnv_decomp/.../menus/recipemenu.cpp`, `CategoryMenu::OnAction`
at 0x007274b0): a recipe list with left and right arrows cycling the
sub-category filter (or all), the selected item's data and icon, the
ingredient list with what the player carries, "Made at", and "Skill
requirement". Accept opens a quantity menu (`CreateQuantityMenu(...,
CraftRecipe, 0x7fffffff)`), so one press makes as many as the player
chooses. Recipes behind a perk or a note don't show until the player has
it (S, the game's loading screen quoted in the wiki).

### <a id="fo4-side"></a>Fallout 4 (V)

`references/Fallout4.esm` dump and the offline CK wiki
(`Constructible_Object.html`, `Furniture.html`):

- **Workbench furniture:** FURN `WBDT` is the bench type. Chemistry
  (`WorkbenchChemistryA`/`B`) and every cooking station
  (`WorkbenchCookingFire`, `Stove`, `Spit`, `GroundPot`) are type 5;
  weapons (`workbenchWeaponsA`/`B`) 2; armor 7; power armor 8. The menu a
  bench opens follows the type; the recipes it lists follow the keyword in
  its KWDA (`WorkbenchChemlab` 0x102158, `WorkbenchCooking` 0x102152).
- **COBJ:** the workbench keyword (`BNAM`), components (`FVPA`), the made
  item and count (`CNAM`, `INTV`), recipe filter keywords (`FNAM`, the
  tabs) and conditions. At the chemistry bench 49 COBJ, tabs `RecipeDrug`
  14, `RecipeHealing` 12, `RecipePoison` 9, `RecipeGrenade` 7,
  `RecipeMines` 5, `RecipeUtility` 2; conditions `HasPerk` 24,
  `GetGlobalValue` 11, `GetItemCount` 1; all yield 1. Cooking 34 COBJ
  (Roast 25, Soup 6, Beverage 2, Utility 1), 3 yielding 2 or 5. Weapon
  mods use COBJ without a bench keyword, found through the gun's
  attach points and `ma_` keywords.
- <a id="fo4-menu"></a>**The menu.** There is no `CookingMenu.swf`: the
  chemistry and cooking benches open `ExamineMenu` in cooking mode
  (`CookingMode()`, `_isCookingMenu`). Decompiled from `Fallout4 -
  Interface.ba2` with FFDec (into `temp/`, not kept): the tabs list
  ("$AVAILABLE RECIPES:"), then a requirements list ("$REQUIRES:") whose
  `RequirementListEntry` draws either a component as `name have/needed` or
  a perk as its name, dimmed when short or not held. There is no row kind
  for an actor value, so **a skill level can't be shown**, and the build
  button makes one item per press: **no quantity**.

## <a id="routes"></a>Routes

### <a id="route-a"></a>a. FO4 workbench furniture (built)

FNV's meshes as FO4 type-5 furniture, FNV's recipes as COBJ under our own
keywords: what we build today. To finish it:

1. Dead Money's vending machine as a fourth `STATIONS` entry (a chem copy).
2. Convert the missing conditions to their FO4 functions (`GetItemCount`,
   `GetStage`, `GetInCell`, `GetEquipped`, `GetDeadCount`, map marker,
   quest variable as the converted script's property).
3. A DLC build writes only its own recipes (`builder.ids.is_own`).
4. Optional, to show skills: each of the 68 (skill, level) pairs as a hidden
   perk named "Repair 50", added and removed by Papyrus when the skill
   changes, and the COBJ tests `HasPerk` on it instead of `GetValue`. The
   menu then lists "Repair 50" under "REQUIRES:", dimmed when short. It
   lags behind buffs from chems or apparel unless re-checked on every
   bench activation.

| | |
|---|---|
| Survives | Recipes, sub-category tabs, component counts, perk and note gates, multi-output (the token), FNV's bench models |
| Drift | FO4's menu look; walked to a marker (the source of three play rounds); no skill level shown (unless step 4); no quantity; the station script dropped (Dead Money's first-use message); "Made at" and the item's stats pane missing |
| Size | S for 1-3, S-M for 4 |
| DLL | No. No F4SE |

### <a id="route-b"></a>b. Our own recipe menu

FNV's stations stay activators running their converted FNV script, and
`ShowRecipeMenu <category>` becomes a Papyrus call that opens our own menu
on f3ui, as the casino and the level-up menu do (F4SE
`UI.RegisterCustomMenu`, [framework](swf_framework.md)). The player never
moves, as in FNV.

- **Data from the build, not the engine** (the level-up menu's pattern,
  [level-up](fo4_level_up_plan.md#tables)): each plugin writes a table
  script of its own recipes: names, category, sub-category, skill AV and
  level, ingredient and output forms and counts, and condition rows. A DLC
  registers its table through a start-game quest and a shared form list,
  so DLC recipes stack and no DLC rewrites the base game's.
- **Conditions as rows** checked in Papyrus at open, all vanilla calls:
  `GetValue` (skill), `HasPerk`, `GetItemCount` (notes as their book),
  `Quest.GetStage`, `GetParentCell`, `IsEquipped`, `ActorBase.GetDeadCount`,
  `IsMapMarkerVisible`, `GetPropertyValue` (quest variables).
- **The movie:** FNV's layout on f3ui's `ScrollList`, `Modal` and `HintBar`:
  sub-category arrows, recipe list, item data, ingredients with what the
  player carries, "Made at", "Skill requirement" in FNV's form, and a
  quantity modal on Accept.
- **Crafting in Papyrus:** `RemoveItem` the ingredients times the quantity,
  `AddItem` every output. Several outputs need no token or swap quest.
- **Everything that called `ShowRecipeMenu` works:** the 5 station scripts,
  Dead Money's first-use message, the 5 dialogue results (Veronica, ED-E,
  Lonesome Road). The hidden-workbench row in the
  [script functions plan](fo4_plan_script_functions.md) goes away.
- **Deleted:** the FURN copies, `station_spot`'s use for stations, the side
  records, the token quest and `F3NV_RecipeOutputs`. Their FormIDs
  (`FNV station side`, the tokens, the outputs quest) must be checked for
  [FormID drift](../../CLAUDE.md#formid-drift) before deleting; the
  stations themselves keep FNV's FormIDs as ACTI.

| | |
|---|---|
| Survives | FNV's whole behavior: activation in place, skill requirement shown and checked against the buffed value, every condition, quantity, several outputs, sub-category filter, "Made at", the station scripts |
| Drift | Our movie's look (FNV's layout, our drawing); no FO4 crafting perks or workshop storage (FNV has neither) |
| Size | M-L: a movie the size of roulette's, one Papyrus script and its table, the build's table writer, the `ShowRecipeMenu` function |
| DLL | No. Needs F4SE, as the casino and level-up menu already do |

### <a id="route-c"></a>c. Hybrid

FNV's three stations, the vending machine and dialogue on our menu (route
b); FO4's weapons workbench kept for weapon mods only, as built. Before
route b lands, route a's steps 1-3 keep today's benches working.

## <a id="weapon-mods"></a>Weapon mods

FNV fits a mod from the Pip-Boy; ours fit at FO4's weapons workbench
(built). Options:

| Option | How | Cost |
|---|---|---|
| Keep the workbench (built) | FO4 object mods, `ma_` keywords per gun, locked recipes, a carried mod item fits it | Drift: needs a bench; a fitted mod comes back off as its item (FNV's never come off) |
| A usable mod item | The loose mod as an aid item whose effect script calls vanilla `AttachModToInventoryItem` on the equipped gun | No DLL; but an aid item isn't FNV's either, and choosing which gun needs a menu |
| A Pip-Boy "Mod" button | Our Pip-Boy injection ([framework](swf_framework.md#pipboy)) | Needs F3NV.dll; the injection isn't played yet |

Keep the workbench. It is FO4's native mechanism, already built on the same
object mods the other options would attach, and the drift is recorded in
[drift](fo4_drift.md#recorded). Revisit the Pip-Boy button once the Pip-Boy
framework is played, since it would reuse every OMOD the workbench uses.

## <a id="recommendation"></a>Recommendation

**Route c.** FNV's benches are menus opened where the player stands, with a
skill check, a quantity and several outputs; FO4's crafting menu can show
none of the first three, and its furniture walk has cost three play rounds.
Our menu framework already runs two menus of this shape with no DLL. Weapon
mods stay at FO4's weapons workbench.

Order:
1. Route a's steps 1-3 (S), so the current benches cover every DLC recipe
   until the menu lands.
2. The recipe table in the build, per plugin (`is_own`), with condition
   rows; tests on the census counts above.
3. `ShowRecipeMenu` as a Papyrus function, the stations as activators
   keeping their FNV scripts.
4. The movie on f3ui, then the quantity modal.
5. Remove the FURN copies, side records and token quest after the FormID
   check, and record the drift.
