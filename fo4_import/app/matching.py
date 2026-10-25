"""Suggested replacements by name: each source form matched to the installed records of its category with the same
name, or whose EditorID is the form's after at most a short prefix (ports often keep the original EditorID behind
one: Project Mojave's 00DCWeap556mmPistol).

Names are compared lowercase, letters and digits only; an EditorID prefix counts only when it is a port's
(PORT_PREFIX: digits, underscores, DC, DLC04, FNV...), so NukaCola does not match 00DCRumNukaCola. Records that
override another plugin's are left out: the original is matched instead, so no needless master is added. When
several records match, the pick prefers name and EditorID together over EditorID alone over name alone (many items
share a name), then a mod's record over the base game's, then the plugin that wins in the user's mod order; the
others are kept so the screen can show "1 of N". A suggestion equal to the current stand-in is left out. Nothing is
written here: the screen asks before accepting.

See: docs/fork/fo4_gui.md#replacements-screen
"""

import re
from dataclasses import dataclass

from fo4_import.app.catalog import BASE_GAME

#: Longest EditorID prefix a port puts before the original (00DC, 00DCDLC04, FNV_...).
MAX_PREFIX = 12
#: What a port's EditorID prefix is made of (lowercase).
PORT_PREFIX = re.compile(r'(?:\d+|_|dc|dlc\d*|fnv|nv|fo3|cw|pm)*')
#: Shortest EditorID matched by its ending, so short ones (Gun, Hat) do not match everything.
MIN_EDID = 5
#: How a record matched, strongest first, with its score.
BOTH, EDITOR_ID, NAME = 'name and EditorID', 'EditorID', 'name'
SCORES = {BOTH: 3, EDITOR_ID: 2, NAME: 1}


@dataclass(frozen=True)
class Match:
    """A suggestion: the picked record, how it matched (SCORES), and the other candidates."""
    entry: object
    how: str
    others: tuple = ()

    @property
    def count(self) -> int:
        """How many records matched."""
        return 1 + len(self.others)

    @property
    def label(self) -> str:
        """Name (else EditorID), plugin, "1 of N" and how, as the table shows it."""
        extra = [f'1 of {self.count}'] if self.others else []
        extra += [f'by {self.how}'] if self.how != BOTH else []
        return f"{self.entry.name or self.entry.edid} ({', '.join([self.entry.plugin, *extra])})"


def normalize(text: str) -> str:
    """`text` lowercase, letters and digits only."""
    return re.sub(r'[^0-9a-z]', '', (text or '').lower())


class Matcher:
    """Indexes one category's installed records by name and EditorID ending, then suggests per form."""

    def __init__(self, entries: list, plugin_order: list):
        """Records `entries` (catalog Entries of one category); `plugin_order` lists plugins, the winning first."""
        self.rank = {name.lower(): i for i, name in enumerate(plugin_order)}
        self.base = {p.lower() for p in BASE_GAME}
        self.by_name, self.by_edid = {}, {}
        for entry in (e for e in entries if not e.owner):
            if normalize(entry.name):
                self.by_name.setdefault(normalize(entry.name), []).append(entry)
            edid = entry.edid.lower()
            for start in range(0, min(MAX_PREFIX, len(edid) - MIN_EDID) + 1):
                if PORT_PREFIX.fullmatch(edid[:start]):
                    self.by_edid.setdefault(edid[start:], []).append(entry)

    def suggest(self, form, current=None) -> 'Match | None':
        """The suggestion for source `form` (standins.SourceForm), or None; `current` is its stand-in entry."""
        named = {id(e): e for e in self.by_name.get(normalize(form.name), [])} if normalize(form.name) else {}
        by_edid = {id(e): e for e in self.by_edid.get(form.edid.lower(), [])} if len(form.edid) >= MIN_EDID else {}
        found = [(e, BOTH if i in named and i in by_edid else NAME if i in named else EDITOR_ID)
                 for i, e in {**named, **by_edid}.items()]
        found = [(e, how) for e, how in found
                 if not current or (e.plugin.lower(), e.edid.lower()) != (current.plugin.lower(), current.edid.lower())]
        if not found:
            return None
        found.sort(key=lambda candidate: self._preference(candidate, form.edid))
        return Match(found[0][0], found[0][1], tuple(e for e, _ in found[1:]))

    def _preference(self, candidate: tuple, edid: str) -> tuple:
        """Sort key: strongest match, then mods first, then the shortest EditorID prefix, then the winning plugin."""
        entry, how = candidate
        prefix = len(entry.edid) - len(edid) if how != NAME else 0
        return (-SCORES[how], entry.plugin.lower() in self.base, prefix,
                self.rank.get(entry.plugin.lower(), len(self.rank)), entry.edid.lower())
