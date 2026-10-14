"""The karma Pip-Boy page (Pip-Boy Tabs, on STAT): the player's alignment and karmic title, as FNV shows them.

Two rows, actor values on the player that TES4_KarmaPage sets whenever the
Pip-Boy opens: Alignment (very evil to very good by FNV's fAlign
thresholds) and Title. FNV's titles are game settings sKarmicTitle<kind><nn>
for kinds Evil, Neutral and Good and levels 1-30: FalloutNV.esm's where it
sets one, else the engine default (DEFAULT_TITLES, read from New Vegas's
GECK with `tools/disasm/oblivion_engine_extract.py --settings sKarmicTitle`;
levels 20-30 share level 20's).

See: docs/fork/fo4_pipeline.md#karma-page
"""

import json
from pathlib import Path

from fo4_import.base.vmad import quest_fragments
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.reputation import KARMA_KEY, PAGE_SITE, STAT_PAGE, actor_value, page_list, write_tab
from tes5_import.character_data_falloutnv import ENGINE_SETTINGS

SCRIPT = 'TES4_KarmaPage'
#: The page's alignment labels, very evil to very good (the Alignment row's values 0-4).
ALIGNMENTS = ('Very Evil', 'Evil', 'Neutral', 'Good', 'Very Good')
#: Title kinds in the Title row's order (5 + kind * LEVELS + level - 1), and the levels with a title.
KINDS, LEVELS = ('Evil', 'Neutral', 'Good'), 30
#: The engine's default titles per kind, levels 1-20 (21-30 take 20's).
DEFAULT_TITLES = {
    'Evil': ('Vault Delinquent', 'Vault Outlaw', 'Opportunist', 'Plunderer', 'Fat Cat', 'Marauder',
             'Pirate of the Wastes', 'Reaver', 'Urban Invader', "Ne'er-do-well", 'Capitol Crimelord', 'Defiler',
             'Vault Boogeyman', 'Harbinger of War', 'Urban Superstition', 'Villain of the Wastes', 'Fiend',
             'Wasteland Destroyer', 'Evil Incarnate', 'Scourge of Humanity'),
    'Neutral': ('Vault Dweller', 'Vault Renegade', 'Seeker', 'Wanderer', 'Citizen', 'Adventurer',
                'Vagabond of the Wastes', 'Mercenary', 'Urban Ranger', 'Observer', 'Capitol Councilor', 'Keeper',
                'Vault Descendant', 'Pinnacle of Survival', 'Urban Myth', 'Strider of the Wastes', 'Beholder',
                'Wasteland Watcher', 'Super-Human', 'Paradigm of Humanity'),
    'Good': ('Vault Guardian', 'Vault Martyr', 'Sentinel', 'Defender', 'Dignitary', 'Peacekeeper',
             'Ranger of the Wastes', 'Protector', 'Urban Avenger', 'Exemplar', 'Capitol Crusader', 'Paladin',
             'Vault Legend', 'Ambassador of Peace', 'Urban Legend', 'Hero of the Wastes', 'Paragon',
             'Wasteland Savior', 'Saint', 'Last, Best Hope of Humanity')}
#: The alignment thresholds (FNV settings) the script reads, by its property.
THRESHOLDS = {'VeryEvilMax': 'fAlignVeryEvilMaxKarma', 'EvilMax': 'fAlignEvilMaxKarma',
              'GoodMin': 'fAlignGoodMinKarma', 'VeryGoodMin': 'fAlignVeryGoodMinKarma'}


def titles(export_dir: Path) -> list:
    """The page's strings: ALIGNMENTS, then each kind's title for levels 1-30 (FalloutNV.esm's, else default)."""
    gmst = {r.get('EditorID'): r.get('DATA.Value') for r in export_records(export_dir, 'GMST')}
    out = list(ALIGNMENTS)
    for kind in KINDS:
        defaults = DEFAULT_TITLES[kind]
        out += [gmst.get(f'sKarmicTitle{kind}{level:02d}') or defaults[min(level, len(defaults)) - 1]
                for level in range(1, LEVELS + 1)]
    return out


def thresholds(export_dir: Path) -> dict:
    """{script property: ('float', value)} of THRESHOLDS: FalloutNV.esm's setting, else the engine's."""
    with open(ENGINE_SETTINGS['falloutnv'], encoding='utf-8') as handle:
        engine = json.load(handle)['settings']
    gmst = {r.get('EditorID'): r.get('DATA.Value') for r in export_records(export_dir, 'GMST')}
    return {prop: ('float', float(gmst.get(name) or engine[name])) for prop, name in THRESHOLDS.items()}


def write_karma_page(builder, export_dir: Path, data_dir: Path, plugin: str, form_map: dict) -> Path:
    """Write the page's actor values, row list, start-game quest running TES4_KarmaPage (karma from `form_map`'s
    KARMA_KEY) and Data\\PBT tab; the tab's path."""
    alignment = actor_value(builder, 'TES4KarmaAlignment', 'Karma')
    title = actor_value(builder, 'TES4KarmaTitle', 'Title')
    rows = page_list(builder, 'TES4KarmaPageRows', [alignment, title])
    props = {'TES4Karma': form_map[KARMA_KEY], 'AlignmentValue': alignment, 'TitleValue': title}
    vmad = quest_fragments('', [], scripts=[(SCRIPT, props, thresholds(export_dir))])
    quest = builder.writer.derive_formid(PAGE_SITE, 'TES4KarmaPageQuest')
    builder.writer.add_record('QUST', R.pack_fnv_quest(quest, 'TES4KarmaPageQuest', '', 0, vmad, [], [], [], True))
    return write_tab(data_dir, plugin, ('Karma', STAT_PAGE), rows, '|'.join(titles(export_dir)))
