"""FO3/FNV's level-up for our own level-up menu, in place of LevelUpMenuEx's PRKF.dll: F3NV_LevelUp on the character
rules quest holds the points and tagged skills, opens the menu (Interface/F3NV_LevelUp.swf, fo4_import/level_up),
and gets from the build what the menu shows without asking the engine: each listed perk's name, description, image,
level and rank chain, each skill's name, description and image, and each playable perk's requirements as rows
("Science 50", "Level 8"). Whether a perk can be taken is still the engine's own test of its conditions.

See: docs/fork/fo4_level_up_plan.md#prkf
"""

from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike.perks import fo4_icon

SCRIPT = 'F3NV_LevelUp'
#: Requirement kinds by FNV condition function: an actor value, the player's sex, another perk, the level.
KINDS = {'GetPermanentActorValue': 0, 'GetActorValue': 0, 'GetIsSex': 1, 'HasPerk': 2, 'GetLevel': 3}
#: A condition's comparison bits, shifted down to 0-5: ==, !=, >, >=, <, <=.
COMPARE_SHIFT = 5
EQUAL, NOT_EQUAL = 0, 1
#: FO3/FNV actor value FormIDs: index + this.
FNV_AVIF_BASE = 0x490
#: Between the entries of a table the menu reads as one string (no entry holds one).
SEP = '\t'


# ---------------------------------------------------------------------------
# Source records and tables
# ---------------------------------------------------------------------------


def av_records(export_dir: Path) -> dict:
    """{FNV actor value index: its AVIF record} of the game's actor values."""
    return {int(r['FormID'], 16) - FNV_AVIF_BASE: r for r in export_records(export_dir, 'AVIF')}


def joined(texts) -> str:
    """`texts` as one SEP-separated string, any SEP inside one made a space."""
    return SEP.join(str(t).replace(SEP, ' ') for t in texts)


# ---------------------------------------------------------------------------
# Requirement rows
# ---------------------------------------------------------------------------


def _sex(cond: dict) -> 'tuple | None':
    """GetIsSex(p1) == or != 0 or 1 as (comparison, value) on the player's sex (0 male, 1 female); None otherwise."""
    compare = cond['op_flags'] >> COMPARE_SHIFT
    if compare not in (EQUAL, NOT_EQUAL) or cond['value'] not in (0.0, 1.0):
        return None
    return (EQUAL if (compare == EQUAL) == (cond['value'] == 1.0) else NOT_EQUAL), float(cond['p1'])


def _row(cond: dict, perks, names: dict) -> 'tuple | None':
    """(kind, form, comparison, value, or-next, label) of one requirement condition; None when the menu cannot show
    it. The label names the actor value or perk tested ('' for sex and level)."""
    kind = KINDS.get(cond['func'])
    if kind is None or cond['op_flags'] & C.USE_GLOBAL:
        return None
    form = {0: perks.forms.get(('av', cond['p1'])), 2: perks.first.get(cond['p1'])}.get(kind, 0)
    test = _sex(cond) if kind == 1 else (cond['op_flags'] >> COMPARE_SHIFT, cond['value'])
    if form is None or test is None:
        return None
    label = names.get((kind, cond['p1']), '')
    return kind, form, *test, int(bool(cond['op_flags'] & 0x01)), label


def labels(perks, avs: dict) -> dict:
    """{(kind, FNV parameter): name} of actor values (by index) and perks.
    See: docs/fork/fo4_level_up_plan.md#menu
    """
    out = {(0, i): avs.get(i, {}).get('FULL') or name for i, name in enumerate(C.FNV_AV_NAMES)}
    out.update({(2, int(r['FormID'], 16)): r.get('FULL', '') for r in perks.records})
    return out


def rows(builder, names: dict = None) -> list:
    """[(first rank, kind, form, comparison, value, or-next, label)] of every playable perk's requirement conditions,
    in record order; a condition the menu cannot show is counted and left out."""
    perks, out = builder.perks, []
    for rec in perks.records:
        if rec.get('DATA.Playable') != '1' or rec.get('DATA.Hidden') == '1':
            continue
        first = perks.first[int(rec['FormID'], 16)]
        for key in sorted((k for k in rec if k.startswith('Condition[')), key=lambda k: int(k[10:k.index(']')])):
            row = _row(C.parse(rec[key]), perks, names or {})
            if row is None:
                builder.counts['level-up requirement not shown'] += 1
            else:
                out.append((first, *row))
    return out


def properties(table: list, values: list = (), listed: list = ()) -> dict:
    """F3NV_LevelUp's Requirement* properties: `table`'s rows as parallel arrays. A row's owner is its perk's index
    in `listed` (the level-up list); its target the index the menu finds the tested value at: in `values` (SPECIAL
    then skills) for an actor value, in `listed` for a perk; -1 when not there."""
    perk, kind, form, compare, value, either, label = zip(*table) if table else ((),) * 7
    where = {0: list(values), 2: list(listed)}
    targets = [where[k].index(f) if f in where.get(k, ()) else -1 for k, f in zip(kind, form)]
    owners = [list(listed).index(p) if p in listed else -1 for p in perk]
    return {'RequirementPerks': ('objects', list(perk)), 'RequirementKinds': ('ints', list(kind)),
            'RequirementForms': ('objects', list(form)), 'RequirementCompares': ('ints', list(compare)),
            'RequirementValues': ('floats', [float(v) for v in value]), 'RequirementOr': ('ints', list(either)),
            'RequirementOwners': ('ints', owners), 'RequirementTargets': ('ints', targets),
            'RequirementLabels': ('string', joined(label))}


# ---------------------------------------------------------------------------
# What the menu shows
# ---------------------------------------------------------------------------


def perk_table(perks) -> dict:
    """The level-up list's perks (perks.offered(), FNV_Perks' order): names, descriptions and images as SEP tables,
    each one's level and rank count, and every rank in order (RankForms, PerkRanks per perk)."""
    offered = perks.offered()
    ranks = [perks.ids[int(r['FormID'], 16)] for r in offered]
    return {'PerkNames': ('string', joined(r.get('FULL', '') for r in offered)),
            'PerkDescriptions': ('string', joined(r.get('DESC', '') for r in offered)),
            'PerkImages': ('string', joined(fo4_icon(r) for r in offered)),
            'PerkLevels': ('ints', [int(r.get('DATA.MinLevel', 0) or 0) for r in offered]),
            'PerkRanks': ('ints', [len(ids) for ids in ranks]),
            'RankForms': ('objects', [fid for ids in ranks for fid in ids])}


def skill_table(avs: dict, skills: list) -> dict:
    """`skills` (FNV actor value names without spaces, FNV_Skills' order): names, descriptions and images as SEP
    tables, from the game's AVIF records."""
    index = {n.replace(' ', ''): i for i, n in enumerate(C.FNV_AV_NAMES)}
    records = [avs.get(index[s], {}) for s in skills]
    return {'SkillNames': ('string', joined(r.get('FULL') or s for r, s in zip(records, skills))),
            'SkillDescriptions': ('string', joined(r.get('DESC', '') for r in records)),
            'SkillImages': ('string', joined(fo4_icon(r) for r in records))}


def menu_properties(builder, avs: dict, values: list, skills: list) -> dict:
    """F3NV_LevelUp's value properties: rows, perk and skill tables.
    See: docs/fork/fo4_level_up_plan.md#menu
    """
    table = rows(builder, labels(builder.perks, avs))
    listed = [builder.perks.ids[int(r['FormID'], 16)][0] for r in builder.perks.offered()]
    return {**properties(table, values, listed), **perk_table(builder.perks), **skill_table(avs, skills)}
