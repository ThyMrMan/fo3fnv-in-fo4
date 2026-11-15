# Plan: catching regressions in the Fallout 4 build (2026-11-15)

Status: planned, nothing built. Status lives in [ROADMAP.md](ROADMAP.md).
Builds on the [preflight build audits](fo4_preflight.md#previous-build), the
[build chain](fo4_chain.md) and the [autoplay plan](fo4_autoplay.md).

**Goal.** When something that worked stops working, find out from the build
itself, before anyone plays it, and name the commit and the code that broke
it. A regression is a difference between a build that worked and one that
doesn't, so every layer below compares against a build the user played and
called good.

## Contents

- [What we already have](#have)
- [1. A known-good build, and a wider diff](#good-build)
- [2. Fixed bugs as frozen cases](#bug-cases)
- [3. Must-pass checks in game](#must-pass)
- [4. Scoped bisect](#bisect)
- [Order and effort](#order)

## <a id="have"></a>What we already have

| Piece | Compares | Misses |
|---|---|---|
| Drift baseline (`build_diff.py`, `--accept-build`) | FormIDs gone, retyped or moved against the last accepted build; counts changed records per type | Content changes; it moves on by itself while no drift shows |
| Previous build (`build_history.py`) | Each build's records (signature, EditorID, CRC of subrecords) against the build before it; records gone are review findings; caches the code change invalidated | Only one build back: a break two builds ago no longer shows. Records only: no scripts, meshes, textures, archives, faces or voice |
| Build stamp | The commit and the changed files a build ran with | Nothing reads it for "which outputs should have changed" |
| Targeted tests | Whatever each test file pins | No shared place for "this bug was fixed, keep it fixed" |
| Preflight ledger | Marks findings new since the last run | No link between a finding and a build that was played |

The add-on builds' lost references (fixed 2026-11-14, `ca01a23e`,
`d2054b90`) are the kind of break the previous-build audit can see. One
build later it can't, and a lost mesh or script it never sees.

## <a id="good-build"></a>1. A known-good build, and a wider diff

**Marking a build good.** After a play test that went well:
`py -3.14 -m tools.validate.preflight --fo4 <plugin> --mark-good "<note>"`.
It copies the audit's `build_seen.json` for that build (about 40 MB for the
whole map, no plugin copies) to `output/preflight/<plugin>/good/<stamp
end>.json`, with the commit, the note and the date. The newest good build is
the regression baseline; older ones stay so a comparison can go further
back. This is separate from the drift baseline, which answers "are saves
safe", not "did it play".

**A fingerprint of every output, not only records.** The same file gains,
per output path in the mod folder and its archives:

| Output | Fingerprint |
|---|---|
| Records | As now: signature, EditorID, CRC of subrecords |
| Scripts | CRC of each `.pex`, and the script names each record's VMAD attaches |
| Meshes, textures, materials | CRC per path inside each BA2 and loose; the paths records name that no file holds |
| Faces | CRC per FaceGen mesh and texture |
| Voice and lip | Count and CRC per voice folder |
| Archives | Entry count per BA2 |

Reading the archives' directories and hashing what changed is cheap next to
the build. Files whose stamp says they were replayed, not rebuilt, can
reuse the previous CRC.

**Changes the commit didn't ask for.** The build stamp lists the code files
that changed since the good build (`git diff --name-only` between the two
commits, as `build_history` already does for caches). A table maps each
output area to the code that writes it:

- records by signature to their `fo4_import` converter modules;
- scripts to `script_convert/`;
- meshes to `fo4_import/nif` and `havok`;
- faces to `fo4_import/face`;
- and so on.

`code_tag.tagged_files()` already holds most of this map for the caches.
The audit then sorts every difference against the good build:

- **expected:** the area's code changed;
- **suspect:** it changed with no code change behind it, which is a review
  finding (`regress|<plugin>|<area>|<what>`);
- **lost:** records, files or attached scripts gone, which is an error
  whatever the code change, until the ledger marks it `ok`.

The add-on references, a dropped script attachment and a mesh no longer
written all land in "lost".

## <a id="bug-cases"></a>2. Fixed bugs as frozen cases

CLAUDE.md asks for a regression test once a fix is confirmed in game. These
go into one collection instead of being spread over test files:
`tests/regressions/` with one small case per fixed bug. A case names:

- the bug (the roadmap row or doc anchor and the fix commit);
- its input: a source record from `export/`, a mesh, or a script;
- the converter call that handles it;
- the output fields that prove the fix (not the whole output, so
  unrelated improvements don't fail it).

A shared runner (`tests/regressions/test_cases.py`) loads every case and
runs only the converter it names, so the whole collection stays inside
the 120 s test limit. Cases whose input isn't in `export/` on a machine
are skipped and counted. Each fix adds a case in the same commit as its
doc note, so the collection grows with every bug.

## <a id="must-pass"></a>3. Must-pass checks in game

Once the [autoplay](fo4_autoplay.md) cell sweep exists:

- **Pinned checks.** Each roadmap row marked "Works", and each bug fixed in
  game, gets a check that must pass on every run. Examples: no crash in Doc
  Mitchell's house; Goodsprings to Primm's quests advancing; a weapon class
  firing. They live in a list (`tools/playtest/must_pass.json`), each with
  its row or bug and its autoplay stop or quest.
- **New since the good run.** Each autoplay run is tied to the build stamp
  it ran on. Finding keys don't change from build to build, so comparing a
  run with the run on the good build splits its findings into "already
  there when it played well" and "new". Only "new" counts as a regression.
- **A failing pinned check is an error** in the `play` audit, whatever the
  ledger says about the finding behind it.

## <a id="bisect"></a>4. Scoped bisect

When a regression shows and its commit isn't obvious, the comparison from
step 1 already names the plugin and the records or files that differ.

1. List the commits between the good build and now that touch the code for
   that area, from the same map.
2. For each commit `git bisect run` tries, rebuild only the affected
   records into `temp/`, at that commit, with the scoped build the main
   session is landing ("only the changed cells", per-artifact stamps,
   record-level builds), and compare them with the good build's
   fingerprint.
3. Report the first commit whose output differs in the regressed records,
   with its diff.

No game launch is needed when the break shows in the output. A break that
shows only in play falls back to one change per play test: a short
autoplay run on the affected cells per step. This waits on the build-speed work: today one
step would be a full rebuild.

## <a id="order"></a>Order and effort

Effort is agent working days.

| Step | What | Size | Needs |
|---|---|---|---|
| 1a | `--mark-good`, keeping good builds' fingerprints, comparing with the newest | S, 1 day | the user marks the next build that plays well |
| 1b | Fingerprints for scripts, meshes, textures, faces, voice and archives | M, 2 days | |
| 1c | Area-to-code map, and expected, suspect and lost findings | M, 2 days | |
| 2 | `tests/regressions/` with its runner, seeded from the fixes of the last two weeks | S to M, 2 days, then one case per fix | |
| 3 | Must-pass list and comparison with the good build's run | S, 1 day | autoplay phase 1 |
| 4 | Scoped bisect | M, 3 days | record-level builds from the build-speed plan |

Step 1a is worth doing first: it is small, and it alone stops a break two
builds old from disappearing.
