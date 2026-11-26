"""The route each FNV/FO3 weapon takes to Fallout 4, the first that works, each counted and listed:

1. its hand table entry;
2. the entry of a listed weapon with the same model (a variant: new stats, texture or name);
3. its own mesh on the FO4 gun spike.gun_choice picks, when it passes the checks (weapon_checks);
4. that gun's own mesh (`stats`), when it fails one;
5. the stand-in of its animation type (`_rules.weapon`), for anything else but a creature's modelless attack gear
   (attack_gear), which is left out: the creature fights with its stand-in's.

Every weapon's route goes in the build's `<plugin>.weapons.tsv` (EditorID, FormID, route, target, why, checks).

See: docs/fork/fo4_weapon_routes_plan.md#order
"""

from dataclasses import dataclass, field
from pathlib import Path

from fo4_import.base.build_files import moved_in
from fo4_import.spike.creatures import fnv_gear
from fo4_import.spike.gun_choice import GUN_TYPES
from fo4_import.spike.replacements import BASE, Replacement

#: The report's file name ending, beside the plugin in its build records.
REPORT_SUFFIX = '.weapons.tsv'
REPORT_HEAD = ('editor_id', 'form_id', 'route', 'target', 'why', 'checks')


def model_key(rec: dict) -> str:
    """WEAP `rec`'s model path, lower case, backslashes; '' without one."""
    return rec.get('Model.MODL', '').replace('/', '\\').replace('\\\\', '\\').lower()


def anim_type(rec: dict) -> int:
    """WEAP export record `rec`'s FNV animation type; -1 without one."""
    return int(rec.get('DNAM.FalloutAnimType', -1))


def attack_gear(rec: dict) -> bool:
    """Whether WEAP `rec` is modelless creature attack gear (left out)."""
    return not model_key(rec) and fnv_gear('WEAP', rec)


def own_gun(rec: dict) -> bool:
    """Whether WEAP `rec` is a gun with a model (gun_choice may build on it)."""
    return anim_type(rec) in GUN_TYPES and bool(model_key(rec))


@dataclass
class Row:
    """One weapon's line in the report."""
    edid: str
    fnv: int
    route: str
    target: str = ''
    why: str = ''
    checks: dict = field(default_factory=dict)

    def line(self) -> str:
        """The row as a TSV line."""
        checks = ' '.join(f'{k}={v}' for k, v in sorted(self.checks.items()))
        return '\t'.join((self.edid, f'{self.fnv:08X}', self.route, self.target, self.why, checks))


class WeaponRoutes:
    """One build's weapon routes: the listed and same-model entries, the stand-ins, what each weapon took."""

    def __init__(self, table, records, counts):
        """`table` (replacements.Table); the models of the listed weapons it copies, from WEAP export `records`
        (the plugin's and its masters')."""
        self.table, self.counts, self.rows, self.decided = table, counts, {}, {}
        self.models = {}
        for rec in sorted(records, key=lambda r: r.get('EditorID', '')):
            entry = table.get(rec.get('EditorID'))
            if entry is not None and entry.base and entry.mode != 'item' and model_key(rec):
                self.models.setdefault(model_key(rec), (rec['EditorID'], entry))

    def listed(self, rec: dict) -> 'tuple | None':
        """(entry, how) of WEAP `rec` from the table, else from a listed weapon with its model; None."""
        entry = self.table.get(rec.get('EditorID'))
        if entry is not None:
            return entry, 'hand table'
        found = self.models.get(model_key(rec))
        return (found[1], f'same model as {found[0]}') if found else None

    def stand_in(self, rec: dict) -> 'Replacement | None':
        """The `_rules.weapon` entry of `rec`'s animation type; None."""
        return self.table.rules.weapon.get(anim_type(rec))

    def entry(self, rec: dict) -> 'Replacement | None':
        """The entry WEAP `rec` is written on: the one decided for it, else listed(), else (not a gun on its own
        mesh) its stand-in."""
        fnv = int(rec['FormID'], 16)
        if fnv in self.decided:
            return self.decided[fnv]
        found = self.listed(rec)
        return found[0] if found else (None if own_gun(rec) or attack_gear(rec) else self.stand_in(rec))

    def decide(self, rec: dict, entry: 'Replacement | None', route: str, why: str = '', checks: dict = None):
        """Record `rec`'s route (its entry, when one other than entry() is used from here on); `entry`."""
        fnv = int(rec['FormID'], 16)
        if entry is not None:
            self.decided[fnv] = entry
        self.note(rec, route, entry.edid if entry else '', why, checks)
        return entry

    def note(self, rec: dict, route: str, target: str, why: str = '', checks: dict = None) -> None:
        """List WEAP `rec`'s route, counted by its kind."""
        fnv = int(rec['FormID'], 16)
        self.rows[fnv] = Row(rec.get('EditorID', ''), fnv, route, target, why, dict(checks or {}))
        self.counts[f'weapon route ({route.split(" as ")[0]})'] += 1

    def demoted(self, rec: dict, template: str, why: str, checks: dict) -> Replacement:
        """`rec` on FO4 gun `template`'s own mesh, for failing check `why`."""
        return self.decide(rec, Replacement(BASE, template, 'stats', category='weapon', origin='route'),
                           'template mesh', why, checks)

    def write(self, plugin: Path) -> int:
        """Write the report beside `plugin` in its build records; the rows written."""
        path = moved_in(plugin.with_name(plugin.name + REPORT_SUFFIX))
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ['\t'.join(REPORT_HEAD)] + [row.line() for _, row in sorted(self.rows.items())]
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return len(self.rows)
