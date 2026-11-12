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

## <a id="record-compared-to-zero"></a>A record compared to 0 on first sight

Willow writes `... && NovacPlayersRoom == 0` with a bare cell name. The `== 0` to
`== None` rewrite asked for the name's type before anything had registered the cell as
a property, so it kept `== 0` on a Cell. `is_ref_typed` now falls back to the record's
own property type.
