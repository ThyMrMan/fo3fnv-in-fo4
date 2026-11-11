# FO4 already has an animation replacer, but no license yet (research, 2026-11-11)

Status: source read, nothing built or played with it. Status lives in
[ROADMAP.md](../ROADMAP.md). **V** = read in source, **S** = from the
repository's README or docs only.

**Why.** While brainstorming open replacements for unlicensed FO4 frameworks
([spin-offs](../spin_offs.md#strategy)), a conditional animation replacer
looked like a gap: Skyrim has Open Animation Replacer (OAR), FO4 seemed to
have nothing. It has one: **DCCStudios/F4-OpenAnimationReplacer**
([GitHub](https://github.com/DCCStudios/F4-OpenAnimationReplacer)). So we
don't build one; the questions are whether it handles creatures, what it
offers our work, and its license.

## <a id="summary"></a>Summary

- **Active and serious.** Created 2026-05-14, last push 2026-09-24
  (v1.1.15), about 27,000 lines of C++, two main authors
  (`TheShinyHaxorus`, 102 commits; `wushen233`, 15 via merged pull requests),
  issues open and answered. (V)
- **Same game versions as ours.** One DLL for OG 1.10.163, NG 1.10.980–984
  and AE 1.11.x through a vendored multi-runtime CommonLibF4 (MIT),
  `COMMONLIB_RUNTIMECOUNT=3` (`CMakeLists.txt`). Field-tested mostly on OG. (V)
- **Creatures: supported, weaker than the player.** See [creatures](#creatures).
- **No license.** The README says "See repository license when published."
  It is read-only for us until that changes ([license](#license)).
- **Not a code port of OAR.** It keeps upstream's file layout but almost none
  of its code, so the Skyrim original's GPL-3.0 does not settle its license
  ([derivation](#derivation)).

## <a id="how"></a>How it works (V)

It hooks Havok `hkbClipGenerator` (vtable `REL::ID(1360555)`) and swaps the
clip's animation for a cached runtime clone of a replacement `.hkx` when a
submod's conditions pass. Replacements live in `OpenAnimationReplacer/`
folders (loose or in `.ba2`), keyed by the path after `Animations\`. Submods
have priorities, variants (`base`, `base_1`…), and a **track filter** that
overwrites only chosen bones over the normal pose. It fires the
replacement's annotations itself and can send custom graph events on start
and end.

**Hard limit:** it only replaces clips a behavior graph already plays. It
adds no states or transitions; graph-authored timings ("leave reload at
2.5 s") still follow the `.hkb` (README, "Replacement modes").

## <a id="creatures"></a>Creatures and NPCs (V)

The hook is per clip, so it runs for every actor. `Hooks.cpp` mentions NPCs
and creatures throughout. But matching differs:

| | Player | NPCs and creatures |
|---|---|---|
| Path matching | Exact: the clip's real on-disk path is resolved from the player's graphs (`PlayerGraphIndexForClip`) | **Filename only** ("leaf matching"): "NPC clips have no swap array to resolve against" |
| Skeleton gate | Compares the `actors\<root>\animations` segment, or 1st/3rd person | Off by default (`bSkeletonCompatibilityGate`), and lets unknown paths through, which is the usual case here |
| Field testing | Every documented field bug is player or weapon | None found for creatures |

So a creature replacement named `idle.hkx` claims every graph's `idle.hkx`.
It must be limited by conditions: `IsRace`, `IsActorBase`, `HasKeyword`
(`ActorTypeNPC` etc.) and `HasGraphVariable` exist
([ConditionReference.md](https://github.com/DCCStudios/F4-OpenAnimationReplacer/blob/main/docs/ConditionReference.md)).

**For our creature rigs** ([prior art](fo4_creature_rig_prior_art.md)): OAR
can add variants on top of a working graph (per-race idles, attacks). It
does not replace building or cloning that graph, ragdoll or skeleton.

## <a id="use"></a>What it offers us

1. **Unique animations for converted weapons without graph edits.** Most
   converted FNV/FO3 guns reuse FO4 animation sets. A submod with
   `IsEquipped` or a keyword gives one weapon its own reload or idle. Fits
   [accept drift](../fo4_drift.md): FO4's mechanism, our content. Needs our
   clip writer's output ([idle clips](../fo4_idles.md#clips)) to load as an
   OAR replacement, untested.
2. **A plugin API instead of our own hooks** (`src/API/`):
   - Conditions API: `RegisterCondition(name, factory)`. F3NV.dll could add
     FNV conditions (needs, the condition stat, Hardcore mode) with no
     change to OAR.
   - Clips API v3: any actor's graphs, bones, animation names, event names,
     clip annotations and active replacements. Useful for debugging creature
     graphs even if we ship no replacement.
3. **Research to read.** `docs/HavokReference.md` and `HavokReference2.md`
   (about 3,300 lines) are field notes on FO4 behavior graphs, clips and
   annotations at runtime. Read-only, like the code.
4. **No hook overlap today.** `tes_runtime/` hooks neither
   `hkbClipGenerator` nor `AIProcess::SetupSpecialIdle`. If we ever need
   those, call OAR's API rather than hook the same functions.

## <a id="derivation"></a>Derivation from Skyrim OAR (V)

Upstream is [ersh1/OpenAnimationReplacer](https://github.com/ersh1/OpenAnimationReplacer),
GPL-3.0. The port's credits link `Andrealphus-Mods/OpenAnimationReplacer`,
which returns 404; ersh1's repository is the one meant.

The port shares 20 source file names with upstream (`BaseConditions`,
`FakeClipGenerator`, `ReplacementAnimation`, `ActiveClip`, `Jobs`…), but
little code. Counting upstream lines over 15 characters that appear
verbatim in the port's file of the same name:

| File | Verbatim |
|---|---|
| `Conditions.cpp` | 6 / 2253 |
| `Parsing.cpp` | 10 / 1076 |
| `ActiveClip.cpp` | 6 / 412 |
| `Variants.cpp` | 6 / 333 |
| `OpenAnimationReplacer-ConditionTypes.h` | 2 / 250 |
| `ReplacementAnimation.cpp` | 2 / 173 |
| `Jobs.h` | 20 / 169 |
| `FakeClipGenerator.cpp` | 1 / 120 |

A rewrite on upstream's architecture, not a copy. Upstream's GPL therefore
doesn't clearly reach it, and only its authors can license it. That's a
line-match count, not a legal opinion.

## <a id="license"></a>License and our rules

Under [our license rules](../spin_offs.md#license) it is like XDI or
HUDFramework: read, depend on, never copy. Two differences make the ask
easier:

- The project already calls itself *Open* Animation Replacer, and the
  README promises a license "when published".
- It has an outside contributor (`wushen233`, five merged pull requests),
  whose code is in the same no-license state; a license now settles that
  before more contributors join.

A license that matches upstream (GPL-3.0, ideally with the modding exception)
would let us contribute fixes and use the APIs from GPL code with no
question. Any open license on [our reuse list](../spin_offs.md#license)
would do.

**Status:** asked 2026-11-11 in
[issue #14](https://github.com/DCCStudios/F4-OpenAnimationReplacer/issues/14)
(GPL-3.0 suggested, modding exception optional, `wushen233` invited to
agree, credits-link fix offered); waiting for an answer.
