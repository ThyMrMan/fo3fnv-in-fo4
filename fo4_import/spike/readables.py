"""FNV books, notes and terminals as their Fallout 4 records, placed or given, for the cell spike.

A book is a FO4 BOOK with FNV's mesh, name, text, value, weight and its
converted script; Can't Be Taken is the same flag in both games. A skill
book (DATA Teaches) also runs F3NV_SkillBook: reading it raises FNV's skill
(the helper plugin's actor value) by fBookPerkBonus and uses the copy up,
as FNV does per copy. FO4's own teach-on-read (DNAM Add Perk, on 113 of
vanilla's 327 books; Advance Actor Value and Add Spell on none) adds a perk
once per book record, so it cannot count copies. A text note is a paper
note (BOOK) with FNV's mesh when it has one; an image note a paper note
showing its image (an img tag, as vanilla's 2 notes with one); a voice note
a holotape (holotapes.py); a terminal a TERM (terminals.py). FNV's sound
notes have no FO4 counterpart vanilla uses (no sound holotapes) and are left
out. Each record keeps its FNV FormID.

See: docs/fork/fo4_pipeline.md#readables
"""

from fo4_import.base.vmad import object_scripts
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.nif.convert_static import fo4_texture, texture_source
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.conditions import fnv_av_name
from fo4_import.spike.holotapes import FNV_VOICE, Holotapes
from fo4_import.spike.say_topics import actor_values
from fo4_import.spike.statics import copy_texture
from fo4_import.spike.terminals import TEXT_NOTE, Terminals

#: FNV NOTE DATA type of an image note.
IMAGE_NOTE = 2
#: FNV skill actor values follow this index (Barter is 32; BOOK DATA Teaches is the skill's place among them).
FIRST_SKILL = 32
#: The FO4 script a skill book runs, and FNV's book skill bonus setting (3 points, as FNV's in-game count).
SKILL_SCRIPT, SKILL_SETTING = 'F3NV_SkillBook', 'fBookPerkBonus'
#: BOOK DNAM flag Can't Be Taken (FNV DATA flag 0x2, FO4 DNAM 0x2).
CANT_BE_TAKEN = 0x2
PLAYER = 0x14


def _bounds(rec: dict) -> tuple:
    """An export record's OBND."""
    return tuple(int(rec.get(f'OBND.{k}', 0)) for k in ('X1', 'Y1', 'Z1', 'X2', 'Y2', 'Z2'))


class Readables:
    """The FO4 records of FNV books, notes and terminals, each made once whether placed or given."""

    def __init__(self, builder):
        """Readables written through cell builder `builder`."""
        self.builder, self.made, self.forms = builder, {}, None
        export_dir = builder.export_dir
        self.terminals = Terminals(builder, export_dir, self.form_map)
        self.holotapes = Holotapes(builder, export_dir, self.form_map)
        settings = {r.get('EditorID'): r for r in export_records(export_dir, 'GMST')}
        self.points = float(settings.get(SKILL_SETTING, {}).get('DATA.Value', 3.0))

    def base(self, fnv: int, sig: str, rec: dict) -> 'int | None':
        """The FO4 record of FNV book, note or terminal `rec` (type `sig`), made once; None when not converted."""
        if fnv not in self.made:
            self.made[fnv] = None
            maker = {'TERM': lambda: self.terminals.term(fnv), 'BOOK': lambda: self._book(rec),
                     'NOTE': lambda: self._note(rec)}.get(sig)
            self.made[fnv] = maker() if maker else None
        return self.made[fnv]

    def lock(self, ref: dict) -> bytes:
        """The XLOC a placed FNV terminal takes from its base (terminals.lock)."""
        return self.terminals.lock(ref)

    def form_map(self) -> dict:
        """FNV to FO4 forms for conditions, gathered once: items, actor values, globals, factions, actors, the
        player, and the quests and references the scripts know by name."""
        if self.forms is None:
            b, named = self.builder, self.builder.scripts.named
            built = {int(r['FormID'], 16): named[r['EditorID']] for sig in ('QUST', 'REFR')
                     for r in export_records(b.export_dir, sig) if r.get('EditorID') in named}
            self.forms = {**b.items.shared, **actor_values(b.scripts.helper_index), **b.globals, **b.factions,
                          **b.actor_refs, PLAYER: PLAYER, **built}
        return self.forms

    def _look(self, rec: dict, default: tuple = (R.NOTE_MODEL, R.NOTE_BOUNDS)) -> tuple:
        """(model, bounds) of FNV `rec`'s mesh; `default` without one."""
        if not rec.get('Model.MODL'):
            return default
        model, bounds = self.builder.mesh(rec['Model.MODL'])
        return model, bounds or _bounds(rec)

    def _write(self, rec: dict, record_of) -> int:
        """Add the BOOK `record_of(FormID)` made from FNV `rec`; its FormID (FNV's)."""
        fid = self.builder.fnv_id(rec['FormID'])
        self.builder.writer.add_record('BOOK', record_of(fid))
        self.builder.counts['BOOK'] += 1
        return fid

    def _note(self, rec: dict) -> 'int | None':
        """A text or image note as a paper note, a voice note as a holotape; None for a sound note (counted)."""
        kind = int(rec.get('DATA.Type', -1))
        if kind == FNV_VOICE:
            return self.holotapes.holotape(rec)
        if kind not in (TEXT_NOTE, IMAGE_NOTE):
            self.builder.counts['NOTE left out (sound note)'] += 1
            return None
        text = rec.get('TNAM.Text', '').replace(chr(13) + chr(10), chr(10)) if kind == TEXT_NOTE else self._image(rec)
        return self._write(rec, lambda fid: R.pack_book(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), text,
                                                         self._look(rec)))

    def _image(self, rec: dict) -> str:
        """An image note's text: its FNV image (copied into the data folder) in an img tag."""
        source = texture_source(rec.get('XNAM', ''))
        copy_texture(self.builder.export_dir, self.builder.data_dir, source)
        return f"<p align='center'><img src='img://Textures/{fo4_texture(source).replace(chr(92), '/')}'></p>"

    def _book(self, rec: dict) -> int:
        """An FNV book: its mesh, name, text, value, weight, script, Can't Be Taken, and its skill (SKILL_SCRIPT)."""
        dnam = CANT_BE_TAKEN if int(rec.get('DATA.Flags', 0)) & CANT_BE_TAKEN else 0
        worth = (int(rec.get('DATA.Value', 0)), float(rec.get('DATA.Weight', 0.0)))
        vmad = self._book_scripts(rec)
        return self._write(rec, lambda fid: R.pack_book(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''),
                                                         rec.get('DESC', ''), self._look(rec), worth, vmad, dnam))

    def _book_scripts(self, rec: dict) -> bytes:
        """The VMAD of a book's converted FNV script and, for a skill book, SKILL_SCRIPT; b'' with neither."""
        scripts, entries = self.builder.scripts, []
        name = scripts.name(int(rec['SCRI'], 16)) if 'SCRI' in rec else None
        if name:
            scripts.used.append(name)
            entries.append((name, scripts.properties(name), {}))
        skill = int(rec.get('DATA.Teaches', -1))
        av = actor_value_form(fnv_av_name(FIRST_SKILL + skill), scripts.helper_index) if 0 <= skill < 0x80 else None
        if av is not None:
            entries.append((SKILL_SCRIPT, {'Skill': av}, {'Points': ('float', self.points)}))
            self.builder.counts['skill books'] += 1
        return object_scripts(entries) if entries else b''
