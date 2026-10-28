"""The Replacements screen's left column: the source game's forms by category and what stands in for each now.

What stands in is asked of the converter's own rules, so the screen never disagrees with a build: a table entry
(any layer), else the rule (equipment.default_entry for armor and melee weapons, the creature's skeleton folder
rule), else the converter's own choice (a gun: the closest FO4 gun, picked at build time; other items: a copy of
FNV's record), else nothing (a creature with no stand-in is skipped).

See: docs/fork/fo4_gui.md#replacements-screen
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from fo4_import.app.files import key
from fo4_import.nif.convert_static import PREFIX
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.creatures import skeleton_folder
from fo4_import.spike.equipment import default_entry
from fo4_import.spike.gun_choice import GUN_TYPES
from fo4_import.spike.replacements import creature_entry

#: Replacement table category -> the source record types listed under it.
CATEGORY_SIGS = {'weapon': ('WEAP',), 'armor': ('ARMO',), 'consumable': ('ALCH',), 'ammo': ('AMMO',),
                 'misc': ('MISC', 'BOOK', 'KEYM', 'NOTE'), 'creature': ('CREA',)}
#: Where the stand-in comes from, as the screen words it.
HOW = {'table': 'table', 'rule': 'rule', 'gun': 'closest FO4 gun (picked at build)',
       'copy': "converted from FNV's record", 'none': 'none: skipped'}
#: Export fields compared on the screen, by label.
STATS = {'damage': 'DATA.Damage', 'value': 'DATA.Value', 'weight': 'DATA.Weight', 'magazine': 'DATA.ClipSize'}


@dataclass(frozen=True)
class SourceForm:
    """One source form: category, record type, FormID, EditorID, name, model, placed count, its export record and
    the export's {spell FormID: EditorID} (a creature's abilities pick its rule)."""
    category: str
    sig: str
    form_id: int
    edid: str
    name: str
    model: str
    placed: int
    record: dict = field(compare=False, hash=False, repr=False)
    spells: dict = field(default_factory=dict, compare=False, hash=False, repr=False)


@dataclass(frozen=True)
class Current:
    """What stands in for a form: its entry (None when the converter decides or nothing does) and how (HOW)."""
    entry: object
    how: str

    @property
    def label(self) -> str:
        """How the stand-in is chosen, with the entry's layer for a table entry."""
        return f'table ({self.entry.origin})' if self.how == 'table' else HOW[self.how]

    @property
    def kind(self) -> str:
        """'mine', 'profile', 'skipped', or 'rough' (an FO4 stand-in nobody picked)."""
        if self.how == 'table' and self.entry.origin in ('user', 'profile'):
            return 'mine' if self.entry.origin == 'user' else 'profile'
        return 'skipped' if self.how == 'none' else 'rough'


def placements(export_dir: Path) -> Counter:
    """{base FormID: placed references} over the export's REFR and ACRE."""
    return Counter(int(r['NAME'], 16) for sig in ('REFR', 'ACRE') for r in export_records(export_dir, sig)
                   if r.get('NAME'))


def source_forms(export_dir: Path, category: str, placed: Counter) -> list:
    """The export's forms of `category` with an EditorID, the most placed first."""
    spells = {int(r['FormID'], 16): r.get('EditorID', '') for r in export_records(export_dir, 'SPEL')
              } if category == 'creature' else {}
    forms = [SourceForm(category, sig, int(r['FormID'], 16), r['EditorID'], r.get('FULL', ''), source_model(r),
                        placed.get(int(r['FormID'], 16), 0), r, spells)
             for sig in CATEGORY_SIGS[category] for r in export_records(export_dir, sig) if r.get('EditorID')]
    return sorted(forms, key=lambda f: (-f.placed, (f.name or f.edid).lower()))


def source_model(rec: dict) -> str:
    """A record's model: an armor's male worn (else world) model, else MODL."""
    if rec.get('Signature') == 'ARMO':
        return rec.get('Male.BipedModel.MODL') or rec.get('Male.WorldModel.MODL', '')
    return rec.get('Model.MODL', '')


def converted_mesh(form: SourceForm) -> str:
    """The Data path a build writes the form's own mesh to (creatures: their parts on the FO4 rig, as
    creatures.Creatures writes them); '' without a model."""
    if form.sig == 'CREA':
        stems = [form.record[f'NIFZ[{i}]'].lower().rsplit('.', 1)[0] for i in range(int(form.record.get('NIFZCount', 0)))]
        folder = skeleton_folder(form.model)
        return f'meshes\\{PREFIX}\\{folder}\\{"_".join(stems)}.nif' if stems and form.model else ''
    return f'meshes\\{PREFIX}\\{key(form.model)}' if form.model else ''


def current(table, form: SourceForm) -> Current:
    """What stands in for `form` under `table` (replacements.load) and its rules (module notes)."""
    if form.sig == 'CREA':
        entry, _, how = creature_entry(table, form.record, skeleton_folder(form.model), form.spells)
        return Current(entry, how)
    if form.edid in table:
        return Current(table[form.edid], 'table')
    rule = default_entry(form.record, table.rules) if form.sig in ('WEAP', 'ARMO') else None
    if rule:
        return Current(rule, 'rule')
    gun = form.sig == 'WEAP' and int(form.record.get('DNAM.FalloutAnimType', -1)) in GUN_TYPES
    return Current(None, 'gun' if gun else 'copy')


def stats(form: SourceForm) -> dict:
    """The form's compared stats from its export record (STATS), the present ones."""
    return {label: form.record[field_name] for label, field_name in STATS.items() if form.record.get(field_name)}
