"""FO3/FNV's level-up for our own level-up menu, in place of LevelUpMenuEx's PRKF.dll: CRUI_LevelUp on the character
rules quest holds the points and tagged skills, opens the menu (Interface/CRUI_LevelUp.swf, fo4_import/level_up),
and gets from the build what the menu shows without asking the engine: each skill's name, description and image,
and from each plugin's CRUI_LevelUpTable its own listed perks' and traits' names, descriptions, images, levels and
rank chains and its perks' requirements as rows ("Science 50", "Level 8"). Whether a perk can be taken is still the
engine's own test of its conditions.

See: docs/fork/fo4_level_up_plan.md#prkf
"""

from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike.perks import fo4_icon

SCRIPT, TABLE_SCRIPT = 'CRUI_LevelUp', 'CRUI_LevelUpTable'
#: DEPRECATED: the level-up script before CRUI_LevelUp, kept on the rules quest so older saves keep its state.
LEGACY_SCRIPT = 'F3NV_LevelUp'
#: Requirement kinds by FNV condition function: an actor value, the player's sex, another perk, the level.
KINDS = {'GetPermanentActorValue': 0, 'GetActorValue': 0, 'GetIsSex': 1, 'HasPerk': 2, 'GetLevel': 3}
#: A condition's comparison bits, shifted down to 0-5: ==, !=, >, >=, <, <=.
COMPARE_SHIFT = 5
EQUAL, NOT_EQUAL = 0, 1
#: FO3/FNV actor value FormIDs: index + this.
FNV_AVIF_BASE = 0x490
#: Between the entries of a table the menu reads as one string (no entry holds one).
SEP = '\t'
#: The tag and trait menus' picks come back as one Papyrus Int, a bit per entry.
MASK_BITS = 31


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


def rows(builder, names: dict = None, records: list = None) -> list:
    """[(first rank, kind, form, comparison, value, or-next, label)] of every playable perk's requirement conditions
    (of `records`, else all), in record order; a condition the menu cannot show is counted and left out."""
    perks, out = builder.perks, []
    for rec in perks.records if records is None else records:
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
    """CRUI_LevelUpTable's Requirement* properties: `table`'s rows as the SEP texts the menu reads, so an open joins
    nothing. A row's owner is its perk's index in `listed` (the table's listed perks); its target the index the menu
    finds the tested value at: in `values` (SPECIAL then skills) for an actor value, in `listed` for a perk; -1 when
    not there. The menu moves both by where the table's perks start. RowTotal counts the rows; UnlistedRows and
    UnlistedPerks are the rows testing a perk the table does not list, which the game is asked about.
    See: docs/fork/fo4_level_up_plan.md#open-delay
    """
    perk, kind, form, compare, value, either, label = zip(*table) if table else ((),) * 7
    where = {0: list(values), 2: list(listed)}
    targets = [where[k].index(f) if f in where.get(k, ()) else -1 for k, f in zip(kind, form)]
    owners = [list(listed).index(p) if p in listed else -1 for p in perk]
    unlisted = [i for i, (k, t) in enumerate(zip(kind, targets)) if k == 2 and t < 0]
    return {'RequirementKinds': ('string', joined(kind)), 'RequirementCompares': ('string', joined(compare)),
            'RequirementValues': ('string', joined(float(v) for v in value)), 'RequirementOr': ('string', joined(either)),
            'RequirementOwners': ('string', joined(owners)), 'RequirementTargets': ('string', joined(targets)),
            'RequirementLabels': ('string', joined(label)), 'RowTotal': ('int', len(kind)),
            'UnlistedRows': ('ints', unlisted), 'UnlistedPerks': ('objects', [form[i] for i in unlisted])}


# ---------------------------------------------------------------------------
# What the menu shows
# ---------------------------------------------------------------------------


def texts(kind: str, records: list, names: list = None) -> dict:
    """`records`' names (`names` where FULL is empty), descriptions and images as the SEP tables <kind>Names,
    <kind>Descriptions and <kind>Images."""
    names = names or [''] * len(records)
    return {f'{kind}Names': ('string', joined(r.get('FULL') or n for r, n in zip(records, names))),
            f'{kind}Descriptions': ('string', joined(r.get('DESC', '') for r in records)),
            f'{kind}Images': ('string', joined(fo4_icon(r) for r in records))}


def perk_table(perks, offered: list) -> dict:
    """Listed perks `offered` (in perks.offered()'s order) as texts(), each one's level and rank count as SEP texts,
    and every rank in order (RankForms, PerkRanks per perk)."""
    ranks = [perks.ids[int(r['FormID'], 16)] for r in offered]
    counts = [len(ids) for ids in ranks]
    return {**texts('Perk', offered),
            'PerkLevels': ('string', joined(int(r.get('DATA.MinLevel', 0) or 0) for r in offered)),
            'PerkRanks': ('ints', counts), 'PerkRanksText': ('string', joined(counts)),
            'RankForms': ('objects', [fid for ids in ranks for fid in ids])}


def skill_table(avs: dict, skills: list) -> dict:
    """`skills` (FNV_Skills' order, spaceless AV names) as texts() from AVIFs."""
    index = {n.replace(' ', ''): i for i, n in enumerate(C.FNV_AV_NAMES)}
    return texts('Skill', [avs.get(index[s], {}) for s in skills], skills)


def table_properties(builder, avs: dict, values: list) -> dict:
    """CRUI_LevelUpTable's value properties for the build's own listed perks and traits (a DLC's, not its masters'):
    their tables and the perks' requirement rows. The trait menu answers with a bit per trait, so a trait past
    MASK_BITS is counted.
    See: docs/fork/fo4_level_up_plan.md#tables
    """
    perks = builder.perks
    offered, traits = (_own(builder, records) for records in (perks.offered(), perks.trait_records()))
    listed = [perks.ids[int(r['FormID'], 16)][0] for r in offered]
    if len(traits) > MASK_BITS:
        builder.counts['level-up menu traits past its mask'] += len(traits) - MASK_BITS
    table = rows(builder, labels(perks, avs), _own(builder, perks.records))
    return {**properties(table, values, listed), **perk_table(perks, offered), **texts('Trait', traits),
            'TraitForms': ('objects', [perks.ids[int(r['FormID'], 16)][0] for r in traits])}


def _own(builder, records) -> list:
    """`records` that are the source plugin's own, not its masters'."""
    return [r for r in records if builder.ids.is_own(int(r['FormID'], 16))]
