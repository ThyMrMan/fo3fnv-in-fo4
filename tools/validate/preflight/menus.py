"""The menu checks: a built plugin's dialogue menus against its links file (fo4_import.dialogue_menu), and our
movies' translation keys against the English file (fo4_import.base.translations).

CleanroomDialogue.dll lists a Player Dialogue action's option only when the links file
links it to an answer topic holding a line, so: every option of the
plugin's own menus has a link; every link names such an option and an answer
topic (the plugin's or a built master's) with a line; every skill check names
an INFO and an actor value that exist.

See: docs/fork/fo4_dialogue_menu_plan.md#converter
See: docs/fork/swf_framework.md#translations
"""

from collections import Counter
from pathlib import Path

from fo4_import.base import translations
from fo4_import.dialogue_menu import LINKS
from tools.validate.preflight.findings import Finding
from tools.validate.preflight.plugin_index import load_plugin, u32

#: A Player Dialogue action's four player topics, in record order.
PLAYER_TOPICS = ('PTOP', 'NTOP', 'NETO', 'QTOP')
#: Rows listed per finding.
SAMPLES = 5
#: Each translation fault's severity: a missing key shows raw in game; an unused one is only clutter.
TRANSLATION_SEVERITY = {'key missing from en.txt': 'error', 'en.txt key no movie uses': 'review',
                        'key only in another language': 'error'}


def player_topics(index) -> set:
    """FormIDs of every Player Dialogue action's player topics in `index`'s scenes."""
    return {u32(sub.data) for scene in index.by_type['SCEN'] for sub in scene.subrecords
            if sub.type in PLAYER_TOPICS and len(sub.data) == 4}


def read_links(path: Path, names: list) -> tuple:
    """([(option, answer)], [(INFO, actor value)]) of the links file `path`, as FormIDs in the load order `names`
    (lower case); a FormID whose plugin is not in `names` is None."""
    def fid(plugin: str, oid: str) -> 'int | None':
        """FormID of `plugin`'s object id `oid` (hex)."""
        return names.index(plugin.lower()) << 24 | int(oid, 16) if plugin.lower() in names else None
    links, checks = [], []
    for line in path.read_text(encoding='utf-8').splitlines() if path.is_file() else ():
        f = line.split('\t')
        if line.startswith('#') or len(f) < 4:
            continue
        (checks if len(f) == 5 else links).append((fid(f[0], f[1]), fid(f[2], f[3])))
    return links, checks


class Records:
    """The built plugin's records and, read when a link needs them, its built masters' (FormIDs in its order)."""

    def __init__(self, index, masters: list):
        """`index` the plugin's, `masters` its built masters' paths."""
        self.index, self.paths, self.loaded = index, {Path(p).name.lower(): Path(p) for p in masters}, {}
        self.counts = {None: Counter(info.parent_dial for info in index.by_type['INFO'])}

    def _master(self, fid: int) -> tuple:
        """(the master index holding `fid`, `fid` in its numbering), or (None, None)."""
        name = self.index.masters[fid >> 24].lower()
        if name not in self.loaded:
            self.loaded[name] = load_plugin(self.paths[name]) if name in self.paths else None
            master = self.loaded[name]
            self.counts[name] = Counter(info.parent_dial for info in master.by_type['INFO']) if master else Counter()
        master = self.loaded[name]
        return (master, len(master.masters) << 24 | fid & 0xFFFFFF) if master else (None, None)

    def get(self, fid: int):
        """Record `fid`: the plugin's, else its master's own; None when neither has it."""
        if fid in self.index.by_fid or fid >> 24 >= len(self.index.masters):
            return self.index.by_fid.get(fid)
        master, local = self._master(fid)
        return master.by_fid.get(local) if master else None

    def lines(self, dial: int) -> int:
        """How many INFOs answer topic `dial` holds (the plugin's and its master's)."""
        own = self.counts[None][dial]
        if own or dial >> 24 >= len(self.index.masters):
            return own
        master, local = self._master(dial)
        return self.counts[self.index.masters[dial >> 24].lower()][local] if master else 0


def link_rows(records: Records, options: set, links: list, checks: list) -> dict:
    """{kind: rows} of the links file's faults against the plugin's menu `options`."""
    linked = {option for option, _ in links}

    def kind(fid: 'int | None', sig: str) -> bool:
        """Whether `fid` is a record of type `sig`."""
        return fid is not None and getattr(records.get(fid), 'type', None) == sig
    return {'option without a link': [f'{o:08X}' for o in sorted(options - linked)],
            'link from no menu option': [f'{o:08X}' if o is not None else '?' for o, _ in links if o not in options],
            'link to no answer topic': [f'{o:08X} -> {a:08X}' if a is not None else f'{o:08X} -> ?'
                                        for o, a in links if not kind(a, 'DIAL')],
            'answer topic with no line': sorted({f'{a:08X}' for o, a in links if kind(a, 'DIAL')
                                                 and not records.lines(a)}),
            'skill check on a missing form': [f'{i}, {v}' for i, v in checks
                                              if not kind(i, 'INFO') or not kind(v, 'AVIF')]}


def audit(game: str, index, plugin: Path, masters: list) -> list:
    """One error per kind of links fault in built `plugin` (masters: its built masters' paths)."""
    topics = player_topics(index)
    options = {info.form_id for info in index.by_type['INFO'] if info.parent_dial in topics and index.is_own(
        info.form_id)}
    path = Path(plugin).parent / LINKS / f'{Path(plugin).stem}.txt'
    if options and not path.is_file():
        return [Finding('dialogue', f'dialogue|{game}|menu|no links file', 'error',
                        f'{len(options)} menu options but no {path.name}: F3NV.dll lists none of them', ())]
    names = [m.lower() for m in index.masters] + [Path(plugin).name.lower()]
    found = link_rows(Records(index, masters), options, *read_links(path, names))
    return [Finding('dialogue', f'dialogue|{game}|menu|{kind}', 'error', f'{len(rows)} {kind} in {path.name}',
                    tuple(rows[:SAMPLES])) for kind, rows in found.items() if rows]


def translation_audit(game: str) -> list:
    """One finding per kind of translation fault in our movies' sources."""
    return [Finding('menus', f'menus|{game}|translation|{kind}', TRANSLATION_SEVERITY[kind],
                    f'{len(rows)} {kind}', tuple(rows[:SAMPLES]))
            for kind, rows in translations.check().items() if rows]
