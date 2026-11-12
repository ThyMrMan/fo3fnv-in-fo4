# Our own Flash menu framework

A plan for one shared Scaleform (Flash) toolkit, containing nothing of
Bethesda's, used by three things: the
[dialogue menu](dialogue_menu_mod.md), the [casino](fo4_casino_plan.md)
menus and a Pip-Boy framework. Part of the [spin-off plan](spin_offs.md).
Status lives in the [roadmap](ROADMAP.md).
**V** = read in source or code, **P** = played in game, **S** = from search
results only.

## <a id="why"></a>Why

Each of our three menus solved the same problems on its own: finding the
F4SE object, mapping keys, making text in the game font, drawing panels,
lists and pop-ups, talking to the DLL. The Pip-Boy work draws everything
from C++ through Scaleform calls, which works but fights the game every
frame. One toolkit gives us one tested copy of each piece. Released on its
own, it gives other FO4 mod authors something they don't have: an open,
licensed way to build menus without starting from decompiled Bethesda files.

## <a id="have"></a>What we have

| Menu | How it's made | State |
|---|---|---|
| Casino (`fo4_import/casino/`) | Our own AS3 on the `f3ui` library, compiled by `mxmlc` (since 2026-11-11, [spike 1](#spikes)). Opened as an F4SE custom menu from Papyrus (`F3NV_Casino.psc`) | FFDec build played (slots in the HUD color). `mxmlc` build played: slots and roulette work |
| Dialogue menu (`fo4_import/dialogue_menu/`) | Our own AS3 only (since 2026-11-11, [spike 3](#spikes)). Since 2026-11-12 on `f3ui` (`Bridge`, `Text`), compiled by `mxmlc` like the casino's. Nothing read from the game | The patched-movie version played; our own movie (FFDec build) played 2026-11-12, looks the same. `mxmlc` build not played |
| Pip-Boy, container, barter, HUD (`tes_runtime/fo4_condition/`) | The Pip-Boy's CND line, repair and ammo lists, and other mods' item-card lines are drawn by our injected movie from the DLL's data ([framework](#pipboy)). The rest is drawn by the DLL into the open vanilla menus from C++: REPAIR and AMMO hints, STAT tabs, the container and barter CND line, HUD needs | CND, repair and tabs played from C++; the movie's versions built, not played. Ammo list and HUD needs built, not played |

Shared already:
- `fo4_import/base/as3/f3ui/`: the AS3 library's first five classes,
  `Bridge`, `Theme`, `Host`, `Text` and `Draw` ([design](#design)), used by
  the casino and the dialogue menu.
- `fo4_import/base/mxmlc.py`: the `mxmlc` build with the library on the
  source path, dated tags dropped, cached by the hash of the sources, the
  library and the options. Every movie we ship is built this way.
- The FFDec build route (a skeleton movie, then FFDec's script import:
  `swf_skeleton.py`, `ffdec.py`) was deleted on 2026-11-12, when the
  dialogue menu moved to `mxmlc`. FFDec stays a tool for reading vanilla
  movies.
- `asset_convert/ui/swf.py`: our SWF reader and writer.

Both builds are byte-stable (`tests/test_fo4_casino.py`,
`tests/test_fo4_dialogue_menu.py`).

## <a id="facts"></a>What we know about FO4's Flash

### From our own play-tests (P)

- `$MAIN_Font` and `$MAIN_Font_Bold` work by name with `embedFonts`; no font
  library needs importing. The game maps the names per language.
- `f4se.MountImage(menu, path, name)` shows a DDS as `img://name`. The path
  is under `Textures` without that prefix. It returns true even for a
  missing file, and images drop when the menu closes.
- F4SE's default custom-menu flags (`0x801849D`) made the casino draw only
  in a box around the cursor. Dropping Custom Rendering (`0x8000`) and
  Assign Cursor To Renderer (`0x10000`) fixed that **and lost the HUD
  color**. A changed registration needs a game restart.
- HUD color: the dialogue menu's holders registered through
  `BGSCodeObj.registerObjects` are tinted by the engine. Anything drawn
  white shows in the HUD color. Inside a tinted holder alpha only darkens,
  so no translucent fills: the backdrop is the engine's shaded background.
- `UI.Invoke` wraps array elements as `{__var__: v}` (casino `Ui.plain`
  unwraps). An AS3 `int` reaches Papyrus as Int.
- `ProcessUserEvent` delivers `Accept`, `Cancel`, `Left`, `Right`; the
  stage's `KEY_DOWN` works too. The mouse wheel comes as `ZoomIn`/`ZoomOut`.
- Pip-Boy: the menu object is `root.Menu_mc`; pages load into the menu's
  class domain; the game refills the item card's `InfoObj` on every
  selection change; Papyrus `OnKeyDown` never fires while it's open; no
  gamepad button is free; a STAT tab must exist before the header reads the
  names. Details in [fo4_condition.md](fo4_condition.md#pipboy) and
  [fo4_pipboy_tabs.md](fo4_pipboy_tabs.md).
- Making a TextField in the dialogue movie's constructor crashed the game.
  Build display objects on the first update call instead.
- **Focus rectangle:** a movie that gives its root the keyboard focus
  (`stage.focus = this`) gets Flash's yellow focus frame round the whole
  screen. Set `stage.stageFocusRect = false` and `focusRect = false`, as
  FO4's own `Shared.IMenu` does (casino, `fd59ed6f`, built, not played).
- **The HUD stays drawn behind a custom menu.** No menu flag hides it, and
  changing the casino's flags stopped the menu opening (spike 2a). The
  casino hides it with F4SE `UI.Set("HUDMenu", "root1.visible", False)` on
  open, shows it on close, and shows it again on every load so a crash
  can't leave it hidden (`F3NV_Casino.psc` `ShowHud`, `fd59ed6f`, built,
  not played). This also hides HUD widgets (HUDFramework, ours) while the
  menu is up, which is what we want. In the library this moves into the DLL
  side of `Host`, so every menu gets it.

### From F4SE, CommonLibF4 and other mods (V)

- **F4SE's root object:** every movie gets `root.f4se` (`SendExternalEvent`,
  `CallFunctionNoWait`, `GetDirectoryListing`, `MountImage`, `AllowTextInput`,
  `version`, `plugins.<name>`). It calls `onF4SEObjCreated(f4se)` on root and
  its direct children, then dispatches `F4SE::Initialized`. It can be missing
  on early frames: poll for it.
- **HUD color for custom menus:** extended flag 1 (InheritColors) applies the
  HUD color to the menu's filter holder, **and only with Custom Rendering on**
  does it reach the shader targets. That explains the casino's lost color.
  A clip that defines `onApplyColorChange(r, g, b, mult)` can override it.
  CommonLibF4's `BSGFxShaderFXTarget` has `SetToHUDColor` and
  `EnableShadedBackground`, which a DLL can call on any clip.
- **Menu flags and depths:** the full lists are in CommonLibF4
  (`UI_MENU_FLAGS.hpp`, 28 flags; `UI_DEPTH_PRIORITY`, 21 levels).
  `AllowSaving` (`0x800`) is in F4SE's default; without it the save button
  is grayed out.
- **Translations:** `Interface\Translations\<name>_<language>.txt`, UTF-16 LE
  with BOM, `$KEY<tab>text` lines; `$KEY` strings in text fields are swapped
  by the game.
- **Supported AS3** (Autodesk's table): Loader, Bitmap, BitmapData, Vector,
  XML, Error and `getDefinitionByName` work. Not supported: convolution and
  shader filters, `drawTriangles`, shader fills, gradient masks, most of
  `flash.net`. Blur, glow and drop shadow work on shapes and text with limits.
  Our own "no try/catch, no uint" rule has no recorded crash behind it; test
  it once, then keep or drop it.
- **`scaleform.gfx.*`** (Extensions, TextFieldEx, FocusManager…) are filled
  in by the game at runtime. Autodesk ships them as source, so stub classes
  with the same names compile; untested in FO4.
- **Injecting instead of replacing.** PipboyTabs and Extra Item Info (both
  unlicensed, read only) and F4-PIP-OS (MIT) add to the Pip-Boy without
  shipping `PipboyMenu.swf`: the DLL spots the movie by
  `root.loaderInfo.url`, loads its own small movie into `root.Menu_mc` with a
  `Loader`, and adds a native API object on root. F4SE's `UI.Load` does the
  same from Papyrus.
- **Pip-Boy movie layout:** `PipboyMenu.swf` is a shell that loads
  `Pipboy_<Stats|Inv|Data|Map|Radio>Page.swf` by name into one class domain
  (from F4-PIP-OS's notes). FallUI Inventory, DEF_INV, Vault Girl and others
  each replace the shell or pages, so only one wins. FallUI keeps the vanilla
  classes, which is why injected mods still work under it.
- **Holotape programs** run an SWF from `Data\Programs` on the Pip-Boy
  screen (826×700, no cursor) (S).

### <a id="hudframework"></a>HUDFramework (V)

The HUD's framework: 2.1M unique downloads, 362 mods using it, updated
2026-09-04, works on next-gen. Source 1.0f and its Nexus page are in
`references/HUDFramework Source Code 1.0f/` (no license file: read only).

- **Ships a patched `HUDMenu.swf`:** Bethesda's HUD movie with its own
  movie injected by an auto-patcher (RABCDASM). It needs no F4SE, so it runs
  on consoles. The cost: any other `HUDMenu.swf` replacer must be
  auto-patched, and the shipped file is Bethesda's movie.
- **Papyrus to Flash without F4SE:** commands are written as
  `| widget | command | body |` strings, joined with `^`, throttled, and
  sent as `Debug.Notification` text that the patched HUD intercepts
  (`HUDFramework.psc` `SendCommandRaw`).
- **Widgets** are SWFs loaded with a `Loader` into the HUD's own class
  domain, parented under the compass bar so they hide and fade with the HUD.
  A widget implements one method, `processMessage(command, params)`.
- **Framework duties it handles well:** register before load; reload every
  widget on each game load (the HUD movie starts over); clear registrations
  whose owner script is gone (an uninstalled mod); saved position, scale and
  opacity per widget, with a drag-to-edit mode; a power armor layout; an AS3
  expression evaluator so Papyrus can change any HUD element (`Eval`).

## <a id="toolchain"></a>Toolchain

Two working routes. Both produce a movie made only of our code.

| | FFDec over a skeleton (ours today) | Apache Flex `mxmlc` |
|---|---|---|
| Proven | Casino, played | fo4-silhouette (GPL-3), F4SEMenuFramework, BetterWeaponScrapping (MIT) |
| Needs | Java 8, FFDec (GPL-3, a tool, not shipped) | Java, Flex SDK 4.16.1 (Apache-2.0), Adobe's `playerglobal.swc` (Adobe license: can't go in our repo; build-time only) |
| Byte-stable | Yes, tested | No: writes a build date (tags 41 and 77). Fixable by stripping them after the build |
| Errors | Lenient: `var x:int = ;` compiles | A real compiler: type errors, missing members |
| New classes | Each needs a skeleton entry (the skeleton does it per `.as` file) | Normal |

**Decision: build with `mxmlc`, strip tags 41 and 77, and keep FFDec only
for reading vanilla movies.** A menu framework that other people build on
needs a real compiler; a lenient one hides bugs until play. Proof first
(spike 1): the casino spike built by `mxmlc` behaves the same in game and
builds byte-identical twice after stripping.

### <a id="mxmlc-setup"></a>`mxmlc` setup (done 2026-11-11, outside the repo)

- **Where:** `C:\Coding\tes4skyrim\tools_ext\FlexSDK` (beside FFDec).
  Downloads kept in `tools_ext\downloads\`.
- **Flex SDK 4.16.1:** `apache-flex-sdk-4.16.1-bin.zip` (72,396,756 bytes)
  from `archive.apache.org/dist/flex/4.16.1/binaries/`; MD5 matches
  Apache's published `.md5` (`8841c64bd5e32f8575eba86e2574873a`).
- **`playerglobal.swc` 11.2:** Adobe's download address now redirects to
  its Flash end-of-life page. Taken from the Internet Archive's copy of
  Adobe's own file
  (`web.archive.org/web/20160611061401id_/http://fpdownload.macromedia.com/get/flashplayer/updaters/11/playerglobal11_2.swc`,
  339,135 bytes). Its SHA-1 (base32 `3QHT2FXRFVNCFA2JX2XHADPEYP3LUCBZ`)
  matches the archive's record for both captures, 2014 and 2016. Installed
  as `frameworks\libs\player\11.2\playerglobal.swc`; `{playerglobalHome}`
  in `frameworks\flex-config.xml` replaced with `libs/player`.
- **Command** (run from the SDK folder; in PowerShell quote every
  argument):
  `java -Xmx1024m -jar lib\mxmlc.jar +flexlib=frameworks -target-player=11.2 -swf-version=15 -static-link-runtime-shared-libraries=true -debug=false -default-size 1280 720 -default-frame-rate 30 -source-path=<src> -output=<out.swf> <src>\<Main>.as`.
  Without `-default-size` and `-default-frame-rate` the movie gets a
  500×375 stage at 24 fps; our skeleton uses 1280×720 at 30.
- **Checked offline:**
  - A small test movie built twice: 696 and 698 bytes, different. With
    tags 41 and 77 removed (a scratch script that re-packs the movie with
    zlib level 9), both builds are **byte-identical**. Tag order: 69, 77,
    65, 9, 41, 43, 82, 76, 1, 0. No Flex framework code is linked in.
  - The casino's AS3 (`fo4_import/casino/as3`) compiles cleanly: 6,070
    bytes, no errors or warnings.
- **In the build** (`fo4_import/base/mxmlc.py`, 2026-11-11): the command
  above with `-default-background-color=0x000000` (the skeleton's black),
  `+flexlib` given as an absolute path so it runs from any folder, and
  `-source-path+=` for the library. Any `Warning:` or `Error:` in the
  output fails the build. Tags 41 and 77 are dropped, FileAttributes'
  HasMetadata bit (`0x10`) cleared, and the movie written **uncompressed**
  (`FWS`). Compressing with zlib is not byte-stable across Python builds:
  Python 3.14 on Windows ships zlib-ng (`zlib.ZLIB_RUNTIME_VERSION`
  `1.3.1.zlib-ng`), Python 3.13 ships stock zlib 1.3.1, and at level 9 the
  same casino movie came out at 11,323 and 11,305 bytes, with every tag
  identical. Uncompressed, the bytes depend only on the sources. (Since
  2026-11-12 the FO4 build has a [pinned zlib](fo4_pipeline.md#pinned-zlib)
  that would make a compressed movie stable too; the movies stay
  uncompressed, the format that has been played.) The SDK is found at `F3NV_FLEX`, else `tools_ext\FlexSDK` beside
  the repo (in a worktree, set `F3NV_FLEX`).
- **The casino moved to `mxmlc` and the library in one change** (spike 1).
  The dialogue menu stayed on FFDec until its own movie was played, so
  only one thing changed per play-test.
- **The dialogue menu moved to `mxmlc` and the library on 2026-11-12**
  (built, not played). Its AS3 compiled cleanly under `mxmlc` unchanged.
  Then: rows made by `Text.field` (bold 18, leading -2, white: the engine
  tints them) and filled through `Text.show`, F3NV.dll's natives through
  `Bridge`. Behavior is unchanged. Movie 9,585 bytes, the same on Python
  3.13 and 3.14. **Play check:** dialogue opens and looks as before; the
  options read in the HUD color, pick and leave as before.

**Ship built movies, don't build at install.** Today the converter runs
FFDec on the player's machine. With our own movies there is nothing of the
player's to compile against, so the release carries the `.swf` files and
players need no Java. This needs a rule change: the pre-push hook blocks
every `.swf` (it exists to keep Bethesda art out). Options:
- **Release assets only** (recommended): built movies go into the release
  package by CI, never into git. The hook stays as it is.
- An allowed folder (`interface_build/`) the hook exempts, with a check that
  each movie in it was built from our source.

## <a id="design"></a>Design

### The AS3 library

One package (name to pick; `f3ui` below), GPL-3.0 with the modding
exception ([license](spin_offs.md#license)), no Bethesda classes:

| Module | Does | Replaces |
|---|---|---|
| `Bridge` | Finds `root.f4se` (event or poll), our plugin's natives, `send`/`call`/`log`, unwraps `{__var__}` | Each menu's own copy |
| `Input` | One map from keys and `ProcessUserEvent` names to actions (up, down, accept, back, page, scroll); ignores the opening key for a moment; platform and gamepad from `SetPlatform`/`uiPlatform`, followed as it changes; text input on and off ([controller support](#controller)) | Two separate key tables |
| `Text` | Text fields and labels in `$MAIN_Font*`, sizes, wrap, `$KEY` translation, HTML-safe text | `Ui.as` and the dialogue menu's own |
| `Draw` | Panels, frames, dividers, arrows, white-for-HUD-color drawing, shaded backdrop request | `Ui.panel`, the dialogue `frame` |
| `ScrollList` | The selectable, scrolling list: rows, markers, icons, disabled and said rows, wheel, numbers 1–9 | The dialogue list, and the C++ repair and ammo lists |
| `HintBar` | Button hints that show keys or gamepad glyphs (`$Controller_Buttons` font) | Bethesda's `BSButtonHintBar` |
| `Modal` | A pop-up over a menu: fade, focus, back closes it | The Pip-Boy repair pop-up in C++ |
| `Images` | `MountImage` with the path rule built in; asks the DLL whether a file exists first | Casino's own |
| `Theme` | The HUD color from the DLL's `HudColor()` native on each open ([spike 2b](#spikes), played), colors over it, sizes, spacing, read from settings the DLL passes in | Hardcoded values |
| `Host` | Safe-rect; menu open/close reset (F4SE keeps a movie alive between openings); focus rectangle off; HUD hidden while open and restored on close and on load ([casino fixes](#facts)) | Each menu's own |

Each menu is then a thin document class on top: `CasinoMenu`,
`DialogueMenu`, and the Pip-Boy overlay.

### Four ways a movie meets the game

| Mode | Used by | How |
|---|---|---|
| **Own menu** | Casino, settings screens | Registered by our DLL through CommonLibF4 (`GameMenuBase`), not Papyrus, so flags, depth and HUD color are set in one place and need no restart |
| **Replace a vanilla movie** | Dialogue menu | Our movie at `Interface\DialogueMenu.swf`, implementing the engine's calls ([contract](dialogue_menu_mod.md#swf)). Only where the engine owns a menu we must take over completely |
| **Inject into a vanilla menu** | Pip-Boy, container, barter | The DLL loads our small movie into the open menu with a `Loader` and gives it a native API object. No vanilla file is shipped, so DEF_UI, FallUI and the rest keep working |
| **HUD widget** | HUD elements (our Hardcore needs) | Hosted by HUDFramework when installed, else injected by our DLL ([how](#hud)) |
| **Holotape program** | Possibly casino games, later | An SWF in `Data\Programs` played on the Pip-Boy screen; the same library, with a native bridge. Research only |

### The DLL side

One shared C++ module, used by every DLL built on the
[shared base](spin_offs.md#runtime):
- menu registration (flags, depth, HUD color, shaded background);
- injection: watch for a menu's movie by URL, load our movie into it, add
  our API object;
- native function registration (one helper, not one class per function);
- GFx helpers: **done in F3NV.dll 2026-11-12**, `gfx.cpp` (`Num`, `Get`,
  `LogMembers`, `FindMenu` for the menu-instance path probe, and the
  `Listen<Handler>` template for native event listeners), used by
  `pipboy.cpp`, `transfer.cpp` and `hardcore.cpp`;
- settings: read the mod's INI and hand it to the movie as one object;
- `bEnableGFXLog` routed into our own log when debugging.

## <a id="pipboy"></a>The Pip-Boy framework

### What moves from C++ into an injected movie

The game refills the item card on each selection, so a line has to be put
back after every refill. An injected movie can instead listen to the item
card's own redraw and add its lines in the same frame, and draw lists and
pop-ups with `ScrollList` and `Modal` instead of faking them as item-card
lines. Key handling moves into the movie, which already gets keys when
Papyrus doesn't.

Phases:
1. **The CND line** (built 2026-11-12, not played). F3NV.dll still resolves
   the highlighted stack and its health each frame, but no longer touches
   the card. Its native `PipboyCardLines()` gives the lines to show
   (`[{text, value, showAsPercent}]`, the CND line of an item that wears;
   null while a list of ours draws the card), and `F3NV_Pipboy.swf` keeps
   them in `CurrentPage.ItemCard_mc.InfoObj`, matched by text, calling
   `onDataChange` only when it adds a line or a value changes. The spike-4
   test line is gone.
   - **FallUI Inventory (2.2.1), read 2026-11-12, not played.** It ships
     its own `PipboyMenu.swf` and `Pipboy_InvPage.swf` (read with FFDec,
     unlicensed, read only). Everything we use is still there:
     `CurrentPage`, `ItemCard_mc`, `InfoObj` (FallUI sometimes assigns a new
     array, which the movie re-reads each frame), `onDataChange`,
     `ModalFadeRect_mc`, `List_mc.disableInput`. Its card draws plain
     `{text, value}` lines; `ItemCardFwCore.preprocessData` only copies the
     array and runs FallUI's own add-on hooks. Three differences:
     - **Color:** FallUI ships `M8rDisablePipboyEffects` (no game screen
       tint) and colors its art from `M8r.Mods.config.stdColor` (green by
       default). The list panel takes that color from the Pip-Boy's classes,
       as FallUI's own add-on API does (`PipboyApi.primaryColor`), else
       white.
     - **Typing:** its list search (F) is a text box, and our `keyUp`
       listener would hear G and V typed into it. Keys whose target is an
       input text field are now ignored.
     - FallUI has its own item-card add-on framework (SWFs in
       `Interface\UI-Framework\ItemCard`). Ours stays independent so it
       works under vanilla too; under FallUI both sets of lines show.
2. **The repair and ammo lists** (built 2026-11-12, not played). The DLL
   keeps each list's state, its keys (the native `keyUp` listener, which
   already works) and the repair, but no longer writes the list over the
   card's `InfoObj` or lifts the card. Its native `PipboyList()` gives the
   open list as `{heading, rows, chosen, notes, keys}` (`RepairView`,
   `OfferView`, `AmmoView`), and the movie's `ListPanel` draws it as a
   pop-up over the item card: a black panel outlined in white, the heading,
   eight rows round the highlighted one (a translucent bar), the notes and
   the keys. It is white, like the Pip-Boy's own art, because the game tints
   the whole screen. While a list is open the movie moves our `Loader` to
   the top of the menu, over the page and its fade. "Not needed", "No spare",
   "One type only" and "Drop a copy first" are card lines from
   `PipboyCardLines`, kept until the selection changes. The DLL opens a list
   only after the movie has called it in this Pip-Boy opening, so a missing
   movie never leaves an invisible list holding the keys (logged once).
   - The REPAIR and AMMO hints stay in C++ (`MakeHint`), which works in play.
3. **The item-card line API for other mods** (built 2026-11-12, not
   played): [below](#card-lines).

### <a id="card-lines"></a>Item-card lines for other mods

`F3NV_ItemCard.SetLine(Form akItem, String asLabel, String asValue)`
(Papyrus, global native; F3NV.dll `card.cpp`) shows a line on the inventory
item card of `akItem`, or of every item carrying it when it is a Keyword. A
second call with the same item and label replaces the line; an empty value
removes it. Our movie draws these lines after F3NV's own, under any Pip-Boy
that keeps the vanilla item card.
- Lines live in F3NV.dll's memory and are forgotten when a save loads or a
  new game starts (F4SE's `PreLoadGame` and `NewGame` messages), so a mod
  sets them again on each game load (`OnPlayerLoadGame`), as HUD widgets
  re-register. Nothing goes in the save, so an uninstalled mod leaves
  nothing behind.
- Values are text, shown as given.
- Test from the console:
  `cgf "F3NV_ItemCard.SetLine" <item form ID> "TEST" "HELLO"`.
- Not yet: lines from an INI, numbers with `showAsPercent`, and per-copy
  values (a line belongs to a form, not to one stack).

### What it offers other mods

From the Pip-Boy survey (S), ranked by what nothing provides today:

1. **Item-card fields.** Any mod registers a line (label, value, a filter by
   form type or keyword), from Papyrus or an INI. Our CND line becomes its
   first user. Nothing like it exists without FallUI.
2. **Pages and tabs with real content.** Not only lists of values
   (PipboyTabs does that) but a mod's own movie: buttons, lists, actions.
   Our STAT tabs move onto it.
3. **Item actions:** a key and hint on the item card that runs a mod's
   action (our Repair and Ammo are the first two), and on a gamepad one
   button that lists them all ([controller support](#controller)).
4. **Map layers and markers**, drawn over whichever map page won. Later.
5. **Radio page extensions.** Later; our radio work may want it.

### Living with other Pip-Boy mods

- Ship no `PipboyMenu.swf` or page movie, ever.
- Find the parts we touch by what they are (the item card's `InfoObj`, the
  STAT page's tab list), not by vanilla paths, and log once when a shell
  hides them. Test under vanilla, FallUI Inventory and DEF_INV.
- **PipboyTabs:** ours duplicated its Skills tab. Detect it and skip our
  version of a tab it already shows. Reading its `Data\PBT\*.ini` format
  for compatibility is possible later; its code is unlicensed, so read only.
- Power armor and VR use other Pip-Boy screens: check power armor; leave VR
  out of the first release.

### What we take from HUDFramework's design

The Pip-Boy framework is HUDFramework's job for a different menu, so it
should do the same housekeeping ([HUDFramework](#hudframework)):
- registrations kept in the save and re-applied each time the Pip-Boy
  movie loads;
- registrations from uninstalled mods cleared on load;
- one message channel with batching, and one method a mod's movie
  implements;
- power armor's Pip-Boy handled as its own layout.

It differs on purpose in one place: it injects through F4SE instead of
shipping a patched Bethesda movie. That keeps it clear of every Pip-Boy
replacer and of Bethesda's files, at the price of PC only.

## <a id="hud"></a>The HUD: work with HUDFramework, never require it

HUDFramework already solves HUD widgets, is installed by millions, and
keeps up with game versions. A second HUD framework would split authors for
little gain. But it has no license, so we can't ship, fork or fix it, and
our mods must not break when it's missing or changes.

**One widget, two hosts.** Our HUD pieces (first: Hardcore's H2O / FOD / SLP,
today drawn into `LeftMeters_mc` by `hardcore.cpp`) are one movie built with
our library. It works under either host, chosen once per game session:

| HUDFramework | Host | What the player gets |
|---|---|---|
| Installed | HUDFramework loads our movie as a widget; our script registers it | Its saved position, scale and opacity and its drag-to-edit mode, alongside their other widgets |
| Not installed | Our DLL injects the same movie into whatever `HUDMenu.swf` is loaded (vanilla, DEF_HUD, anything), as with the Pip-Boy | The widget at its default place, settings from our INI |

How, without depending on it:
- **No compile dependency.** Our Papyrus finds its quest with
  `Game.GetFormFromFile` on `HUDFramework.esm`, then calls it through
  `CastAs("HUDFramework")` and `CallFunction` (vanilla Papyrus), so our
  scripts compile and run without its `.psc` or `.esm`.
- **The movie speaks both ways:** it implements `processMessage(command,
  params)` for HUDFramework, and takes the same commands from our DLL's
  native calls. Values come from our DLL either way, not through
  HUDFramework's notification channel, so we add no on-screen message
  traffic and no throttle.
- **Detect, don't assume:** the patched HUD sets a `HUDFramework` member on
  the HUD movie. Our DLL checks for it before injecting, so a widget is never
  loaded twice.

Playing nicely:
- Ship no `HUDMenu.swf`, and never patch theirs.
- Add nothing to the HUD's root under their names; namespace ours.
- Follow their power armor switch when hosted; handle it ourselves when not.
- Test with vanilla, HUDFramework, and HUDFramework's DEF_UI patch.

### What we could add to it

Only with the author's agreement, offered as contributions, since we can't
release changes to unlicensed code:
- **The F4SE fast path it already reserves.** `HUDFramework.psc` calls
  `HUDFrameworkNative.SendMessageRaw` but forces it off
  (`StartSession`: "TODO - Unlock this once native functions are
  implemented"), so every message on PC goes through notification text and
  a throttle. A small DLL with that native, built on our shared base, would
  make PC messages instant. Their script must switch it on, so it needs them.
- **A license.** Asking costs nothing; with one, we could depend on it fully.

The Nexus author is registrator2000, very likely reg2k (XDI, MCM). If so,
one conversation covers this, the [`XDI.esm` stand-in](dialogue_menu_mod.md#decisions)
and MCM. Neanka (XDI co-author, DEF_UI, PipboyTabs) is the other person to
ask.

### <a id="hud-layout"></a>HUD layouts (what DEF_HUD did)

DEF_HUD lets players move, rotate, resize, recolor and hide every part of
the HUD, but it does so by replacing `HUDMenu.swf` (one copy per screen
shape), so it fights every other HUD mod and needs a merged copy for
HUDFramework ([DEF_UI](spin_offs.md#def-ui)). The same result needs no
replaced movie:
- **A layout module** in our injected HUD movie: once the HUD has loaded,
  it finds each of the game's HUD parts by name and sets its position,
  scale, rotation, color and visibility.
- **Reads `DEF_HUD.xml`**, so players' existing layouts carry over. Per
  element it holds `x`, `y`, `scaleX`, `scaleY`, `rotation`, `color`,
  `color2`, `flags`, `parname` (the parent clip) and the defaults. What
  `flags` and `color2` switch is to be worked out from the XML and the
  game's HUD parts, not from DEF's movies (its permissions forbid reuse).
- **One layout for every screen shape:** positions relative to the safe
  area, instead of five copies.
- **Edited in game:** a drag-to-edit mode, as HUDFramework has for widgets,
  instead of DEF's outside programs.
- **Kept applied:** re-applied when the game moves parts itself (power
  armor, safe-area changes, HUD mode switches).
- **Colors:** the engine tints HUD parts with the HUD color; whether our
  color on a part survives that tint is a test to run first.
- **Stands down** when DEF_HUD's own `HUDMenu.swf` is installed, since that
  movie already applies the layout.

Together with the widget host this covers both of the HUD's frameworks
in one injected movie, with no `HUDMenu.swf` shipped by anyone.

## <a id="casino"></a>The casino on the framework

- Move `Ui.as` and the bridge into the library; the games keep their own
  classes. **Done 2026-11-11** ([spike 1](#spikes)).
- Register the menu from the DLL. Spike 2 tests HUD color with Custom
  Rendering on and only Assign Cursor To Renderer off.
- Keep the Python reference models and in-game self-tests; they test game
  rules, which the library doesn't change.

## <a id="translations"></a>Translations

Every release should work in every language the game ships, and a
translator should be able to translate it by adding files, never by editing
a plugin or a movie.

### Where each kind of text comes from

| Text | Example | Comes from | Who translates |
|---|---|---|---|
| **Game data** | Dialogue options and lines, item, skill and actor value names, quest names | The game's own records, already in the player's language (strings files) | Nobody: we read it through the engine, never copy it into our files |
| **Our fixed words** | `[Leave]`, hint labels, tab names, settings labels, "CND" | `$KEY` strings in our movies, swapped by the game from `Interface\Translations\<Mod>_<language>.txt` | Translators, one file per language |
| **Text we build** | `[Speech 45/50]`, "Repair with: Laser Pistol (62%)" | A template under a `$KEY` with named slots (`[{skill} {have}/{need}]`), filled by our `Text` module; the slots take game data | Translators translate the template; word order is theirs |
| **Other mods' text** | A tab or item-card line another mod registers | That mod passes either game text or its own `$KEY` | That mod's translators, in that mod's file |
| **Settings pages** | MCM page names and help | `$KEY`s in MCM's config, the same translation files | Translators, same file |
| **Plugin records** | Messages, keywords' names | Keep player-visible words out of our plugins; where a record must hold text, use a `$KEY` | Same file |
| **Converted FNV text** | Casino labels from FNV's settings | The player's FNV install, in its own language. The converter must write it under the player's FO4 `sLanguage`, not always `_en` as the [casino design](fo4_casino_plan.md#design-text) says, or a German game misses it | Nobody: it follows the source game |

Papyrus has no translation of its own, so scripts pass `$KEY` strings, never
English sentences, to anything shown on screen.

### Files

- `Interface\Translations\<plugin>_<language>.txt`: UTF-16 LE with BOM, one
  `$KEY<tab>text` per line (F4SE `Translation.cpp`, V). `<language>` is the
  game's `sLanguage` (`en`, `de`, `fr`, `ru`, …). **`<plugin>` must be an
  active plugin's name:** F4SE reads `plugins.txt` and, for each `*` line
  ending `.esm`, `.esp` or `.esl`, loads that plugin's file through the
  game's file system (loose or BA2), once, when the translator is made (F4SE
  0.7.9 `ImportTranslationFiles`). A file named after anything else, such as
  a menu, is never read. Lines start with `$`, split at the last tab, and
  stop at 511 characters; no BOM means the file is skipped.
- **Ours are named after `FalloutHelpers.esl`**, which every converted
  FO3/FNV plugin masters: `FalloutHelpers_<language>.txt` holds every
  `$F3UI_` and menu key (`fo4_import/base/translations.py`).
- In the repo: one **English source** file per release in UTF-8, so changes
  show in diffs (`fo4_import/base/translation_files/en.txt`). The build
  writes the UTF-16 file for each language that exists
  (`translations.install`, with the casino today).
- Translations arrive as one file per language and ship in the main
  download, or as separate Nexus translation uploads that hold only that
  file.

### Fallback

**Unverified:** what the game shows for a `$KEY` when the player's language
has no file (likely the raw `$KEY`). Our `Text` module must never show a
raw key:
- the DLL reads our English file at load and hands the movie a fallback
  table;
- `Text` uses the game's translation first, then the fallback, then the key
  name without its `$`;
- the DLL logs once which keys fell back, so translators can find gaps.

### Fonts

- Use only `$MAIN_Font`, `$MAIN_Font_Bold`, `$Terminal_Font` and the other
  names `FontConfig.txt` maps. Each language's font library supplies the
  letters, so Cyrillic, Polish and Chinese, Japanese and Korean work without
  us shipping fonts.
- Never embed a font of our own: it would lack other languages' letters.
- Controller glyphs come from `$Controller_Buttons`, which is the same in
  every language.

### Layout

- No fixed text widths. German runs about a third longer than English, and
  CJK text breaks lines differently. `Text` measures the text and wraps, or
  shrinks within limits, and lists scroll horizontally only as a last resort.
- A **test language**: a tool writes a fake translation with every string
  lengthened and accented (`[Lëävë~~~~]`), installed as a language file. One
  look in game shows any text that is cut off or never translated.
- Right-to-left scripts: the game doesn't support them; out of scope.

### Checks

**Built 2026-11-12:** `translations.check()` reads every `"$KEY"` string in
our movies' AS3 (each `as3/` folder under `fo4_import/`, `//` comment lines
and the font names `$MAIN_Font`/`$MAIN_Font_Bold` left out) and finds:
- keys the English file lacks (error: the game shows them raw);
- English keys no movie uses (review);
- keys another language has that English lacks (error).

Preflight's `menus` audit reports them for every FO4 build
(`menus.translation_audit`), and `test_our_movies_use_only_keys_the_english_file_has`
holds the repo to none. `en.txt` is empty since spike 5's test key went:
`install` writes no file for a language without keys.

Still planned:
- keys in C++ and Papyrus sources too, once those pass `$KEY`s to a movie;
- each language file has the same `{slots}` as English;
- a count of untranslated keys per language for the release notes.

### Compatibility

- XDI ships translations (for example Ukrainian), and players will expect
  ours too. Our dialogue menu shows the game's own text for options and
  lines, so only our few fixed words need translating.
- Key names carry the mod's prefix (`$F3UI_Leave`), so two mods' files
  never fight over a key.
- Never ship a copy of the game's own `Interface\Translate_<lang>.txt`.
  DEF_UI does, and must redo it after every game update; our own files
  can't go stale that way.

## <a id="controller"></a>Controller support

Every menu must be fully usable with a gamepad, the same as with keyboard
and mouse: every action reachable, every hint showing the right button. A
feature that works only on keyboard is not finished.

### Where we stand

| Menu | Gamepad today | Gap |
|---|---|---|
| Dialogue menu | Designed for it: D-pad (`QuickkeyUp/Down`) moves, A (`Accept`) picks, B (`Cancel`) leaves (`DialogueMenu.as`) | Never played with a pad |
| Casino | FO4's own controls are wired (`Accept`, `Cancel`, `Left`, `Right`); the gamepad cursor flag is set | The planned gamepad pass was never played |
| Pip-Boy repair and ammo | **None.** Keyboard only (G, V); hints hidden on a pad, because every gamepad button is taken in the Pip-Boy ([condition](fo4_condition.md#pipboy)) | A way in on a pad |
| STAT tabs | The game's own tab switching | Check with a pad |

### Rules for the library

- **Actions, not keys.** `Input` maps keys, mouse and `ProcessUserEvent`
  control names to one set of actions (up, down, accept, back, page left
  and right, more). Menus only ever see actions, so no menu can forget the
  pad.
- **Follow the device as it changes.** The game reports the platform
  (`SetPlatform` / `uiPlatform`), and players switch between mouse and pad
  mid-menu. Hints, cursor and focus follow at once.
- **Hints from the action.** `HintBar` draws each action's current button:
  key names on keyboard, glyphs from the `$Controller_Buttons` font on a pad
  (Xbox or PlayStation layout as the game reports). A hint for an action
  the device can't do is a bug.
- **Focus always visible.** On a pad there is no pointer, so one row or
  button is always highlighted, and lists scroll to it.
- **No mouse-only actions:** nothing that needs hover, drag or a right click.
- **Remapping:** use the game's control names, so a player's remapped
  controls carry over; our own keyboard keys are settings.
- **Steam Deck** counts as a gamepad: test it, or at least a pad on PC
  with mouse and keyboard unplugged.

### The Pip-Boy problem

Item actions (our Repair and Ammo, and every action other mods register
through the framework) can't each have a button on a pad. Design:
- **One "more" button opens an action list** for the highlighted item:
  every registered action that applies, in a `ScrollList` pop-up. One
  button for all mods, so actions never fight over buttons.
- **Which button** is a research item: candidates are a long press on a
  button the page already uses, a stick click, or a shoulder-plus-button
  combination. Read what the inventory page leaves free on a pad, and check
  what FallUI and DEF_INV already use, before choosing.
- On keyboard, actions keep their own keys (G, V) as well as the list.

### Testing

- Each spike and each release is played once with a controller, start to
  finish, with mouse and keyboard untouched.
- The menus' self-test logs record which device drove each action, so a
  report shows whether the pad path ran.
- VR's motion controllers come later, with the [VR build](spin_offs.md#platforms).

## <a id="testing"></a>Testing

- No headless Flash player runs our movies. Keep logic in plain classes
  that Python reference models can mirror (as the casino does), and keep
  the movies thin.
- A **movie check** in preflight: every class we ship comes from our
  source; no tag imports assets from a Bethesda movie; font names are ones
  `FontConfig.txt` maps; the build is byte-stable.
- One in-game test scene per mode: own menu, replaced movie, injected
  overlay, each with a self-test log line.

## <a id="spikes"></a>Spikes, in order

Each spike is one change, played in game.

1. **`mxmlc` build:** the casino spike built by `mxmlc` (tags stripped)
   behaves the same and builds byte-identical twice.
   - **Played 2026-11-11: passed.** Slots and roulette both work on the
     `mxmlc`/`f3ui` movie (user: "both work fine with the custom menu
     work"). The movie played was zlib-compressed; it is now written
     uncompressed ([why](#mxmlc-setup)), the same format as the dialogue
     menu's own movie, which also loads in game.
   - **Built 2026-11-11.** The casino now compiles with `mxmlc`
     on the library's first five classes:
     - `Bridge`: the f4se object, `send`, `natives`, `mount`, `plain`;
     - `Theme`: `color`, `fromHud`;
     - `Host`: `focus` (focus rectangle off);
     - `Text`: `field`, `label`;
     - `Draw`: `button`, `panel`.

     The casino's own `Ui.as` is gone; its screens and document class call
     the library. Nothing else in the casino changed: same calls, keys,
     drawing and colors.
   - **Checked offline:** strict compile, no warnings. Byte-identical
     twice, from any folder or worktree. Tags: 69, 65, 9, 43, 82, 76, 1, 0. FFDec
     decompiles only our 11 classes (6 casino, 5 `f3ui`). A type error
     FFDec let through (`var a:int = "one"`) now fails the build
     (`tests/test_fo4_casino.py`).
   - **Play check:** a build with the new `Interface\F3NV_Casino.swf` (no
     DLL or script change). The slots open in the HUD color with no yellow
     frame; spin, the bet buttons, keys and mouse work; Tab or Esc closes;
     the log shows `F3NV_Casino: input hud color …`. Roulette opens the
     same way.
2. **HUD color in our own menu.** One change per play-test; each needs a
   game restart, because F4SE keeps a menu's first registration.
   - **2a:** flags `0x800849D` (Custom Rendering back on, Assign Cursor To
     Renderer still off), extended `3` (Inherit Colors + gamepad cursor).
     Why it may work: F4SE pushes the HUD color to a custom menu's shader
     targets only with Custom Rendering on, and Assign Cursor To Renderer is
     the flag that hands the cursor to the custom renderer, the likelier
     cause of the box. The menu needs drawing in white for the tint to show,
     as in the dialogue menu. Only `F3NV_Casino.psc` changes, so it can be
     tested as a one-script patch on the built plugin.
   - **2a result (played 2026-11-11): failed.** With `0x800849D` / `3` the
     slot machine menu didn't open at all (the box didn't come back; the
     menu never showed). The original `.pex` was restored. Per the plan, no
     further flag tries.
   - **2b: works. The way our own menus get the HUD color.** The menu
     colors itself; no engine tint, no flag change (menu flags stay
     `0x800049D` / `2`).
     - **How** (commit `df3f9972`, in F3NV.dll from `2d3fc70c`): a
       `HudColor()` native on `f4se.plugins.F3NV` (every movie already gets
       F3NV.dll's natives) returns the player's `iHUDColorR/G/B`, read
       fresh on each call through the same `HudColor` the Hardcore HUD
       uses. The casino sets `Ui.color` from it each time a screen opens,
       and every outline and text that was white uses `Ui.color`. Only what
       we draw takes the color: reel symbols, card faces and roulette
       pockets share containers with the text, so a color transform on a
       whole layer would tint them too.
     - **Played 2026-11-11** (new F3NV.dll + casino movie, old casino
       script; slots only, roulette waits for the full build): slots open
       and play, drawn in the HUD color ("Slots work in the HUD color
       now"). The log shows `F3NV_Casino: input hud color f774f7` on both
       openings, the same color the Hardcore HUD read at load (`F774F7`
       in F3NV.log).
     - **Screenshot (The Tops, slots):** reel symbols and payout icons keep
       their own colors; text, button outlines and borders are in the HUD
       color. The buttons' 10% fill shows as a see-through tint: with the
       menu coloring itself, translucent fills work, unlike inside an
       engine-tinted holder (the dialogue menu's finding).
     - **Not checked yet:** the menu following a HUD color changed in
       Settings (both openings had the same color). The fallback path (no
       F3NV.dll, white) wasn't tried.
     - **Seen in the same play, fixed by the casino session** (`fd59ed6f`,
       built, not played; [casino notes](fo4_casino_plan.md#hud-hidden)):
       the game's HUD showed through behind the menu, and Flash drew its
       yellow focus rectangle round the whole screen. Both fixes belong in
       the `Host` module ([what we know](#facts)).
     - **Limit:** a color changed while the menu is open shows on the next
       opening. Fine for the casino: its flags include Disable Pause Menu
       (`0x80`), so the settings can't be opened while it is up.
   - **2c: not needed.** Real engine shader targets from the DLL
     (CommonLibF4's `BSGFxShaderFXTarget`) stay unbuilt unless a menu ever
     needs the engine's live tint.
3. **Replaced dialogue movie:** five empty holders and a text list as
   `DialogueMenu.swf`; does the engine tint them?
   - **Played 2026-11-11: works.** The engine tints holders made in code:
     the list showed in the HUD color ("Hud color matches the text box").
     Opening, picking, leaving and the talk going on all worked "nearly as
     well" as the patched menu, without its styling. One bug: `[Leave]`
     showed twice. The converted topic list already ends in its own
     `[Leave]` option (`conversation.py`), and the spike added one more;
     the shipping menu adds its own only when F3NV.dll has no options.
     Fixed in the spike source, not replayed. So the dialogue menu can drop
     the patched Bethesda movie: the XDI replacement starts from our own
     movie.
   - **Played 2026-11-12: works.** The shipping dialogue menu on its own
     movie plays fine and looks the same as before (user).
   - **Done 2026-11-11:** the shipping dialogue menu moved
     onto its own movie ([dialogue menu plan](fo4_dialogue_menu_plan.md#own-movie)).
     Spike 3 also settles two open facts: `try/catch` ran in game (the
     spike's placement used it), and `scaleform.gfx.Extensions` needs no
     stub to compile against when looked up by name.
   - **Built 2026-11-11.** Two AS3 classes, no Bethesda code or
     art: a root (`DialogueMenuRoot`) that holds the menu at `root.Menu_mc`,
     as the game's own movie does (its `MainTimeline` has only `Menu_mc`),
     and `f3ui.dialogue.DialogueMenu`, which answers the game's calls
     (`onCodeObjCreate` → `registerObjects` of five code-made holders,
     `SetButtonText`, `Show/HideButtonHelp`, `Enable/DisableMenu`,
     `ProcessUserEvent`, `SetSafeRect`, `SetPlatform`) and its own base
     class's job (focus rect off, safe-area placement). One white list in the
     Question holder: F3NV.dll's options, else the game's four buttons, plus
     `[Leave]`. `PlaySpeechChallengeAnim` has no animation and reports done
     on the next frame. No shaded background or failed-check tint (one
     variable). `mxmlc` output 3,440 bytes stripped, byte-identical twice;
     no font tags (`$MAIN_Font_Bold` by name).
   - **Play check:** loose `Interface\DialogueMenu.swf` with the current
     F3NV.dll. Dialogue opens; the list is in the HUD color (white means the
     engine didn't tint it); options pick and the talk goes on; `[Leave]`,
     Tab and the controller's B leave; F3NV.log shows `spike 3 menu ready`.
4. **Pip-Boy injection:** a `Loader` movie in `root.Menu_mc` that adds one
   item-card line, under vanilla and under FallUI Inventory.
   - **Played 2026-11-12: works** (vanilla Pip-Boy). The inventory cards
     show `F3UI  SPIKE 4` (user). F3NV.log: `Pip-Boy: F3NV_Pipboy.swf
     loading`, `loaded into [object PipboyMenu] (F3NV.dll found)`, `added
     our line to an item card (1 lines)`, then `(9 lines)` on a weapon's
     card. The second opening loaded it again: the game makes a new
     Pip-Boy menu each time, and our movie comes with it. **Not yet tried
     under FallUI Inventory.**
   - **Built 2026-11-12.** Two pieces, no Pip-Boy movie of the
     game's shipped or read:
     - **F3NV.dll** (`pipboy.cpp` `LoadOverlay`): in the hook that already
       runs once per Pip-Boy menu (the `fnvConditionHooked` flag), it makes
       a `flash.display.Loader`, adds it to the menu instance
       (`root.Menu_mc`) and loads `F3NV_Pipboy.swf` (a path under
       `Data\Interface`, as HUDFramework's widgets load), the same calls as
       F4SE's `UI.Load`. Logs `Pip-Boy: F3NV_Pipboy.swf loading`.
     - **The movie** (`fo4_import/pipboy_overlay/as3/F3NV_Pipboy.as`,
       `mxmlc` with `f3ui`, 2,325 bytes): it finds the menu as its Loader's
       parent and F4SE's object on the Pip-Boy movie's root. Each frame it
       puts a line `F3UI  SPIKE 4` back on the shown page's
       `ItemCard_mc.InfoObj` when the game's refill dropped it, then calls
       `onDataChange()`, as `pipboy.cpp` does for CND today. It draws
       nothing and takes no input. It logs through F3NV.dll's `Log`
       native, so its lines read `dialogue menu: Pip-Boy movie: …` in
       F3NV.log (that native's prefix).
     - The masterless build installs `Interface\F3NV_Pipboy.swf` (count
       `Pip-Boy movie installed`).
   - **Checked offline:** `pipboy.cpp` compiles with the DLL's flags, no
     warnings; the movie builds the same on Python 3.13 and 3.14; the name
     the DLL loads is the name the build installs
     (`tests/test_fo4_pipboy_overlay.py`).
   - **Needs:** a rebuilt F3NV.dll and the movie.
   - **Play check, vanilla Pip-Boy:** open the inventory and move between
     a few items: each card shows `F3UI  SPIKE 4` under its own lines (and
     CND where it applies). F3NV.log: `Pip-Boy: F3NV_Pipboy.swf loading`,
     `Pip-Boy movie: loaded into … (F3NV.dll found)`, `added our line to
     an item card`. The STAT and DATA pages are unchanged.
   - **Then under FallUI Inventory**, if installed: the same checks.
5. **Translation files:** the spike 1 movie shows one `$KEY` from our own
   `_en` file, then the same with `sLanguage` set to a language we have no
   file for. Records what the game shows, which settles the
   [fallback](#translations) design. Can ride along with spike 1.
   - **Played 2026-11-12: the translation works; one drawing bug.**
     - f4se.log: `Reading translations from
       Interface\Translations\FalloutHelpers_en.txt...`. The log: the
       present key reads back `Translated from FalloutHelpers_en.txt`, the
       absent one reads back `$F3UI_TranslationAbsent`. **So the game shows
       a key no file has as the raw `$KEY`**, which settles the
       [fallback](#translations): `Text` must never show an untranslated
       key itself.
     - **Bug:** both lines drew one small mark per letter (10, 4 and 21
       marks on the left: the words of the translation; 23 on the right:
       the raw key). The buttons beside them, made by the same
       `Text.field` (same font name, embedded fonts on), drew fine, and so
       do roulette's size 11 and 14 labels, so neither the font name nor
       the size is the cause. The only difference: these two texts start
       with `$` and go through the game's translator. Likely cause: the
       translator's result replaces the text without the field's default
       format, so it falls back to a font that isn't embedded, and the
       game draws a mark for each missing letter.
     - **First fix, played 2026-11-12: failed** (looks the same).
       `Text.show` reapplied `setTextFormat(defaultTextFormat)` after the
       assignment. Log, both keys: `font Times New Roman then Times New
       Roman`, so after the `$` assignment even the field's default format
       read as Times New Roman (Flash's default font, which the game
       doesn't embed).
     - **Second try, played 2026-11-12: works.** All three lines draw as
       text. **Cause, confirmed by the log:** assigning a string that starts
       with `$` to a code-made field resets both its text format and its
       `defaultTextFormat` to Times New Roman, whether or not the key is
       translated; plain text keeps `$MAIN_Font`. So f3ui puts text in a
       field only through `Text.show`, never `field.text = "$…"`:

       | Line | After a plain assignment (its default) | After `Text.show` |
       |---|---|---|
       | Key in our file | Times New Roman (Times New Roman) | `$MAIN_Font` |
       | Key in no file | Times New Roman (Times New Roman) | `$MAIN_Font` |
       | Plain text | `$MAIN_Font` (`$MAIN_Font`) | `$MAIN_Font` |
     - **What was built for it:** `Text.field` keeps its
       own copy of each field's format; `Text.show` assigns the text, then
       puts that copy back as the default and over all of the text.
       `Draw.button` uses it too. A third, plain line (no `$`) is the
       control. Each line logs `font: default <before>, plain <after a
       plain assignment> (default <its default then>), shown <after
       Text.show>`. Movie 19,014 bytes.
     - **Spike done.** The three test lines and `$F3UI_TranslationCheck`
       were removed 2026-11-12; the [check](#translations) now keeps keys
       and the English file in step.
   - **Built 2026-11-12.** Two changes from the plan:
     - The file is `Interface\Translations\FalloutHelpers_en.txt`, not
       `F3NV_Casino_en.txt`: F4SE loads only files named after an active
       plugin ([files](#translations)).
     - **No `sLanguage` change.** With no file for the player's language,
       F4SE loads nothing, which is the same as a key no file has. So one
       play shows both cases: `$F3UI_TranslationCheck` (in our file) and
       `$F3UI_TranslationAbsent` (in none). Changing `sLanguage` on an
       English install would also lose the game's own strings.
   - **What's built:** every casino screen (slots, roulette) shows both keys
     in small text under the buttons, and logs what each field reads back
     (`F3NV_Casino: input translation $F3UI_… reads back '…'`). The build
     writes the file from `fo4_import/base/translation_files/en.txt`
     (UTF-8) as UTF-16 LE with BOM and CRLF (`translations.install`, count
     `menu translation files installed`). Checked offline: the movie
     contains both keys (18,646 bytes, the same on Python 3.13 and 3.14);
     `tests/test_fo4_translations.py`.
   - **Play check:** a build with the new `Interface\F3NV_Casino.swf` and
     `Interface\Translations\FalloutHelpers_en.txt`, then open slots. Note,
     or screenshot, what each bottom line shows:
     - left: `Translated from FalloutHelpers_en.txt` means our file loads;
       `$F3UI_TranslationCheck` means it doesn't;
     - right: whatever the game shows for a key no file has (the raw key,
       an empty line, or something else). This settles the
       [fallback](#translations).
     - F4SE's log (`f4se.log`) should say `Reading translations from
       Interface\Translations\FalloutHelpers_en.txt...`; the casino lines
       in the Papyrus log give what each field reads back.

Spikes 1, 2 and 4 need nothing from the CommonLibF4 port; they can run on
today's F3NV.dll and Papyrus.

## <a id="release"></a>Release

- **The library** as its own GPL-3.0 repo (with the modding exception, so
  menus built on it can use any license) with an example menu and docs: for
  FO4 authors who want a menu without decompiling Bethesda's files.
- **The Pip-Boy framework** as a DLL + movie on Nexus, with the Papyrus API
  and INI format documented.
- The dialogue menu and the converter use both.

## <a id="decisions"></a>Open decisions

- Where built movies live: release assets only, or an exempt folder in git.
- Library and Papyrus prefix names.
- Whether the Pip-Boy framework reads PipboyTabs' INI files.
- Whether to contact HUDFramework's author (license, the F4SE fast path),
  together with the XDI question.
