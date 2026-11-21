"""An own rig's hit reactions from FNV's hit-reaction idles: IDLE records playing a clip in the rig's folder, gated by
GetHitLocation on themselves or a parent. Each FO4 body part type of the rig's body part data plays the clip FNV
plays for the FNV part covering that part's bone; the root graph's HitReaction state picks it.

See: docs/fork/fo4_own_rig.md#hit-reactions
"""

from dataclasses import replace
from pathlib import PureWindowsPath

from fo4_import.rig import records
from fo4_import.spike import conditions as C
from fo4_import.spike.say_topics import parsed

#: The FNV function the hit-reaction idles test, and the locations it returns for a part (FNV body part types).
HIT_LOCATION, LOCATIONS = 'GetHitLocation', range(15)
#: FO4 body part type -> the FNV one of the same name (xEdit's two Part Type enums), for a bone no FNV part covers.
SAME_NAMED = {0: 0, 1: 1, 5: 2, 6: 3, 7: 4, 8: 5, 9: 6, 10: 7, 11: 8, 12: 9, 13: 10, 14: 11, 15: 12, 16: 13, 17: 14}


def lineage(rec: dict, by_id: dict) -> list:
    """FNV idle `rec` and its parents (ANAM.Parent), nearest first."""
    out, seen = [], set()
    while rec and rec.get('FormID') not in seen:
        seen.add(rec.get('FormID'))
        out.append(rec)
        rec = by_id.get(int(rec.get('ANAM.Parent', '0') or '0', 16))
    return out


def locations(recs: list) -> list:
    """The FNV hit locations passing every GetHitLocation OR-group of records `recs` (an idle and its parents),
    other tests left out; [] when none tests it."""
    tests = [[c for c in group if c['func'] == HIT_LOCATION] for rec in recs for group in C.groups(parsed(rec))]
    tests = [group for group in tests if group]
    if not tests:
        return []
    return [at for at in LOCATIONS if all(any(C.compare(c, at) for c in group) for group in tests)]


def location_clips(rig, idles: tuple, fnv_dir) -> dict:
    """{FNV hit location: clip under `rig`'s folder} of FNV's hit-reaction idles (`idles`: FNV IDLE records) whose
    clip is in `fnv_dir`, the first idle in record order per location."""
    by_id = {int(rec['FormID'], 16): rec for rec in idles}
    out, folder = {}, rig.folder + '\\'
    for rec in idles:
        model = rec.get('Model.MODL', '')
        if not (model.lower().startswith(folder) and model.lower().endswith('.kf')):
            continue
        clip = model[len(folder):]
        if (fnv_dir / clip).is_file():
            for at in locations(lineage(rec, by_id)):
                out.setdefault(at, clip)
    return out


def role(clip: str) -> str:
    """FNV hit clip `clip`'s rig clip role (its file under the rig's Animations)."""
    return 'Hit_' + PureWindowsPath(clip).stem


def with_hits(rig, t, idles: tuple, bones: list, fnv_dir):
    """`rig` with its hit reactions: per part type of its template's body part data (records.template_parts), the
    role (role()) of the clip FNV's hit idles (location_clips) play for the FNV part covering that part's bone (the
    SAME_NAMED part when none covers it), '' for none, each played clip added to rig.clips; `rig` itself when FNV
    has none.
    See: docs/fork/fo4_own_rig.md#hit-reactions
    """
    clips = location_clips(rig, idles, fnv_dir)
    if not clips:
        return rig
    parents = {b.name: bones[b.parent].name for b in bones if b.parent >= 0}
    types = {}
    for bone, _, kind in records.fnv_parts(rig.folder):
        types.setdefault(bone, kind)
    hits = {}
    for part, bone in records.template_parts(rig, t):
        at = records.covering(bone, types, parents)
        clip = clips.get(SAME_NAMED.get(part) if at is None else at)
        hits.setdefault(part, role(clip) if clip else '')
    played = {role(clip): clip for clip in clips.values() if role(clip) in hits.values()}
    return replace(rig, clips={**rig.clips, **played}, hits=tuple(sorted(hits.items())))
