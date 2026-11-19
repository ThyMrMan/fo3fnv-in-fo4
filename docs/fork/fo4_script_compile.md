# Converted scripts that failed to compile

**Code:** `script_convert/cross_ref.py` (`build_ref_as_int_map`), `script_convert/symbols.py`
(`_classify_assignment`), `script_convert/converter.py` (cell-family helpers).

NVWillow.esp (Nov 10 build) compiled 868 of 926 scripts. Every script in its folder, compiled
the same way against the FalloutNV.esm sources, went from 956 of 1,015 to 1,015 of 1,015 with
the fixes below. 18 failures had errors of their own;
the other ~40 failed only because a script they use (a property type) had no `.pex`.
A missing `.pex` also breaks scripts that did compile: each read of a property typed with
that script is None, so `falloutnv_willow1script.OnTimer` logs
"Cannot call McCarranNonNCR() on a None object" on every tick.

## <a id="ref-as-number"></a>A `ref` that holds a number

TES4's `ref` can hold a number, and mods do this: `ref RaulBGnow` / `set RaulBGnow to
RaulREF.GetItemCount Bubblegum`. Papyrus then has an ObjectReference given an Int.

The variable becomes Int when every value set into it is a number and it is never used
as a reference (`var.Call`). These values count as numbers:
- a literal;
- arithmetic;
- a command whose converted return type is Int or Float (`GetItemCount`, `GetAV`, ...);
- a global's EditorID.

Two places apply the rule:
- `symbols._classify_assignment`, for a script's own sets;
- `cross_ref.build_ref_as_int_map`, across scripts.

The cross-script scan now also reads the plugin's INFO and QUST result scripts. Willow's
dialogue writes `Set AWillow4a.RaulBG to RaulREF.GetItemCount Bubblegum`, and those lines
were never seen before.

## <a id="digit-names"></a>EditorIDs that start with a digit

A cell or worldspace EditorID such as `2EOVault21` is not a valid Papyrus name. Properties
get a `d` prefix (`safe_property_name`). The cell-family helpers wrote the raw name in their
`If TES4_parentCell == ...` tests, so the test named a property that did not exist.

## <a id="region-case"></a>A region written in another case

`IsPlayerInRegion vMapMojaveOutpostregion` names `vMapMojaveOutpostRegion`. TES4 names
are case-insensitive. The command row registered its GlobalVariable type under the name
as written, and the record resolver registered ObjectReference under the EditorID. Both
landed in one script as two entries differing only in case. The declaration kept the
first one in sorted order, ObjectReference, so `TES4Polyfill.InRegion` was passed the
wrong type. Row-typed arguments now key on the record's EditorID too (`property_of` in
`emit/commands.py`).

With one key, a row that takes any form (`types={0: 'Form'}`, such as `AddItemHealthPercent`)
would overwrite the Weapon, Book or Armor the resolver had found. The split keys had hidden
this, because the capitalized EditorID sorted first. `_register` keeps the native type over
a generic Form or ObjectReference. It never keeps a generated script class: an armor base
whose object script would be the type cannot fill an ObjectReference script property.

Measured on FalloutNV.esm against HEAD: 97 of 17,507 sources change. Apart from name case,
every change is Form becoming Book (131), Weapon (30) or Armor (25), and all 97 compile but
one. The exception is `QJJasWilkinsScript` (`OnDeath` on an ObjectReference script), which
fails the same way at HEAD. The ref-as-number, base-form and cross-script sets match HEAD
exactly on FalloutNV.esm and Fallout3.esm.

## <a id="nvse-version"></a>GetNVSEVersion

Mods check `GetNVSEVersion < 2` to warn that NVSE is missing. The converted build stands
in for xNVSE: it reads 6, with revision 4 and beta 9, from `nvse_version.h` in
`references/xNVSE`. Before this, the name had no row and converted as an undefined
variable.

## <a id="result-script-tabs"></a>Result scripts read with their tabs

`_scan_plugin_result_scripts` turned only `\r\n` and `\n` back into line breaks. An
indented line kept its `\t`, so `\tSet AWillow4a.CapsInHand to ...` was never seen as a
`set`. It now uses the export's own `unescape_value`. This feeds both the ref-as-number
scan and the cross-script Property scan.

## <a id="remote-int"></a>Reading another script's numeric `ref`

`remote_type_of` answered from the TES4 declaration (`ref`, so ObjectReference). So
`AWillow4a.PCsexpartners == 0` became `== None` against what is now an Int. It now checks
the ref-as-number map first, just as it already checked the Actor promotion.

## <a id="ondeath-on-a-reference"></a>OnDeath on a reference script

A script that sits on both containers and creatures extends ObjectReference, and Fallout 4
refuses an `Event OnDeath` there ("new event ondeath cannot be defined because the script
is not flagged as native"). Fallout 3's `FFER05LootBoxSCRIPT` (three containers, one
brahmin) failed this way, and with it every script naming it (`FFERepeatA`, `FFER15LootBox`,
`FFER73LootBox`). The block now becomes Fallout 4's remote event,
`Event Actor.OnDeath(Actor akSender, Actor akKiller)`, registered with
`RegisterForRemoteEvent` on the script's own actor from OnCellAttach, OnLoad and OnInit,
next to OnHit's `RegisterForHitEvent`. On a container the actor cast is None and
nothing registers. Code: `target.remote_death`, `assemble.lifecycle`.

## <a id="player-faction-mirror"></a>No PlayerFaction mirror on Fallout 4

`setfactionreaction X PlayerFaction n` also called `TES4Polyfill.MirrorPlayerFactionRelation`,
which copies the change onto Skyrim's own PlayerFaction. The Fallout 4 polyfill has no such
function (it is in `FALLOUT4_UNUSED_HELPERS`), and FO3/FNV's PlayerFaction already is Fallout
4's (`factions.ENGINE_FACTIONS`), so the converter no longer writes the call there. Fallout 3's
`MS01QuestScript` (Big Town) failed to compile on it. Through `BigtownSentryScript`, so
did every dialogue line's end fragment that runs a generic `SayToDone`, Dad's "boy or a girl?"
line included: the birth stopped before the sex choice.

## <a id="ref-widening"></a>A `ref` widened to Form

A TES4 `ref` holds references, base records and the number 0 alike. Papyrus will not put a
base record (`let rCrosshairsLast := JailShoes`, an Armor) in an ObjectReference, so a `ref`
that also holds one is declared Form, the one type that takes both. Only a value an
ObjectReference cannot hold widens it: an ObjectReference, an Actor or a converted script's
type stays as is (`symbols._fits_reference`).

`_mixed_record_type`, the case of a `ref` also cleared with 0, widened on any record type
it was given, and read `player` as its NPC_ record, an ActorBase. The player is emitted
`Game.GetPlayer()`, an Actor, as the record-kinds pass already knew. Fallout 3's
`MQ01Script` sets `targetRef` to 0, the player and four actors' references, so it became
Form, and passing it as the target of `SayWhenFree` (an ObjectReference) failed to compile.
Both passes now share `_assigned_type` (the player is an Actor) and `_fits_reference`, so
`MQ01Script` and the ten scripts that name it compile (Sarah Lyons' squad, `QF_MQ01` and
its lines).

## <a id="package-events"></a>Package blocks run from the package's fragments (2026-11-16, not yet played)

`begin OnPackageStart|Done|End|Change <package>` became Fallout 4's `OnPackageStart` and
`OnPackageEnd`/`OnPackageChange` actor events, guarded on the package. Those events never
reach a converted actor script: every scripted actor's `OnPackageStart` traces `pkgstart`,
and no log has a single one. In Fallout 3's baby steps, Dad walked to
`CG01DadExitRoomMarker` and stood in the open playroom door, because
`OnPackageDone CG01DadCloseDoor` (stage 18 closes and locks the door) never ran. His
`CG01DadCloseGate` package, which sets stage 16 from its own OnEnd script, did run. Vanilla
answers a package from its fragments too: one vanilla script uses the events.

On Fallout 4 the block is now a function on its own script, `TES4_<block>_<package>()`, and
the named package's fragments call it on the actor through a cast that is None for any
other actor, as SayToDone does: Start in OnBegin, Done in OnEnd (completed), Change in
OnChange (left), End in both. A package that a block names gets that fragment even with no
script of its own. `package_events.package_hooks` reads the scripts and packages once, and
the converter (`PF_` script) and the importer (VMAD flags) share it through
`package_sections(rec, hooked)`. Fallout 3 has 67 such blocks in 35 scripts, New Vegas 36 in
20.

## <a id="record-compared-to-zero"></a>A record compared to 0 on first sight

Willow writes `... && NovacPlayersRoom == 0` with a bare cell name. The `== 0` to
`== None` rewrite asked for the name's type before anything had registered the cell as
a property, so it kept `== 0` on a Cell. `is_ref_typed` now falls back to the record's
own property type.
