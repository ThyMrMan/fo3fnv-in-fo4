# AnimTextData: what the Creation Kit writes for our build, and writing it ourselves (research, 2026-11-06)

Status: investigated on the whole-map build's CK output (`temp/profile_data`,
21,452 files) and every vanilla AnimTextData file in the game's BA2s. The
third-person gun writer is built and runs in the build after the CK step
(`fo4_import/havok/gun_anim_text.py`, `build_finish._gun_anim_text`,
[writer](#writer)); **not yet in a game build, not played**. Status lives in
[ROADMAP.md](../ROADMAP.md).

**Why.** The build runs `CreationKit.exe -GenerateAnimInfo` after the plugin
is written ([anim-info](../fo4_own_rig.md#anim-info)): 1,231 s on the
whole-map build of 2026-10-31. Fallout 34 writes AnimTextData itself
([prior art](../fo4_replacements.md#fallout34)), which suggested we could too.

## <a id="ids"></a>The file id rule (verified)

`<id>.txt`, id = `crc(folders) << 32 | crc(graph.lower())`; crc = CRC-32
with zero start and no final inversion (`gun_anim_text.entry_id`).

- **folders**: the subgraph entry's `SAPT` paths joined by `|`. **One folder:
  hashed in its authored case. Two or more: the joined string lower-cased.**
  Fallout 34's note (always lower case) and `gun_clips.crc` hold only for
  the multi-folder case, which every gun entry is.
- **Ids below 2³²** are a project's own files: crc of the lower-cased
  project path (`actors\fnvgiantant\fnvgiantantproject.hkx` → 229394221).
- Checked: all 3,144 Fallout4.esm entries. 2,786 have a file under this id;
  the other 358 are listed in the archives'
  `PersistantSubgraphInfoAndOffsetData.txt` instead. Folder lists with the
  case kept, or always lower-cased, explain fewer of the entries.
- For our plugin, all 8,401 entries are explained:
  - 6,184 got a CK file.
  - 2,063 got none: vanilla already ships a file under that id.
  - 154 got none: they are in vanilla's persistent list.
  - The 128 CK files with no subgraph entry are the projects.
- So the CK wrote nothing for ids whose data the load order already holds
  (in archives; whether a deployed loose file counts is not yet tested).

## <a id="what"></a>What the 21,452 files are

| Kind | Files | Size | Distinct contents |
|---|---|---|---|
| AnimationOffsets | 5,380 | 552 MB | 555 |
| AnimationSpeedInfo | 5,286 | 647 MB | 5,264 |
| AnimationStanceData | 5,368 | 148 MB | 1,539 |
| DynamicIdleData | 5,380 | 0.1 MB | 1 (`Version 1\n`) |
| FileData, EventInfo, ClipGeneratorData | 12 each | small | |
| SyncAnimData | 1 | | |

5,252 of the 5,380 entries are the **gun entries** on
`FNV_HumanRaceSubGraphDataAdditive` (7,775 entries; the injured-arm wrapping
graphs and `WeaponBehavior` lead). The 11 own-rig creatures are a few dozen
files. `FNV_SuperMutantRaceSubGraphDataAdditive`'s 608 entries got nothing;
vanilla covers every one of their ids. **98% of the CK's files, 1.35 GB, are
gun data**, not the own-rig creatures that `anim_info` runs for (time per
entry not measured). The gun entries' AnimationFileData is already ours:
`gun_clips._anim_text` copies the template's under the new id, pointing the
clips it wrote at the FNV folder.

**Where FNV clips land** (a 411-entry sample of the CK's files): no
third-person entry resolves an FNV clip (FNV third-person clips are not
built yet). Only first-person `GunBehavior` and
`Pistol_GunWrappingBehavior` entries do, 414 records in 10 files; those have
offsets and stance, no speed info.

## <a id="offsets"></a>AnimationOffsets V4 (decoded)

A string is a u8 length (including the NUL), then the bytes. The layout:

```
'V4\n', str graph
u32 n, n x (str clip name, str clip path)        name -> resolved file
u32 m, m x (str clip path, f32 duration,
            u32 t, t x (f32 time, x, y, z),        root translation keys
            u32 r, r x (f32 time, quaternion),     root rotation keys
            u32 e, e x (f32 time, str event))      annotations (FootLeft ...)
```

All 3,154 vanilla and 5,380 CK files parse to their last byte.

- The CK's files hold 1.49 M clip records:
  - 3,884 are FNV clips, which are new;
  - 1,187 are vanilla clips that no vanilla file has;
  - the rest are vanilla clips that vanilla already has.
- Vanilla clips against vanilla's own records:
  - Duration and events always match.
  - Translation and rotation match within 0.001 for 99.5% of records: float
    noise from recomputing.
  - 4,958 records differ by more.
- 4,817 CK files have a vanilla template: the same entry with the
  `Actors\FNV` folders dropped. All have the same clip set and the same
  length as their template. Only the order (hash order) and float noise
  differ.
- **An FNV clip's record**, all 414 sampled reproduced exactly:
  - the duration from our clip;
  - one zero translation key and one identity rotation key, at
    float32(frames × frame length) (90 × 0.033333335 = 3.0000002);
  - our clip's annotations, kept only when the graph or a graph it
    references names that event, spelled as vanilla's offsets files spell
    it (`weaponFire` → `WeaponFire`; sound events dropped).
- **The names list** is the clips the graph's clip generators play through
  the entry, narrower than every `hkbClipGenerator` in the graph and its
  references: `WPNAssemblyPose` is in the graph but in no list.

## <a id="others"></a>Speed and stance data (not decoded)

- **AnimationSpeedInfo:**
  - About 124 KB for a weapon graph.
  - u32 6, u32 state-machine count, then each state machine's `.hkb/` path
    with its contours. Contour types are `SpeedSampledAnimationSpeedContour`,
    `CollectionAnimationSpeedContourName` and
    `IndividualClipAnimationSpeedContour`.
  - The CK's state machine names (`RifleSneakFireAutoStateMachine00`) are not
    in vanilla's file for the same graph: vanilla's files come from older
    graphs, and the game runs vanilla guns on them.
- **AnimationStanceData:**
  - `AnimationBoneTransform`, u32 1, u32 count, then per pose a u8 pair and
    bone transforms as floats, then a second section.
  - First-person entries playing FNV clips: the same length as the
    template's, other transforms (worked out from the clips).

## <a id="persistent"></a>The persistent list

`AnimationOffsets\PersistantSubgraphInfoAndOffsetData.txt`, one `<id>.txt`
per line. Each DLC archive ships its own (333 to 366 ids, 398 joined); a
loose copy replaces them all. The CK's for our build holds 768: the 333
every archive shares plus 435 of ours. **One of our entries is on it exactly
when its template is on vanilla's** (423 of 423, and none of the 4,817
others); the CK's 12 others are entries the CK keeps.

## <a id="writer"></a>The writer (built 2026-11-06)

`fo4_import/havok/gun_anim_text.py` writes the entries the CK would compute
from vanilla clips only:

- **Which:**
  - third-person entries with FNV and vanilla folders, on a graph vanilla has
    offsets for;
  - none of the FNV clips in the entry's file data (gun_clips) is named in
    any vanilla offsets file of that graph.
- **What:** the template's offsets, speed, stance and dynamic idle files,
  byte for byte, under the entry's id. That is the data the game already
  uses for the template entry. The entry is added to the persistent list
  when its template is listed (`merge_persistent`). So do the master
  builds' listed ids, since a DLC build's loose list hides the base's.
- **When:** after the CK step, so these files are ours whatever the CK
  wrote, and every build ends the same way.
- **Checked against the CK snapshot:**
  - 5,154 entries copied. In the 411-entry sample, all 378 copied are
    entries where the CK resolved no FNV clip, and all 10 that resolve one
    are left to the CK.
  - The offsets have the CK's clip set in all 356 with a template file. The
    other 22 have persistent-only templates and, like vanilla, no offsets
    file.
  - The persistent ids match the CK's list.
  - Loading vanilla takes 1.1 s, choosing the entries 2.4 s warm, writing
    378 entries 1.2 s.
- **Left to the CK:** first-person entries (FNV clip records are reproducible,
  stance is not decoded) and own-rig creatures.

**Time.** The CK sees MO2's Data (the deployed mod), so it can skip our
files only once they are deployed. If it skips ids that have files (as it
did for vanilla's), its run shrinks to the first-person entries and the
creatures. If it doesn't, its output replaces ours and the build is as
before. Not yet measured: needs a CK run after a deploy.
