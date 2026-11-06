# The FNV source decompilation

A matching C++ decompilation of `FalloutNV.exe` exists:
[momusdigital/fnv_decomp](https://github.com/momusdigital/fnv_decomp). Use it
to answer "what does FNV itself do?" before disassembling the exe.

## <a id="get-it"></a>Getting it

`references/` is gitignored, so each machine clones its own copy:

```bash
git clone --depth 1 https://github.com/momusdigital/fnv_decomp references/fnv_decomp
```

The copy here was cloned 2026-11-03 at commit `87eb937`. Run `git -C
references/fnv_decomp pull` to update it.

## <a id="what"></a>What it is

- The target is Steam `FalloutNV.exe` 1.4.0.525. All 70,611 in-scope functions
  compile to the original bytes.
- `build/units.json` maps every function to its address and mangled name.
  Search it for an address to get the function's name.
- The source is in `src/`:
  - `src/fallout/` holds `ai`, `audio`, `dialogue`, `interface`, `magic` and
    `misc`;
  - `src/fallout_shared/` holds the form classes (`testopic.cpp`, …);
  - `src/bs*` and `src/gamebryo2.2` hold the engine layers.
- **Addresses match our GOG exe.** Checked on two functions we had already
  found by disassembly:
  - `0x61A7D0` is `TESTopic::FindMatchingTopicInfo`, the line picker in
    [fo4_menu_audit.md](../fo4_menu_audit.md#sources);
  - `0x60FB60` is `QuestStage::MarkDone`, the stage runner in
    [fo4_spikes.md](../fo4_spikes.md).

  A disassembly address from `tools/disasm` can be looked up in
  `units.json` directly.

## <a id="names"></a>Names from the Xbox 360 symbols

[nv-rs](https://github.com/slaterain/nv-rs), a Rust translation of the same
exe, publishes `research/engine-map/engine_map.tsv`: each PC function's name
from the Xbox 360 prototype build's debug symbols, matched by vtable slot
(`vt`), call graph (`cg`) or referenced strings (`str`), with the Xbox source
file. Kept here as `references/nv-rs/engine_map.tsv` (nv-rs commit
`c3473121`, 2026-11-04); fetch it again with:

```bash
gh api -H "Accept: application/vnd.github.raw" repos/slaterain/nv-rs/contents/research/engine-map/engine_map.tsv > references/nv-rs/engine_map.tsv
```

`py -3.14 -m tools.disasm.fnv_names <address>... | --find <regex>` prints
both names side by side, and the function holding an address inside one.

Measured 2026-11-04:
- The map names 17,981 functions. 11,012 of the decomp's 39,082 placeholder
  names get one (28%), 4,606 of them game code: `CaravanMenu::DoIdle`
  (`0x741500`), `PlayerCharacter::Update` (`0x93E860`), `Actor::HitMe`
  (`0x89A760`), `HighProcess::Update` (`0x8EEEC0`).
- Where both name a function, they agree on about 700 of about 4,000. In the
  four checked, the map's name fit the decomp's own source file or the
  decomp's names were machine-made: `0x5E24D0` is `ScriptRunManager::Instance`
  in `tesscriptrunmanager.cpp` (decomp: `ScriptExecutor`), `0x9D8D40`
  `CombatProcedureSearch::Update` in `combatproceduresearch.cpp`.
- The map's names are Bethesda's, but carried across builds by matching, so
  some are wrong. A name is a lead in both sources; the body decides.

nv-rs is GPL-3: read its files, never copy its code here.

## <a id="rules"></a>Rules for using it

- **Read it, cite it, never copy it.** The repository grants no license. A
  finding goes into our docs as a description, with the function name and
  address. No decomp code goes into this repo. This is the same rule we follow
  for disassembly.
- **Names are leads.** Many functions still have placeholder names
  (`FUN_00xxxxxx`), and most names and comments were proposed by AI models.
  Confirm what a function does from its body and its callers, then confirm the
  result against the records (`export/`) and the
  strategy guides (`references/FNV_Guide`) before acting on it.
- It explains FNV only. FO4 behavior still comes from FO4's data,
  `Fallout4.exe` and the play log. With [accepted drift](../fo4_drift.md), a
  difference from FNV is fine where FO4 has its own mechanism.

## <a id="uses"></a>Where it helps

Open questions where FNV's own rule is the missing piece:

- Line selection and say-once: why `Greetings_Scene1` (2,656 INFOs) freezes,
  and the lost-dialogue cases (`FindMatchingTopicInfo`, `src/fallout/dialogue`).
- What each condition function returns, for the dialogue audit errors and the
  condition reviews.
- What drives a securitron's face screen while it talks.
- AI package behavior (sandbox, stay put; `src/fallout/ai`) for the package
  reviews.
- Quest script timing and order, for the timing reviews and the
  [Papyrus cost plan](../performance.md#papyrus).
- The original numbers for weapon condition and repair, ammo switching, perk
  entry points, challenges and reputation.

It does not help with FO4 rigs, behavior graphs, ragdolls, mesh or texture
conversion, or FO4Edit.
