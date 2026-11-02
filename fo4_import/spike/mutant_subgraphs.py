"""Super mutants' weapon behaviour for FNV weapons: an additive subgraph race on FO4's SuperMutantRace.

FO4's SuperMutantRace picks a weapon's behaviour by keyword, with entries for
nine: AnimsHuntingRifle, AnimsGripRifleAssault, AnimsRecieverHandmadePipe,
AnimsLaserGripRifle, AnimsMinigun, AnimsMissileLauncher, AnimsFatManBomb,
Anims2hmWideWeapon and unarmed. A weapon matching none of them never
animates, so the mutant fights with its race's unarmed weapon. Two kinds of
FNV weapon match none:
- A gun on FNV's clips: it trades its template's Anims keyword for its own
  (spike.guns.anim_keywords), which only the human additive race maps.
- Two-handed melee: it carries the baseball bat's Anims2hmWeapon, which
  super mutants have no entry for. Vanilla's sledges and boards carry
  Anims2hmWideWeapon instead.

This race adds copies of the super mutant entries of each such keyword's
class. The class is the vanilla keyword a gun's own keyword replaced, or
the nearest super mutant class for a kind FO4 never gave super mutants
(NEAREST): flamers hold like the minigun, submachine guns like the assault
rifle, the Fat Man like the missile launcher. A copy keeps the entry's
actor keywords (its crippled-limb variants), graph and clips, and targets
the one keyword.
See: docs/fork/fo4_spikes.md#spike-4-creatures
"""

import struct
from pathlib import Path

from fo4_import.base.writer import pack_fo4_record
from fo4_import.havok.gun_clips import HEAD, HUMAN_SUBGRAPHS, ROLE_WEAPON, entry_subrecords, subgraph_entries
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: Fallout4.esm's SuperMutantRace, which the entries are added to (SADD).
SUPER_MUTANT = 0x1A009
#: Anims keyword of a weapon kind SuperMutantRace has no entry for -> the super mutant class it holds like.
NEAREST = {'Anims2hmWeapon': 'Anims2hmWideWeapon', 'AnimsFlamer': 'AnimsMinigun',
           'AnimsSubmachineGun': 'AnimsGripRifleAssault', 'AnimsFatMan': 'AnimsMissileLauncher'}
#: derive_formid site and EditorID of the additive race.
RACE_SITE, RACE_EDID = 'FNV super mutant anims RACE', 'FNV_SuperMutantRaceSubGraphDataAdditive'


def weapon_entries(subs: list) -> list:
    """A race's weapon subgraph entries (SRAF role ROLE_WEAPON)."""
    return [e for e in subgraph_entries(subs) if struct.unpack_from('<H', e['flags'])[0] == ROLE_WEAPON]


def mutant_entries(entries: list, classes: dict) -> list:
    """Copies of super mutant weapon `entries` for each keyword in `classes` ({keyword: the keyword of the class
    it holds like}), each targeting that keyword alone; a keyword whose class has no entry gets none."""
    out = []
    for keyword, cls in classes.items():
        out += [dict(e, target=[keyword]) for e in entries if cls in e['target']]
    return out


def keyword_classes(replaced: dict, keywords: dict, vanilla: bool) -> dict:
    """{keyword: class keyword} a super mutant needs mapped: every gun's own keyword (`replaced`: own -> the vanilla
    one it replaced) to its class, nearest (NEAREST) when super mutants have none; with `vanilla`, also NEAREST's
    vanilla keywords. `keywords` maps Fallout4.esm's keyword EditorIDs to FormIDs."""
    nearest = {keywords[k]: keywords[v] for k, v in NEAREST.items() if k in keywords and v in keywords}
    out = {own: nearest.get(old, old) for own, old in replaced.items()}
    if vanilla:
        out.update(nearest)
    return out


def additive_race(edid: str, head_from: list, entries: list) -> list:
    """The additive race's subrecords: the head the human gun race uses (HEAD, filled from `head_from`), SADD on
    SuperMutantRace, then `entries`."""
    seen, out = {}, []
    for sig in HEAD:
        k = seen[sig] = seen.get(sig, -1) + 1
        body = (edid + '\0').encode() if sig == 'EDID' else [b for s, b in head_from if s == sig.encode()][k]
        out.append((sig.encode(), body))
    out.append((b'SADD', struct.pack('<I', SUPER_MUTANT)))
    for entry in entries:
        out += entry_subrecords(entry)
    return out


def write_mutant_subgraphs(builder, guns) -> None:
    """Write the additive race mapping FNV weapons' keywords to super mutant behaviour (none without one). A DLC's
    build maps only its own guns' keywords; the vanilla ones are the base game's (as spike.guns.write_subgraphs)."""
    writer, built = builder.writer, builder.built
    own = (lambda kw: kw >> 24 == writer.own_index) if built else (lambda kw: True)
    replaced = {new: old for made in guns.converted.values() for old, new in made.replaces.items() if own(new)}
    races = {r.form_id: list(subrecords(r.body)) for r, _ in walk(builder.fo4, b'RACE')
             if r.form_id in (SUPER_MUTANT, HUMAN_SUBGRAPHS)}
    entries = mutant_entries(weapon_entries(races[SUPER_MUTANT]), keyword_classes(replaced, builder.keywords,
                                                                                  not built))
    if not entries:
        return
    edid = f'{RACE_EDID}_{Path(builder.export_dir.name).stem}' if built else RACE_EDID
    subs = additive_race(edid, races[HUMAN_SUBGRAPHS], entries)
    writer.add_record('RACE', pack_fo4_record('RACE', writer.derive_formid(RACE_SITE, edid), 0, b''.join(
        pack_subrecord(s.decode(), b) for s, b in subs)))
