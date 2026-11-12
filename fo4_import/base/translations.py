"""Our menus' translation files: the UTF-8 sources in translation_files/ written as the files F4SE loads.

F4SE loads `Interface/Translations/<plugin>_<sLanguage>.txt` only for each plugin active in plugins.txt, so ours
are named after FalloutHelpers.esl, which every converted FO3/FNV plugin masters. Each source `<language>.txt`
holds `$KEY<tab>text` lines; the installed file is UTF-16 LE with a BOM and CRLF lines, as F4SE requires. Every
game language gets a file, its missing keys in English, since F4SE has no fallback of its own. A key's text may
hold `{0}`, `{1}` slots: the code sends `$KEY<tab>slot0<tab>slot1`, and f3ui's Text.show fills them.
check() holds the `"$KEY"` strings in our movies, F3NV.dll and MCM pages against the English file.

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
#: Fallout 4's sLanguage values (its own Interface/translate_<language>.txt files).
LANGUAGES = ('cn', 'de', 'en', 'es', 'esmx', 'fr', 'it', 'ja', 'pl', 'ptbr', 'ru')
#: The repo root, under which our code's sources are found.
REPO = Path(__file__).resolve().parents[2]
#: Our code that shows keys: (folder, glob) — the movies' AS3, F3NV.dll's C++ and our MCM pages' templates.
CODE = ((REPO / 'fo4_import', '**/as3/**/*.as'), (REPO / 'tes_runtime' / 'fo4_condition', '*.cpp'),
        (REPO / 'fo4_import', '**/mcm/*.json'))
#: `"$..."` strings that are the game's font names (fontconfig.txt), not translation keys.
FONTS = frozenset({'$MAIN_Font', '$MAIN_Font_Bold', '$Controller_Buttons'})
#: A `"$KEY"` string literal, or a template's `"$KEY\t`.
KEY_LITERAL = re.compile(r'"(\$[A-Za-z_][A-Za-z0-9_]*)(?=["\\])')


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
    """Write <data_dir>/Interface/Translations/<PLUGIN>_<language>.txt for every game language: English, with the
    language's own source over it where one exists; how many were written (none while English has no keys)."""
    english = entries(Path(sources) / 'en.txt')
    if not english:
        return 0
    folder = Path(data_dir) / 'Interface' / 'Translations'
    folder.mkdir(parents=True, exist_ok=True)
    for language in LANGUAGES:
        own = Path(sources) / f'{language}.txt'
        table = {**english, **(entries(own) if own.is_file() else {})}
        (folder / f'{PLUGIN}_{language}.txt').write_bytes(encoded(table))
    return len(LANGUAGES)


def used_keys(code=CODE) -> dict:
    """{key: [files]} of the `"$KEY"` strings in `code` ((folder, glob) pairs), fonts and `//` comment lines left
    out."""
    out = {}
    for folder, pattern in code:
        for path in sorted(Path(folder).glob(pattern)):
            lines = path.read_text(encoding='utf-8').splitlines()
            text = '\n'.join(line for line in lines if not line.lstrip().startswith('//'))
            for key in KEY_LITERAL.findall(text):
                if key not in FONTS:
                    out.setdefault(key, []).append(path.name)
    return out


def check(code=CODE, sources: Path = SOURCES) -> dict:
    """{fault: sorted rows}: keys our code uses that en.txt lacks (shown raw in game), en.txt keys nothing uses,
    and other languages' keys en.txt lacks."""
    english = entries(Path(sources) / 'en.txt')
    used = used_keys(code)
    others = {f'{source.name}: {key}' for source in Path(sources).glob('*.txt') if source.stem != 'en'
              for key in entries(source) if key not in english}
    return {'key missing from en.txt': sorted(f'{key} ({", ".join(sorted(set(files)))})'
                                              for key, files in used.items() if key not in english),
            'en.txt key no movie uses': sorted(set(english) - set(used)),
            'key only in another language': sorted(others)}
