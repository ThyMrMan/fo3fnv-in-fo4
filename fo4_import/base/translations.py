"""Our menus' translation files: the UTF-8 sources in translation_files/ written as the files F4SE loads.

F4SE loads `Interface/Translations/<plugin>_<sLanguage>.txt` only for each plugin active in plugins.txt, so ours
are named after FalloutHelpers.esl, which every converted FO3/FNV plugin masters. Each source `<language>.txt`
holds `$KEY<tab>text` lines; the installed file is UTF-16 LE with a BOM and CRLF lines, as F4SE requires.
check() holds our movies' `"$KEY"` strings against the English file, which F4SE falls back to.

See: docs/fork/swf_framework.md#translations
"""

import re
from pathlib import Path

#: The UTF-8 sources, one `<language>.txt` per language.
SOURCES = Path(__file__).resolve().parent / 'translation_files'
#: The plugin the files are named after.
PLUGIN = 'FalloutHelpers'
#: F4SE's line buffer, in UTF-16 units: a longer line is cut.
LINE_LIMIT = 511
#: The English source, the table every other language falls back to.
ENGLISH = SOURCES / 'en.txt'
#: Where our movies' AS3 sources live (every as3/ folder under it).
MOVIES = Path(__file__).resolve().parents[1]
#: `"$..."` strings that are the game's font names (fontconfig.txt), not translation keys.
FONTS = frozenset({'$MAIN_Font', '$MAIN_Font_Bold'})
#: A `"$KEY"` string literal in AS3.
KEY_LITERAL = re.compile(r'"(\$[A-Za-z_][A-Za-z0-9_]*)"')


def entries(source: Path) -> dict:
    """{key: text} of the source file `source`; ValueError on a line that is not `$KEY<tab>text`, or too long."""
    out = {}
    for number, line in enumerate(Path(source).read_text(encoding='utf-8').splitlines(), 1):
        key, tab, text = line.partition('\t')
        if not (key.startswith('$') and len(key) > 1 and tab and text) or '\t' in text:
            raise ValueError(f'{source}:{number}: not a $KEY<tab>text line')
        if len(line.encode('utf-16-le')) // 2 > LINE_LIMIT:
            raise ValueError(f'{source}:{number}: longer than F4SE reads ({LINE_LIMIT} characters)')
        out[key] = text
    return out


def encoded(table: dict) -> bytes:
    """`table` as an F4SE file: BOM, UTF-16 LE, a CRLF line per key."""
    return ('﻿' + ''.join(f'{key}\t{text}\r\n' for key, text in table.items())).encode('utf-16-le')


def install(data_dir: Path, sources: Path = SOURCES) -> int:
    """Write each source with keys as <data_dir>/Interface/Translations/<PLUGIN>_<language>.txt; how many were."""
    tables = {source.stem: entries(source) for source in sorted(Path(sources).glob('*.txt'))}
    tables = {language: table for language, table in tables.items() if table}
    folder = Path(data_dir) / 'Interface' / 'Translations'
    for language, table in tables.items():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f'{PLUGIN}_{language}.txt').write_bytes(encoded(table))
    return len(tables)


def used_keys(movies: Path = MOVIES) -> dict:
    """{key: [files]} of the `"$KEY"` strings in the .as files of every as3/ folder under `movies`, fonts and
    `//` comment lines left out."""
    out = {}
    for path in sorted(Path(movies).glob('**/as3/**/*.as')):
        code = [line for line in path.read_text(encoding='utf-8').splitlines() if not line.lstrip().startswith('//')]
        for key in KEY_LITERAL.findall('\n'.join(code)):
            if key not in FONTS:
                out.setdefault(key, []).append(path.name)
    return out


def check(movies: Path = MOVIES, sources: Path = SOURCES) -> dict:
    """{fault: sorted rows}: keys our movies use that en.txt lacks (shown raw in game), en.txt keys no movie uses,
    and other languages' keys en.txt lacks."""
    english = entries(Path(sources) / 'en.txt')
    used = used_keys(movies)
    others = {f'{source.name}: {key}' for source in Path(sources).glob('*.txt') if source.stem != 'en'
              for key in entries(source) if key not in english}
    return {'key missing from en.txt': sorted(f'{key} ({", ".join(sorted(set(files)))})'
                                              for key, files in used.items() if key not in english),
            'en.txt key no movie uses': sorted(set(english) - set(used)),
            'key only in another language': sorted(others)}
