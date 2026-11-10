"""The FO4 hairs an FNV hair may become: the one of its name, else its style's group, else every hair.

FNV names its hairs (HAIR FULL) and FO4 names its hair head parts (HDPT
FULL, a Fallout4.esm string); many FO4 names are Fallout 3's, which FNV
keeps. A hair whose name an FO4 hair of the NPC's sex shares becomes that
hair. Otherwise the style table (data/hair_styles.json) lists the FO4 hairs
drawn in its style. The coverage matcher (hair.best_part) picks among what
is left: every hair when neither rule applies.

See: docs/fork/fo4_spikes.md#hair-styles
"""

import json
import re
from functools import cache
from pathlib import Path

from fo4_import.base import strings
from fo4_import.face import hair

TABLE = Path(__file__).resolve().parents[1] / 'data' / 'hair_styles.json'


def name_key(text: str) -> str:
    """A hair name as compared: lower case, letters and digits only."""
    return re.sub(r'[^a-z0-9]', '', text.lower())


@cache
def table() -> tuple:
    """({group: FO4 EditorIDs}, {FNV EditorID: group}), read once."""
    data = json.loads(TABLE.read_text(encoding='utf-8'))
    return {g: frozenset(ids) for g, ids in data['groups'].items()}, data['styles']


def fo4_name(assets: hair.Fo4Assets, form_id: int) -> str:
    """An FO4 head part's name, '' when it has none."""
    full = assets.parts[form_id].get(b'FULL', [b''])[0]
    return strings.fallout4().get(int.from_bytes(full[:4], 'little'), b'').decode('cp1252') if len(full) == 4 else ''


def candidates(assets: hair.Fo4Assets, record: dict, female: bool) -> tuple:
    """(the FO4 hairs of one sex FNV HAIR `record` may become, the rule: 'name', 'style' or 'coverage')."""
    every = assets.candidates(hair.HAIR, female)
    wanted = name_key(record.get('FULL', ''))
    named = [f for f in every if wanted and name_key(fo4_name(assets, f)) == wanted]
    if named:
        return named, 'name'
    groups, styles = table()
    group = groups.get(styles.get(record.get('EditorID', ''), ''), frozenset())
    styled = [f for f in every if assets.edid(f) in group]
    return (styled, 'style') if styled else (every, 'coverage')
