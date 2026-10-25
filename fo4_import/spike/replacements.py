"""The replacement table: which record stands in for each FNV/FO3 form, and how.

Three layers, each laid over the one before entry by entry: the defaults
(`fo4_import/data/replacements.json`), a profile (`--profile`, a name in
`fo4_import/data/profiles/` or a path), then the user's file
(`--replacements`). Entries sit under a category (CATEGORIES) keyed by the
source EditorID: `{"use": "Plugin|EditorID", "as": mode, "mods": [...]}`:

- `item`: the target record itself, with its own name, stats and model;
- `stats`: a copy of the target with the source's name and stats;
- `fnv`: a copy showing the source's own mesh.

`_rules` says what forms the table leaves out get: creatures by skeleton
folder, NPC bodies, armor by biped slot, melee weapons by animation type.

Fallout4.esm targets take any mode. Another plugin's record (a DLC's, a
mod's) is used only as an `item`: copying it would mean renumbering every
FormID in it. That plugin becomes a master, appended (the DLCs first, in the
game's order); it is read from the game's Data folder or the plugin folders.
An entry whose plugin is not installed (or names a master that is not) is
dropped with a warning, so the layer below it applies: a mod is never required.

See: docs/fork/fo4_gui.md#replacement-data
"""

import json
import struct
from dataclasses import dataclass
from pathlib import Path

from core.mod_sources import find_file
from fo4_import.base.install import FALLOUT4_DIR
from tes5_import.base.tes5_reader import first_sub, subrecords, walk

BASE = 'Fallout4.esm'
#: Fallout 4's official add-ons in the game's load order; as masters they come before any mod's plugin.
DLC = ('DLCRobot.esm', 'DLCworkshop01.esm', 'DLCCoast.esm', 'DLCworkshop02.esm', 'DLCworkshop03.esm',
       'DLCNukaWorld.esm')
MODES = ('item', 'stats', 'fnv')
DATA = Path(__file__).resolve().parents[1] / 'data'
DEFAULTS = DATA / 'replacements.json'
PROFILES = DATA / 'profiles'
ITEM_CATEGORIES = ('weapon', 'armor', 'consumable', 'ammo', 'misc')
CATEGORIES = ITEM_CATEGORIES + ('creature',)
#: Record types a replacement may name: items, and for creatures an actor or a leveled actor list.
ITEM_TYPES = (b'WEAP', b'ARMO', b'ALCH', b'AMMO', b'MISC', b'BOOK', b'KEYM', b'NOTE')
CREATURE_TYPES = (b'NPC_', b'LVLN')
#: FNV BMDT biped slot names (xEdit wbDefinitionsFNV) -> bit; the armor rules' `covers`.
BIPED = {'Head': 0x1, 'Hair': 0x2, 'Upper Body': 0x4, 'Left Hand': 0x8, 'Right Hand': 0x10, 'Weapon': 0x20,
         'PipBoy': 0x40, 'Backpack': 0x80, 'Necklace': 0x100, 'Headband': 0x200, 'Hat': 0x400,
         'Eye Glasses': 0x800, 'Nose Ring': 0x1000, 'Earrings': 0x2000, 'Mask': 0x4000, 'Choker': 0x8000,
         'Mouth Object': 0x10000, 'Body AddOn 1': 0x20000, 'Body AddOn 2': 0x40000, 'Body AddOn 3': 0x80000}
#: Melee rule keys -> FNV WEAP DNAM animation type.
MELEE_ANIMS = {'hand_to_hand': 0, 'one_hand': 1, 'two_hand': 2}
BODY_KINDS = ('human_male', 'human_female', 'ghoul_male', 'ghoul_female')
#: A FO4 plugin's file header is 24 bytes; its masters are MAST subrecords.
HEADER = 24


# ---------------------------------------------------------------------------
#  The table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Replacement:
    """One entry: the target's plugin and EditorID, its mode, gun parts, category and layer (origin)."""
    plugin: str
    edid: str
    mode: str
    mods: tuple = ()
    category: str = ''
    origin: str = 'default'

    @property
    def base(self) -> bool:
        """Whether the target is Fallout4.esm's."""
        return self.plugin.lower() == BASE.lower()

    @property
    def use(self) -> str:
        """The target as the table writes it: 'Plugin|EditorID'."""
        return f'{self.plugin}|{self.edid}'


@dataclass(frozen=True)
class Rules:
    """What forms the table leaves out get: {skeleton folder: entry}, {BODY_KINDS: entry},
    ((biped bits, entry), ...) first match wins, {FNV animation type: entry}."""
    creature: dict
    body: dict
    armor: tuple
    melee: dict

    def entries(self) -> list:
        """Every rule's entry."""
        return [*self.creature.values(), *self.body.values(), *(e for _, e in self.armor), *self.melee.values()]


class Table(dict):
    """{source EditorID: Replacement} of the item categories, plus `creatures` (by CREA EditorID), `rules` (Rules)
    and the load's `warnings`."""

    def __init__(self, items: dict, creatures: dict, rules: Rules, warnings: list = ()):
        """The table of `items`, `creatures`, `rules` and load `warnings`."""
        super().__init__(items)
        self.creatures, self.rules, self.warnings = dict(creatures), rules, list(warnings)

    @classmethod
    def of(cls, items: dict) -> 'Table':
        """A table of exactly `items`, with the default creatures and rules (tests)."""
        defaults = load()
        return cls(items, defaults.creatures, defaults.rules)

    def entries(self) -> list:
        """Every entry: items, creatures and rules."""
        return [*self.values(), *self.creatures.values(), *self.rules.entries()]


# ---------------------------------------------------------------------------
#  Loading
# ---------------------------------------------------------------------------

def load(user: 'Path | None' = None, profile: 'str | Path | None' = None, dirs: tuple = ()) -> Table:
    """The defaults, then `profile`'s and `user`'s entries laid over them; plugins looked for in `dirs`."""
    present, warnings = presence(dirs), []
    items, creatures = {}, {}
    rules = {'creature': {}, 'body': {}, 'armor': (), 'melee': {}}
    for data, origin in layers(user, profile):
        warnings += _missing_requirements(data, present)
        kept = _Layer(origin, present, warnings)
        for category in CATEGORIES:
            target = creatures if category == 'creature' else items
            target.update(kept.entries(data.get(category, {}), category))
        _lay_rules(rules, data.get('_rules', {}), kept)
    missing = [kind for kind in BODY_KINDS if kind not in rules['body']]
    if missing:
        raise ValueError(f'replacement rules give no body for {missing}')
    return Table(items, creatures, Rules(**rules), warnings)


def layers(user: 'Path | None' = None, profile: 'str | Path | None' = None) -> list:
    """[(layer JSON, origin)] lowest first: the defaults, `profile`'s, `user`'s."""
    out = [(_read(DEFAULTS), 'default')]
    out += [(_read(profile_path(profile)), 'profile')] if profile else []
    return out + ([(_read(Path(user)), 'user')] if user else [])


def profile_path(profile: 'str | Path') -> Path:
    """The file of `profile`: a path to a JSON file, else a name in PROFILES."""
    path = Path(profile)
    if path.suffix.lower() == '.json':
        return path
    named = PROFILES / f'{profile}.json'
    if not named.is_file():
        known = sorted(p.stem for p in PROFILES.glob('*.json')) if PROFILES.is_dir() else []
        raise FileNotFoundError(f'no replacement profile {profile!r}; known: {known}')
    return named


def parse(key: str, spec: dict, category: str, origin: str = 'default') -> Replacement:
    """Entry `key`'s Replacement from its `spec`; refuses unknown modes and copies of another plugin's record."""
    plugin, _, edid = spec['use'].partition('|')
    made = Replacement(plugin, edid, spec.get('as', 'item'), tuple(spec.get('mods', ())), category, origin)
    if made.mode not in MODES or not edid or (not made.base and made.mode != 'item'):
        raise ValueError(f'replacement {key}: {spec} (another plugin\'s record can only be an item)')
    if category == 'body' and not made.base:
        raise ValueError(f'replacement body {key}: {spec} (a body must be a Fallout4.esm NPC)')
    return made


class _Layer:
    """Parses one layer's entries, dropping (with a warning) those whose plugin is not installed."""

    def __init__(self, origin: str, present, warnings: list):
        """Layer `origin`'s entries; `present(plugin)`: is it installed."""
        self.origin, self.present, self.warnings = origin, present, warnings

    def entry(self, key: str, spec: dict, category: str) -> 'Replacement | None':
        """parse() of `spec`, or None (warned) when its plugin is not installed."""
        made = parse(key, spec, category, self.origin)
        if made.base or self.present(made.plugin):
            return made
        self.warnings.append(f'{self.origin} {category} {key}: {made.plugin} is not installed; the layer below '
                             'applies')
        return None

    def entries(self, specs: dict, category: str) -> dict:
        """{key: Replacement} of `specs`, the uninstalled left out."""
        made = {key: self.entry(key, spec, category) for key, spec in specs.items()}
        return {key: entry for key, entry in made.items() if entry}


def _lay_rules(rules: dict, layer: dict, kept: _Layer) -> None:
    """Lay one layer's `_rules` over `rules`: creature, body and melee entry by entry, armor as a whole list."""
    rules['creature'].update({k.lower(): v for k, v in kept.entries(layer.get('creature', {}), 'creature').items()})
    for kind in layer.get('body', {}):
        if kind not in BODY_KINDS:
            raise ValueError(f'replacement body {kind!r} is not one of {BODY_KINDS}')
    rules['body'].update(kept.entries(layer.get('body', {}), 'body'))
    for key in layer.get('melee', {}):
        if key not in MELEE_ANIMS:
            raise ValueError(f'replacement melee rule {key!r} is not one of {tuple(MELEE_ANIMS)}')
    rules['melee'].update({MELEE_ANIMS[k]: v for k, v in kept.entries(layer.get('melee', {}), 'weapon').items()})
    if 'armor' in layer:
        armor = [(_bits(rule['covers']), kept.entry(f'covers {rule["covers"]}', rule, 'armor'))
                 for rule in layer['armor']]
        rules['armor'] = tuple((bits, entry) for bits, entry in armor if entry)


def _bits(slots: list) -> int:
    """The BMDT bits of biped slot names (BIPED)."""
    unknown = [s for s in slots if s not in BIPED]
    if unknown:
        raise ValueError(f'unknown biped slots {unknown}; known: {list(BIPED)}')
    return sum(BIPED[s] for s in slots)


def _missing_requirements(data: dict, present) -> list:
    """Warnings for uninstalled plugins a profile's `_profile.requires` names."""
    header = data.get('_profile', {})
    return [f"profile {header.get('name', '?')}: {req['plugin']} is not installed (Nexus {req.get('nexus_id', '?')})"
            for req in header.get('requires', ()) if not present(req['plugin'])]


def presence(dirs: tuple):
    """present(plugin): whether a plugin and every master it names are in the game's Data folder or `dirs`, each
    looked up once (a master cycle counts as missing)."""
    known = {}

    def present(plugin: str) -> bool:
        """Whether `plugin` is installed and loadable."""
        key = plugin.lower()
        if key not in known:
            known[key] = False
            found = find_file(plugin, [FALLOUT4_DIR / 'Data', *dirs])
            known[key] = found is not None and all(present(m) for m in file_masters(found))
        return known[key]
    return present


def file_masters(path: Path) -> list:
    """A plugin file's master names, read from its header record only."""
    with open(path, 'rb') as f:
        head = f.read(HEADER)
        return plugin_masters(head + f.read(struct.unpack_from('<I', head, 4)[0]))


def _read(path: Path) -> dict:
    """A table layer's JSON."""
    return json.loads(Path(path).read_text(encoding='utf-8'))


# ---------------------------------------------------------------------------
#  Masters and targets
# ---------------------------------------------------------------------------

def extra_masters(table: Table) -> list:
    """Masters to append: the table's other plugins, DLCs first in game order."""
    named = {r.plugin.lower(): r.plugin for r in table.entries() if not r.base}
    dlc = [d for d in DLC if d.lower() in named]
    return dlc + sorted((p for k, p in named.items() if k not in {d.lower() for d in dlc}), key=str.lower)


def plugin_masters(data: bytes) -> list:
    """A plugin's master file names, from its file header."""
    size = struct.unpack_from('<I', data, 4)[0]
    return [body.rstrip(b'\0').decode('cp1252') for sig, body in subrecords(data[HEADER:HEADER + size])
            if sig == b'MAST']


def _find(plugin: str, dirs: list) -> Path:
    """`plugin`'s file (any case) in the game's Data folder or one of `dirs`."""
    found = find_file(plugin, [FALLOUT4_DIR / 'Data', *dirs])
    if not found:
        raise FileNotFoundError(f'{plugin} not in the Data folder or {dirs}')
    return found


def _ours(fid: int, theirs: list, plugin: str, masters: list) -> int:
    """A FormID of `plugin` (masters `theirs`) in our numbering, `masters` ours."""
    index = fid >> 24
    owner = plugin if index >= len(theirs) else theirs[index]
    lower = [m.lower() for m in masters]
    if owner.lower() not in lower:
        raise ValueError(f'{plugin} record {fid:08X} belongs to {owner}, not a master of ours')
    return lower.index(owner.lower()) << 24 | fid & 0xFFFFFF


def items(table: dict, fo4: bytes, masters: list, dirs: tuple = ()) -> dict:
    """targets() of the table's item entries among ITEM_TYPES."""
    return targets(table, fo4, masters, dirs, ITEM_TYPES)


def targets(entries: dict, fo4: bytes, masters: list, dirs: tuple, types: tuple) -> dict:
    """{key: FormID in our numbering} of the `item` entries in `entries` {key: Replacement}, among `types`."""
    out = {}
    for plugin in {r.plugin for r in entries.values() if r.mode == 'item'}:
        wanted = {}
        for key, r in entries.items():
            if r.mode == 'item' and r.plugin == plugin:
                wanted.setdefault(r.edid.lower(), []).append(key)
        base = plugin.lower() == BASE.lower()
        data = fo4 if base else _find(plugin, dirs).read_bytes()
        theirs = [] if base else plugin_masters(data)
        for rec, _ in walk(data, *types):
            for key in wanted.get((first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252').lower(), ()):
                out[key] = rec.form_id if base else _ours(rec.form_id, theirs, plugin, masters)
    return out
