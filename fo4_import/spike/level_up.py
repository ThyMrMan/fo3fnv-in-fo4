"""FO3/FNV's level-up state for our own level-up menu, in place of LevelUpMenuEx's PRKF.dll: F3NV_LevelUp on the
character rules quest holds the points and tagged skills, and gets each playable perk's requirements as rows the
menu shows ("Science 50", "Level 8"); whether a perk can be taken is the engine's own test of its conditions.

See: docs/fork/fo4_level_up_plan.md#prkf
"""

from fo4_import.spike import conditions as C

SCRIPT = 'F3NV_LevelUp'
#: Requirement kinds by FNV condition function: an actor value, the player's sex, another perk, the level.
KINDS = {'GetPermanentActorValue': 0, 'GetActorValue': 0, 'GetIsSex': 1, 'HasPerk': 2, 'GetLevel': 3}
#: A condition's comparison bits, shifted down to 0-5: ==, !=, >, >=, <, <=.
COMPARE_SHIFT = 5


def _row(cond: dict, perks) -> 'tuple | None':
    """(kind, form, comparison, value, or-next) of one requirement condition; None when the menu cannot show it."""
    kind = KINDS.get(cond['func'])
    if kind is None or cond['op_flags'] & C.USE_GLOBAL:
        return None
    form = {0: perks.forms.get(('av', cond['p1'])), 2: perks.first.get(cond['p1'])}.get(kind, 0)
    if form is None:
        return None
    return kind, form, cond['op_flags'] >> COMPARE_SHIFT, cond['value'], int(bool(cond['op_flags'] & 0x01))


def rows(builder) -> list:
    """[(first rank, kind, form, comparison, value, or-next)] of every playable perk's requirement conditions, in
    record order; a condition the menu cannot show is counted and left out."""
    perks, out = builder.perks, []
    for rec in perks.records:
        if rec.get('DATA.Playable') != '1' or rec.get('DATA.Hidden') == '1':
            continue
        first = perks.first[int(rec['FormID'], 16)]
        for key in sorted((k for k in rec if k.startswith('Condition[')), key=lambda k: int(k[10:k.index(']')])):
            row = _row(C.parse(rec[key]), perks)
            if row is None:
                builder.counts['level-up requirement not shown'] += 1
            else:
                out.append((first, *row))
    return out


def properties(table: list) -> dict:
    """F3NV_LevelUp's Requirement* properties: `table`'s rows as parallel arrays."""
    perk, kind, form, compare, value, either = zip(*table) if table else ((),) * 6
    return {'RequirementPerks': ('objects', list(perk)), 'RequirementKinds': ('ints', list(kind)),
            'RequirementForms': ('objects', list(form)), 'RequirementCompares': ('ints', list(compare)),
            'RequirementValues': ('floats', [float(v) for v in value]), 'RequirementOr': ('ints', list(either))}
