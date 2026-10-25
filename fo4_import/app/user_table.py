"""The user's replacement file: read it, set or clear one entry, write it back. Its shape is the defaults' (entries
under their category), so it lays over the defaults and profile entry by entry (fo4_import.spike.replacements).

See: docs/fork/fo4_gui.md#replacement-data
"""

import json
from pathlib import Path

from fo4_import.spike.replacements import CATEGORIES, parse

ABOUT = ('Your replacements, laid over the converter defaults and the profile. Written by the app; keyed by the '
         'source EditorID under each category. See docs/fork/fo4_gui.md#replacement-data.')


def read(path: Path) -> dict:
    """The user file's entries {category: {key: spec}}; {} when there is none yet."""
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def set_entry(data: dict, category: str, edid: str, use: str, mode: str) -> None:
    """Set `edid`'s entry in `category` to `use` ('Plugin|EditorID') as `mode`, refusing what the loader would."""
    if category not in CATEGORIES:
        raise ValueError(f'{category!r} is not one of {CATEGORIES}')
    spec = {'use': use, 'as': mode}
    parse(edid, spec, category)
    data.setdefault(category, {})[edid] = spec


def clear_entry(data: dict, category: str, edid: str) -> bool:
    """Drop `edid`'s entry from `category`; whether there was one."""
    return data.get(category, {}).pop(edid, None) is not None


def write(path: Path, data: dict) -> Path:
    """Write the user file (empty categories left out, sorted keys); its path."""
    path = Path(path)
    body = {'_about': ABOUT, **{c: dict(sorted(data[c].items())) for c in CATEGORIES if data.get(c)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2) + '\n', encoding='utf-8')
    return path
