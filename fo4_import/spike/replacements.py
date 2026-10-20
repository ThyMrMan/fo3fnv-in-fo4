"""The replacement table: which record stands in for each FNV item, and how.

The defaults are `fo4_import/data/item_replacements.json`; a user file of
the same shape is laid over them entry by entry. An entry is
`{FNV EditorID: {"use": "Plugin|EditorID", "as": mode, "mods": [...]}}`:

- `item`: the target record itself, with its own name, stats and model;
- `stats`: a copy of the target with FNV's name and stats;
- `fnv`: a copy showing FNV's own mesh (melee weapons, headgear; guns on
  the FO4 gun spike.gun_choice picks, experimental).

`mods` (OMOD EditorIDs) replace a gun's default parts at the same attach
points. Fallout4.esm targets take any mode. Another plugin's record is
used only as an `item`: copying it would mean renumbering every FormID in
it. That plugin becomes a master of the converted plugin, appended, so only
our own records' top FormID byte changes; it is read from the game's Data
folder or one of `plugin_dirs` (MO2 mod folders).

See: docs/fork/fo4_replacements.md
"""

import json
import struct
from dataclasses import dataclass
from pathlib import Path

from fo4_import.base.install import FALLOUT4_DIR
from tes5_import.base.tes5_reader import first_sub, subrecords, walk

BASE = 'Fallout4.esm'
MODES = ('item', 'stats', 'fnv')
DEFAULTS = Path(__file__).resolve().parents[1] / 'data' / 'item_replacements.json'
#: Record types a replacement may name.
ITEM_TYPES = (b'WEAP', b'ARMO', b'ALCH', b'AMMO', b'MISC', b'BOOK', b'KEYM', b'NOTE')
#: A FO4 plugin's file header is 24 bytes; its masters are MAST subrecords.
HEADER = 24


@dataclass(frozen=True)
class Replacement:
    """One entry: the target's plugin and EditorID, its mode, and the gun parts it sets."""
    plugin: str
    edid: str
    mode: str
    mods: tuple = ()

    @property
    def base(self) -> bool:
        """Whether the target is Fallout4.esm's."""
        return self.plugin.lower() == BASE.lower()


def load(user: 'Path | None' = None) -> dict:
    """{FNV EditorID: Replacement}: the defaults with `user`'s entries laid over them."""
    table = json.loads(DEFAULTS.read_text(encoding='utf-8'))
    if user:
        table.update(json.loads(Path(user).read_text(encoding='utf-8')))
    out = {}
    for fnv, entry in table.items():
        if fnv.startswith('_'):
            continue
        plugin, _, edid = entry['use'].partition('|')
        made = Replacement(plugin, edid, entry.get('as', 'item'), tuple(entry.get('mods', ())))
        if made.mode not in MODES or not edid or (not made.base and made.mode != 'item'):
            raise ValueError(f'replacement {fnv}: {entry} (another plugin\'s record can only be an item)')
        out[fnv] = made
    return out


def extra_masters(table: dict) -> list:
    """The plugins other than Fallout4.esm the table names, sorted: masters to append."""
    return sorted({r.plugin for r in table.values() if not r.base}, key=str.lower)


def plugin_masters(data: bytes) -> list:
    """A plugin's master file names, from its file header."""
    size = struct.unpack_from('<I', data, 4)[0]
    return [body.rstrip(b'\0').decode('cp1252') for sig, body in subrecords(data[HEADER:HEADER + size])
            if sig == b'MAST']


def _find(plugin: str, dirs: list) -> Path:
    """`plugin`'s file in the game's Data folder or one of `dirs`."""
    for folder in [FALLOUT4_DIR / 'Data', *map(Path, dirs)]:
        if (folder / plugin).exists():
            return folder / plugin
    raise FileNotFoundError(f'{plugin} not in the Data folder or {dirs}')


def _ours(fid: int, theirs: list, plugin: str, masters: list) -> int:
    """A FormID of `plugin` (masters `theirs`) in our numbering, `masters` ours."""
    index = fid >> 24
    owner = plugin if index >= len(theirs) else theirs[index]
    lower = [m.lower() for m in masters]
    if owner.lower() not in lower:
        raise ValueError(f'{plugin} record {fid:08X} belongs to {owner}, not a master of ours')
    return lower.index(owner.lower()) << 24 | fid & 0xFFFFFF


def items(table: dict, fo4: bytes, masters: list, dirs: tuple = ()) -> dict:
    """{FNV EditorID: FormID in our numbering} of the table's `item` entries, found by EditorID."""
    out = {}
    for plugin in {r.plugin for r in table.values() if r.mode == 'item'}:
        edids = {}
        for fnv, r in table.items():
            if r.mode == 'item' and r.plugin == plugin:
                edids.setdefault(r.edid.lower(), []).append(fnv)
        base = plugin.lower() == BASE.lower()
        data = fo4 if base else _find(plugin, dirs).read_bytes()
        theirs = [] if base else plugin_masters(data)
        for rec, _ in walk(data, *ITEM_TYPES):
            for fnv in edids.get((first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252').lower(), ()):
                out[fnv] = rec.form_id if base else _ours(rec.form_id, theirs, plugin, masters)
    return out
