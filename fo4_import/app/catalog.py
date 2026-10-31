"""The record catalog: what each installed FO4 plugin offers as a replacement, by category, and what to preview.

Per record: EditorID, name (a localized plugin's from its strings files, read through fo4_import.app.files), its
own model, the stats the Replacements screen compares (value, weight, damage, armor rating, magazine, ammo), the
master it overrides (`owner`), and its links to other records as catalog-wide keys ('owner plugin|low 24 bits',
lowercase plugin): a gun's default parts, an armor's addons, an NPC's skin, race and template, a leveled list's
entries. Object mods, armor addons and races are listed too, under categories no screen shows, so preview_models()
can follow links across plugins (a mod's NPC on a vanilla race, an armor whose addon is a DLC's). Nothing is
cached between runs: a scan is fast.

See: docs/fork/fo4_gui.md#replacements-screen
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path

from fo4_import.base.strings import KINDS, parse
from fo4_import.spike.actor_data import ACBS_TEMPLATE
from fo4_import.spike.equipment import DNAM_AMMO, DNAM_CAPACITY, DNAM_DAMAGE, DNAM_VALUE, DNAM_WEIGHT
from fo4_import.spike.gun_choice import OBTS_DEFAULT, includes
from fo4_import.base.install import masters_of
from fo4_import.spike.replacements import BASE, DLC
from tes5_import.base.tes5_reader import subrecords, walk

#: Replacement table category -> the record types it lists (fo4_import.spike.replacements.CATEGORIES).
CATEGORY_TYPES = {'weapon': (b'WEAP',), 'armor': (b'ARMO',), 'consumable': (b'ALCH',), 'ammo': (b'AMMO',),
                  'misc': (b'MISC', b'BOOK', b'KEYM', b'NOTE'), 'creature': (b'NPC_', b'LVLN')}
#: Record types listed only so links can be followed, under categories no screen shows.
LINKED = {b'OMOD': 'part', b'ARMA': 'addon', b'RACE': 'race'}
PARTS = LINKED[b'OMOD']
#: Record types whose model is their male third-person model (MOD2), not MODL.
MOD2_TYPES = (b'ARMO', b'ARMA')
#: TES4 header flag: FULL and DESC hold string IDs into the plugin's strings files.
LOCALIZED = 0x80
#: FO4 ACBS template flag taking traits (race, skin) from the template.
USE_TRAITS = 0x1
#: Plugins shown together as "Fallout 4 + DLC".
BASE_GAME = (BASE, *DLC)
#: Links followed at most in a row (templates of templates, lists of lists), against loops.
MAX_DEPTH = 8


# ---------------------------------------------------------------------------
#  Entries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Entry:
    """One record a replacement may name (`use`: 'Plugin|EditorID'), with its links (catalog keys)."""
    plugin: str
    form_id: int
    sig: str
    edid: str
    name: str
    category: str
    model: str = ''
    owner: str = ''
    stats: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)

    @property
    def use(self) -> str:
        """The replacement table's `use` for this record."""
        return f'{self.plugin}|{self.edid}'

    @property
    def key(self) -> str:
        """This record's catalog key: owner plugin (lowercase)|low 24 bits."""
        return f'{(self.owner or self.plugin).lower()}|{self.form_id & 0xFFFFFF:06X}'


# ---------------------------------------------------------------------------
#  Scanning
# ---------------------------------------------------------------------------

def scan(path: Path, files=None, language: str = 'en') -> list:
    """Every listed record of the plugin at `path` (Entries); names of a localized plugin through `files`."""
    data = Path(path).read_bytes()
    localized = bool(struct.unpack_from('<I', data, 8)[0] & LOCALIZED)
    names = plugin_strings(files, Path(path).stem, language) if localized and files else {}
    kinds = {sig: cat for cat, sigs in CATEGORY_TYPES.items() for sig in sigs} | LINKED
    plugin = _Plugin(Path(path).name, masters_of(data), localized, names)
    return [plugin.entry(rec, kinds[rec.sig]) for rec, _ in walk(data, *kinds) if not rec.deleted
            and first_subs(rec.body).get(b'EDID')]


@dataclass
class _Plugin:
    """What a scan knows of one plugin: its name, masters and localized names."""
    name: str
    masters: list
    localized: bool
    names: dict

    def owner(self, fid: int) -> str:
        """The master a FormID of this plugin belongs to ('' for the plugin's own records)."""
        index = fid >> 24
        return self.masters[index] if index < len(self.masters) else ''

    def key(self, fid: int) -> str:
        """The catalog key of a FormID as this plugin writes it."""
        return f'{(self.owner(fid) or self.name).lower()}|{fid & 0xFFFFFF:06X}'

    def entry(self, rec, category: str) -> Entry:
        """The Entry of record `rec` under `category`."""
        subs = first_subs(rec.body)
        return Entry(self.name, rec.form_id, rec.sig.decode(), _text(subs[b'EDID']),
                     _name(subs.get(b'FULL'), self.localized, self.names), category,
                     _text(subs.get(b'MOD2' if rec.sig in MOD2_TYPES else b'MODL')), self.owner(rec.form_id),
                     stats(rec.sig, subs), self.links(rec, subs))

    def links(self, rec, subs: dict) -> dict:
        """The record's links to other records, as catalog keys, by kind."""
        every = subrecords(rec.body)
        if rec.sig == b'WEAP':
            return {'parts': self.parts(every)}
        if rec.sig == b'ARMO':
            return {'addons': tuple(self.key(_form(d)) for tag, d in every if tag == b'MODL' and len(d) >= 4)}
        if rec.sig == b'LVLN':
            return {'entries': tuple(self.key(struct.unpack_from('<I', d, 4)[0]) for tag, d in every
                                     if tag == b'LVLO' and len(d) >= 8)}
        if rec.sig == b'RACE':
            return {'skin': self.key(_form(subs[b'WNAM']))} if _form(subs.get(b'WNAM')) else {}
        if rec.sig == b'ARMA':
            return {'races': tuple(self.key(_form(d)) for tag, d in every if tag in (b'RNAM', b'MODL') and len(d) >= 4)}
        if rec.sig == b'NPC_':
            return {**self.npc_links(subs), 'parts': self.parts(every)}
        return {}

    def parts(self, every: list) -> tuple:
        """Default (else first) combination's object mods, as catalog keys."""
        combos = [body for tag, body in every if tag == b'OBTS']
        chosen = next((body for body in combos if body[OBTS_DEFAULT]), combos[0] if combos else None)
        return tuple(self.key(fid) for fid in (includes(chosen) if chosen else []))

    def npc_links(self, subs: dict) -> dict:
        """An NPC's skin, race and template keys, and whether it takes its traits from the template."""
        acbs = subs.get(b'ACBS', b'')
        flags = struct.unpack_from('<H', acbs, ACBS_TEMPLATE)[0] if len(acbs) >= ACBS_TEMPLATE + 2 else 0
        made = {name: self.key(_form(subs[tag])) for name, tag in (('skin', b'WNAM'), ('race', b'RNAM'),
                                                                   ('template', b'TPLT')) if _form(subs.get(tag))}
        return {**made, 'traits': bool(flags & USE_TRAITS) and 'template' in made}


def stats(sig: bytes, subs: dict) -> dict:
    """The stats compared on the Replacements screen, from one record's subrecords {tag: data}."""
    out = {}
    if sig == b'WEAP' and len(subs.get(b'DNAM', b'')) >= DNAM_DAMAGE + 2:
        d = subs[b'DNAM']
        out = {'damage': struct.unpack_from('<H', d, DNAM_DAMAGE)[0], 'value': struct.unpack_from('<I', d, DNAM_VALUE)[0],
               'weight': round(struct.unpack_from('<f', d, DNAM_WEIGHT)[0], 3),
               'magazine': struct.unpack_from('<H', d, DNAM_CAPACITY)[0],
               'ammo': f"{struct.unpack_from('<I', d, DNAM_AMMO)[0]:08X}"}
    elif sig in (b'ARMO', b'AMMO', b'MISC', b'KEYM') and len(subs.get(b'DATA', b'')) >= 8:
        value, weight = struct.unpack_from('<if', subs[b'DATA'])
        out = {'value': value, 'weight': round(weight, 3)}
    elif sig == b'ALCH' and len(subs.get(b'DATA', b'')) >= 4:
        out = {'weight': round(struct.unpack_from('<f', subs[b'DATA'])[0], 3)}
        out.update({'value': struct.unpack_from('<i', subs[b'ENIT'])[0]} if len(subs.get(b'ENIT', b'')) >= 4 else {})
    if sig == b'ARMO' and len(subs.get(b'FNAM', b'')) >= 2:
        out['armor rating'] = struct.unpack_from('<H', subs[b'FNAM'])[0]
    if sig == b'AMMO' and len(subs.get(b'DNAM', b'')) >= 12:
        out['damage'] = round(struct.unpack_from('<f', subs[b'DNAM'], 8)[0], 3)
    return out


def first_subs(body: bytes) -> dict:
    """{tag: data} of a record's subrecords, the FIRST of each tag: object templates (OBTE) repeat FULL and others."""
    out = {}
    for tag, data in subrecords(body):
        out.setdefault(tag, data)
    return out


def plugin_strings(files, stem: str, language: str = 'en') -> dict:
    """{string ID: text bytes} of a localized plugin's strings files, as `files` finds them (loose or archived)."""
    out = {}
    for ext, sized in KINDS:
        raw = files.read(f'strings\\{stem}_{language}.{ext}')
        out.update(parse(raw, sized) if raw else {})
    return out


def _form(data: 'bytes | None') -> int:
    """A FormID subrecord's value (0 without one)."""
    return struct.unpack_from('<I', data)[0] if data and len(data) >= 4 else 0


def _text(data: 'bytes | None') -> str:
    """A NUL-ended cp1252 string subrecord as text ('' without one)."""
    return (data or b'').split(b'\0', 1)[0].decode('cp1252', errors='replace')


def _name(full: 'bytes | None', localized: bool, names: dict) -> str:
    """A FULL subrecord as text: a localized plugin's is a string ID into `names`."""
    if localized and full and len(full) >= 4:
        return names.get(struct.unpack_from('<I', full)[0], b'').decode('cp1252', errors='replace')
    return _text(full)


# ---------------------------------------------------------------------------
#  The catalog
# ---------------------------------------------------------------------------

def catalog(plugins: dict, files=None, language: str = 'en') -> dict:
    """{plugin name: [Entry]} of `plugins` {name: path} (core.mod_sources.plugins)."""
    return {path.name: scan(path, files, language) for path in plugins.values()}


def index(found: dict) -> dict:
    """{catalog key: Entry} over every plugin in `found`; for a record several plugins carry, the first found."""
    out = {}
    for entries in found.values():
        for entry in entries:
            out.setdefault(entry.key, entry)
    return out


def in_category(found: dict, category: str, plugins: 'tuple | None' = None) -> list:
    """The Entries of `category` from `found` (catalog()), only `plugins`' when given, sorted by name."""
    wanted = {p.lower() for p in plugins} if plugins else None
    out = [e for name, entries in found.items() if wanted is None or name.lower() in wanted
           for e in entries if e.category == category]
    return sorted(out, key=lambda e: (e.name or e.edid).lower())


# ---------------------------------------------------------------------------
#  What to preview
# ---------------------------------------------------------------------------

def preview_models(entry: Entry, known: dict, depth: int = 0) -> tuple:
    """(the models previewing `entry` (paths under Meshes), why there are none or ''), its links followed across
    plugins through `known` (index()): a gun's parts, an armor's addon, an NPC's skin, race or template, a leveled
    list's first entry with a model."""
    if depth > MAX_DEPTH:
        return [], 'links go round in a loop'
    if entry.sig == 'WEAP':
        parts = _part_models(entry, known)
        if parts or entry.model:
            return [entry.model, *parts], ''
        return [], "neither the weapon nor its default parts have a mesh"
    if entry.sig == 'ARMO':
        return _armor(entry, known)
    if entry.sig == 'NPC_':
        return _npc(entry, known, depth)
    if entry.sig == 'LVLN':
        return _leveled(entry, known, depth)
    return ([entry.model], '') if entry.model else ([], f'this {entry.sig} record has no model')


def _armor(entry: Entry, known: dict) -> tuple:
    """An armor's first addon with a worn model, else its own (world) model."""
    worn = next((known[k].model for k in entry.links.get('addons', ()) if k in known and known[k].model), '')
    if worn or entry.model:
        return [worn or entry.model], ''
    missing = [k for k in entry.links.get('addons', ()) if k not in known]
    return [], (f'its armor addon {missing[0]} is not in any installed plugin' if missing
                else 'neither the armor nor its addons have a model')


def _body(skin: Entry, race: str, known: dict) -> list:
    """A skin's addon models made for `race` (torso, hands, feet), else _armor()'s."""
    addons = [known[k] for k in skin.links.get('addons', ()) if k in known and known[k].model]
    for_race = list(dict.fromkeys(a.model for a in addons if race and race in a.links.get('races', ())))
    return for_race or _armor(skin, known)[0]


def _part_models(entry: Entry, known: dict) -> list:
    """The meshes of an entry's default object mods (gun or robot parts)."""
    return [known[k].model for k in entry.links.get('parts', ()) if k in known and known[k].model]


def _npc(entry: Entry, known: dict, depth: int) -> tuple:
    """An NPC's body: from its template when it takes its traits from it, else its object mods (a robot's parts),
    else its skin, else its race's skin, else its template's."""
    links, template = entry.links, known.get(entry.links.get('template', ''))
    if links.get('traits') and template is not None:
        return preview_models(template, known, depth + 1)
    if _part_models(entry, known):
        return _part_models(entry, known), ''
    race = known.get(links.get('race', ''))
    for skin_key in (links.get('skin'), race.links.get('skin') if race else None):
        skin = known.get(skin_key or '')
        body = _body(skin, links.get('race', ''), known) if skin is not None else []
        if body:
            return body, ''
    if template is not None:
        return preview_models(template, known, depth + 1)
    if links.get('template') and links.get('traits'):
        return [], f"its template {links['template']} is not in any installed plugin"
    return [], 'no skin is found for this NPC or its race in the installed plugins'


def _leveled(entry: Entry, known: dict, depth: int) -> tuple:
    """A leveled list's first entry that previews."""
    entries = entry.links.get('entries', ())
    if not entries:
        return [], 'this leveled list has no entries'
    for key in entries:
        if key in known:
            models, _ = preview_models(known[key], known, depth + 1)
            if models:
                return models, ''
    return [], 'none of the leveled list\'s entries has a model in the installed plugins'
