"""FNV terminals (TERM) as Fallout 4 terminals, for the cell spike.

Each FNV terminal keeps its FormID. Its welcome text (DESC) is the body
text (BTXT); each menu item keeps its text (ITXT), result text (RNAM) and
conditions, and takes FO4's item type: a sub-menu opens that TERM (4), a
displayed note shows the note's text (8, UNAM), ForceTerminalBack returns
to the top level (5), Force Redraw redraws (6), anything else shows its
result (8). An item's script runs as the TERM's fragment
(script_convert.terminal_fragments). The mesh is FNV's with its screen made
FO4's (nif.terminal); the user stands where vanilla's desk terminal puts
them relative to its screen, with the template's keywords and marker
(DN054_ZekesTerminal). FNV locks the terminal on the base (difficulty,
Leveled, Unlocked); FO4 on each reference (XLOC level, as vanilla's). FNV's
looping sound (the computer hum) is not written: Fallout4.exe's furniture
loader, which terminals share (0x44B814), reads every SNAM as marker data,
so a Looping Sound SNAM ahead of the markers crashes the game on load.

See: docs/fork/fo4_pipeline.md#terminals
"""

import math
import re
import struct
from pathlib import Path

from fo4_import.base.vmad import terminal_fragments
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.say_topics import conditions_of
from fo4_import.spike.statics import terminal_assets
from script_convert.terminal_fragments import fragment_items, fragment_name
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: A terminal's converted fragment script: terminal_script_name() in the FNV namespace, then its FormID.
TERMINAL_PREFIX = 'FALLOUTNV_TM__'
#: Vanilla DN054_ZekesTerminal (TerminalOn.nif on a desk) and the fields a converted terminal copies from it.
TEMPLATE, KEPT = 0x1F2B69, (b'KSIZ', b'KWDA', b'PNAM', b'FNAM', b'MNAM', b'WBDT', b'XMRK')
#: The user's spot from the screen's centre, out and down: TerminalOn.nif's screen (0, -5.8, 79.3), template's (0, -61, 0).
REACH, BELOW = 55.2, 79.3
#: A marker's entry sides and their 3 unused bytes, as all 777 vanilla terminal markers.
ENTRY = b'\xff' * 4
#: FO4 menu item types (ANAM): sub-menu, return to top level, force redraw, display text.
SUBMENU, TOP_LEVEL, REDRAW, DISPLAY = 4, 5, 6, 8
#: FNV item flag Force Redraw; TERM DNAM flags Leveled and Unlocked; difficulty Requires Key.
FORCE_REDRAW, LEVELED, UNLOCKED, REQUIRES_KEY = 0x2, 0x1, 0x2, 5
#: FO4 XLOC: lock level per FNV difficulty step (0 to 100, as vanilla's), the level only a key opens, Leveled.
LOCK_STEP, KEY_ONLY, LEVELED_LOCK = 25, 255, 0x4
#: FNV NOTE DATA type of a text note.
TEXT_NOTE = 1
_BACK = re.compile(r'^\s*forceterminalback\b', re.I | re.M)


def marker(screen: 'tuple | None') -> bytes:
    """SNAM: the user's spot and heading before `screen` (centre, facing); the origin without a screen."""
    if screen is None:
        return pack_subrecord('SNAM', struct.pack('<4fI', 0.0, 0.0, 0.0, 0.0, 0) + ENTRY)
    centre, facing = screen[:2]
    length = math.hypot(facing[0], facing[1]) or 1.0
    fx, fy = facing[0] / length, facing[1] / length
    spot = (centre[0] + fx * REACH, centre[1] + fy * REACH, centre[2] - BELOW)
    return pack_subrecord('SNAM', struct.pack('<4fI', *spot, math.atan2(-fx, -fy) % math.tau, 0) + ENTRY)


def item_type(rec: dict, item: int, shown: bool) -> int:
    """FO4 ANAM of FNV item `item` of `rec`; `shown`: it displays a note's text."""
    if rec.get(f'Item[{item}].SubMenu'):
        return SUBMENU
    if shown:
        return DISPLAY
    if _BACK.search(rec.get(f'Item[{item}].Script') or ''):
        return TOP_LEVEL
    return REDRAW if int(rec.get(f'Item[{item}].Flags') or 0) & FORCE_REDRAW else DISPLAY


def item_conditions(rec: dict, item: int) -> dict:
    """An item's conditions as a record of their own, for conditions_of."""
    prefix = f'Item[{item}].'
    return {key[len(prefix):]: value for key, value in rec.items() if key.startswith(prefix + 'Condition[')}


def _zstr(sig: str, text: str) -> bytes:
    """A null-terminated string subrecord."""
    return pack_string_subrecord(sig, text)


class Terminals:
    """FO4 TERMs for FNV terminals, each made once (a sub-menu with the terminal that opens it)."""

    def __init__(self, builder, export_dir: Path, form_map):
        """Terminals written through `builder`; `form_map()` gives the FNV-to-FO4 forms conditions name."""
        self.builder, self.export_dir, self.form_map = builder, export_dir, form_map
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'TERM')}
        self.notes = {int(r['FormID'], 16): r for r in export_records(export_dir, 'NOTE')}
        self.made, self.looks = {}, {}
        found = next((r for r, _ in walk(builder.fo4, b'TERM') if r.form_id == TEMPLATE), None)
        self.template = {tag: data for tag, data in subrecords(found.body) if tag in KEPT}

    def term(self, fnv: int) -> 'int | None':
        """The FO4 TERM of FNV terminal `fnv`, made once; None when FNV has no such terminal."""
        if fnv not in self.made:
            rec = self.records.get(fnv)
            self.made[fnv] = self.builder.fnv_id(fnv) if rec else None
            if rec:
                self.builder.writer.add_record('TERM', self._record(self.made[fnv], rec))
                self.builder.counts['TERM'] += 1
        return self.made[fnv]

    def turn(self, ref: dict) -> float:
        """Radians `ref`'s terminal mesh is turned by (nif.terminal); else 0."""
        rec = self.records.get(int(ref['NAME'], 16), {})
        screen = self.looks.get(rec.get('Model.MODL', ''), (None, None))[1]
        return screen[2] if screen else 0.0

    def _look(self, model: str) -> tuple:
        """((FO4 model, bounds), screen) of FNV terminal mesh `model`, converted once; screen None without one."""
        if model not in self.looks:
            made = terminal_assets(self.export_dir, model, self.builder.data_dir)
            if made is not None:
                self.builder.meshes[f'{model}#terminal'] = made[0]
            self.looks[model] = made or (self.builder.mesh(model), None)
        return self.looks[model]

    def _record(self, fid: int, rec: dict) -> bytes:
        """The FO4 TERM of FNV terminal `rec` on `fid`."""
        model = rec.get('Model.MODL', '')
        (path, bounds), screen = self._look(model) if model else (('', None), None)
        bounds = bounds or tuple(int(rec.get(f'OBND.{k}', 0)) for k in ('X1', 'Y1', 'Z1', 'X2', 'Y2', 'Z2'))
        subs = _zstr('EDID', f'FNV_{rec["EditorID"]}') + self._vmad(rec)
        subs += pack_subrecord('OBND', struct.pack('<6h', *bounds)) + _zstr('FULL', rec.get('FULL', ''))
        subs += _zstr('MODL', path) if path else b''
        subs += b''.join(pack_subrecord(tag.decode(), data) for tag, data in self.template.items()
                         if tag != b'XMRK' or path)
        subs += marker(screen) + self._body(rec.get('DESC', '')) + self._items(rec)
        return pack_fo4_record('TERM', fid, 0, subs)

    @staticmethod
    def _body(text: str) -> bytes:
        """BSIZ and the body text (BTXT); count 0 without text, as 368 vanilla."""
        if not text:
            return pack_subrecord('BSIZ', struct.pack('<I', 0))
        return pack_subrecord('BSIZ', struct.pack('<I', 1)) + _zstr('BTXT', text)

    def _items(self, rec: dict) -> bytes:
        """ISIZ and the menu items whose conditions convert (counted when one does not)."""
        items = [self._item(rec, i) for i in range(max(int(rec.get('ItemCount') or 0), 0))]
        kept = [item for item in items if item is not None]
        self.builder.counts['terminal item left out (condition)'] += len(items) - len(kept)
        return pack_subrecord('ISIZ', struct.pack('<I', len(kept))) + b''.join(kept)

    def _item(self, rec: dict, item: int) -> 'bytes | None':
        """One menu item (ID item + 1); None when its conditions cannot convert."""
        conditions = conditions_of(item_conditions(rec, item), self.form_map(), self.builder.script_vars)
        if conditions is None:
            return None
        prefix, shown = f'Item[{item}].', self._shown(rec.get(f'Item[{item}].Note', ''))
        kind = item_type(rec, item, shown is not None)
        out = _zstr('ITXT', rec.get(prefix + 'Text', ''))
        out += _zstr('RNAM', rec[prefix + 'Result']) if rec.get(prefix + 'Result') else b''
        out += pack_subrecord('ANAM', bytes([kind])) + pack_subrecord('ITID', struct.pack('<H', item + 1))
        out += _zstr('UNAM', shown) if kind == DISPLAY and shown else b''
        sub = self.term(int(rec[prefix + 'SubMenu'], 16)) if kind == SUBMENU else None
        return out + (pack_subrecord('TNAM', struct.pack('<I', sub)) if sub else b'') + conditions

    def _shown(self, note: str) -> 'str | None':
        """The text a displayed FNV note shows on the terminal; None for no note, or one of another type (counted)."""
        rec = self.notes.get(int(note, 16)) if note else None
        if rec is None:
            return None
        if int(rec.get('DATA.Type', -1)) != TEXT_NOTE:
            self.builder.counts['terminal note shown left out (not text)'] += 1
            return None
        return rec.get('TNAM.Text', '')

    def _vmad(self, rec: dict) -> bytes:
        """The VMAD binding FNV terminal `rec`'s converted item scripts as its fragments; b'' without any."""
        scripts, name = self.builder.scripts, TERMINAL_PREFIX + rec['FormID'].upper()
        items = fragment_items(rec)
        if not items or not scripts.dir or not (scripts.dir / f'{name}.psc').exists():
            self.builder.counts['terminal fragments not converted'] += bool(items)
            return b''
        scripts.used.append(name)
        vmad = terminal_fragments(name, [(i + 1, fragment_name(i)) for i in items], scripts.properties(name))
        return pack_subrecord('VMAD', vmad)

    def lock_of(self, ref: dict) -> 'tuple | None':
        """(XLOC level, Leveled, password note FNV FormID or 0) of a placed FNV terminal its base locks; None for one
        it leaves open."""
        rec = self.records.get(int(ref['NAME'], 16))
        flags = int(rec.get('DNAM.Flags', 0)) if rec else UNLOCKED
        if flags & UNLOCKED:
            return None
        difficulty = int(rec.get('DNAM.Difficulty', 0))
        level = KEY_ONLY if difficulty >= REQUIRES_KEY else difficulty * LOCK_STEP
        return level, bool(flags & LEVELED), int(rec.get('PNAM', '0'), 16)

    def lock(self, ref: dict) -> bytes:
        """XLOC of a placed FNV terminal its base locks (FO4 locks the reference); b'' for one it leaves open."""
        lock = self.lock_of(ref)
        if lock is None:
            return b''
        self.builder.counts['locked terminals'] += 1
        return pack_subrecord('XLOC', struct.pack('<B3xIB3xI', lock[0], 0, LEVELED_LOCK if lock[1] else 0, 0))
